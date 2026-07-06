-- BE-14 · Delegated war-game runs.
--
-- PB-505 lets the user queue a scenario in the morning and read the
-- verdict with their coffee. We persist the queue here so the
-- scheduler executor (services/agent/delegation_executor.py) can
-- pick it up.

CREATE TABLE IF NOT EXISTS delegated_runs (
    run_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requested_by     UUID NOT NULL,
    war_room_id      UUID,
    scenario_kind    TEXT NOT NULL,
    parameters       JSONB NOT NULL DEFAULT '{}'::jsonb,
    wake_at          TIMESTAMPTZ NOT NULL,
    status           TEXT NOT NULL DEFAULT 'queued'
                     CHECK (status IN ('queued','running','complete','failed','cancelled')),
    result           JSONB,
    error_message    TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    started_at       TIMESTAMPTZ,
    completed_at     TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_delegated_runs_due
    ON delegated_runs (status, wake_at)
    WHERE status = 'queued';

CREATE INDEX IF NOT EXISTS idx_delegated_runs_user
    ON delegated_runs (requested_by, created_at DESC);
