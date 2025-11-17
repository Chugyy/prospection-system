#!/usr/bin/env python3
# app/api/routes/connections.py

from fastapi import APIRouter, HTTPException
from config.logger import logger
from app.database import crud
from app.api.models import ConnectionCreate, ConnectionUpdate
from app.core.handler.connection import send_connection_request, accept_connection_request

router = APIRouter(prefix="/connections", tags=["connections"])

@router.post("/send")
async def send_connection(connection_data: ConnectionCreate):
    """Envoie une demande de connexion (mocké)."""
    try:
        # CRUD: créer la connexion
        connection_id = await crud.create_connection(
            prospect_id=connection_data.prospect_id,
            account_id=connection_data.account_id,
            initiated_by=connection_data.initiated_by
        )

        # Business logic (mocké)
        result = await send_connection_request(
            prospect_id=connection_data.prospect_id,
            account_id=connection_data.account_id
        )

        await crud.create_log(
            action='connection_sent',
            source='user',
            account_id=connection_data.account_id,
            prospect_id=connection_data.prospect_id,
            entity_type='connection',
            entity_id=connection_id,
            status='success',
            details=result
        )

        return {"status": "success", "connection_id": connection_id, "result": result}
    except Exception as e:
        logger.error(f"Error sending connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/accept")
async def accept_connection(connection_data: ConnectionCreate):
    """Accepte une demande de connexion (mocké)."""
    try:
        # CRUD: créer la connexion
        connection_id = await crud.create_connection(
            prospect_id=connection_data.prospect_id,
            account_id=connection_data.account_id,
            initiated_by=connection_data.initiated_by
        )

        # Business logic (mocké)
        result = await accept_connection_request(
            prospect_id=connection_data.prospect_id,
            account_id=connection_data.account_id
        )

        await crud.create_log(
            action='connection_accepted',
            source='system',
            account_id=connection_data.account_id,
            prospect_id=connection_data.prospect_id,
            entity_type='connection',
            entity_id=connection_id,
            status='success',
            details=result
        )

        return {"status": "success", "connection_id": connection_id, "result": result}
    except Exception as e:
        logger.error(f"Error accepting connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{connection_id}/status")
async def update_connection_status(connection_id: int, connection_data: ConnectionUpdate):
    """Met à jour le statut d'une connexion."""
    try:
        success = await crud.update_connection(
            connection_id=connection_id,
            status=connection_data.status,
            connection_date=str(connection_data.connection_date) if connection_data.connection_date else None
        )
        if not success:
            raise HTTPException(status_code=404, detail="Connection not found")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating connection: {e}")
        raise HTTPException(status_code=500, detail=str(e))
