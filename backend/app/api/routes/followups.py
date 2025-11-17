#!/usr/bin/env python3
# app/api/routes/followups.py

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from config.logger import logger
from app.database import crud
from app.api.models import FollowupCreate, FollowupUpdate

router = APIRouter(prefix="/followups", tags=["followups"])

@router.get("")
async def list_followups(status: Optional[str] = Query(None), followup_type: Optional[str] = Query(None)):
    """Liste tous les followups avec filtres optionnels."""
    try:
        followups = await crud.list_followups(status=status, followup_type=followup_type)
        return {"status": "success", "followups": followups}
    except Exception as e:
        logger.error(f"Error listing followups: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/schedule")
async def schedule_followup(followup_data: FollowupCreate):
    """Crée un followup manuel."""
    try:
        followup_id = await crud.create_followup(
            prospect_id=followup_data.prospect_id,
            account_id=followup_data.account_id,
            followup_type=followup_data.followup_type,
            scheduled_at=str(followup_data.scheduled_at),
            content=followup_data.content
        )
        await crud.create_log(
            action='followup_scheduled',
            source='user',
            account_id=followup_data.account_id,
            prospect_id=followup_data.prospect_id,
            entity_type='followup',
            entity_id=followup_id,
            status='success'
        )
        return {"status": "success", "followup_id": followup_id}
    except Exception as e:
        logger.error(f"Error scheduling followup: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{followup_id}/cancel")
async def cancel_followup(followup_id: int):
    """Annule un followup."""
    try:
        success = await crud.update_followup_status(followup_id, 'cancelled')
        if not success:
            raise HTTPException(status_code=404, detail="Followup not found")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling followup: {e}")
        raise HTTPException(status_code=500, detail=str(e))
