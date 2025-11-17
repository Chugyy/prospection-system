#!/usr/bin/env python3
# app/api/routes/accounts.py

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
from config.logger import logger
from app.database import crud
from app.api.models import AccountCreate, AccountUpdate

router = APIRouter(prefix="/accounts", tags=["accounts"])

@router.post("")
async def create_account(account_data: AccountCreate, user_id: int):
    """Crée un nouveau compte LinkedIn."""
    try:
        account_id = await crud.create_account(
            user_id=user_id,
            unipile_account_id=account_data.unipile_account_id,
            linkedin_url=account_data.linkedin_url,
            first_name=account_data.first_name or '',
            last_name=account_data.last_name or '',
            headline=account_data.headline or '',
            company=account_data.company or ''
        )
        await crud.create_log(
            action='account_created',
            source='user',
            user_id=user_id,
            entity_type='account',
            entity_id=account_id,
            status='success'
        )
        return {"status": "success", "account_id": account_id}
    except Exception as e:
        logger.error(f"Error creating account: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("")
async def list_accounts(user_id: int):
    """Liste tous les comptes d'un utilisateur."""
    try:
        accounts = await crud.list_accounts(user_id)
        return {"status": "success", "accounts": accounts}
    except Exception as e:
        logger.error(f"Error listing accounts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{account_id}")
async def get_account(account_id: int):
    """Récupère un compte spécifique."""
    try:
        account = await crud.get_account(account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Account not found")
        return {"status": "success", "account": account}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting account: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{account_id}")
async def update_account(account_id: int, account_data: AccountUpdate):
    """Met à jour un compte."""
    try:
        update_fields = {k: v for k, v in account_data.dict(exclude_unset=True).items() if v is not None}
        success = await crud.update_account(account_id, **update_fields)
        if not success:
            raise HTTPException(status_code=404, detail="Account not found")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating account: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{account_id}")
async def delete_account(account_id: int):
    """Supprime un compte."""
    try:
        success = await crud.delete_account(account_id)
        if not success:
            raise HTTPException(status_code=404, detail="Account not found")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting account: {e}")
        raise HTTPException(status_code=500, detail=str(e))
