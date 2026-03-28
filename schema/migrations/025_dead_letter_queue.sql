-- Migration 025: Dead-letter queue for failed pipeline records
-- Per lead assessment: failed records should be persisted for retry,
-- not just logged as errors.

CREATE TABLE IF NOT EXISTS failed_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    etl_run_id TEXT,
    source_type TEXT NOT NULL,
    external_id TEXT,
    record_type TEXT,
    error_message TEXT NOT NULL,
    error_traceback TEXT,
    raw_payload JSONB,
    provenance JSONB,
    retry_count INT DEFAULT 0,
    max_retries INT DEFAULT 3,
    status TEXT DEFAULT 'pending',  -- pending, retried, resolved, ignored
    created_at TIMESTAMPTZ DEFAULT NOW(),
    resolved_at TIMESTAMPTZ,
    resolution_notes TEXT
);

CREATE INDEX IF NOT EXISTS idx_failed_records_source ON failed_records(source_type);
CREATE INDEX IF NOT EXISTS idx_failed_records_status ON failed_records(status);
CREATE INDEX IF NOT EXISTS idx_failed_records_created ON failed_records(created_at DESC);
