#!/usr/bin/env python3
# app/core/job/metrics.py

from config.logger import logger
from app.database.crud import get_db_pool

async def update_daily_metrics():
    """
    Calcule et met à jour les métriques du jour.

    Analyse les tables existantes sans modification :
    - logs → messages envoyés
    - messages → réponses reçues + appels planifiés (via regex sur content)
    - prospects → prospects archived
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # 1. Messages envoyés (via logs)
        messages_sent = await conn.fetchval("""
            SELECT COUNT(*) FROM logs
            WHERE DATE(executed_at) = CURRENT_DATE
              AND status = 'success'
              AND action IN ('send_first_contact', 'send_followup_a_1',
                             'send_followup_a_2', 'send_followup_a_3',
                             'send_followup_b', 'send_followup_c', 'send_reply')
        """)

        # 2. Réponses reçues
        responses_received = await conn.fetchval("""
            SELECT COUNT(*) FROM messages
            WHERE sent_by = 'prospect'
              AND DATE(sent_at) = CURRENT_DATE
        """)

        # 3. Appels planifiés (détection via regex PostgreSQL)
        calls_scheduled = await conn.fetchval(r"""
            SELECT COUNT(*) FROM messages
            WHERE sent_by = 'prospect'
              AND DATE(sent_at) = CURRENT_DATE
              AND (
                content ~* 'meet\.google\.com' OR
                content ~* 'calendly\.com' OR
                content ~* 'zoom\.us' OR
                content ~* 'teams\.microsoft' OR
                content ~* '\d{1,2}[h:]\d{2}' OR
                content ~* '\b(appel|call|rdv|rendez-vous|meeting|réunion)\b'
              )
        """)

        # 4. Prospects archived
        prospects_archived = await conn.fetchval("""
            SELECT COUNT(*) FROM prospects
            WHERE status = 'archived'
              AND DATE(updated_at) = CURRENT_DATE
        """)

        # 5. UPSERT dans daily_metrics
        await conn.execute("""
            INSERT INTO daily_metrics
                (date, messages_sent, responses_received, calls_scheduled, prospects_archived)
            VALUES (CURRENT_DATE, $1, $2, $3, $4)
            ON CONFLICT (date) DO UPDATE SET
                messages_sent = EXCLUDED.messages_sent,
                responses_received = EXCLUDED.responses_received,
                calls_scheduled = EXCLUDED.calls_scheduled,
                prospects_archived = EXCLUDED.prospects_archived,
                updated_at = NOW()
        """, messages_sent, responses_received, calls_scheduled, prospects_archived)

        logger.info(
            f"📊 Metrics updated: sent={messages_sent}, "
            f"received={responses_received}, calls={calls_scheduled}, "
            f"archived={prospects_archived}"
        )

async def run_metrics_worker_loop():
    """
    Worker de mise à jour des métriques journalières.
    Tourne toutes les 5 minutes tant que workflow actif.
    """
    from app.core.utils.scheduler import smart_sleep

    logger.info("Starting metrics worker loop")

    while True:
        try:
            await update_daily_metrics()
        except Exception as e:
            logger.error(f"Error in metrics worker: {e}", exc_info=True)

        await smart_sleep(300)  # 5 minutes
