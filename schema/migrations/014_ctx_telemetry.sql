-- Migration 014: CTX Telemetry
-- Tracks per-query CTX context-building metrics for compression
-- ratio analysis, token savings, and build-time monitoring.

CREATE TABLE IF NOT EXISTS ctx_telemetry (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    question_hash VARCHAR(64),
    intent VARCHAR(50),
    ctx_tokens INTEGER,
    legacy_tokens INTEGER,
    compression_ratio REAL,
    build_time_ms REAL,
    mode VARCHAR(20),
    evidence_raw_tokens INTEGER,
    evidence_compressed_tokens INTEGER
);

CREATE INDEX IF NOT EXISTS idx_ctx_telemetry_created ON ctx_telemetry(created_at);
