-- SPEC_023 — Decision Briefs: first-class framing object for the flywheel.
-- Promotes the framing layer into a structured object with state machine,
-- options, evidence refs, and stakeholder metadata. Unblocks the frontend
-- Decision Workspace and is a prerequisite for Framing Triggers (SPEC_029),
-- War-Game Adversaries (SPEC_028), and Decision signing.

-- ─── decision_briefs ─────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS decision_briefs (
    brief_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question              TEXT NOT NULL CHECK (char_length(question) BETWEEN 1 AND 2000),
    trigger_kind          TEXT NOT NULL DEFAULT 'manual'
                          CHECK (trigger_kind IN ('manual','threshold','cluster','calendar')),
    trigger_signal_ids    UUID[] NOT NULL DEFAULT '{}',
    trigger_metadata      JSONB NOT NULL DEFAULT '{}'::jsonb,
    stakeholders          TEXT[] NOT NULL DEFAULT '{}',
    time_horizon_days     INTEGER CHECK (time_horizon_days IS NULL OR time_horizon_days > 0),
    evidence_refs         JSONB NOT NULL DEFAULT '[]'::jsonb,
    constraints           TEXT[] NOT NULL DEFAULT '{}',
    success_criteria      TEXT,
    confidence_to_proceed REAL CHECK (confidence_to_proceed IS NULL OR (confidence_to_proceed >= 0 AND confidence_to_proceed <= 1)),
    state                 TEXT NOT NULL DEFAULT 'draft'
                          CHECK (state IN ('draft','human_review','simulation_pending','simulation_complete','decision_pending','committed','in_review','closed')),
    owner_user_id         UUID,
    war_room_id           UUID,
    decision_id           UUID,
    archived_at           TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_briefs_state
    ON decision_briefs(state)
    WHERE archived_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_briefs_owner
    ON decision_briefs(owner_user_id)
    WHERE owner_user_id IS NOT NULL AND archived_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_briefs_war_room
    ON decision_briefs(war_room_id)
    WHERE war_room_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_briefs_created_at
    ON decision_briefs(created_at DESC);

-- ─── decision_brief_options ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS decision_brief_options (
    option_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brief_id           UUID NOT NULL REFERENCES decision_briefs(brief_id) ON DELETE CASCADE,
    ordinal            INTEGER NOT NULL CHECK (ordinal >= 1),
    label              TEXT NOT NULL CHECK (char_length(label) BETWEEN 1 AND 500),
    description        TEXT,
    predicted_outcome  TEXT,
    cost_estimate      TEXT,
    risk_notes         TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (brief_id, ordinal)
);

CREATE INDEX IF NOT EXISTS idx_brief_options_brief
    ON decision_brief_options(brief_id, ordinal);

-- ─── decision_brief_state_log ────────────────────────────────────────
-- Append-only audit trail for state transitions. Indexed by brief for fast
-- reasoning-trace rendering in the frontend Decision Workspace.
CREATE TABLE IF NOT EXISTS decision_brief_state_log (
    log_id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brief_id         UUID NOT NULL REFERENCES decision_briefs(brief_id) ON DELETE CASCADE,
    from_state       TEXT,
    to_state         TEXT NOT NULL,
    actor_user_id    UUID,
    reason           TEXT,
    transitioned_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_brief_state_log_brief
    ON decision_brief_state_log(brief_id, transitioned_at DESC);

-- ─── trigger to maintain updated_at ──────────────────────────────────
CREATE OR REPLACE FUNCTION decision_briefs_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_decision_briefs_updated_at ON decision_briefs;
CREATE TRIGGER trg_decision_briefs_updated_at
    BEFORE UPDATE ON decision_briefs
    FOR EACH ROW EXECUTE FUNCTION decision_briefs_set_updated_at();
