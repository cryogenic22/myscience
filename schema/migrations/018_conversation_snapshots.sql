-- Migration 018: Conversation memory snapshots
-- Persists ConversationMemory state (exchanges + entity counts) to PostgreSQL
-- so sessions survive API restarts.

CREATE TABLE IF NOT EXISTS conversation_snapshots (
    session_id VARCHAR(255) PRIMARY KEY,
    snapshot JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
