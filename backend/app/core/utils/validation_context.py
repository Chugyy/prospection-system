#!/usr/bin/env python3
# app/core/utils/validation_context.py

from typing import Dict, List, Optional
from config.logger import logger
from app.database import crud


async def build_validation_context(log: dict) -> dict:
    """
    Construit le contexte enrichi pour faciliter la décision de validation.

    Retourne un JSON clair sans répétition d'info.
    """

    prospect_id = log.get('prospect_id')
    payload = log.get('payload', {})

    if not prospect_id:
        return {"error": "No prospect_id in log"}

    try:
        # 1. Prospect info
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            return {"error": f"Prospect {prospect_id} not found"}

        # 2. Historique messages (limité aux 10 derniers)
        messages = await crud.list_messages(prospect_id, limit=10)

        # 3. Actions passées (succès uniquement)
        past_actions = await crud.list_logs(
            prospect_id=prospect_id,
            status='success'
        )

        # Filtrer uniquement actions d'envoi
        sent_actions = [
            a for a in past_actions
            if a['action'] in ['send_first_contact', 'send_followup_a_1',
                              'send_followup_a_2', 'send_followup_a_3',
                              'send_followup_b', 'send_followup_c']
        ]

        # 4. Rejets précédents
        past_rejections = await crud.list_logs(
            prospect_id=prospect_id,
            validation_status='rejected'
        )

        # Build context JSON (clair et sans répétition)
        context = {
            "prospect": {
                "id": prospect_id,
                "name": f"{prospect.get('first_name', '')} {prospect.get('last_name', '')}".strip(),
                "company": prospect.get('company'),
                "title": prospect.get('job_title'),
                "status": prospect.get('status'),
                "rejection_count": prospect.get('rejection_count', 0),
                "linkedin_url": prospect.get('linkedin_url')
            },
            "conversation": {
                "total_messages": len(messages),
                "last_message": {
                    "from": messages[-1]['sent_by'] if messages else None,
                    "date": messages[-1]['sent_at'].isoformat() if messages else None,
                    "preview": messages[-1]['content'][:100] + "..." if messages and len(messages[-1]['content']) > 100 else messages[-1]['content'] if messages else None
                } if messages else None,
                "history": [
                    {
                        "from": m['sent_by'],
                        "content": m['content'],
                        "date": m['sent_at'].isoformat()
                    }
                    for m in messages
                ]
            },
            "proposed_action": {
                "type": log['action'],
                "content": payload.get('content') or payload.get('reply'),
                "scheduled_for": payload.get('scheduled_at'),
                "reason": payload.get('reason'),
                "llm_analysis": log.get('details')
            },
            "history": {
                "messages_sent": len(sent_actions),
                "last_sent": sent_actions[-1]['created_at'].isoformat() if sent_actions else None,
                "rejections": {
                    "count": len(past_rejections),
                    "reasons": [
                        {
                            "reason": r.get('rejection_reason'),
                            "category": r.get('rejection_category'),
                            "date": r.get('validated_at').isoformat() if r.get('validated_at') else None
                        }
                        for r in past_rejections[-3:]  # 3 derniers seulement
                    ] if past_rejections else []
                }
            },
            "metadata": {
                "log_id": log['id'],
                "created_at": log['created_at'].isoformat(),
                "source": log['source'],
                "priority": log.get('priority', 3)
            }
        }

        return context

    except Exception as e:
        logger.error(f"Error building validation context: {e}")
        return {"error": str(e)}


def format_conversation_for_display(messages: List[dict]) -> str:
    """Formate l'historique de conversation pour affichage."""
    if not messages:
        return "(Aucun message)"

    formatted = []
    for msg in messages:
        sender = "Vous" if msg['sent_by'] == 'account' else msg['sent_by'].capitalize()
        date = msg['sent_at'].strftime("%Y-%m-%d %H:%M")
        content = msg['content'][:150] + "..." if len(msg['content']) > 150 else msg['content']
        formatted.append(f"[{date}] {sender}: {content}")

    return "\n".join(formatted)
