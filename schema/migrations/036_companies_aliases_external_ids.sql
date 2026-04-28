-- Migration 036: companies aliases + external_ids + lei + parent_company_id
--
-- SPEC-016 §7 swimlane A1, task A1.1.
--
-- Extends `companies` with the CI-relevant identity fields catalog/intel
-- both depend on. The previous schema had `cik`, `ticker`, `name`, but
-- could not represent:
--   1. Multiple aliases per company (legal name vs common name vs ticker form)
--   2. Vendor IDs from Tier 3 sources (Cortellis, Pitchbook, openFDA labeler, …)
--   3. Corporate hierarchy (parent_company_id self-FK)
--   4. Cross-jurisdictional identity (LEI for non-US filers)
--
-- All additions are idempotent (IF NOT EXISTS) so re-running is safe.

BEGIN;

-- ============================================================
-- New columns
-- ============================================================

ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS aliases JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN companies.aliases IS
    'Array of normalised name forms — legal name, common name, ticker form, '
    'historical names. Used by entity_resolver alias cascade. Curated by '
    'integration/company_identity.merge_aliases().';

ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS external_ids JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN companies.external_ids IS
    'Bag of vendor + canonical IDs: cik, lei, duns, isin, openfda_labeler_codes, '
    'cortellis_id, pitchbook_id, gleif_lei, etc. Each key may carry a sibling '
    '_source_<key> recording which connector last wrote the value, used for '
    'authority-based conflict resolution by '
    'integration/company_identity.merge_external_ids().';

ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS lei TEXT;

COMMENT ON COLUMN companies.lei IS
    'Legal Entity Identifier (ISO 17442). Top-level for join-friendliness; '
    'mirrored in external_ids.lei. NULL for non-LEI-registered entities.';

ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS parent_company_id UUID REFERENCES companies(id);

COMMENT ON COLUMN companies.parent_company_id IS
    'Self-FK for corporate hierarchy. NULL for top-level entities. When a '
    'subsidiary is acquired, its parent_company_id is updated and the prior '
    'parent ends up in the merge audit log (existing entity_consolidator).';

-- ============================================================
-- Indexes
-- ============================================================

-- GIN on aliases for fast jsonb @> '"some_alias"'::jsonb containment
CREATE INDEX IF NOT EXISTS idx_companies_aliases
    ON companies USING GIN (aliases);

-- GIN on external_ids for fast lookup-by-vendor-id
-- (e.g. external_ids @> '{"cik": "0000078003"}')
CREATE INDEX IF NOT EXISTS idx_companies_external_ids
    ON companies USING GIN (external_ids);

-- Btree on lei (sparse — many NULLs; partial index)
CREATE UNIQUE INDEX IF NOT EXISTS idx_companies_lei
    ON companies (lei)
    WHERE lei IS NOT NULL;

-- Btree on parent_company_id for hierarchy walks
CREATE INDEX IF NOT EXISTS idx_companies_parent
    ON companies (parent_company_id)
    WHERE parent_company_id IS NOT NULL;

-- ============================================================
-- Backfill existing aliases from entity_aliases table
-- (safe: only INSERTs into the new aliases column for rows where it's empty)
-- ============================================================

-- Only attempt backfill if entity_aliases table exists (defensive)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.tables WHERE table_name = 'entity_aliases'
    ) THEN
        UPDATE companies c
        SET aliases = COALESCE(
            (
                SELECT jsonb_agg(DISTINCT ea.alias)
                FROM entity_aliases ea
                WHERE ea.entity_type = 'company'
                  AND ea.entity_id = c.id::text
            ),
            '[]'::jsonb
        )
        WHERE jsonb_array_length(c.aliases) = 0;
    END IF;
END $$;

-- Backfill external_ids.cik from existing companies.cik column for traceability
UPDATE companies
SET external_ids = jsonb_set(
    COALESCE(external_ids, '{}'::jsonb),
    '{cik}',
    to_jsonb(cik)
)
WHERE cik IS NOT NULL
  AND NOT (external_ids ? 'cik');

COMMIT;
