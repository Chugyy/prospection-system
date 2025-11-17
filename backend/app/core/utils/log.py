#!/usr/bin/env python3
# app/core/utils/log.py

import json
from config.logger import logger
from app.database import crud


async def execute_approved_log(log_id: int) -> dict:
    """
    Exécute une action approuvée depuis un log.

    Args:
        log_id: ID du log à exécuter

    Returns:
        dict: {"executed": bool, "action": str, "result": dict}
    """
    try:
        # Récupérer le log
        log = await crud.get_log(log_id)
        if not log:
            raise ValueError(f"Log {log_id} not found")

        # Vérifier statut de validation
        if log.get('validation_status') != 'approved':
            raise ValueError(f"Log {log_id} is not approved (status={log.get('validation_status')})")

        # Vérifier si déjà exécuté
        if log.get('executed_at'):
            logger.warning(f"Log {log_id} already executed at {log.get('executed_at')}")
            return {
                "executed": False,
                "action": log.get('action'),
                "result": None,
                "reason": "already_executed"
            }

        action = log.get('action')
        payload = log.get('payload')
        # payload is already parsed by get_log
        if isinstance(payload, str):
            payload = json.loads(payload)
        if not payload:
            payload = {}

        prospect_id = log.get('prospect_id')
        account_id = log.get('account_id')

        logger.info(f"Executing approved log {log_id}: action={action}")

        result = None

        # Dispatcher selon l'action
        if action == 'followup_proposed':
            # Créer le followup proposé par le LLM
            followup_type = payload.get('followup_type', 'long_term')
            scheduled_at = payload.get('scheduled_at')
            reason = payload.get('reason')

            # Générer contenu du followup
            prospect = await crud.get_prospect(prospect_id)
            first_name = prospect.get('first_name', '') if prospect else ''

            content = f"Bonjour {first_name},\n\nComme convenu, je reviens vers vous concernant {reason}.\n\nÊtes-vous disponible pour en discuter ?"

            followup_id = await crud.create_followup(
                prospect_id=prospect_id,
                account_id=account_id,
                followup_type=followup_type,
                scheduled_at=scheduled_at,
                content=content
            )

            result = {"followup_id": followup_id, "scheduled_at": scheduled_at}
            logger.info(f"Followup {followup_id} created from approved log {log_id}")

        elif action == 'message_proposed':
            # Envoyer le message proposé par le LLM
            from app.core.handler.message import send_message_via_unipile

            reply = payload.get('reply')

            send_result = await send_message_via_unipile(
                prospect_id=prospect_id,
                account_id=account_id,
                content=reply,
                message_type='llm_reply'
            )

            result = send_result
            logger.info(f"Message sent from approved log {log_id}: success={send_result['success']}")

        else:
            raise ValueError(f"Unknown action: {action}")

        # Marquer log comme exécuté
        await crud.mark_log_executed(log_id)

        logger.info(f"Log {log_id} executed successfully")

        return {
            "executed": True,
            "action": action,
            "result": result
        }

    except Exception as e:
        logger.error(f"Error executing approved log {log_id}: {e}")
        return {
            "executed": False,
            "action": None,
            "result": None,
            "error": str(e)
        }
