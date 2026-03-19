-- Migration 012: Normalize source naming and add unresolved_entities status column
--
-- Fixes:
--   1. Inconsistent source_authority/source_api naming ('clinicaltrials_gov' → 'clinical_trials_gov')
--   2. Adds status column to unresolved_entities for batch processing workflow

-- 1. Normalize source naming in drugs table
UPDATE drugs SET source_authority = 'clinical_trials_gov' WHERE source_authority = 'clinicaltrials_gov';
UPDATE drugs SET source_api = 'clinical_trials_gov' WHERE source_api = 'clinicaltrials_gov';

-- 2. Add status column to unresolved_entities for processing workflow
ALTER TABLE unresolved_entities ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'pending';

-- Backfill status from existing resolved flag
UPDATE unresolved_entities SET status = 'resolved' WHERE resolved = TRUE AND status = 'pending';

-- Index for efficient batch queries
CREATE INDEX IF NOT EXISTS idx_unresolved_status ON unresolved_entities(status) WHERE status = 'pending';

-- Record migration
INSERT INTO etl_runs (id, source_name, api_endpoint, query_params, status, records_processed, started_at, completed_at)
VALUES (
    gen_random_uuid(),
    'migration_012',
    'schema/migrations/012_normalize_and_validate.sql',
    '{}',
    'SUCCESS',
    0,
    NOW(),
    NOW()
);
