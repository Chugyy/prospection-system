#!/usr/bin/env python3
# app/core/job/queue.py

import asyncio
from config.logger import logger
from config.config import settings
from app.database import crud

async def process_queue() -> dict:
    """
    Traite les tâches depuis la queue par priorité.

    Processus:
    1. Vérifier quota journalier (early exit)
    2. Récupérer N tâches pending triées par priorité ASC
    3. Dispatcher vers handler approprié
    4. Marquer comme completed/failed

    Returns:
        dict: {"processed": int, "failed": int}
    """

    try:
        logger.info("🔄 Processing queue")

        batch_size = settings.MAX_BATCH_SIZE
        pending = await crud.get_pending_tasks(limit=batch_size)

        if not pending:
            logger.info("No pending tasks")
            return {"processed": 0, "failed": 0}

        logger.info(f"📋 Processing {len(pending)} tasks")

        processed = 0
        failed = 0

        for task in pending:
            try:
                task_id = task['id']
                task_type = task['type']
                priority = task['priority']

                logger.info(f"⚙️  Task {task_id} (type: {task_type}, priority: {priority})")

                await crud.update_task_status(task_id, 'processing')

                # Dispatcher
                if task_type == 'process_connection':
                    result = await handle_connection(task)
                else:
                    logger.warning(f"Unknown task type: {task_type}")
                    await crud.update_task_status(task_id, 'failed', error=f"Unknown type: {task_type}")
                    failed += 1
                    continue

                await crud.update_task_status(task_id, 'completed', result=result)
                processed += 1
                logger.info(f"✅ Task {task_id} completed")

            except Exception as e:
                failed += 1
                logger.error(f"Error processing task {task.get('id')}: {e}")

                # Retry logic
                retry_count = task.get('retry_count', 0)
                max_retries = task.get('max_retries', 3)

                if retry_count < max_retries:
                    await crud.increment_retry(task['id'])
                    logger.info(f"Task {task['id']} will retry ({retry_count + 1}/{max_retries})")
                else:
                    await crud.update_task_status(task['id'], 'failed', error=str(e))
                    logger.error(f"Task {task['id']} failed after {max_retries} retries")

        logger.info(f"✅ Queue processed: {processed} completed, {failed} failed")

        return {"processed": processed, "failed": failed}

    except Exception as e:
        logger.error(f"Fatal error processing queue: {e}")
        raise


async def handle_connection(task: dict) -> dict:
    """
    Handler pour tâche 'process_connection'.

    Process connection and create prospect with enriched data from Unipile.
    """
    from app.core.job.connection import sync_messages_for_prospect, analyze_and_plan_actions
    from app.core.services.unipile.api.endpoints.users import get_user_profile

    payload = task['payload']
    account_id = task['account_id']
    linkedin_id = payload['linkedin_identifier']

    # Extract attendee_provider_id with fallback to raw.member_id
    attendee_provider_id = payload.get('attendee_provider_id')
    if not attendee_provider_id:
        attendee_provider_id = payload.get('raw', {}).get('member_id')

    logger.info(f"Processing connection: {linkedin_id} (attendee_id: {attendee_provider_id})")

    # Enrichir données via Unipile get_user_profile
    enriched_data = {}
    try:
        unipile_account = await crud.get_account(account_id)
        unipile_account_id = unipile_account.get('unipile_account_id') if unipile_account else None

        profile = get_user_profile(linkedin_id, account_id=unipile_account_id)

        # Extraction des données enrichies
        if profile:
            enriched_data['company'] = profile.get('company', '')
            enriched_data['job_title'] = profile.get('headline', '')  # Unipile utilise 'headline' pour job title
            enriched_data['profile_picture_url'] = profile.get('profile_picture_url', '')

            logger.info(f"✅ Enriched profile data for {linkedin_id}: company={enriched_data.get('company')}, job={enriched_data.get('job_title')}")
    except Exception as e:
        logger.warning(f"Failed to enrich profile for {linkedin_id}: {e} - continuing with basic data")

    # 1. VÉRIFICATION AVATAR CIBLE (3 niveaux: blacklist, whitelist, LLM)
    from app.core.utils.avatar_filter import quick_avatar_check
    from app.core.handler.connection import check_avatar_match

    headline = payload.get('headline', '')
    job_title = enriched_data.get('job_title', '')
    company = enriched_data.get('company', '')

    # Niveau 1 & 2: Pattern matching rapide
    decision, reason = quick_avatar_check(headline, job_title, company)

    if decision == "reject":
        logger.info(f"❌ Connection rejected (avatar filter): {linkedin_id} - {reason}")
        return {
            "prospect_id": None,
            "messages_synced": 0,
            "actions_planned": 0,
            "error": "avatar_mismatch",
            "reason": reason
        }

    # 2. Créer prospect (temporaire si LLM needed)
    prospect_id = await crud.create_prospect(
        account_id=account_id,
        first_name=payload.get('first_name', ''),
        last_name=payload.get('last_name', ''),
        linkedin_identifier=linkedin_id,
        attendee_provider_id=attendee_provider_id,
        linkedin_url=f"https://www.linkedin.com/in/{linkedin_id}",
        headline=headline,
        company=company,
        job_title=job_title,
        status='pending' if decision == "llm_needed" else 'connected',
        avatar_match=True if decision == "accept" else None
    )

    # Niveau 3: LLM pour cas ambigus
    if decision == "llm_needed":
        logger.info(f"🤖 Avatar check (LLM needed): prospect {prospect_id} - {reason}")
        is_match = await check_avatar_match(prospect_id)

        if not is_match:
            await crud.update_prospect(prospect_id, status='rejected', avatar_match=False)
            logger.info(f"❌ Connection rejected (LLM): prospect {prospect_id}")
            return {
                "prospect_id": prospect_id,
                "messages_synced": 0,
                "actions_planned": 0,
                "error": "avatar_mismatch_llm"
            }

        # LLM approved → update status
        await crud.update_prospect(prospect_id, status='connected', avatar_match=True)
        logger.info(f"✅ Avatar match confirmed (LLM): prospect {prospect_id}")

    # 2. Sync messages
    sync_result = await sync_messages_for_prospect(prospect_id, account_id)

    # STOP si erreur de sync
    if sync_result.get('error'):
        logger.warning(f"Sync failed for prospect {prospect_id}: {sync_result['error']}, skipping analysis")
        return {
            "prospect_id": prospect_id,
            "messages_synced": 0,
            "actions_planned": 0,
            "error": sync_result['error']
        }

    # 3. Analyser + planifier actions
    plan_result = await analyze_and_plan_actions(prospect_id, account_id)

    logger.info(f"✅ Connection processed: prospect={prospect_id}, messages={sync_result.get('messages_synced')}, actions={plan_result.get('actions_planned')}")

    return {
        "prospect_id": prospect_id,
        "messages_synced": sync_result.get('messages_synced', 0),
        "actions_planned": plan_result.get('actions_planned', 0)
    }


async def run_queue_loop():
    """
    Worker générique de traitement de queue.

    Traite toutes tâches par priorité.
    Fréquence: QUEUE_INTERVAL (30 min par défaut).
    Pause nocturne: 22h-6h (heure de Paris).
    """
    from app.core.utils.scheduler import smart_sleep

    logger.info("Starting queue processor")

    while True:
        try:
            await process_queue()
        except Exception as e:
            logger.error(f"Error in queue processor: {e}")

        await smart_sleep(settings.QUEUE_INTERVAL)
