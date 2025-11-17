#!/usr/bin/env python3
# app/api/routes/workflow.py

from fastapi import APIRouter, Depends, HTTPException
from config.logger import logger
from app.api.routes.auth import get_current_user
from app.core.utils.scheduler import (
    start_all_workers,
    is_workflow_running,
    stop_all_workers,
    start_worker,
    stop_worker,
    is_worker_running,
    get_workers_status
)

router = APIRouter(prefix="/workflow", tags=["workflow"])

VALID_WORKERS = ["followup", "connection", "conversation", "queue", "reply"]

@router.post("/start")
async def start_workflow(current_user: dict = Depends(get_current_user)):
    """
    Démarre le workflow de prospection (tous les workers).

    Nécessite authentification.
    """
    import asyncio

    if is_workflow_running():
        return {"status": "success", "message": "Workflow already running"}

    try:
        # Launch workers in background without blocking HTTP response
        asyncio.create_task(start_all_workers())
        logger.info(f"Workflow started by user {current_user['id']}")
        return {"status": "success", "message": "Workflow started"}
    except Exception as e:
        logger.error(f"Failed to start workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop")
async def stop_workflow(current_user: dict = Depends(get_current_user)):
    """
    Arrête le workflow de prospection (tous les workers).

    Nécessite authentification.
    """
    if not is_workflow_running():
        return {"status": "success", "message": "Workflow already stopped"}

    try:
        stop_all_workers()
        logger.info(f"Workflow stopped by user {current_user['id']}")
        return {"status": "success", "message": "Workflow stopped"}
    except Exception as e:
        logger.error(f"Failed to stop workflow: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status")
async def workflow_status(current_user: dict = Depends(get_current_user)):
    """
    Retourne le statut actuel du workflow et de tous les workers.

    Nécessite authentification.
    """
    running = is_workflow_running()
    workers = get_workers_status()

    return {
        "running": running,
        "status": "active" if running else "stopped",
        "workers": workers
    }

@router.post("/start/{worker_name}")
async def start_specific_worker(worker_name: str, current_user: dict = Depends(get_current_user)):
    """
    Démarre un worker spécifique.

    Nécessite authentification.
    """
    if worker_name not in VALID_WORKERS:
        raise HTTPException(status_code=400, detail=f"Invalid worker name. Valid: {VALID_WORKERS}")

    try:
        import asyncio
        success = await start_worker(worker_name)

        if success:
            logger.info(f"Worker '{worker_name}' started by user {current_user['id']}")
            return {"status": "success", "message": f"Worker '{worker_name}' started"}
        else:
            return {"status": "success", "message": f"Worker '{worker_name}' already running"}

    except Exception as e:
        logger.error(f"Failed to start worker '{worker_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/stop/{worker_name}")
async def stop_specific_worker(worker_name: str, current_user: dict = Depends(get_current_user)):
    """
    Arrête un worker spécifique.

    Nécessite authentification.
    """
    if worker_name not in VALID_WORKERS:
        raise HTTPException(status_code=400, detail=f"Invalid worker name. Valid: {VALID_WORKERS}")

    try:
        success = stop_worker(worker_name)

        if success:
            logger.info(f"Worker '{worker_name}' stopped by user {current_user['id']}")
            return {"status": "success", "message": f"Worker '{worker_name}' stopped"}
        else:
            return {"status": "success", "message": f"Worker '{worker_name}' not running"}

    except Exception as e:
        logger.error(f"Failed to stop worker '{worker_name}': {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/status/{worker_name}")
async def get_worker_status(worker_name: str, current_user: dict = Depends(get_current_user)):
    """
    Retourne le statut d'un worker spécifique.

    Nécessite authentification.
    """
    if worker_name not in VALID_WORKERS:
        raise HTTPException(status_code=400, detail=f"Invalid worker name. Valid: {VALID_WORKERS}")

    running = is_worker_running(worker_name)
    return {
        "worker": worker_name,
        "running": running,
        "status": "active" if running else "stopped"
    }

@router.delete("/cleanup")
async def cleanup_today_data(current_user: dict = Depends(get_current_user)):
    """
    Supprime les messages et logs du jour.

    Nécessite authentification.
    """
    from app.database import crud

    try:
        deleted_messages = await crud.delete_today_messages()
        deleted_logs = await crud.delete_today_logs()

        logger.info(f"Cleanup by user {current_user['id']}: {deleted_messages} messages, {deleted_logs} logs")
        return {
            "status": "success",
            "deleted_messages": deleted_messages,
            "deleted_logs": deleted_logs
        }
    except Exception as e:
        logger.error(f"Failed to cleanup: {e}")
        raise HTTPException(status_code=500, detail=str(e))
