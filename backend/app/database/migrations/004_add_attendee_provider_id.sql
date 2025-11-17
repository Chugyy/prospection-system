-- Migration: Ajout de attendee_provider_id pour matching avec messages Unipile
-- Date: 2025-11-17

ALTER TABLE prospects
ADD COLUMN IF NOT EXISTS attendee_provider_id VARCHAR(255);

-- Index pour recherche rapide par attendee_provider_id
CREATE INDEX IF NOT EXISTS idx_prospects_attendee_provider_id
ON prospects(attendee_provider_id)
WHERE attendee_provider_id IS NOT NULL;

-- Commentaire
COMMENT ON COLUMN prospects.attendee_provider_id IS 'ID provider Unipile (format long ACoAAG...) pour matching avec messages';
