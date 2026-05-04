-- Migration 049: Decision Ledger (SPEC-021 Phase C)
--
-- A decision is a promoted war-room round: the moment a hypothesis
-- becomes a commitment with owner, deadline, and target outcome.
--
-- Decisions outlive their source room (FKs are ON DELETE SET NULL).
-- Snapshots of move_type/move_payload/confidence are taken at promotion
-- time so the ledger entry is immutable even if the source is changed.
--
-- Phase D's outcome columns (actual_outcome, calibration_score) are
-- defined now (NULL-able) so D doesn't need its own migration.
--
-- Migration is additive + idempotent. Safe to re-run.

CREATE TABLE IF NOT EXISTS decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Provenance — survive room deletion via SET NULL
    war_room_round_id UUID REFERENCES war_room_rounds(id) ON DELETE SET NULL,
    war_room_id       UUID REFERENCES war_rooms(id)       ON DELETE SET NULL,
    source_signal_id  UUID REFERENCES signals(id)         ON DELETE SET NULL,

    -- Snapshot at promotion time
    title             TEXT NOT NULL,
    rationale         TEXT,
    move_type         TEXT NOT NULL,
    move_payload_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,

    owner_user_id      UUID REFERENCES users(id) ON DELETE SET NULL,
    owner_display_name TEXT NOT NULL,

    -- The expected frame
    target_metric     TEXT,
    target_value      TEXT,
    deadline          DATE,
    confidence_at_commit REAL
        CHECK (confidence_at_commit IS NULL OR confidence_at_commit BETWEEN 0.0 AND 1.0),

    status TEXT NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'in_progress', 'verified', 'missed', 'cancelled')),

    -- Phase D fields — defined now to avoid a follow-on migration
    actual_outcome    TEXT,
    actual_outcome_recorded_at TIMESTAMPTZ,
    calibration_score REAL
        CHECK (calibration_score IS NULL OR calibration_score BETWEEN 0.0 AND 1.0),

    notes TEXT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_decisions_owner
    ON decisions (owner_user_id, status);

CREATE INDEX IF NOT EXISTS idx_decisions_room
    ON decisions (war_room_id) WHERE war_room_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_decisions_round
    ON decisions (war_room_round_id) WHERE war_room_round_id IS NOT NULL;

-- Partial index optimized for the "what decisions are overdue" query
CREATE INDEX IF NOT EXISTS idx_decisions_deadline
    ON decisions (deadline)
    WHERE deadline IS NOT NULL AND status IN ('open', 'in_progress');

COMMENT ON TABLE decisions IS
    'SPEC-021 Phase C decision ledger. A promoted war-room round = a '
    'committed strategic decision with owner, deadline, expected '
    'outcome. Outlives source room (FK SET NULL). Phase D fills in '
    'actual_outcome + calibration_score from outcome detection.';

COMMENT ON COLUMN decisions.confidence_at_commit IS
    'Mean confidence_score across the source round''s reactions, '
    'snapshotted at promotion time. Used in Phase D as the predicted '
    'value for prediction-error calculations.';

COMMENT ON COLUMN decisions.move_payload_snapshot IS
    'Frozen copy of the war_room_round.move_payload at promotion time. '
    'Source round can be edited later; the ledger entry is immutable.';
