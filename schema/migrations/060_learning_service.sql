-- SPEC_032 — Learning Service: close the flywheel.
-- Append-only run log + per-(decision, source) attribution + prompt flags.

-- ─── learning_service_runs ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS learning_service_runs (
    run_id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    started_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at          TIMESTAMPTZ,
    status                TEXT NOT NULL DEFAULT 'running'
                          CHECK (status IN ('running','complete','failed')),
    since_cursor          TIMESTAMPTZ,
    decisions_processed   INTEGER NOT NULL DEFAULT 0 CHECK (decisions_processed >= 0),
    sources_updated       INTEGER NOT NULL DEFAULT 0 CHECK (sources_updated >= 0),
    prompts_flagged       INTEGER NOT NULL DEFAULT 0 CHECK (prompts_flagged >= 0),
    failure_reason        TEXT,
    summary_jsonb         JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_by_user_id    UUID
);

CREATE INDEX IF NOT EXISTS idx_lsr_started
    ON learning_service_runs (started_at DESC);

CREATE INDEX IF NOT EXISTS idx_lsr_status
    ON learning_service_runs (status, started_at DESC);

-- ─── source_attribution_log ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS source_attribution_log (
    attribution_id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id               UUID NOT NULL REFERENCES learning_service_runs(run_id) ON DELETE CASCADE,
    decision_id          UUID NOT NULL,
    source_id            TEXT NOT NULL,
    calibration_score    REAL NOT NULL CHECK (calibration_score >= 0 AND calibration_score <= 1),
    prior_accuracy       REAL CHECK (prior_accuracy IS NULL OR (prior_accuracy >= 0 AND prior_accuracy <= 1)),
    posterior_accuracy   REAL NOT NULL CHECK (posterior_accuracy >= 0 AND posterior_accuracy <= 1),
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sal_run
    ON source_attribution_log (run_id, created_at);

CREATE INDEX IF NOT EXISTS idx_sal_source_time
    ON source_attribution_log (source_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_sal_decision
    ON source_attribution_log (decision_id);

-- ─── prompt_quality_flag ─────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS prompt_quality_flag (
    flag_id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                UUID NOT NULL REFERENCES learning_service_runs(run_id) ON DELETE CASCADE,
    prompt_id             UUID NOT NULL,
    prompt_name           TEXT,
    decisions_observed    INTEGER NOT NULL CHECK (decisions_observed > 0),
    mean_calibration      REAL NOT NULL CHECK (mean_calibration >= 0 AND mean_calibration <= 1),
    flag_reason           TEXT NOT NULL CHECK (flag_reason IN ('low_calibration','low_volume_high_var')),
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pqf_prompt
    ON prompt_quality_flag (prompt_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_pqf_run
    ON prompt_quality_flag (run_id);
