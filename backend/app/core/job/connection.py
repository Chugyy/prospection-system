#!/usr/bin/env python3
# app/core/job/connection_worker.py

import asyncio
from datetime import datetime
from config.logger import logger
from app.database import crud
from app.core.handler.connection import accept_connection_request
from app.core.services.avatar.filter import quick_avatar_check

async def scan_and_queue_connections():
    """
    Scan connexions Unipile et ajoute à la queue.

    Processus:
    1. Scanner connexions des derniers CUTOFF_DAYS jours
    2. Stopper dès qu'on atteint une date antérieure
    3. Pour chaque nouvelle: créer tâche 'process_connection' en queue
    4. Priorité haute (1) pour traiter en premier

    Returns:
        dict: {"scanned": int, "queued": int, "filtered": int}
    """
    from app.core.services.unipile.api.endpoints.connections import get_connections_list
    from app.core.utils.cutoff import get_cutoff_date, get_cutoff_datetime
    from config.config import settings

    try:
        logger.info("🔍 Starting connection scan and queue")

        cutoff_date = get_cutoff_date()
        cutoff_datetime = get_cutoff_datetime()
        require_avatar = settings.REQUIRE_AVATAR

        logger.info(f"📅 Cutoff date (last {settings.CUTOFF_DAYS} days): {cutoff_datetime.strftime('%Y-%m-%d %H:%M:%S')}")

        accounts = await crud.list_all_accounts()
        if not accounts:
            return {"scanned": 0, "queued": 0, "filtered": 0}

        account_id = accounts[0]['id']

        cursor = None
        scanned = 0
        queued = 0
        filtered = 0

        while True:
            connections_data = get_connections_list(
                account_id=settings.UNIPILE_ACCOUNT_ID,
                limit=100,
                cursor=cursor
            )

            items = connections_data.get('items', [])

            if not items:
                logger.warning(f"⚠️  No items returned from Unipile API")
                break

            logger.info(f"Processing batch of {len(items)} connections")

            for connection in items:
                scanned += 1

                created_at = connection.get('created_at')

                # STOPPING: Si avant cutoff date
                if created_at and created_at < cutoff_date:
                    logger.info(f"✋ Reached cutoff date, stopping (scanned {scanned} total)")
                    return {"scanned": scanned, "queued": queued, "filtered": filtered}

                linkedin_id = connection.get('public_identifier') or connection.get('member_id')
                member_id = connection.get('member_id')  # attendee_provider_id long format

                if not linkedin_id:
                    continue

                # Vérifier si déjà en queue
                existing_task = await crud.get_task_by_payload(
                    type='process_connection',
                    field='linkedin_identifier',
                    value=linkedin_id
                )

                if existing_task:
                    logger.debug(f"Connection {linkedin_id} already queued")
                    continue

                # Vérifier si déjà traité
                existing_prospect = await crud.get_prospect_by_linkedin_identifier(linkedin_id)
                if existing_prospect:
                    logger.debug(f"Connection {linkedin_id} already processed")
                    continue

                # Filtre avatar
                if require_avatar:
                    avatar = connection.get('profile_picture_url')
                    if not avatar:
                        filtered += 1
                        logger.debug(f"Filtered {linkedin_id}: no avatar")
                        continue

                # Ajouter à queue avec priorité haute (1)
                await crud.create_task(
                    type='process_connection',
                    account_id=account_id,
                    priority=1,
                    payload={
                        'linkedin_identifier': linkedin_id,
                        'attendee_provider_id': member_id,  # Long format pour matching messages
                        'first_name': connection.get('first_name'),
                        'last_name': connection.get('last_name'),
                        'headline': connection.get('headline'),
                        'profile_picture_url': connection.get('profile_picture_url'),
                        'connection_urn': connection.get('connection_urn'),
                        'created_at': created_at,
                        'raw': connection
                    }
                )

                queued += 1
                logger.info(f"✅ Queued: {connection.get('first_name')} {connection.get('last_name')}")

            cursor = connections_data.get('cursor')
            if not cursor:
                break

        logger.info(f"✅ Scan completed: {scanned} scanned, {queued} queued, {filtered} filtered")

        return {"scanned": scanned, "queued": queued, "filtered": filtered}

    except Exception as e:
        logger.error(f"Error scanning connections: {e}")
        raise

async def sync_messages_for_prospect(prospect_id: int, account_id: int) -> dict:
    """
    Récupère tous les messages échangés avec un prospect depuis Unipile.

    Processus:
    1. Récupérer le chat_id associé au prospect
    2. Pagination sur get_chat_messages()
    3. Insérer chaque message en BDD

    Returns:
        dict: {"messages_synced": int}
    """
    from app.core.services.unipile.api.endpoints.messaging import find_attendee_by_provider_id, get_chat_messages
    from config.config import settings

    try:
        prospect = await crud.get_prospect(prospect_id)
        account = await crud.get_account(account_id)

        if not prospect or not account:
            raise ValueError(f"Prospect {prospect_id} or account {account_id} not found")

        linkedin_id = prospect.get('linkedin_identifier')
        attendee_provider_id = prospect.get('attendee_provider_id')
        unipile_account_id = account.get('unipile_account_id')

        logger.info(f"Syncing messages for prospect {prospect_id} ({linkedin_id})")

        # 1. Trouver le chat_id via attendee_provider_id (OPTIMISÉ)
        chat_id = None

        if attendee_provider_id:
            logger.info(f"🔍 Searching chat using attendee_provider_id: {attendee_provider_id}")
            attendee_data = find_attendee_by_provider_id(attendee_provider_id, account_id=unipile_account_id)

            if attendee_data:
                chat_id = attendee_data.get('chat_id')
                logger.info(f"✅ Chat found via attendee API: chat_id={chat_id}")
            else:
                logger.warning(f"No attendee found for provider_id {attendee_provider_id}")
        else:
            logger.warning(f"No attendee_provider_id for prospect {prospect_id}")

        if not chat_id:
            logger.warning(f"No chat found for prospect {prospect_id}")
            return {"messages_synced": 0, "error": "chat_not_found"}

        logger.info(f"Found chat_id {chat_id} for prospect {prospect_id}")

        # 2. Récupérer dernier message connu
        last_known = await crud.get_last_message_for_prospect(prospect_id)
        last_unipile_id = last_known['unipile_message_id'] if last_known else None

        # 3. Récupérer messages avec stopping intelligent
        synced = 0
        messages_cursor = None

        while True:
            messages_data = get_chat_messages(
                chat_id=chat_id,
                account_id=unipile_account_id,
                cursor=messages_cursor,
                limit=100
            )

            items = messages_data.get('items', [])
            if not items:
                break

            for msg in items:
                msg_id = msg.get('id')

                # STOPPING: Si message déjà connu
                if msg_id == last_unipile_id:
                    logger.info(f"Reached last known message, stopping")
                    return {"messages_synced": synced}

                # Vérifier doublon (sécurité)
                existing = await crud.get_message_by_unipile_id(msg_id)
                if existing:
                    continue

                # Process attachments (audio transcription)
                from app.core.services.media.transcriptor import process_message_attachments
                content = process_message_attachments(msg, unipile_account_id)

                # Insérer
                await crud.create_message(
                    prospect_id=prospect_id,
                    account_id=account_id,
                    sent_by='account' if msg.get('from_me') else 'prospect',
                    content=content,
                    message_type='manual',  # Messages sync depuis Unipile = manual (historique)
                    sent_at=msg.get('date'),
                    unipile_message_id=msg_id
                )
                synced += 1

            messages_cursor = messages_data.get('cursor')
            if not messages_cursor:
                break

        logger.info(f"Synced {synced} messages for prospect {prospect_id}")

        return {"messages_synced": synced}

    except Exception as e:
        logger.error(f"Error syncing messages for prospect {prospect_id}: {e}")
        return {"messages_synced": 0, "error": str(e)}

async def analyze_and_plan_actions(prospect_id: int, account_id: int) -> dict:
    """
    Analyse la conversation avec un prospect et planifie les actions nécessaires.

    Processus:
    1. Appeler analyze_conversation_with_llm()
    2. Créer des logs d'actions (table logs) avec délais aléatoires
    3. Retourner nombre d'actions planifiées

    Returns:
        dict: {"actions_planned": int, "action_ids": list}
    """
    import random
    from datetime import timedelta

    try:
        from app.core.handler.message import analyze_conversation_with_llm

        logger.info(f"Analyzing conversation and planning actions for prospect {prospect_id}")

        # 1. Analyser conversation
        analysis = await analyze_conversation_with_llm(prospect_id)

        # 2. Créer logs pour chaque action recommandée
        action_ids = []
        priority = 1

        # Action: Premier message
        if analysis.get('needs_first_message'):
            # GARDE: Vérifier si action déjà créée
            existing = await crud.list_logs(prospect_id=prospect_id, action='send_first_contact')
            if existing:
                logger.info(f"First contact already planned for prospect {prospect_id}, skipping")
            else:
                scheduled_at = datetime.now() + timedelta(minutes=random.randint(0, 5))

                action_id = await crud.create_log(
                    action='send_first_contact',
                    prospect_id=prospect_id,
                    account_id=account_id,
                    source='system',
                    validation_status='auto_execute',
                    status='pending',
                    priority=priority,
                    payload={
                        'scheduled_at': scheduled_at.isoformat(),
                        'analysis': analysis
                    }
                )
                action_ids.append(action_id)
                priority += 1
                logger.info(f"Planned first contact for prospect {prospect_id} at {scheduled_at}")

        # Action: Followups
        if analysis.get('needs_followup'):
            followup_type = analysis.get('followup_type')

            if followup_type == 'type_a':
                # Followups après 1er message (3j, 7j, 14j)
                delays = analysis.get('followup_delays_days', [3, 7, 14])
                for i, delay_days in enumerate(delays):
                    scheduled_at = datetime.now() + timedelta(days=delay_days, minutes=random.randint(30, 180))

                    action_id = await crud.create_log(
                        action=f'send_followup_a_{i+1}',
                        prospect_id=prospect_id,
                        account_id=account_id,
                        source='system',
                        validation_status='auto_execute',
                        status='pending',
                        priority=priority,
                        payload={
                            'scheduled_at': scheduled_at.isoformat(),
                            'followup_number': i+1,
                            'analysis': analysis
                        }
                    )
                    action_ids.append(action_id)
                    priority += 1
                    logger.info(f"Planned followup A{i+1} for prospect {prospect_id} at {scheduled_at}")

            elif followup_type == 'type_b':
                # Relance conversation stale
                scheduled_at = datetime.now() + timedelta(days=2, minutes=random.randint(30, 180))

                action_id = await crud.create_log(
                    action='send_followup_b',
                    prospect_id=prospect_id,
                    account_id=account_id,
                    source='system',
                    validation_status='auto_execute',
                    status='pending',
                    priority=priority,
                    payload={
                        'scheduled_at': scheduled_at.isoformat(),
                        'analysis': analysis
                    }
                )
                action_ids.append(action_id)
                logger.info(f"Planned followup B for prospect {prospect_id} at {scheduled_at}")

            elif followup_type == 'type_c':
                # Long terme → nécessite validation humaine
                long_term_date = analysis.get('long_term_date')

                action_id = await crud.create_log(
                    action='send_followup_c',
                    prospect_id=prospect_id,
                    account_id=account_id,
                    source='llm',
                    validation_status='pending',
                    requires_validation=True,
                    status='pending',
                    priority=priority,
                    payload={
                        'scheduled_at': long_term_date,
                        'analysis': analysis
                    }
                )
                action_ids.append(action_id)
                logger.info(f"Planned followup C for prospect {prospect_id} (requires validation)")

        logger.info(f"Planned {len(action_ids)} actions for prospect {prospect_id}")

        return {
            "actions_planned": len(action_ids),
            "action_ids": action_ids
        }

    except Exception as e:
        logger.error(f"Error planning actions for prospect {prospect_id}: {e}")
        return {"actions_planned": 0, "action_ids": [], "error": str(e)}

async def run_connection_worker_loop():
    """
    Worker de scan des connexions.

    Lance scan_and_queue_connections selon SCAN_INTERVAL (2h par défaut).
    Pause nocturne: 22h-6h (heure de Paris).
    """
    from config.config import settings
    from app.core.utils.scheduler import smart_sleep

    logger.info("Starting connection worker (scan only)")

    while True:
        try:
            await scan_and_queue_connections()
        except Exception as e:
            logger.error(f"Error in connection worker: {e}")

        await smart_sleep(settings.SCAN_INTERVAL)
