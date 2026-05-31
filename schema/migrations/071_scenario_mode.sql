-- Migration 071: scenario mode on war_rooms (W1)
--
-- The F11 WarRoomPage ships a 3-mode toggle (Guided / Autonomous /
-- Game-theoretic). Before this migration, the backend had no
-- representation of "what mode this room is in". W2/W3/W4 plug their
-- per-mode engines off this column.
--
-- Default 'guided' so existing rooms keep their current implicit semantics
-- (round submission → competitor reaction generation, which is the Guided
-- flow). The CHECK constraint mirrors the ScenarioMode enum in
-- services/scenario_state.py — a test pins the alignment.
--
-- mode_changed_at is set by transition_mode() via NOW(); rooms that
-- never transitioned (e.g. all pre-W1 rooms, plus W1-era rooms that
-- stayed in GUIDED) leave it NULL.
--
-- Partial index on non-default modes: GUIDED is the overwhelming majority
-- so a full index on `mode` is a waste; analytics only ever cares about
-- the explicit non-default transitions.

BEGIN;

ALTER TABLE war_rooms
    ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'guided'
        CHECK (mode IN ('guided', 'autonomous', 'game_theoretic'));

ALTER TABLE war_rooms
    ADD COLUMN IF NOT EXISTS mode_changed_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_war_rooms_mode
    ON war_rooms (mode)
    WHERE mode != 'guided';

COMMIT;
