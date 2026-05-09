-- SPEC_033 — Counter-Recommendation Enforcement.
-- Append-only synthesis log so admins can reproduce what the user saw.

CREATE TABLE IF NOT EXISTS recommendation_synthesis_runs (
    recommendation_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brief_id             UUID,  -- loose pointer; FK conditional
    inputs_jsonb         JSONB NOT NULL,
    primary_option_id    UUID NOT NULL,
    primary_rationale    TEXT NOT NULL CHECK (char_length(primary_rationale) BETWEEN 1 AND 4000),
    counter_option_id    UUID NOT NULL,
    counter_rationale    TEXT NOT NULL CHECK (char_length(counter_rationale) BETWEEN 1 AND 4000),
    dissent_score        REAL NOT NULL CHECK (dissent_score >= 0 AND dissent_score <= 1),
    synthesis_method     TEXT NOT NULL CHECK (synthesis_method IN ('score_based','dimension_split','llm_v1')),
    started_by_user_id   UUID,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Service enforces this; CHECK at the DB level prevents data-layer drift
    CHECK (primary_option_id <> counter_option_id)
);

CREATE INDEX IF NOT EXISTS idx_rsr_brief
    ON recommendation_synthesis_runs (brief_id, created_at DESC)
    WHERE brief_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_rsr_created
    ON recommendation_synthesis_runs (created_at DESC);

-- Conditional FK to decision_briefs
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'decision_briefs') THEN
        BEGIN
            ALTER TABLE recommendation_synthesis_runs
              ADD CONSTRAINT fk_rsr_brief
              FOREIGN KEY (brief_id) REFERENCES decision_briefs(brief_id) ON DELETE SET NULL;
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END;
    END IF;
END $$;
