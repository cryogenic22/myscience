-- 092_scenario_probability_history.sql
--
-- Loop 2 (Helix temporal / decision-memory) — scenario probability HISTORY.
--
-- scenario_calibration recomputes current_prob from the prior each run and keeps
-- only the latest calibration_note. There was no time-series, so "why did this
-- scenario move 0.38 -> 0.12?" was unanswerable and the Helix Output-Quality
-- Benchmark OQ2 gate ("every probability change has an audit row") failed.
--
-- This append-only ledger records each genuine change (prev -> new, delta, the
-- triggering signals, method, and the human-readable note). It is general
-- temporal intelligence — consumed by CI as-of replay, and available to chat /
-- any future consumer asking "how did this evolve?". Not CI- or TA-specific.

CREATE TABLE IF NOT EXISTS scenario_probability_history (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_id             UUID NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
    prev_prob               REAL,                 -- NULL on first calibration
    new_prob                REAL,                 -- NULL when cleared to uncalibrated
    delta                   REAL,                 -- new - prev (NULL if either side NULL)
    triggering_signal_ids   UUID[] NOT NULL DEFAULT '{}',
    method                  TEXT NOT NULL DEFAULT 'ewma_calibration',
    note                    TEXT,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CHECK (prev_prob IS NULL OR (prev_prob >= 0 AND prev_prob <= 1)),
    CHECK (new_prob  IS NULL OR (new_prob  >= 0 AND new_prob  <= 1))
);

CREATE INDEX IF NOT EXISTS idx_scenario_prob_history_scenario
    ON scenario_probability_history (scenario_id, created_at DESC);
