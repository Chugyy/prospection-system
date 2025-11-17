#!/usr/bin/env python3
# app/api/routes/prospects.py

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from config.logger import logger
from app.database import crud
from app.api.models import ProspectCreate, ProspectUpdate

router = APIRouter(prefix="/prospects", tags=["prospects"])

@router.post("")
async def create_prospect(prospect_data: ProspectCreate):
    """Crée un nouveau prospect."""
    try:
        prospect_id = await crud.create_prospect(
            account_id=prospect_data.account_id,
            linkedin_url=prospect_data.linkedin_url,
            first_name=prospect_data.first_name or '',
            last_name=prospect_data.last_name or '',
            company=prospect_data.company or '',
            job_title=prospect_data.job_title or '',
            avatar_match=prospect_data.avatar_match or False
        )
        await crud.create_log(
            action='prospect_created',
            source='user',
            account_id=prospect_data.account_id,
            entity_type='prospect',
            entity_id=prospect_id,
            status='success'
        )
        return {"status": "success", "prospect_id": prospect_id}
    except Exception as e:
        logger.error(f"Error creating prospect: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("")
async def list_prospects(account_id: Optional[int] = Query(None), status: Optional[str] = Query(None)):
    """Liste tous les prospects avec filtres optionnels."""
    try:
        prospects = await crud.list_prospects(account_id=account_id, status=status)
        return {"status": "success", "prospects": prospects}
    except Exception as e:
        logger.error(f"Error listing prospects: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{prospect_id}")
async def get_prospect(prospect_id: int):
    """Récupère un prospect spécifique."""
    try:
        prospect = await crud.get_prospect(prospect_id)
        if not prospect:
            raise HTTPException(status_code=404, detail="Prospect not found")
        return {"status": "success", "prospect": prospect}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting prospect: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{prospect_id}")
async def update_prospect(prospect_id: int, prospect_data: ProspectUpdate):
    """Met à jour un prospect."""
    try:
        update_fields = {k: v for k, v in prospect_data.dict(exclude_unset=True).items() if v is not None}
        success = await crud.update_prospect(prospect_id, **update_fields)
        if not success:
            raise HTTPException(status_code=404, detail="Prospect not found")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating prospect: {e}")
        raise HTTPException(status_code=500, detail=str(e))
