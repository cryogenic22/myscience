-- Migration 069: business_context_briefs (Z4)
--
-- The ZS framework's most upstream commitment. An engagement starts when
-- the lead types a BCB stating the situation, the competitive set, and the
-- specific decisions the wargame must inform.
--
-- One BCB per Engagement (UNIQUE on engagement_id). The Python type
-- (services/business_context_brief.py:BusinessContextBrief) enforces:
--   - >= 1 strategic_decisions (wargame must inform something)
--   - non-empty focal_asset
--   - valid situation
--   - paired sign-off (all three or none).
-- Mirrored here as JSONB CHECK + paired-state CHECK (defence in depth).

BEGIN;

CREATE TABLE IF NOT EXISTS business_context_briefs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id       UUID NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,

    focal_asset         TEXT NOT NULL,
    situation           TEXT NOT NULL
                        CHECK (situation IN ('launch','defense','lcm')),

    strategic_decisions JSONB NOT NULL,    -- list of {statement, rationale}
    competitive_set     JSONB NOT NULL DEFAULT '[]'::jsonb,
    success_criteria    JSONB NOT NULL DEFAULT '[]'::jsonb,
    constraints         JSONB NOT NULL DEFAULT '[]'::jsonb,

    created_by          TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    signed_off          BOOL NOT NULL DEFAULT FALSE,
    signed_off_by       TEXT,
    signed_off_at       TIMESTAMPTZ,

    CONSTRAINT bcb_unique_per_engagement UNIQUE (engagement_id),
    CONSTRAINT bcb_strategic_decisions_nonempty
        CHECK (jsonb_array_length(strategic_decisions) >= 1),
    CONSTRAINT bcb_focal_asset_nonempty
        CHECK (length(btrim(focal_asset)) > 0),
    CONSTRAINT bcb_signoff_paired
        CHECK (
            (signed_off = FALSE AND signed_off_by IS NULL AND signed_off_at IS NULL)
            OR
            (signed_off = TRUE  AND signed_off_by IS NOT NULL AND signed_off_at IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_bcb_engagement
    ON business_context_briefs (engagement_id);
CREATE INDEX IF NOT EXISTS idx_bcb_situation
    ON business_context_briefs (situation);

COMMENT ON TABLE business_context_briefs IS
    'Business Context Brief (ZS framework upstream). One per engagement. Z4.';

COMMIT;
