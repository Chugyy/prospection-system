-- Migration: Ajout de la table webhook_logs
-- Date: 2025-11-17

CREATE TABLE IF NOT EXISTS webhook_logs (
    id SERIAL PRIMARY KEY,
    received_at TIMESTAMP DEFAULT NOW(),
    payload JSONB NOT NULL
);

CREATE INDEX idx_webhook_logs_received_at ON webhook_logs(received_at DESC);

COMMENT ON TABLE webhook_logs IS 'Log brut de tous les webhooks reçus';
