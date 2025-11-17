import logging
from fastapi import APIRouter, Request, HTTPException
from app.database.db import get_async_db_connection

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

    conn = await get_async_db_connection()
    try:
        await conn.execute(
            "INSERT INTO webhook_logs (payload) VALUES ($1)",
            payload
        )
        logger.info("Webhook logged")
    finally:
        await conn.close()

    return {"status": "ok"}


