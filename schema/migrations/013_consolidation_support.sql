-- Migration 013: Consolidation Support
-- Adds indexes for fast entity deduplication lookups
-- and source_authority column on companies.
--
-- Part of P0: Entity Consolidation & Retroactive Resolution Sweep

-- Index for fast drug dedup by normalized generic_name
CREATE INDEX IF NOT EXISTS idx_drugs_generic_lower
    ON drugs(LOWER(generic_name)) WHERE record_status != 'superseded';

-- Index for fast company dedup by normalized name
CREATE INDEX IF NOT EXISTS idx_companies_name_lower
    ON companies(LOWER(name)) WHERE record_status != 'superseded';

-- source_authority on companies (drugs already has it from migration 007)
ALTER TABLE companies ADD COLUMN IF NOT EXISTS source_authority TEXT;
UPDATE companies SET source_authority = source_api WHERE source_authority IS NULL;

-- Record migration (etl_runs uses source_name, not run_id)
INSERT INTO etl_runs (source_name, status, started_at, completed_at, records_processed, records_inserted, records_updated)
VALUES (
    'migration_013_consolidation_support',
    'SUCCESS',
    NOW(), NOW(), 0, 0, 0
) ON CONFLICT DO NOTHING;
