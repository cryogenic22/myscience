-- 007_resolution_overhaul.sql
-- Entity resolution overhaul: traceability, TEXT IDs for entity_links,
-- source_authority tracking for drugs.

-- 1. Change entity_links ID columns from UUID to TEXT.
--    Existing UUID values are valid TEXT strings, so this is backward-compatible.
--    This unblocks linking clinical_trials (TEXT NCT IDs) into the graph.
ALTER TABLE entity_links ALTER COLUMN source_entity_id TYPE TEXT;
ALTER TABLE entity_links ALTER COLUMN target_entity_id TYPE TEXT;

-- Recreate the unique index (type changed)
DROP INDEX IF EXISTS idx_links_unique;
CREATE UNIQUE INDEX idx_links_unique ON entity_links(source_entity_id, target_entity_id, link_type);

-- 2. Resolution audit table: every entity resolution decision is logged here.
CREATE TABLE IF NOT EXISTS resolution_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_value TEXT NOT NULL,
    entity_type TEXT NOT NULL,                -- drug, company, investigator, etc.
    resolved_entity_id TEXT,                  -- what it resolved to (NULL if unresolved)
    resolution_method TEXT NOT NULL,          -- exact_id, alias, fuzzy, embedding, llm, auto_create
    confidence FLOAT NOT NULL,
    reasoning TEXT,                           -- human-readable explanation of why this match was chosen
    candidates_considered JSONB,              -- [{id, name, score, method}...]
    source_type TEXT NOT NULL,                -- which connector triggered this
    source_record_id TEXT,                    -- external_id of the triggering record
    accepted BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_audit_entity ON resolution_audit(entity_type, resolved_entity_id);
CREATE INDEX idx_audit_method ON resolution_audit(resolution_method);
CREATE INDEX idx_audit_source ON resolution_audit(source_type);
CREATE INDEX idx_audit_created ON resolution_audit(created_at DESC);
CREATE INDEX idx_audit_unresolved ON resolution_audit(entity_type) WHERE resolved_entity_id IS NULL;

-- 3. Track provenance authority on drugs: FDA-authoritative vs auto-created
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS source_authority TEXT DEFAULT 'fda_orange_book';
-- Values: 'fda_orange_book', 'clinicaltrials_gov', 'pubmed', 'manual'

-- 4. Unique CIK on companies (prevents CIK collision during EDGAR upsert)
-- First clean up: if any CIK dupes exist, null out the later ones
DO $$
DECLARE
    rec RECORD;
BEGIN
    FOR rec IN
        SELECT cik, array_agg(id ORDER BY created_at) as ids
        FROM companies
        WHERE cik IS NOT NULL
        GROUP BY cik
        HAVING count(*) > 1
    LOOP
        -- Keep first, null out rest
        UPDATE companies SET cik = NULL WHERE id = ANY(rec.ids[2:]);
    END LOOP;
END $$;

CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_cik_unique
    ON companies(cik) WHERE cik IS NOT NULL;

-- 5. Extend unresolved_entities with LLM analysis fields
ALTER TABLE unresolved_entities ADD COLUMN IF NOT EXISTS llm_analysis TEXT;
ALTER TABLE unresolved_entities ADD COLUMN IF NOT EXISTS llm_confidence FLOAT;
ALTER TABLE unresolved_entities ADD COLUMN IF NOT EXISTS resolution_method TEXT;
ALTER TABLE unresolved_entities ADD COLUMN IF NOT EXISTS candidates_considered JSONB;

-- Record migration
INSERT INTO etl_runs (id, source_name, api_endpoint, query_params, status, records_processed, started_at, completed_at)
VALUES (gen_random_uuid(), 'migration_007', 'schema/migrations/007_resolution_overhaul.sql',
        '{"description": "Entity resolution overhaul"}'::jsonb, 'SUCCESS', 0, NOW(), NOW());
