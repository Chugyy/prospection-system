#!/usr/bin/env python3
# app/core/job/followup_worker.py

import asyncio
import random
from config.logger import logger
from app.database import crud
from app.core.handler.message import send_message_via_unipile
from app.core.utils.quota import should_process_today

# Délais minimums entre actions (secondes)
MIN_DELAYS = {
    'send_first_contact': 120,  # 2 min
    'send_followup_a_1': 180,   # 3 min
    'send_followup_a_2': 180,
    'send_followup_a_3': 180,
    'send_followup_b': 180,
    'send_followup_c': 180,
    'send_reply': 120,          # 2 min
}

async def process_pending_followups():
    """
    Action executor with rate-limiting and early quota checks.

    Fréquence recommandée : toutes les 2-5 minutes

    Processus:
    1. Récupérer actions pending depuis table logs
    2. Grouper par type et vérifier quotas (early exit par type)
    3. Exécuter avec délais aléatoires
    4. Respecter limites LinkedIn

    Actions supportées:
    - send_first_contact
    - send_followup_a_1/2/3
    - send_followup_b
    - send_followup_c (après validation humaine)
    """
    try:
        logger.info("🚀 Starting ACTION EXECUTOR (rate-limited)")

        # 1. Récupérer actions pending
        pending_actions = await crud.get_pending_actions(limit=10)
        logger.info(f"📋 Found {len(pending_actions)} pending actions")

        if not pending_actions:
            return {"executed": 0, "skipped": 0, "failed": 0}

        # 2. Grouper par type d'action
        actions_by_type = {}
        for action in pending_actions:
            action_type = action['action']
            if action_type not in actions_by_type:
                actions_by_type[action_type] = []
            actions_by_type[action_type].append(action)

        logger.info(f"📊 Actions grouped: {', '.join([f'{k}={len(v)}' for k, v in actions_by_type.items()])}")

        executed_count = 0
        skipped_count = 0
        failed_count = 0

        # 3. Traiter par type d'action
        for action_type, actions in actions_by_type.items():
            # Traiter les actions de ce type
            for action in actions:
                # Vérifier quota AVANT chaque action
                quota_check = await should_process_today(action_type)

                if not quota_check['can_process']:
                    logger.warning(
                        f"⚠️  Daily quota reached for {action_type} "
                        f"({quota_check['current']}/{quota_check['limit']}) - skipping remaining actions"
                    )
                    skipped_count += 1
                    continue

                try:
                    prospect_id = action['prospect_id']
                    account_id = action['account_id']
                    log_id = action['id']

                    logger.info(f"⚙️  Processing action {action_type} for prospect {prospect_id}")

                    # Vérifier si prospect peut être traité
                    should_process, reason = await crud.should_process_prospect(prospect_id)
                    if not should_process:
                        logger.info(f"Skipping prospect {prospect_id}: {reason}")
                        await crud.update_log_validation(log_id, 'cancelled')
                        skipped_count += 1
                        continue

                    # 4. Vérifier si prospect a répondu (annulation dynamique)
                    last_message = await crud.get_last_prospect_message(prospect_id)
                    if last_message and last_message['sent_at'] > action['created_at']:
                        content = last_message.get('content', '').strip().lower()
                        if len(content) > 50:
                            logger.info(f"🚫 Prospect {prospect_id} replied, skipping action {action_type}")
                            await crud.update_log_validation(log_id, 'cancelled')
                            skipped_count += 1
                            continue

                    # 5. Exécuter l'action selon le type
                    if action_type.startswith('send_first_contact'):
                        result = await execute_send_first_contact(prospect_id, account_id)
                    elif action_type.startswith('send_followup'):
                        result = await execute_send_followup(action, prospect_id, account_id)
                    elif action_type.startswith('send_reply'):
                        result = await execute_send_reply(action, prospect_id, account_id)
                    else:
                        logger.warning(f"Unknown action type: {action_type}")
                        skipped_count += 1
                        continue

                    # 6. Marquer action comme exécutée
                    await crud.mark_log_executed(log_id)
                    await crud.update_log_validation(log_id, 'auto_executed')

                    executed_count += 1
                    logger.info(f"✅ Action {action_type} executed successfully")

                    # 7. Délai aléatoire avant prochaine action
                    delay = random.randint(
                        MIN_DELAYS.get(action_type, 120),
                        MIN_DELAYS.get(action_type, 120) * 2
                    )
                    logger.info(f"⏱️  Waiting {delay}s before next action")
                    await asyncio.sleep(delay)

                except Exception as e:
                    failed_count += 1
                    logger.error(f"❌ Error executing action {action.get('id')}: {e}")

        logger.info(f"✅ Action executor completed: {executed_count} executed, {skipped_count} skipped, {failed_count} failed")

        return {
            "executed": executed_count,
            "skipped": skipped_count,
            "failed": failed_count
        }

    except Exception as e:
        logger.error(f"Fatal error in followup worker: {e}")
        raise

async def execute_send_first_contact(prospect_id: int, account_id: int) -> dict:
    """Exécute l'envoi du premier message de contact."""
    from app.core.templates.composer import message_composer

    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"Prospect {prospect_id} not found")

        # Générer message personnalisé avec IA
        content = await message_composer.generate_welcome_message(prospect)

        # Envoyer message
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
    """Exécute l'envoi d'un followup (A, B ou C)."""
    from app.core.templates.composer import message_composer

    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"Prospect {prospect_id} not found")

        action_type = action['action']

        # Sélectionner message selon type
        if 'send_followup_a_1' in action_type:
            content = message_composer.generate_followup_message(prospect, step=1)
        elif 'send_followup_a_2' in action_type:
            content = message_composer.generate_followup_message(prospect, step=2)
        elif 'send_followup_a_3' in action_type:
            content = message_composer.generate_followup_message(prospect, step=3)
        elif 'send_followup_b' in action_type:
            # Relance conversation (utiliser step 1 pour rester léger)
            content = message_composer.generate_followup_message(prospect, step=1)
        elif 'send_followup_c' in action_type:
            # Long terme: contenu stocké dans payload ou généré par IA
            payload = action.get('payload', {})
            content = payload.get('content')
            if not content:
                # Fallback: générer avec IA
                content = await message_composer.generate_welcome_message(prospect)
        else:
            raise ValueError(f"Unknown followup type: {action_type}")

        # Envoyer message
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

async def execute_send_reply(action: dict, prospect_id: int, account_id: int) -> dict:
    """Exécute l'envoi d'une réponse générée par LLM."""
    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise ValueError(f"Prospect {prospect_id} not found")

        # Récupérer le contenu de la réponse depuis le payload
        payload = action.get('payload', {})
        content = payload.get('content')

        if not content:
            raise ValueError(f"No content found in reply action payload")

        # Envoyer message
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


async def run_followup_worker_loop():
    """
    Boucle infinie du worker de followup (transformé en ACTION EXECUTOR).

    Lance process_pending_followups toutes les 5 minutes (300s).
    Pause nocturne: 22h-6h (heure de Paris).
    """
    from app.core.utils.scheduler import smart_sleep

    logger.info("Starting ACTION EXECUTOR loop")

    while True:
        try:
            await process_pending_followups()
        except Exception as e:
            logger.error(f"Error in action executor loop: {e}")

        # Attendre 5 minutes (avec pause nocturne)
        await smart_sleep(300)
