-- Migration 066: insights table + rejected_insights (Z2)
--
-- Closes Riya's "insights without provenance" finding structurally.
-- An insight requires a non-empty derived_from list of fact citations,
-- enforced both by the Python type (services/insights.py:Insight) and by
-- the CHECK constraint on jsonb_array_length here.
--
-- rejected_insights captures candidates that failed the synthesis test —
-- a procurement-grade audit artifact preserving why a candidate did not
-- become an insight.

BEGIN;

CREATE TABLE IF NOT EXISTS insights (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    statement                TEXT NOT NULL,
    strategic_frame          TEXT NOT NULL
                             CHECK (strategic_frame IN ('risk','opportunity','assumption','trigger')),
    derived_from             JSONB NOT NULL,    -- list of {fact_id, predicate, contribution}
    synthesis_test_passed    BOOL NOT NULL DEFAULT TRUE,
    synthesis_test_rationale TEXT NOT NULL,
    domain                   TEXT NOT NULL,     -- ZS dossier domain
    created_by               TEXT NOT NULL DEFAULT 'intelligence_agent',
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_scope             TEXT,              -- nullable = global (E phase enforces)
    CONSTRAINT insights_derived_from_nonempty
        CHECK (jsonb_array_length(derived_from) >= 1),
    CONSTRAINT insights_statement_nonempty
        CHECK (length(btrim(statement)) > 0),
    CONSTRAINT insights_rationale_nonempty
        CHECK (length(btrim(synthesis_test_rationale)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_insights_domain
    ON insights (domain, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_insights_frame
    ON insights (strategic_frame, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_insights_created_at
    ON insights (created_at DESC);

CREATE TABLE IF NOT EXISTS rejected_insights (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_statement TEXT NOT NULL,
    rejection_reason    TEXT NOT NULL,
    derived_from        JSONB,             -- nullable: rejection may be because none
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rejected_insights_created_at
    ON rejected_insights (created_at DESC);

COMMENT ON TABLE insights IS
    'Typed insights (ZS Pharma Wargaming Framework synthesis test). '
    'Every insight has >= 1 fact citation via derived_from JSONB. '
    'Z2.';
COMMENT ON TABLE rejected_insights IS
    'Insight candidates that failed the synthesis test. Audit artifact: '
    'preserves the rejection reason so analysts can see why a candidate '
    'did not become an insight. Z2.';

COMMIT;
