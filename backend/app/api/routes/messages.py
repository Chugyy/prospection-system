#!/usr/bin/env python3
# app/api/routes/messages.py

from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from config.logger import logger
from app.database import crud
from app.api.models import MessageCreate
from app.core.handler.message import send_message_via_unipile, generate_llm_reply

router = APIRouter(prefix="/messages", tags=["messages"])

@router.post("/send")
async def send_message(message_data: MessageCreate):
    """Envoie un message (mocké)."""
    try:
        # CRUD: créer le message
        message_id = await crud.create_message(
            prospect_id=message_data.prospect_id,
            account_id=message_data.account_id,
            sent_by=message_data.sent_by,
            content=message_data.content,
            message_type=message_data.message_type
        )

        # Business logic (mocké)
        result = await send_message_via_unipile(
            prospect_id=message_data.prospect_id,
            account_id=message_data.account_id,
            content=message_data.content
        )

        await crud.create_log(
            action='message_sent',
            source='user',
            account_id=message_data.account_id,
            prospect_id=message_data.prospect_id,
            entity_type='message',
            entity_id=message_id,
            status='success',
            details=result
        )

        return {"status": "success", "message_id": message_id, "result": result}
    except Exception as e:
        logger.error(f"Error sending message: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("")
async def list_messages(prospect_id: int = Query(...)):
    """Liste tous les messages d'un prospect."""
    try:
        messages = await crud.list_messages(prospect_id)
        return {"status": "success", "messages": messages}
    except Exception as e:
        logger.error(f"Error listing messages: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/llm-reply")
async def llm_reply(prospect_id: int):
    """Génère une réponse via LLM (mocké)."""
    try:
        # Business logic (mocké)
        result = await generate_llm_reply(prospect_id)

        await crud.create_log(
            action='llm_reply_generated',
            source='llm',
            prospect_id=prospect_id,
            requires_validation=True,
            validation_status='pending',
            status='success',
            payload=result
        )

        return {"status": "success", "result": result}
    except Exception as e:
        logger.error(f"Error generating LLM reply: {e}")
        raise HTTPException(status_code=500, detail=str(e))
