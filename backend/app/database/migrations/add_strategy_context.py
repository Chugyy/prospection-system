#!/usr/bin/env python3
"""
Migration: Add strategy_context column to messages table.
Stores LLM2 strategic analysis JSON for conversation continuity.
"""
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import asyncio
from app.database.db import get_async_db_connection


async def migrate():
    """Add strategy_context column to messages table."""
    conn = await get_async_db_connection()

    try:
        print("🔄 Adding strategy_context column to messages table...")

        # Add column if not exists
        await conn.execute("""
            ALTER TABLE messages
            ADD COLUMN IF NOT EXISTS strategy_context JSONB
        """)

        print("✅ Migration completed successfully!")
        print("   - Added column: messages.strategy_context (JSONB)")

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        raise
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(migrate())
