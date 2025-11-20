#!/usr/bin/env python3
# app/core/utils/scheduler.py

import asyncio
from datetime import datetime, timedelta
import pytz
from config.logger import logger
from app.core.job.actions import run_queue_worker_loop
from app.core.job.connection import run_connection_worker_loop
from app.core.job.conversation import run_conversation_worker_loop
from app.core.job.tasks import run_queue_loop
from app.core.job.reply import run_reply_worker_loop
from app.core.job.metrics import run_metrics_worker_loop

_workers_running = False
_worker_tasks = {}

async def smart_sleep(base_interval: int) -> None:
    """
    Sleep with time-window awareness (6h-22h Paris time).

    If current time is outside 6h-22h window, sleeps until 6am.
    Otherwise, sleeps for base_interval seconds.

    Args:
        base_interval: Normal sleep interval in seconds
    """
    paris_tz = pytz.timezone('Europe/Paris')
    now = datetime.now(paris_tz)
    hour = now.hour

    # Check if outside working hours (22h-6h)
    if hour >= 22 or hour < 6:
        next_6am = now.replace(hour=6, minute=0, second=0, microsecond=0)

        # If after 22h, target tomorrow's 6am
        if hour >= 22:
            next_6am += timedelta(days=1)

        wait_seconds = (next_6am - now).total_seconds()
        logger.info(f"⏸️  Workers paused until 6am Paris time ({wait_seconds:.0f}s / {wait_seconds/3600:.1f}h)")
        await asyncio.sleep(wait_seconds)
    else:
        # Normal working hours: standard interval
        await asyncio.sleep(base_interval)

def is_workflow_running() -> bool:
    """Retourne True si le workflow est en cours d'exécution."""
    return _workers_running

def get_workers_status() -> dict:
    """
    Retourne le statut de tous les workers.

    Returns:
        dict: {worker_name: {"running": bool, "task_done": bool}}
    """
    status = {}
    worker_names = ["action_executor", "connection", "conversation", "connection_queue", "reply", "metrics"]

    for name in worker_names:
        task = _worker_tasks.get(name)
        status[name] = {
            "running": task is not None and not task.done(),
            "task_exists": task is not None
        }

    return status

def is_worker_running(worker_name: str) -> bool:
    """
    Vérifie si un worker spécifique est en cours d'exécution.

    Args:
        worker_name: Nom du worker (action_executor, connection, conversation, connection_queue, reply, metrics)

    Returns:
        bool: True si le worker est actif
    """
    task = _worker_tasks.get(worker_name)
    return task is not None and not task.done()

def stop_worker(worker_name: str) -> bool:
    """
    Arrête un worker spécifique.

    Args:
        worker_name: Nom du worker à arrêter

    Returns:
        bool: True si le worker a été arrêté, False sinon
    """
    global _worker_tasks, _workers_running

    task = _worker_tasks.get(worker_name)
    if task and not task.done():
        task.cancel()
        del _worker_tasks[worker_name]
        logger.info(f"🛑 Worker '{worker_name}' stopped")

        # Si plus aucun worker actif, marquer le workflow comme arrêté
        if not any(not t.done() for t in _worker_tasks.values()):
            _workers_running = False

        return True

    logger.warning(f"Worker '{worker_name}' not running")
    return False

def stop_all_workers():
    """
    Arrête tous les workers en annulant les tâches asyncio.

    Utilise task.cancel() pour interrompre les boucles infinies.
    """
    global _workers_running, _worker_tasks

    if not _workers_running:
        logger.warning("Workers not running, nothing to stop")
        return

    logger.info("🛑 Stopping all workers...")

    for task in _worker_tasks.values():
        task.cancel()

    _workers_running = False
    _worker_tasks = {}

    logger.info("✅ All workers stopped")

async def start_all_workers(skip_initial_sequence: bool = False):
    """
    Lance tous les workers avec exécution séquentielle initiale.

    Processus:
    1. Exécution séquentielle de tous les workers (ordre logique)
    2. Lancement des boucles infinies avec délais configurés

    Args:
        skip_initial_sequence: Si True, skip la séquence initiale (utile pour les tests)
    """
    global _workers_running, _worker_tasks

    if _workers_running:
        logger.warning("Workers already running, skipping start")
        return

    logger.info("🚀 Starting workers...")

    # 1. EXÉCUTION SÉQUENTIELLE INITIALE
    if not skip_initial_sequence:
        logger.info("Running initial worker sequence...")
        try:
            from app.core.job.connection import scan_and_queue_connections
            from app.core.job.tasks import process_queue
            from app.core.job.reply import process_unread_messages
            from app.core.job.actions import process_pending_actions
            from app.core.job.conversation import detect_stale_conversations

            logger.info("1/5 Connection scan...")
            await scan_and_queue_connections()

            logger.info("2/5 Connection queue processing...")
            await process_queue()

            logger.info("3/5 Reply to unread messages...")
            await process_unread_messages()

            logger.info("4/5 Action executor...")
            await process_pending_actions()

            logger.info("5/5 Conversation staleness...")
            await detect_stale_conversations()

            logger.info("✅ Initial sequence completed")

        except Exception as e:
            logger.error(f"Error during initial sequence: {e}")
    else:
        logger.info("⏭️  Initial sequence skipped")

    # 2. LANCER LES BOUCLES INFINIES EN PARALLÈLE
    logger.info("🔄 Starting worker loops with configured delays...")

    _worker_tasks["action_executor"] = asyncio.create_task(run_queue_worker_loop(), name="action_executor_worker")
    _worker_tasks["connection"] = asyncio.create_task(run_connection_worker_loop(), name="connection_worker")
    _worker_tasks["conversation"] = asyncio.create_task(run_conversation_worker_loop(), name="conversation_worker")
    _worker_tasks["connection_queue"] = asyncio.create_task(run_queue_loop(), name="connection_queue_worker")
    _worker_tasks["reply"] = asyncio.create_task(run_reply_worker_loop(), name="reply_worker")
    _worker_tasks["metrics"] = asyncio.create_task(run_metrics_worker_loop(), name="metrics_worker")

    _workers_running = True
    logger.info("✅ All workers running (next runs according to configured delays)")

    # Note: Workers running in background, no await here
    # Use stop_all_workers() to cancel them

async def start_worker(worker_name: str) -> bool:
    """
    Démarre un worker spécifique.

    Args:
        worker_name: Nom du worker (action_executor, connection, conversation, connection_queue, reply, metrics)

    Returns:
        bool: True si le worker a été démarré, False si déjà actif
    """
    global _worker_tasks, _workers_running

    # Vérifier si le worker existe déjà et est actif
    if is_worker_running(worker_name):
        logger.warning(f"Worker '{worker_name}' already running")
        return False

    # Mapping worker_name -> fonction de loop
    worker_loops = {
        "action_executor": run_queue_worker_loop,
        "connection": run_connection_worker_loop,
        "conversation": run_conversation_worker_loop,
        "connection_queue": run_queue_loop,
        "reply": run_reply_worker_loop,
        "metrics": run_metrics_worker_loop,
    }

    if worker_name not in worker_loops:
        logger.error(f"Unknown worker name: {worker_name}")
        return False

    # Créer et lancer la tâche
    _worker_tasks[worker_name] = asyncio.create_task(
        worker_loops[worker_name](),
        name=f"{worker_name}_worker"
    )

    _workers_running = True
    logger.info(f"✅ Worker '{worker_name}' started")
    return True

if __name__ == "__main__":
    """
    Permet de lancer les workers en tant que processus séparé:

    python -m app.core.utils.scheduler
    """
    async def run_standalone():
        logger.info("Starting workers as standalone process")
        await start_all_workers()
        # Keep process alive while workers run
        try:
            while _workers_running:
                await asyncio.sleep(60)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
            stop_all_workers()

    asyncio.run(run_standalone())
