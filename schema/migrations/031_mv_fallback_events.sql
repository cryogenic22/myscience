-- Migration 031: Materialized view fallback tracking
-- Records when MV queries fall back to realtime SQL so we can detect stale MVs.

CREATE TABLE IF NOT EXISTS mv_fallback_events (
    id SERIAL PRIMARY KEY,
    method_name VARCHAR(100) NOT NULL,
    mv_name VARCHAR(100) NOT NULL,
    reason VARCHAR(50) NOT NULL DEFAULT 'insufficient_data',
    row_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_mvfe_created ON mv_fallback_events(created_at);
CREATE INDEX IF NOT EXISTS idx_mvfe_mv_name ON mv_fallback_events(mv_name);
