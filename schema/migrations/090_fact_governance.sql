-- Migration 090: fact governance & trust model (Agent Readiness Layer)
--
-- The keystone of FAIR "Reusable" + agent-trust: every fact carries the trust
-- metadata an agent needs to reason safely. Today the ledger has a single
-- `confidence` REAL — opaque, uncomposed, and not derived from a documented
-- model. An autonomous agent cannot tell a regulatory-grounded structured fact
-- from an LLM guess off a stale deck. This adds the dimensions that, composed,
-- yield a single explainable `trust_score`, plus a `review_status` lifecycle.
--
-- ADDITIVE + idempotent by design: every column is ADD COLUMN IF NOT EXISTS,
-- every index IF NOT EXISTS. Existing rows keep NULL on the new dimensions until
-- the backfill (scripts/backfill_fact_governance.py) computes them; NEW facts
-- get governance at write time via services/fact_governance.score_fact wired
-- into assert_fact. No existing column or constraint is changed, so every
-- current consumer (dossier_kb facts_as_of, fact_emitters, conservation gates)
-- keeps working unchanged.
--
-- The six dimensions (all REAL in [0,1] unless noted):
--   source_reliability    tier of the originating source (regulatory ~0.95 …)
--   extraction_confidence 1.0 for structured/connector; <1 for LLM/document
--   resolver_confidence   confidence the subject entity was resolved correctly
--   freshness_at          the as-of timestamp used for staleness decay
--   review_status         unreviewed | auto_approved | human_approved | flagged
--   schema_version        version of the governance model that wrote the row
--   trust_score           composite (documented in services/fact_governance.py)

BEGIN;

ALTER TABLE facts ADD COLUMN IF NOT EXISTS source_reliability REAL;
ALTER TABLE facts ADD COLUMN IF NOT EXISTS extraction_confidence REAL;
ALTER TABLE facts ADD COLUMN IF NOT EXISTS resolver_confidence REAL;
ALTER TABLE facts ADD COLUMN IF NOT EXISTS freshness_at TIMESTAMPTZ;
ALTER TABLE facts ADD COLUMN IF NOT EXISTS review_status TEXT DEFAULT 'unreviewed';
ALTER TABLE facts ADD COLUMN IF NOT EXISTS schema_version INTEGER DEFAULT 1;
ALTER TABLE facts ADD COLUMN IF NOT EXISTS trust_score REAL;

-- Bound the three new probability dimensions + trust_score to [0,1] (NULLs
-- allowed pre-backfill). Guarded so re-running does not error on the existing one.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'facts_governance_range'
    ) THEN
        ALTER TABLE facts ADD CONSTRAINT facts_governance_range CHECK (
            (source_reliability    IS NULL OR (source_reliability    >= 0 AND source_reliability    <= 1)) AND
            (extraction_confidence IS NULL OR (extraction_confidence >= 0 AND extraction_confidence <= 1)) AND
            (resolver_confidence   IS NULL OR (resolver_confidence   >= 0 AND resolver_confidence   <= 1)) AND
            (trust_score           IS NULL OR (trust_score           >= 0 AND trust_score           <= 1))
        );
    END IF;
END$$;

-- review_status must be one of the four lifecycle states (NULL never set; has a default).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'facts_review_status_valid'
    ) THEN
        ALTER TABLE facts ADD CONSTRAINT facts_review_status_valid CHECK (
            review_status IN ('unreviewed', 'auto_approved', 'human_approved', 'flagged')
        );
    END IF;
END$$;

-- Partial index: the review queue only cares about flagged facts (small set).
CREATE INDEX IF NOT EXISTS idx_facts_flagged
    ON facts (review_status)
    WHERE review_status = 'flagged';

-- Trust-ranked scans (agent "give me the most trustworthy facts" queries).
CREATE INDEX IF NOT EXISTS idx_facts_trust_score
    ON facts (trust_score DESC NULLS LAST);

COMMENT ON COLUMN facts.source_reliability IS
    'Governance: tier of the originating source in [0,1] (regulatory/peer-reviewed '
    '~0.95, corporate filing ~0.85, news ~0.6, inferred ~0.4). Migration 090.';
COMMENT ON COLUMN facts.extraction_confidence IS
    'Governance: 1.0 for structured/connector facts; <1 for LLM/document-extracted. 090.';
COMMENT ON COLUMN facts.resolver_confidence IS
    'Governance: confidence the subject entity was resolved correctly (resolution_audit). 090.';
COMMENT ON COLUMN facts.freshness_at IS
    'Governance: as-of timestamp used for staleness decay (defaults to valid_from/created_at). 090.';
COMMENT ON COLUMN facts.review_status IS
    'Governance lifecycle: unreviewed | auto_approved | human_approved | flagged. 090.';
COMMENT ON COLUMN facts.schema_version IS
    'Governance: version of the trust model that wrote this row. 090.';
COMMENT ON COLUMN facts.trust_score IS
    'Governance: composite trust in [0,1], a documented weighted blend of the five '
    'dimensions × freshness decay. See services/fact_governance.py. 090.';

COMMIT;
