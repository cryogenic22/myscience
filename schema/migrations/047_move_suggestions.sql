-- Migration 047: move_suggestions audit trail (SPEC-021 Phase A.5)
--
-- Persists every batch of LLM-generated move suggestions. Used for:
--   - audit ("why did the system suggest these 3 moves on May 5?")
--   - prompt-version comparison when we tune the suggester
--   - Phase D learning loop ("which suggestions did the user actually pick?")
--
-- Each row is one batch of N ranked suggestions for a war room +
-- optional source signal context. The actual chosen move (if the user
-- runs one) lands in war_room_rounds.
--
-- Migration is additive. Idempotent via IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS move_suggestions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    war_room_id UUID NOT NULL REFERENCES war_rooms(id) ON DELETE CASCADE,
    source_signal_id UUID REFERENCES signals(id) ON DELETE SET NULL,
    suggestions JSONB NOT NULL,
    rule_version_id TEXT,
    requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_move_suggestions_room
    ON move_suggestions (war_room_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_move_suggestions_signal
    ON move_suggestions (source_signal_id)
    WHERE source_signal_id IS NOT NULL;

COMMENT ON TABLE move_suggestions IS
    'SPEC-021 A.5 audit trail. Every batch of LLM-suggested moves is '
    'persisted with prompt rule_version so we can correlate suggestions '
    'with downstream picks (war_room_rounds) for Phase D learning.';

COMMENT ON COLUMN move_suggestions.suggestions IS
    'Array of {move_type, move_payload, rationale, expected_impact_score, '
    'confidence_score, evidence_basis}. Rendered to UI as ranked cards.';
