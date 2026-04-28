-- Migration 041: patents table (skeleton)
--
-- SPEC-016 §7 swimlane A1, task A1.5.
--
-- Per CI design, patents are needed for:
--   - LOE (Loss of Exclusivity) computation per drug — A5.2
--   - Patent challenges / IPR proceedings tracking (Phase 2 PTAB connector)
--   - Cross-link to drugs via Orange Book listings (existing data)
--
-- This migration creates the SCHEMA only. Population is A5.1 USPTO
-- PatentsView connector. Until then, patent_id columns on entity_links
-- and elsewhere can FK to this empty table.

BEGIN;

CREATE TABLE IF NOT EXISTS patents (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Identity
    patent_number           TEXT NOT NULL,
    patent_office           TEXT NOT NULL DEFAULT 'USPTO',
                            -- USPTO | EPO | WIPO | JPO | CNIPA | ...
    patent_type             TEXT NOT NULL DEFAULT 'grant',

    -- Assignee (owner) — FK to companies, nullable for unresolved cases
    assignee_company_id     UUID REFERENCES companies(id),
    assignee_name_raw       TEXT,
                            -- raw name as it appeared in PatentsView
                            -- (resolved to assignee_company_id by entity_resolver)

    -- Dates
    filing_date             DATE,
    grant_date              DATE,
    expiration_date         DATE,
    priority_date           DATE,

    -- Classification
    cpc_codes               TEXT[] NOT NULL DEFAULT '{}',
                            -- Cooperative Patent Classification codes

    -- Lifecycle
    status                  TEXT NOT NULL DEFAULT 'granted',

    -- Content
    title                   TEXT,
    abstract                TEXT,

    -- Provenance
    source_api              TEXT NOT NULL DEFAULT 'uspto_patentsview',
    source_url              TEXT,
    retrieved_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Audit
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT patents_patent_type_check
        CHECK (patent_type IN ('grant', 'application', 'design', 'PTE')),
    CONSTRAINT patents_status_check
        CHECK (status IN (
            'granted', 'pending', 'application',
            'abandoned', 'expired', 'challenged', 'withdrawn'
        ))
);

COMMENT ON TABLE patents IS
    'Patent records — populated by USPTO PatentsView connector (A5.1) + '
    'cross-walked to drugs via Orange Book (existing). Read by LOE '
    'computation service (A5.2) for floor-LOE per drug. Phase 2 adds '
    'PTAB IPR proceedings + global patents (WIPO PATENTSCOPE).';

COMMENT ON COLUMN patents.patent_type IS
    'grant = utility patent granted; application = pending application; '
    'design = design patent; PTE = patent term extension grant';

COMMENT ON COLUMN patents.cpc_codes IS
    'Cooperative Patent Classification codes (e.g. A61K31/00 for medicinal '
    'preparations). Pharma-relevant filtering happens via these.';

-- ============================================================
-- Indexes
-- ============================================================

CREATE UNIQUE INDEX IF NOT EXISTS idx_patents_patent_number
    ON patents (patent_office, patent_number);

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
