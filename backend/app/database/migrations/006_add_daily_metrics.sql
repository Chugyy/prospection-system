-- Migration: Ajout de la table daily_metrics
-- Date: 2025-11-18

CREATE TABLE IF NOT EXISTS daily_metrics (
    id SERIAL PRIMARY KEY,
    date DATE UNIQUE NOT NULL,
    messages_sent INT DEFAULT 0,
    responses_received INT DEFAULT 0,
    calls_scheduled INT DEFAULT 0,
    prospects_archived INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_daily_metrics_date ON daily_metrics(date DESC);

COMMENT ON TABLE daily_metrics IS 'Métriques journalières du système de prospection';
COMMENT ON COLUMN daily_metrics.messages_sent IS 'Nombre de messages envoyés (via logs)';
COMMENT ON COLUMN daily_metrics.responses_received IS 'Nombre de réponses reçues des prospects';
COMMENT ON COLUMN daily_metrics.calls_scheduled IS 'Nombre de messages avec liens meet/calendly ou dates';
COMMENT ON COLUMN daily_metrics.prospects_archived IS 'Nombre de prospects archivés (closed)';
