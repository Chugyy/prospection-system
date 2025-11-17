#!/usr/bin/env python3
"""
Conversation orchestrator - 2-LLM architecture.
Coordinates strategic analysis (LLM2) and conversational generation (LLM1).
"""
from typing import Dict, List
from config.logger import logger
from app.core.services.llm.strategic import StrategicLLM
from app.core.services.llm.conversational import ConversationalLLM


class ConversationOrchestrator:
    """Orchestrates conversation generation via 2-LLM pipeline."""

    def __init__(self):
        self.strategic = StrategicLLM()
        self.conversational = ConversationalLLM()

    async def generate_response(
        self,
        prospect_message: str,
        conversation_history: List[Dict[str, str]],
        prospect_profile: Dict[str, str],
        return_strategy: bool = False
    ) -> str | tuple[str, Dict]:
        """
        Generate conversational response via 2-LLM pipeline.

        Pipeline:
        1. LLM2 (Strategic) → Analyze conversation + decide strategy
        2. LLM1 (Conversational) → Generate message based on strategy

        Args:
            prospect_message: Latest message from prospect
            conversation_history: Full conversation history (role/content pairs)
            prospect_profile: Prospect data (first_name, job_title, company, etc.)
            return_strategy: If True, return (response, strategy_dict)

        Returns:
            str: Generated conversational message
            or tuple[str, Dict]: (response, strategy) if return_strategy=True
        """
        try:
            logger.info("🎯 Orchestrator: Starting 2-LLM pipeline")

            # Step 1: Strategic analysis (LLM2)
            logger.debug("Step 1/2: LLM2 (Strategic) analyzing conversation...")
            strategy = await self.strategic.analyze(
                prospect_message=prospect_message,
                history=conversation_history,
                profile=prospect_profile
            )

            logger.debug(f"LLM2 strategy: {strategy.get('objective', 'N/A')}")

            # Step 2: Conversational generation (LLM1)
            logger.debug("Step 2/2: LLM1 (Conversational) generating message...")
            response = await self.conversational.generate(
                strategy=strategy,
                history=conversation_history,
                profile=prospect_profile
            )

            logger.info(f"✅ Orchestrator: Generated response ({len(response)} chars)")

            if return_strategy:
                return response, strategy
            return response

        except Exception as e:
            logger.error(f"❌ Orchestrator pipeline failed: {e}")
            raise


# Global singleton instance
orchestrator = ConversationOrchestrator()
