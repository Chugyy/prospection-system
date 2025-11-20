-- Migration: Add 'reply' to message_type constraint
-- Date: 2025-11-20
-- Description: Aligns database constraint with code to allow 'reply' message type

ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_message_type_check;
ALTER TABLE messages ADD CONSTRAINT messages_message_type_check
  CHECK (message_type IN ('first_contact', 'followup', 'llm_reply', 'manual', 'reply'));
