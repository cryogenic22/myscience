-- Migration 019: Query telemetry + CTX benchmark extensions
-- Captures per-query signals for data gap detection and steward prioritization.
-- Extends ctx_telemetry with quality proxy columns for CTX benefit measurement.

CREATE TABLE IF NOT EXISTS query_telemetry (
    id SERIAL PRIMARY KEY,
    session_id VARCHAR(255),
    question_hash VARCHAR(64) NOT NULL,
    question_text TEXT,
    intent VARCHAR(50),
    entities_requested TEXT[],
    entities_found TEXT[],
    confidence REAL,
    evidence_count INTEGER DEFAULT 0,
    sources_used TEXT[],
    response_latency_ms REAL,
    gap_type VARCHAR(50),
    gap_details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_qt_created ON query_telemetry(created_at);
CREATE INDEX IF NOT EXISTS idx_qt_gap_type ON query_telemetry(gap_type) WHERE gap_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_qt_question_hash ON query_telemetry(question_hash);
CREATE INDEX IF NOT EXISTS idx_qt_entities_requested ON query_telemetry USING GIN(entities_requested);

-- Extend ctx_telemetry with quality proxy columns for CTX benefit measurement
ALTER TABLE ctx_telemetry ADD COLUMN IF NOT EXISTS answer_quality_proxy REAL;
ALTER TABLE ctx_telemetry ADD COLUMN IF NOT EXISTS query_complexity INTEGER;
ALTER TABLE ctx_telemetry ADD COLUMN IF NOT EXISTS entity_count INTEGER;
ALTER TABLE ctx_telemetry ADD COLUMN IF NOT EXISTS hop_depth INTEGER;
