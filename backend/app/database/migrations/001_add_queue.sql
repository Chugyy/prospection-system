-- Migration: Ajout de la table queue générique
-- Date: 2025-11-11

CREATE TABLE IF NOT EXISTS queue (
    id SERIAL PRIMARY KEY,

    -- Type de tâche (extensible)
    type VARCHAR(100) NOT NULL,

    -- État
    status VARCHAR(50) DEFAULT 'pending',
    priority INT DEFAULT 5,

    -- Entités liées
    account_id INT REFERENCES accounts(id),
    prospect_id INT,

    -- Données spécifiques (JSON flexible)
    payload JSONB NOT NULL,

    -- Résultat après exécution
    result JSONB,
    error TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    scheduled_at TIMESTAMP DEFAULT NOW(),
    started_at TIMESTAMP,
    completed_at TIMESTAMP,

    -- Retry logic
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 3
);

-- Index pour performance
CREATE INDEX idx_queue_status_priority ON queue(status, priority ASC, scheduled_at ASC);
CREATE INDEX idx_queue_type ON queue(type, status);

-- Commentaires
COMMENT ON TABLE queue IS 'Queue générique pour toutes les tâches asynchrones';
COMMENT ON COLUMN queue.type IS 'Type de tâche: process_connection, send_message, analyze_conversation, etc.';
COMMENT ON COLUMN queue.priority IS '1 = haute priorité, 10 = basse priorité';
COMMENT ON COLUMN queue.payload IS 'Données JSON spécifiques à chaque type de tâche';
