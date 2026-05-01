-- Migration 041: extend patents table with USPTO PatentsView columns
--
-- SPEC-016 §7 swimlane A1, task A1.5.
--
-- The `patents` table was created by migration 006 with a drug-centric
-- schema (drug_id, patent_number, patent_expiry_date, patent_type,
-- applicant_holder). This migration ADDS the columns the USPTO
-- PatentsView connector (A5.1) needs:
--   - patent_office, assignee_company_id, assignee_name_raw
--   - filing_date, grant_date, expiration_date, priority_date
--   - cpc_codes, status, title, abstract, updated_at
--
-- All additions use ADD COLUMN IF NOT EXISTS so re-running is safe.
-- CHECK constraints are intentionally skipped: existing rows use the
-- legacy vocabulary ("Drug Substance", "Drug Product", "Method of Use")
-- which would violate any new check on patent_type/status. The connector
-- writes the new vocabulary; legacy values can be migrated separately.

BEGIN;

-- ============================================================
-- Ensure base table exists (no-op if migration 006 already ran)
-- ============================================================

CREATE TABLE IF NOT EXISTS patents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    patent_number TEXT NOT NULL
);

-- ============================================================
-- Add USPTO PatentsView columns
-- ============================================================

ALTER TABLE patents ADD COLUMN IF NOT EXISTS patent_office TEXT NOT NULL DEFAULT 'USPTO';
ALTER TABLE patents ADD COLUMN IF NOT EXISTS assignee_company_id UUID REFERENCES companies(id);
ALTER TABLE patents ADD COLUMN IF NOT EXISTS assignee_name_raw TEXT;
ALTER TABLE patents ADD COLUMN IF NOT EXISTS filing_date DATE;
ALTER TABLE patents ADD COLUMN IF NOT EXISTS grant_date DATE;
ALTER TABLE patents ADD COLUMN IF NOT EXISTS expiration_date DATE;
ALTER TABLE patents ADD COLUMN IF NOT EXISTS priority_date DATE;
ALTER TABLE patents ADD COLUMN IF NOT EXISTS cpc_codes TEXT[] NOT NULL DEFAULT '{}';
ALTER TABLE patents ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'granted';
ALTER TABLE patents ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE patents ADD COLUMN IF NOT EXISTS abstract TEXT;
ALTER TABLE patents ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW();

COMMENT ON COLUMN patents.cpc_codes IS
    'Cooperative Patent Classification codes (e.g. A61K31/00 for medicinal '
    'preparations). Pharma-relevant filtering happens via these.';

COMMENT ON COLUMN patents.assignee_company_id IS
    'FK to companies — populated by entity_resolver from assignee_name_raw.';

-- ============================================================
-- Indexes (idempotent)
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_patents_assignee
    ON patents (assignee_company_id)
    WHERE assignee_company_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_patents_expiration
    ON patents (expiration_date)
    WHERE expiration_date IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_patents_cpc
    ON patents USING GIN (cpc_codes);

CREATE INDEX IF NOT EXISTS idx_patents_status
    ON patents (status);

COMMIT;
