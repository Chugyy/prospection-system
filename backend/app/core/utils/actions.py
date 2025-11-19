#!/usr/bin/env python3
# app/core/utils/actions.py

from config.logger import logger
from app.database import crud
from app.core.handler.message import send_message_via_unipile


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
