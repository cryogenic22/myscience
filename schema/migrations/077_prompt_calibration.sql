-- BE-41 · Outcome-to-prompt calibration table.

CREATE TABLE IF NOT EXISTS prompt_calibration (
    prompt_id          UUID PRIMARY KEY,
    calibration_score  REAL NOT NULL DEFAULT 0.65
                       CHECK (calibration_score BETWEEN 0 AND 1),
    outcomes_seen      INTEGER NOT NULL DEFAULT 0
                       CHECK (outcomes_seen >= 0),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_prompt_calibration_score
    ON prompt_calibration (calibration_score);
