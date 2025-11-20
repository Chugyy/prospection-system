#!/usr/bin/env python3
"""
Centralized LLM service with automatic fallback.
Unified wrapper for Claude/OpenAI with error handling.
"""
import asyncio
import logging
from typing import Optional, Dict, Any, List

try:
    from anthropic import Anthropic, APIStatusError
except ImportError:
    Anthropic = None
    APIStatusError = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from config.config import settings
from config.logger import logger


class LLMService:
    """Centralized service for all LLM calls with automatic fallback"""

    def __init__(self):
        # Initialize clients only if libraries and API keys are available
        if Anthropic and hasattr(settings, 'ANTHROPIC_API_KEY') and settings.ANTHROPIC_API_KEY:
            self.anthropic_client = Anthropic(api_key=settings.ANTHROPIC_API_KEY)
        else:
            self.anthropic_client = None

        if OpenAI and hasattr(settings, 'OPENAI_API_KEY') and settings.OPENAI_API_KEY:
            self.openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
        else:
            self.openai_client = None

        # Model configuration
        self.claude_model = "claude-sonnet-4-5-20250929"
        self.openai_model = "gpt-5-2025-08-07"

        # Rate limiter: max 5 concurrent requests
        self._semaphore = asyncio.Semaphore(5)

    def generate(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict] = None,
        temperature: Optional[float] = None,
        model_preference: str = "claude"
    ) -> str:
        """
        Synchronous wrapper for generate_text (for backward compatibility).

        Args:
            messages: List of messages (role/content)
            response_format: {"type": "json_object"} for JSON output
            temperature: Temperature (0.0-1.0), defaults to 1.0 for compatibility
            model_preference: "claude" or "openai"

        Returns:
            str: Generated text

        Raises:
            ValueError: If generation fails completely
        """
        result = asyncio.run(self.generate_text(
            messages=messages,
            response_format=response_format,
            temperature=temperature if temperature is not None else 1.0,
            model_preference=model_preference
        ))

        if result is None:
            raise ValueError("LLM generation failed completely (both Claude and OpenAI failed)")

        return result

    async def generate_text(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict] = None,
        temperature: float = 0.0,
        model_preference: str = "claude"
    ) -> Optional[str]:
        """
        Generate text with automatic fallback and rate limiting.

        Args:
            messages: List of messages (role/content)
            response_format: {"type": "json_object"} for JSON output
            temperature: Temperature (0.0-1.0)
            model_preference: "claude" or "openai"

        Returns:
            str: Generated text or None if total failure
        """
        async with self._semaphore:
            try:
                # Try Claude first (unless OpenAI explicitly requested)
                if model_preference != "openai":
                    result = await self._try_claude(messages, response_format, temperature)
                    if result is not None:
                        return result

                    logger.info("Automatic fallback to OpenAI")

                # Fallback to OpenAI
                return await self._try_openai(messages, response_format, temperature)

            except Exception as e:
                logger.error(f"Critical error in LLMService.generate_text: {e}")
                return None

    async def _try_claude(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict],
        temperature: float
    ) -> Optional[str]:
        """Try Claude with retry on rate limits - immediate fallback on other errors"""
        if not self.anthropic_client:
            logger.warning("Anthropic client not available")
            return None

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"Claude retry attempt {attempt + 1}/{max_retries}")

                logger.debug(f"Attempting Claude... (attempt {attempt + 1})")

                # Extract system message (Claude API requires separate system parameter)
                system_message = None
                filtered_messages = []
                for msg in messages:
                    if msg["role"] == "system":
                        system_message = msg["content"]
                    else:
                        filtered_messages.append(msg)

                # If JSON output requested, use prefill technique
                if response_format and response_format.get("type") == "json_object":
                    # Add assistant prefill to force JSON output (no trailing whitespace)
                    messages_with_prefill = filtered_messages + [
                        {"role": "assistant", "content": "{"}
                    ]

                    params = {
                        "model": self.claude_model,
                        "max_tokens": 16000,
                        "temperature": temperature,
                        "messages": messages_with_prefill
                    }

                    if system_message:
                        params["system"] = system_message

                    response = self.anthropic_client.messages.create(**params)

                    # Prepend the prefill to the response
                    result = "{" + response.content[0].text
                else:
                    params = {
                        "model": self.claude_model,
                        "max_tokens": 16000,
                        "temperature": temperature,
                        "messages": filtered_messages
                    }

                    if system_message:
                        params["system"] = system_message

                    response = self.anthropic_client.messages.create(**params)
                    result = response.content[0].text

                logger.debug(f"Claude succeeded (attempt {attempt + 1})")
                return result

            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                status_code = getattr(e, 'status_code', None)

                # Retry on rate limits (429) or server errors (5xx)
                if status_code in [429, 500, 502, 503, 504]:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(f"Claude error {status_code} ({error_type}): {error_msg} - Retrying in {wait_time}s...")

                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"Claude failed after {max_retries} retries - Fallback to OpenAI")
                        return None
                else:
                    # Immediate fallback on other errors
                    if status_code:
                        logger.warning(f"Claude error {status_code} ({error_type}): {error_msg} - Immediate fallback to OpenAI")
                    else:
                        logger.warning(f"Claude error ({error_type}): {error_msg} - Immediate fallback to OpenAI")
                    return None

        return None

    async def _try_openai(
        self,
        messages: List[Dict[str, str]],
        response_format: Optional[Dict],
        temperature: float
    ) -> Optional[str]:
        """Try OpenAI with retry on rate limits"""
        if not self.openai_client:
            logger.error("OpenAI client not available")
            return None

        max_retries = 3
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    logger.info(f"OpenAI retry attempt {attempt + 1}/{max_retries}")

                logger.debug(f"Attempting OpenAI... (attempt {attempt + 1})")

                params = {
                    "model": self.openai_model,
                    "messages": messages
                }

                # Note: gpt-5-2025-08-07 only supports temperature=1.0 (default)
                # Skip temperature parameter to use model default

                if response_format:
                    params["response_format"] = response_format

                completion = self.openai_client.chat.completions.create(**params)

                logger.debug(f"OpenAI succeeded (attempt {attempt + 1})")
                return completion.choices[0].message.content

            except Exception as e:
                error_type = type(e).__name__
                error_msg = str(e)
                status_code = getattr(e, 'status_code', None)

                # Retry on rate limits or server errors
                if status_code in [429, 500, 502, 503, 504] or 'rate_limit' in str(e).lower():
                    wait_time = 2 ** attempt  # Exponential backoff
                    logger.warning(f"OpenAI error {status_code or 'rate_limit'} ({error_type}): {error_msg} - Retrying in {wait_time}s...")

                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                        continue
                    else:
                        logger.error(f"OpenAI failed after {max_retries} retries")
                        return None
                else:
                    logger.error(f"OpenAI error ({error_type}): {error_msg}")
                    return None

        return None


# Global reusable instance
llm_service = LLMService()
