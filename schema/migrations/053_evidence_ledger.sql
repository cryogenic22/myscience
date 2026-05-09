-- SPEC_024 — Evidence Ledger: content-addressed claim provenance.
-- Append-only ledger so every claim in user-facing artifacts is traceable
-- to one or more immutable evidence records. Foundation for decision
-- signing (immutable evidence_snapshot) and the frontend Evidence
-- Affordance pattern.

-- ─── claims ──────────────────────────────────────────────────────────
-- A structured assertion about an entity. Deduplicated by (text_hash, entity).
CREATE TABLE IF NOT EXISTS claims (
    claim_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_text        TEXT NOT NULL CHECK (char_length(claim_text) BETWEEN 1 AND 8000),
    claim_text_hash   BYTEA NOT NULL,
    claim_type        TEXT NOT NULL DEFAULT 'other'
                      CHECK (claim_type IN ('regulatory','clinical','commercial','pricing','safety','pipeline','other')),
    entity_type       TEXT CHECK (entity_type IS NULL OR entity_type IN ('drug','company','trial','indication','mechanism','therapeutic_area','event','patent','literature')),
    entity_id         UUID,
    confidence        REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Dedup: same claim text + same entity = same claim. Two partial unique
-- indexes handle NULL entity_id (which is treated as distinct under
-- standard UNIQUE semantics).
CREATE UNIQUE INDEX IF NOT EXISTS uq_claims_text_entity
    ON claims (claim_text_hash, entity_type, entity_id)
    WHERE entity_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_claims_text_no_entity
    ON claims (claim_text_hash, claim_type)
    WHERE entity_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_claims_entity
    ON claims (entity_type, entity_id)
    WHERE entity_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_claims_type
    ON claims (claim_type, created_at DESC);

-- ─── evidence_records ────────────────────────────────────────────────
-- The append-only ledger.
CREATE TABLE IF NOT EXISTS evidence_records (
    evidence_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id              TEXT NOT NULL CHECK (char_length(source_id) BETWEEN 1 AND 200),
    source_url             TEXT,
    source_content_hash    BYTEA NOT NULL,
    archived_snapshot_ref  TEXT,
    retrieved_at           TIMESTAMPTZ NOT NULL,
    extraction_method      JSONB NOT NULL DEFAULT '{}'::jsonb,
    extracted_text         TEXT NOT NULL CHECK (char_length(extracted_text) BETWEEN 1 AND 65536),
    confidence             REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    retrieved_by_user_id   UUID,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Dedup: same content from same source on same day = same evidence
CREATE UNIQUE INDEX IF NOT EXISTS uq_evidence_dedup
    ON evidence_records (source_content_hash, source_id, (retrieved_at::date));

CREATE INDEX IF NOT EXISTS idx_evidence_source
    ON evidence_records (source_id, retrieved_at DESC);

CREATE INDEX IF NOT EXISTS idx_evidence_content_hash
    ON evidence_records (source_content_hash);

-- Append-only trigger: reject UPDATE on all columns except
-- archived_snapshot_ref (one-time fill after archive job).
CREATE OR REPLACE FUNCTION evidence_records_append_only()
RETURNS TRIGGER AS $$
BEGIN
    -- Allow archived_snapshot_ref to be set IF currently null
    IF OLD.archived_snapshot_ref IS NULL
       AND NEW.archived_snapshot_ref IS NOT NULL
       AND OLD.evidence_id          IS NOT DISTINCT FROM NEW.evidence_id
       AND OLD.source_id            IS NOT DISTINCT FROM NEW.source_id
       AND OLD.source_url           IS NOT DISTINCT FROM NEW.source_url
       AND OLD.source_content_hash  IS NOT DISTINCT FROM NEW.source_content_hash
       AND OLD.retrieved_at         IS NOT DISTINCT FROM NEW.retrieved_at
       AND OLD.extraction_method::text IS NOT DISTINCT FROM NEW.extraction_method::text
       AND OLD.extracted_text       IS NOT DISTINCT FROM NEW.extracted_text
       AND OLD.confidence           IS NOT DISTINCT FROM NEW.confidence
       AND OLD.retrieved_by_user_id IS NOT DISTINCT FROM NEW.retrieved_by_user_id
       AND OLD.created_at           IS NOT DISTINCT FROM NEW.created_at
    THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'evidence_records is append-only; only archived_snapshot_ref may be filled once'
        USING ERRCODE = '42501';  -- insufficient_privilege
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_evidence_append_only ON evidence_records;
CREATE TRIGGER trg_evidence_append_only
    BEFORE UPDATE ON evidence_records
    FOR EACH ROW EXECUTE FUNCTION evidence_records_append_only();

-- Block DELETE entirely
CREATE OR REPLACE FUNCTION evidence_records_no_delete()
RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'evidence_records is append-only; DELETE is forbidden'
        USING ERRCODE = '42501';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_evidence_no_delete ON evidence_records;
CREATE TRIGGER trg_evidence_no_delete
    BEFORE DELETE ON evidence_records
    FOR EACH ROW EXECUTE FUNCTION evidence_records_no_delete();

-- ─── claim_evidence_links ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS claim_evidence_links (
    link_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id       UUID NOT NULL REFERENCES claims(claim_id) ON DELETE CASCADE,
    evidence_id    UUID NOT NULL REFERENCES evidence_records(evidence_id) ON DELETE RESTRICT,
    relation       TEXT NOT NULL DEFAULT 'supports'
                   CHECK (relation IN ('supports','contradicts','qualifies')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (claim_id, evidence_id, relation)
);

CREATE INDEX IF NOT EXISTS idx_cel_claim
    ON claim_evidence_links (claim_id);

CREATE INDEX IF NOT EXISTS idx_cel_evidence
    ON claim_evidence_links (evidence_id);

-- ─── evidence_snapshots ──────────────────────────────────────────────
-- Content-addressed; snapshot_hash IS the primary key.
CREATE TABLE IF NOT EXISTS evidence_snapshots (
    snapshot_hash   BYTEA PRIMARY KEY,
    body            JSONB NOT NULL,
    brief_id        UUID,
    decision_id     UUID,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshots_brief
    ON evidence_snapshots (brief_id)
    WHERE brief_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_snapshots_decision
    ON evidence_snapshots (decision_id)
    WHERE decision_id IS NOT NULL;

-- updated_at trigger for claims (only)
CREATE OR REPLACE FUNCTION claims_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_claims_updated_at ON claims;
CREATE TRIGGER trg_claims_updated_at
    BEFORE UPDATE ON claims
    FOR EACH ROW EXECUTE FUNCTION claims_set_updated_at();
