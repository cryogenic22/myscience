-- SPEC_034 — Decision Signing: immutable evidence_snapshot + HMAC.
-- Additive columns on the existing decisions table (back-compat — NULL
-- means unsigned, which is the state of every existing row).

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'decisions') THEN
        RAISE NOTICE 'decisions table not found; skipping decision-signing columns';
        RETURN;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'decisions' AND column_name = 'evidence_snapshot_hash') THEN
        ALTER TABLE decisions ADD COLUMN evidence_snapshot_hash BYTEA;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'decisions' AND column_name = 'signature') THEN
        ALTER TABLE decisions ADD COLUMN signature BYTEA;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'decisions' AND column_name = 'signing_algo') THEN
        ALTER TABLE decisions ADD COLUMN signing_algo TEXT;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'decisions' AND column_name = 'signed_at') THEN
        ALTER TABLE decisions ADD COLUMN signed_at TIMESTAMPTZ;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'decisions' AND column_name = 'signing_user_id') THEN
        ALTER TABLE decisions ADD COLUMN signing_user_id UUID;
    END IF;

    IF NOT EXISTS (SELECT 1 FROM information_schema.columns
                    WHERE table_name = 'decisions' AND column_name = 'signing_metadata_jsonb') THEN
        ALTER TABLE decisions ADD COLUMN signing_metadata_jsonb JSONB;
    END IF;
END $$;

-- Index for "find signed decisions" admin queries
CREATE INDEX IF NOT EXISTS idx_decisions_signed_at
    ON decisions (signed_at DESC)
    WHERE signed_at IS NOT NULL;
