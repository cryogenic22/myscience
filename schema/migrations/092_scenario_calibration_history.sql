-- Migration 092: scenario_calibration_history (Helix FS-1 / OQ2 / gap H-b)
--
-- The calibration loop (PB-H14, services/scenario_calibration.py) re-weights a
-- scenario's prior into a current probability as signals land — and since the
-- signal-stance loop (#223) it can move BOTH ways (a negative rival signal
-- refutes a competitive-pressure scenario). But it stored only the latest
-- current_prob + a note: the *tape* of how the probability moved, and why, was
-- lost. The Helix red-team requires "every scenario probability change has an
-- audit row" (OQ2). This table is that append-only tape.
--
-- One row per ACTUAL move (idempotent recomputes that don't change the value
-- write nothing). prev/new/delta + the stance mix (how many corroborating vs
-- contradicting signals drove it) + the triggering signal make each move
-- explainable and replayable. Append-only: the loop only INSERTs.

BEGIN;

CREATE TABLE IF NOT EXISTS scenario_calibration_history (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scenario_id         UUID NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,

    -- The move. prev is the prior probability on the first calibration, then the
    -- previous current_prob thereafter; new is the recomputed current_prob.
    prev_prob           REAL CHECK (prev_prob IS NULL OR (prev_prob >= 0 AND prev_prob <= 1)),
    new_prob            REAL NOT NULL CHECK (new_prob >= 0 AND new_prob <= 1),
    delta               REAL NOT NULL,

    -- Why it moved: the stance mix (since #223) and the latest mover signal.
    n_supporting        INTEGER NOT NULL DEFAULT 0,
    n_contradicting     INTEGER NOT NULL DEFAULT 0,
    -- Latest mover; FK-soft (SET NULL) so signal pruning never orphans the tape.
    triggering_signal_id UUID REFERENCES signals(id) ON DELETE SET NULL,

    method              TEXT NOT NULL DEFAULT 'ewma_stance',
    calibration_note    TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Read pattern: a scenario's tape, newest first.
CREATE INDEX IF NOT EXISTS idx_scenario_calib_history
    ON scenario_calibration_history (scenario_id, created_at DESC);

COMMENT ON TABLE scenario_calibration_history IS
    'Append-only audit tape of scenario probability moves (Helix OQ2 / gap H-b). '
    'One row per actual change; idempotent recomputes write nothing.';

COMMIT;
