-- Migration: Ajout de unipile_message_id pour éviter doublons
-- Date: 2025-11-11

ALTER TABLE messages
ADD COLUMN IF NOT EXISTS unipile_message_id VARCHAR(255);

-- Index unique pour éviter doublons
CREATE UNIQUE INDEX IF NOT EXISTS idx_messages_unipile_id
ON messages(unipile_message_id)
WHERE unipile_message_id IS NOT NULL;

-- Commentaire
COMMENT ON COLUMN messages.unipile_message_id IS 'ID unique du message depuis Unipile pour éviter doublons lors du sync';
