-- Migration 040: investigators.roles_history + canonical_name + linkedin_url
--
-- SPEC-016 §7 swimlane A1, task A1.4.
--
-- The existing `investigators` table holds people in their trial-PI capacity.
-- A2.1 (8-K Item 5.02 parser) and the future PulseAction · CI Exec Tracker
-- need to record corporate role transitions as well. Rather than create a
-- new `persons` table now (Phase 2 rename), we extend `investigators` with:
--
--   - roles_history JSONB        append-only role timeline per company
--   - canonical_name TEXT        lowercased+normalised form for resolver match
--   - linkedin_url TEXT          (CONFIRMATION ONLY, never trigger — per CI design)
--
-- The 8-K parser writes role entries here; the pattern detector reads them
-- (e.g. "3 leadership departures from same TA team in 90d").

BEGIN;

ALTER TABLE investigators
    ADD COLUMN IF NOT EXISTS roles_history JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN investigators.roles_history IS
    'Append-only array of corporate role entries. Each entry: '
    '{ company_id, company_name, title, functional_area '
    '(CEO|CFO|CSO|CMO|CCO|head_of_RD|board|other), seniority_tier '
    '(C-suite|EVP/SVP|VP|Director|Other), start_date, end_date, '
    'transition_id, source_document_id, confirmed }. '
    'transition_id pairs related exit + arrival events for the same role transition.';

ALTER TABLE investigators
    ADD COLUMN IF NOT EXISTS canonical_name TEXT;

COMMENT ON COLUMN investigators.canonical_name IS
    'Lowercased, accent-stripped, suffix-stripped form of name. Used by the '
    'entity_resolver fuzzy cascade. Populated by services/person_roles.normalise_name.';

ALTER TABLE investigators
    ADD COLUMN IF NOT EXISTS linkedin_url TEXT;

COMMENT ON COLUMN investigators.linkedin_url IS
    'LinkedIn profile URL. Per CI design: confirmation-only signal, never a trigger. '
    'A LinkedIn change creates a candidate signal at confidence_tier=inferred, '
    'promoted to confirmed only by 8-K Item 5.02 or company leadership-page diff.';

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_investigators_roles_history
    ON investigators USING GIN (roles_history);

-- canonical_name lookups during resolver cascade
CREATE INDEX IF NOT EXISTS idx_investigators_canonical_name
    ON investigators (canonical_name)
    WHERE canonical_name IS NOT NULL;

-- LinkedIn URL is sparse; partial unique to allow nulls
CREATE UNIQUE INDEX IF NOT EXISTS idx_investigators_linkedin_url
    ON investigators (linkedin_url)
    WHERE linkedin_url IS NOT NULL;

-- ============================================================
-- Backfill canonical_name for existing rows
-- ============================================================

UPDATE investigators
SET canonical_name = LOWER(
    TRIM(
        REGEXP_REPLACE(
            -- strip common honorifics + degree suffixes
            REGEXP_REPLACE(
                COALESCE(name, ''),
                '(^|\s)(Dr|Mr|Mrs|Ms|Prof|Professor|Sir)\.?(\s|$)',
                ' ', 'gi'
            ),
            ',?\s+(Ph\.?D\.?|M\.?D\.?|MBA|J\.?D\.?|Esq\.?)$',
            '', 'i'
        )
    )
)
WHERE canonical_name IS NULL AND name IS NOT NULL;

COMMIT;
