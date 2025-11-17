-- Migration: Enrichissement système de validation
-- Date: 2025-11-15
-- Description: Ajoute colonnes validation + tracking rejets prospects

-- 1. Enrichir table logs
ALTER TABLE logs
ADD COLUMN IF NOT EXISTS validated_by INTEGER REFERENCES users(id),
ADD COLUMN IF NOT EXISTS validated_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS validation_feedback TEXT,
ADD COLUMN IF NOT EXISTS rejection_reason TEXT,
ADD COLUMN IF NOT EXISTS rejection_category VARCHAR(50) CHECK (rejection_category IN ('tone', 'timing', 'content', 'irrelevant', 'other'));

-- Index pour performances
CREATE INDEX IF NOT EXISTS idx_logs_validated_by ON logs(validated_by);
CREATE INDEX IF NOT EXISTS idx_logs_validated_at ON logs(validated_at);
CREATE INDEX IF NOT EXISTS idx_logs_rejection_category ON logs(rejection_category);

-- 2. Enrichir table prospects
ALTER TABLE prospects
ADD COLUMN IF NOT EXISTS rejection_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_rejection_at TIMESTAMP,
ADD COLUMN IF NOT EXISTS closed_reason TEXT,
ADD COLUMN IF NOT EXISTS closed_at TIMESTAMP;

CREATE INDEX IF NOT EXISTS idx_prospects_status ON prospects(status);
CREATE INDEX IF NOT EXISTS idx_prospects_rejection_count ON prospects(rejection_count);

COMMENT ON COLUMN logs.validated_by IS 'User ID qui a validé/rejeté';
COMMENT ON COLUMN logs.validation_feedback IS 'Feedback optionnel lors validation';
COMMENT ON COLUMN logs.rejection_reason IS 'Raison du rejet (obligatoire si rejected)';
COMMENT ON COLUMN logs.rejection_category IS 'Catégorie du rejet pour analytics';

COMMENT ON COLUMN prospects.rejection_count IS 'Nombre de validations rejetées';
COMMENT ON COLUMN prospects.closed_reason IS 'Raison de clôture (ex: trop de rejets)';
