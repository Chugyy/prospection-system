#!/usr/bin/env python3
# app/core/handler/sender.py

import json
from config.logger import logger
from app.database import crud
from app.core.handler.message import send_message_via_unipile


# ============================
# SEND ACTIONS
# ============================

async def execute_send_first_contact(prospect_id: int, account_id: int) -> dict:
    """Envoie immédiatement le premier message de contact."""
    from app.core.templates.composer import message_composer

    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"Prospect {prospect_id} not found")

        content = await message_composer.generate_welcome_message(prospect)

        result = await send_message_via_unipile(
            prospect_id=prospect_id,
            account_id=account_id,
            content=content,
            message_type='first_contact'
        )

        if not result['success']:
            raise ValueError(f"Failed to send first contact: {result['error']}")

        logger.info(f"First contact sent to prospect {prospect_id}")
        return result

    except Exception as e:
        logger.error(f"Error sending first contact: {e}")
        raise


async def execute_send_followup(action: dict, prospect_id: int, account_id: int) -> dict:
    """Envoie immédiatement un followup (A, B ou C)."""
    from app.core.templates.composer import message_composer

    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"Prospect {prospect_id} not found")

        action_type = action['action']

        if 'send_followup_a_1' in action_type:
            content = message_composer.generate_followup_message(prospect, step=1)
        elif 'send_followup_a_2' in action_type:
            content = message_composer.generate_followup_message(prospect, step=2)
        elif 'send_followup_a_3' in action_type:
            content = message_composer.generate_followup_message(prospect, step=3)
        elif 'send_followup_b' in action_type:
            content = message_composer.generate_followup_message(prospect, step=1)
        elif 'send_followup_c' in action_type:
            payload = action.get('payload', {})
            content = payload.get('content')
            if not content:
                content = await message_composer.generate_welcome_message(prospect)
        else:
            raise ValueError(f"Unknown followup type: {action_type}")

        result = await send_message_via_unipile(
            prospect_id=prospect_id,
            account_id=account_id,
            content=content,
            message_type='followup'
        )

        if not result['success']:
            raise ValueError(f"Failed to send followup: {result['error']}")

        logger.info(f"Followup {action_type} sent to prospect {prospect_id}")
        return result

    except Exception as e:
        logger.error(f"Error sending followup: {e}")
        raise


async def execute_send_reply(prospect_id: int, account_id: int, content: str) -> dict:
    """Envoie immédiatement une réponse générée."""
    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"Prospect {prospect_id} not found")

        if not content:
            raise ValueError("No content provided for reply")

        result = await send_message_via_unipile(
            prospect_id=prospect_id,
            account_id=account_id,
            content=content,
            message_type='reply'
        )

        if not result['success']:
            raise ValueError(f"Failed to send reply: {result['error']}")

        logger.info(f"Reply sent to prospect {prospect_id}")
        return result

    except Exception as e:
        logger.error(f"Error sending reply: {e}")
        raise


# ============================
# APPROVED LOG EXECUTION
# ============================

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
