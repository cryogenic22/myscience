-- Migration 039: clinical_trials.status_history JSONB
--
-- SPEC-016 §7 swimlane A1, task A1.3.
--
-- Adds the append-only history of (status, phase, primary_completion_date)
-- snapshots per trial. The A3.1 diff service appends entries when CT.gov
-- reports a change. Each entry is read by:
--   - The intel layer's clustering service (to anchor trial_status_change events)
--   - Signal Detail UI's "history strip" component
--   - The pattern detector (e.g. "trial slipped completion 3+ times")
--
-- Entry shape:
--   {
--     "status": "...",
--     "phase": "..." | null,
--     "primary_completion_date": "YYYY-MM-DD" | null,
--     "observed_at": "YYYY-MM-DDTHH:MM:SS+00:00",
--     "source_document_id": "<uuid>" | null
--   }

BEGIN;

ALTER TABLE clinical_trials
    ADD COLUMN IF NOT EXISTS status_history JSONB NOT NULL DEFAULT '[]'::jsonb;

COMMENT ON COLUMN clinical_trials.status_history IS
    'Append-only array of (status, phase, primary_completion_date) snapshots. '
    'Maintained by services/trial_status_history.py + the A3.1 CT.gov diff '
    'connector. Each append corresponds to exactly one trial_status_change '
    'market_event.';

-- GIN index for jsonb path queries (e.g. "@? $[*].status == \"Terminated\"")
CREATE INDEX IF NOT EXISTS idx_trials_status_history
    ON clinical_trials USING GIN (status_history);

-- ============================================================
-- Backfill: every existing trial gets one history entry capturing
-- its current state. Gives the diff service a baseline.
-- ============================================================

UPDATE clinical_trials t
SET status_history = jsonb_build_array(
    jsonb_build_object(
        'status', t.status,
        'phase', t.phase,
        'primary_completion_date',
            CASE
                WHEN t.completion_date IS NOT NULL
                THEN to_char(t.completion_date, 'YYYY-MM-DD')
                ELSE NULL
            END,
        'observed_at', to_char(NOW() AT TIME ZONE 'UTC',
                               'YYYY-MM-DD"T"HH24:MI:SS+00:00'),
        'source_document_id', NULL
    )
)
WHERE jsonb_array_length(status_history) = 0;

COMMIT;
