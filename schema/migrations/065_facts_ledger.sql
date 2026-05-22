-- Migration 065: facts ledger (PB-1307)
--
-- The semantic moat: typed, time-stamped, evidence-linked facts with a
-- temporal model. Pulled forward (critical-analysis §9.1) because the
-- dossier and the war-game both depend on it.
--
-- The killer capability is the ANTICIPATORY fact: "Novo Wegovy WAC will be
-- $675 effective 2027-01-01" is stored with valid_from in the FUTURE. The
-- war-game then queries facts AS-OF a target date, getting the correctly
-- timed world state. Without this, every "what if as of date X" is hand-rolled.
--
-- Append-only ledger: facts are never deleted; corrections supersede via
-- superseded_by (the prior fact stays for audit/replay).
--
-- Entities are polymorphic across drugs/companies/trials/etc (no `entities`
-- table), so subject is (type, id) text — mirroring the signals table.
-- tenant_scope is nullable now (null = global); E11 enforcement adds the
-- WHERE-filter later without a backfill.

BEGIN;

CREATE TABLE IF NOT EXISTS facts (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Temporal kind (data_strategy.md §2.4)
    kind                TEXT NOT NULL
                        CHECK (kind IN ('point', 'interval', 'anticipatory')),

    -- The claim
    predicate           TEXT NOT NULL,                 -- 'wac_usd_monthly', 'fda_approval_date', ...
    subject_entity_type TEXT NOT NULL,                 -- 'company' | 'drug' | 'trial' | ...
    subject_entity_id   TEXT NOT NULL,
    object_value        JSONB NOT NULL,                -- typed payload per predicate

    -- Validity window
    valid_from          TIMESTAMPTZ,
    valid_to            TIMESTAMPTZ,
    asserted_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),  -- when we learned it

    -- Provenance
    source_doc_id       UUID,                          -- → evidence_records(evidence_id), loose (ingest flexibility)
    confidence          REAL NOT NULL DEFAULT 1.0
                        CHECK (confidence >= 0 AND confidence <= 1),
    created_by          TEXT NOT NULL DEFAULT 'system',  -- agent name or human id

    -- Supersession (append-only)
    superseded_by       UUID REFERENCES facts(id),

    -- Tenancy (E11 enforcement later; column now avoids backfill)
    tenant_scope        TEXT,                          -- null = global

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- An interval fact needs an end; a point/anticipatory may leave valid_to null
    CONSTRAINT facts_interval_has_end
        CHECK (kind <> 'interval' OR valid_to IS NOT NULL)
);

-- Subject lookups + as-of scans
CREATE INDEX IF NOT EXISTS idx_facts_subject
    ON facts (subject_entity_type, subject_entity_id, predicate, valid_from DESC);
CREATE INDEX IF NOT EXISTS idx_facts_predicate
    ON facts (predicate, valid_from DESC);
CREATE INDEX IF NOT EXISTS idx_facts_source
    ON facts (source_doc_id);
-- Range index for "valid at instant T" queries
CREATE INDEX IF NOT EXISTS idx_facts_validity
    ON facts USING GIST (tstzrange(valid_from, valid_to));

-- Append-only: DELETE is forbidden (replay/audit integrity).
CREATE OR REPLACE FUNCTION facts_no_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'facts is append-only; DELETE is forbidden (supersede instead)'
        USING ERRCODE = '42501';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_facts_no_delete ON facts;
CREATE TRIGGER trg_facts_no_delete
    BEFORE DELETE ON facts
    FOR EACH ROW EXECUTE FUNCTION facts_no_delete();

COMMENT ON TABLE facts IS
    'Temporal, append-only, evidence-linked facts. point/interval/anticipatory '
    'validity. Anticipatory facts (future valid_from) power as-of war-game '
    'queries. Superseded never deleted. PB-1307.';

COMMIT;
