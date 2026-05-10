-- BE-1 · evidence_records card-render fields.
--
-- PB-101 (frontend) needs source_name + tier badge + published_at
-- + snippet to render an EvidenceCard. These four columns join the
-- ledger as nullable additions, with the existing append-only
-- trigger widened to allow a one-time first-fill (same pattern as
-- archived_snapshot_ref).
--
-- See specs/BE_001_evidence_card_fields.md.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'evidence_records') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'evidence_records' AND column_name = 'source_name'
        ) THEN
            ALTER TABLE evidence_records ADD COLUMN source_name TEXT;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'evidence_records' AND column_name = 'source_tier'
        ) THEN
            ALTER TABLE evidence_records
                ADD COLUMN source_tier TEXT
                CHECK (source_tier IS NULL OR source_tier IN ('T1','T2','T3','T4'));
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'evidence_records' AND column_name = 'published_at'
        ) THEN
            ALTER TABLE evidence_records ADD COLUMN published_at TIMESTAMPTZ;
        END IF;

        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'evidence_records' AND column_name = 'snippet'
        ) THEN
            ALTER TABLE evidence_records
                ADD COLUMN snippet TEXT
                CHECK (snippet IS NULL OR char_length(snippet) <= 1000);
        END IF;
    END IF;
END $$;

-- Widen the append-only trigger to allow a one-time first-fill of any
-- of the four new columns (mirrors the archived_snapshot_ref pattern).
CREATE OR REPLACE FUNCTION evidence_records_append_only()
RETURNS TRIGGER AS $$
BEGIN
    -- archived_snapshot_ref first-fill (existing behaviour)
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
       AND OLD.source_name          IS NOT DISTINCT FROM NEW.source_name
       AND OLD.source_tier          IS NOT DISTINCT FROM NEW.source_tier
       AND OLD.published_at         IS NOT DISTINCT FROM NEW.published_at
       AND OLD.snippet              IS NOT DISTINCT FROM NEW.snippet
    THEN
        RETURN NEW;
    END IF;

    -- BE-1 first-fill of source_name / source_tier / published_at / snippet:
    -- allowed if every column is either unchanged OR transitions from NULL
    -- to a non-NULL value (no value can be reset, no immutable column may move).
    IF  OLD.evidence_id          IS NOT DISTINCT FROM NEW.evidence_id
        AND OLD.source_id            IS NOT DISTINCT FROM NEW.source_id
        AND OLD.source_url           IS NOT DISTINCT FROM NEW.source_url
        AND OLD.source_content_hash  IS NOT DISTINCT FROM NEW.source_content_hash
        AND OLD.retrieved_at         IS NOT DISTINCT FROM NEW.retrieved_at
        AND OLD.extraction_method::text IS NOT DISTINCT FROM NEW.extraction_method::text
        AND OLD.extracted_text       IS NOT DISTINCT FROM NEW.extracted_text
        AND OLD.confidence           IS NOT DISTINCT FROM NEW.confidence
        AND OLD.retrieved_by_user_id IS NOT DISTINCT FROM NEW.retrieved_by_user_id
        AND OLD.created_at           IS NOT DISTINCT FROM NEW.created_at
        AND OLD.archived_snapshot_ref IS NOT DISTINCT FROM NEW.archived_snapshot_ref
        AND (OLD.source_name  IS NULL OR OLD.source_name  IS NOT DISTINCT FROM NEW.source_name)
        AND (OLD.source_tier  IS NULL OR OLD.source_tier  IS NOT DISTINCT FROM NEW.source_tier)
        AND (OLD.published_at IS NULL OR OLD.published_at IS NOT DISTINCT FROM NEW.published_at)
        AND (OLD.snippet      IS NULL OR OLD.snippet      IS NOT DISTINCT FROM NEW.snippet)
    THEN
        RETURN NEW;
    END IF;

    RAISE EXCEPTION 'evidence_records is append-only; only first-fill of nullable enrichment columns may be performed'
        USING ERRCODE = '42501';  -- insufficient_privilege
END;
$$ LANGUAGE plpgsql;
