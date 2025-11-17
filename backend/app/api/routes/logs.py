#!/usr/bin/env python3
# app/api/routes/logs.py

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from config.logger import logger
from app.database import crud
from app.api.models import LogApprove
from app.core.utils.log import execute_approved_log

router = APIRouter(prefix="/logs", tags=["logs"])

@router.get("")
async def list_logs(
    validation_status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None)
):
    """Liste tous les logs avec filtres optionnels."""
    try:
        logs = await crud.list_logs(
            validation_status=validation_status,
            source=source,
            action=action,
            user_id=user_id
        )
        return {"status": "success", "logs": logs}
    except Exception as e:
        logger.error(f"Error listing logs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{log_id}")
async def get_log(log_id: int):
    """Récupère un log spécifique."""
    try:
        log = await crud.get_log(log_id)
        if not log:
            raise HTTPException(status_code=404, detail="Log not found")
        return {"status": "success", "log": log}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting log: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{log_id}/approve")
async def approve_log(log_id: int, approval_data: LogApprove):
    """Approuve ou rejette un log."""
    try:
        success = await crud.update_log_validation(log_id, approval_data.validation_status)
        if not success:
            raise HTTPException(status_code=404, detail="Log not found")

        # Si approuvé, exécuter (mocké)
        if approval_data.validation_status == 'approved':
            result = await execute_approved_log(log_id)
            await crud.mark_log_executed(log_id)
            return {"status": "success", "executed": True, "result": result}

        return {"status": "success", "executed": False}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving log: {e}")
        raise HTTPException(status_code=500, detail=str(e))
