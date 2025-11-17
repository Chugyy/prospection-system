#!/usr/bin/env python3
# app/core/job/conversation_worker.py

import asyncio
from datetime import datetime, timedelta
from config.logger import logger
from app.database import crud
from app.core.handler.followup import create_auto_conversation_followup

async def detect_stale_conversations():
    """
    Worker qui détecte les conversations sans réponse (Type B).

    Fréquence recommandée : 1 fois par jour

    À implémenter:
    1. Récupérer toutes les conversations actives (status='connected')
    2. Pour chaque prospect:
        a. Vérifier le dernier message du prospect
        b. Si > 5 jours sans réponse ET pas de followup Type B en attente
        c. Créer un followup Type B via create_auto_conversation_followup
        d. Logger l'action
    3. Gérer les erreurs
    """
    try:
        logger.info("Starting conversation staleness detection")

        # Récupérer tous les prospects connectés
        connected_prospects = await crud.list_prospects(status='connected')
        logger.info(f"Found {len(connected_prospects)} connected prospects")

        stale_count = 0
        followups_created = 0
        failed_count = 0

        for prospect in connected_prospects:
            try:
                prospect_id = prospect['id']
                account_id = prospect['account_id']

                # Vérifier si prospect peut être traité
                should_process, reason = await crud.should_process_prospect(prospect_id)
                if not should_process:
                    logger.info(f"Skipping prospect {prospect_id}: {reason}")
                    continue

                # Récupérer le dernier message du prospect
                last_prospect_message = await crud.get_last_prospect_message(prospect_id)

                if not last_prospect_message:
                    # Pas de message du prospect → pas de conversation établie
                    continue

                # Calculer le délai depuis le dernier message
                last_message_date = last_prospect_message['sent_at']
                days_since = (datetime.now() - last_message_date).days

                if days_since < 5:
                    # Conversation encore fraîche
                    continue

                # Vérifier si un followup Type B est déjà en attente
                existing_followups = await crud.list_followups(
                    status='pending',
                    followup_type='auto_conversation'
                )

                has_pending = any(f['prospect_id'] == prospect_id for f in existing_followups)

                if has_pending:
                    logger.info(f"Prospect {prospect_id} already has pending Type B followup, skipping")
                    continue

                # Créer un followup Type B
                logger.info(f"Creating Type B followup for prospect {prospect_id} (stale for {days_since} days)")

                result = await create_auto_conversation_followup(
                    prospect_id=prospect_id,
                    account_id=account_id
                )

                await crud.create_log(
                    action='followup_scheduled',
                    source='system',
                    account_id=account_id,
                    prospect_id=prospect_id,
                    entity_type='followup',
                    status='success',
                    details=result
                )

                stale_count += 1
                followups_created += 1

            except Exception as e:
                failed_count += 1
                logger.error(f"Error processing prospect {prospect.get('id')}: {e}")

        logger.info(f"Conversation staleness detection completed: {stale_count} stale detected, {followups_created} followups created, {failed_count} failed")

        return {
            "stale_detected": stale_count,
            "followups_created": followups_created,
            "failed": failed_count
        }

    except Exception as e:
        logger.error(f"Fatal error in conversation worker: {e}")
        raise

async def run_conversation_worker_loop():
    """
    Boucle infinie du worker de détection de conversations stagnantes.

    Lance detect_stale_conversations 1 fois par jour.
    Pause nocturne: 22h-6h (heure de Paris).
    """
    from app.core.utils.scheduler import smart_sleep

    logger.info("Starting conversation staleness worker loop")

    while True:
        try:
            await detect_stale_conversations()
        except Exception as e:
            logger.error(f"Error in conversation worker loop: {e}")

        await smart_sleep(86400)
