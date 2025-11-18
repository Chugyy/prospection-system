import logging
import json
from fastapi import APIRouter, Request, HTTPException
from app.database.db import get_async_db_connection
from config.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/webhook/unipile")
async def unipile_webhook(request: Request):
    """Log all incoming webhooks to webhook_logs table"""
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Invalid JSON: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # Filter by account_id - only process events for our configured account
    account_id = payload.get("account_id")
    if account_id != settings.UNIPILE_ACCOUNT_ID:
        logger.debug(f"Ignoring webhook for different account: {account_id}")
        return {"status": "ignored", "reason": "different_account"}

    conn = await get_async_db_connection()
    try:
        await conn.execute(
            "INSERT INTO webhook_logs (payload) VALUES ($1)",
            json.dumps(payload)
        )
        logger.info(f"Webhook logged for account {account_id}, event: {payload.get('event')}")
    finally:
        await conn.close()

    return {"status": "ok"}


