-- 091_crosswalk_records.sql
--
-- Loop L1b — the substrate for evidence-backed RxNorm/ATC -> internal crosswalk
-- mappings (SME docs/pharmcore_atc.md crosswalk_record_schema). A crosswalk record
-- ENRICHES an internal entity with an external mapping; it NEVER overwrites the
-- internal entity's identity. Each row carries an explicit relation/scope/confidence
-- + review_status + source_version so a steward can see and govern it, and so a
-- many-to-many mapping is recorded as multiple rows rather than silently collapsed.
--
-- The governed relation/scope/confidence/action are computed by
-- services/ontology_crosswalk.classify() (Loop L1a); this table persists them.
-- Additive, idempotent (UNIQUE natural key), reversible (drop table).

CREATE TABLE IF NOT EXISTS crosswalk_records (
    crosswalk_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    internal_entity_id  TEXT NOT NULL,
    internal_entity_type TEXT NOT NULL,            -- molecule / drug_class / ...
    external_system     TEXT NOT NULL,             -- rxnorm / atc
    external_id         TEXT NOT NULL,             -- rxcui / atc_code
    external_label      TEXT,
    mapping_relation    TEXT NOT NULL,             -- exact|narrower|broader|related|inferred|rejected
    mapping_scope       TEXT,                      -- substance_level / drug_class_level / ...
    mapping_confidence  NUMERIC,
    mapping_method      TEXT,                      -- exact_identifier / atc_hierarchy / ...
    ambiguity_flags     TEXT[] DEFAULT '{}',
    source_version      TEXT,                      -- external release the mapping came from
    review_status       TEXT NOT NULL DEFAULT 'machine_only',  -- machine_only/pending_review/approved/rejected/superseded
    action              TEXT,                      -- approved_auto / approved_with_audit / review_required / rejected_or_quarantined
    evidence_record_ids UUID[] DEFAULT '{}',
    resolver_audit_id   TEXT,
    notes               TEXT,
    valid_from          TIMESTAMPTZ DEFAULT NOW(),
    valid_to            TIMESTAMPTZ,
    record_status       TEXT DEFAULT 'active',     -- active / superseded (soft-delete)
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW(),
    -- one mapping per (internal entity, external system, external id): idempotent
    -- re-runs, and many-to-many is many ROWS (never a silent collapse).
    UNIQUE (internal_entity_id, external_system, external_id)
);

CREATE INDEX IF NOT EXISTS idx_crosswalk_internal ON crosswalk_records (internal_entity_id);
CREATE INDEX IF NOT EXISTS idx_crosswalk_external  ON crosswalk_records (external_system, external_id);
CREATE INDEX IF NOT EXISTS idx_crosswalk_review    ON crosswalk_records (review_status)
    WHERE review_status IN ('pending_review', 'machine_only');

COMMENT ON TABLE crosswalk_records IS
    'Evidence-backed RxNorm/ATC -> internal ontology mappings (migration 091, Loop L1b). '
    'Enriches, never overwrites, internal identity. relation/scope/confidence computed by '
    'services/ontology_crosswalk.classify(). Many-to-many = many rows, never collapsed.';
