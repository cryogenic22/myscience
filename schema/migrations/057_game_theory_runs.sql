-- SPEC_025 — Game-Theoretic Simulation: append-only run log.
-- Stores Bayesian / Stackelberg / POMDP runs with their inputs + outputs
-- so the frontend can render a history of simulation results per brief.

CREATE TABLE IF NOT EXISTS game_theory_runs (
    run_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brief_id            UUID,  -- loose pointer; no FK because this table may
                               -- be created before decision_briefs in some deploys
    kind                TEXT NOT NULL CHECK (kind IN ('bayesian','stackelberg','pomdp')),
    inputs_jsonb        JSONB NOT NULL,
    outputs_jsonb       JSONB NOT NULL,
    compute_ms          INTEGER CHECK (compute_ms IS NULL OR compute_ms >= 0),
    started_by_user_id  UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gt_runs_kind_created
    ON game_theory_runs (kind, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_gt_runs_brief
    ON game_theory_runs (brief_id, created_at DESC)
    WHERE brief_id IS NOT NULL;
