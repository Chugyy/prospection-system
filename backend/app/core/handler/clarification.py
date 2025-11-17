#!/usr/bin/env python3
# app/core/handler/clarification.py

import json
from config.logger import logger
from app.database import crud
from app.core.services.llm.llm import llm_service


async def analyze_with_llm_clarification(
    prospect_id: int,
    question: str,
    original_analysis: dict
) -> dict:
    """
    Re-appelle le LLM avec une question spécifique de l'humain.

    Args:
        prospect_id: ID du prospect
        question: Question spécifique de l'humain
        original_analysis: Analyse LLM originale

    Returns:
        dict: {
            "clarification": str,
            "additional_context": str,
            "revised_recommendation": str (optionnel)
        }
    """

    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"Prospect {prospect_id} not found")

        messages = await crud.list_messages(prospect_id)

        conversation_history = "\n".join([
            f"[{m['sent_by']}] {m['content']}" for m in messages
        ])

        llm_messages = [
            {
                "role": "system",
                "content": "Tu es un expert en prospection LinkedIn. Un humain a une question sur ton analyse précédente. Fournis une clarification détaillée."
            },
            {
                "role": "user",
                "content": f"""Prospect: {prospect.get('first_name')} {prospect.get('last_name')}
Entreprise: {prospect.get('company')}
Poste: {prospect.get('job_title')}

Conversation:
{conversation_history}

Ton analyse précédente:
{json.dumps(original_analysis, indent=2, ensure_ascii=False)}

Question de l'humain:
"{question}"

Fournis une clarification détaillée en JSON:
{{
    "clarification": "explication détaillée de ta recommandation",
    "additional_context": "contexte supplémentaire pertinent",
    "revised_recommendation": "recommendation révisée si la question révèle un élément important (optionnel)"
}}"""
            }
        ]

        response = await llm_service.generate_text(
            messages=llm_messages,
            response_format={"type": "json_object"},
            temperature=0.5
        )

        if not response:
            logger.warning(f"LLM returned no response for clarification")
            return {
                "clarification": "Erreur LLM",
                "additional_context": "Le LLM n'a pas pu répondre",
                "revised_recommendation": None
            }

        result = json.loads(response)
        logger.info(f"Clarification generated for prospect {prospect_id}")

        return result

    except Exception as e:
        logger.error(f"Error generating clarification: {e}")
        return {
            "clarification": f"Erreur: {str(e)}",
            "additional_context": None,
            "revised_recommendation": None,
            "error": str(e)
        }
