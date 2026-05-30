"""W1 — tests for the scenario state + mode toggle.

The F11 WarRoomPage ships a 3-mode toggle (Guided / Autonomous / Game-
theoretic). Before W1 the backend had no representation of the toggle.
This module owns the state, the chokepoint that mutates it, and the
typed errors HTTP routes lean on.

Tests cover:
- The 5-step acceptance contract from SPEC_W1
- The F11 enum value pinning (so a rename forces a coordinated change)
- All public surface paths (coerce, load, transition) and their failure modes
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from services.scenario_state import (
    InvalidScenarioMode,
    ScenarioMode,
    ScenarioNotFound,
    ScenarioState,
    coerce_mode,
    load_scenario_state,
    transition_mode,
)


# ──────────────────────────────────────────────────────────────────
# Fixtures — a MagicMock DB shaped like a war_rooms row.
# ──────────────────────────────────────────────────────────────────

def _room_row(mode="guided", mode_changed_at=None):
    return {
        "id": "room-1",
        "mode": mode,
        "mode_changed_at": mode_changed_at,
    }


def _make_db(*, room=None, round_count=0):
    """Return a MagicMock DB whose fetch_one returns the room row.

    `fetch_one` is also used for the round-count probe. The selector branches
    on whether the SQL contains 'count' to disambiguate.
    """
    db = MagicMock()

    def fetch_one(sql, params=None):
        s = sql.lower()
        if "count" in s and "war_room_rounds" in s:
            return {"count": round_count}
        if "war_rooms" in s:
            return room
        return None

    db.fetch_one = MagicMock(side_effect=fetch_one)
    db.execute = MagicMock()
    return db


# ──────────────────────────────────────────────────────────────────
# ScenarioMode enum — pin the F11 contract
# ──────────────────────────────────────────────────────────────────

class TestScenarioModeContract:
    def test_values_match_f11_frontend_contract(self):
        # Source of truth: frontend/src/pages/WarRoomPage.tsx
        #   export type WarRoomMode = 'guided' | 'autonomous' | 'game_theoretic';
        assert {m.value for m in ScenarioMode} == {
            "guided",
            "autonomous",
            "game_theoretic",
        }

    def test_enum_is_str_subclass_for_json_serialization(self):
        # FastAPI/JSON need the enum to round-trip as a plain string.
        assert isinstance(ScenarioMode.GUIDED, str)
        assert ScenarioMode.GUIDED == "guided"


# ──────────────────────────────────────────────────────────────────
# coerce_mode — single string→enum chokepoint
# ──────────────────────────────────────────────────────────────────

class TestCoerceMode:
    def test_accepts_known_strings(self):
        assert coerce_mode("guided") is ScenarioMode.GUIDED
        assert coerce_mode("autonomous") is ScenarioMode.AUTONOMOUS
        assert coerce_mode("game_theoretic") is ScenarioMode.GAME_THEORETIC

    def test_accepts_enum_passthrough(self):
        assert coerce_mode(ScenarioMode.AUTONOMOUS) is ScenarioMode.AUTONOMOUS

    def test_rejects_unknown_string(self):
        with pytest.raises(InvalidScenarioMode):
            coerce_mode("nope")

    def test_rejects_none(self):
        with pytest.raises(InvalidScenarioMode):
            coerce_mode(None)  # type: ignore[arg-type]

    def test_rejects_case_drift(self):
        # 'GUIDED' is not a valid mode; case-sensitivity is intentional
        # so the DB CHECK constraint and the enum stay aligned.
        with pytest.raises(InvalidScenarioMode):
            coerce_mode("GUIDED")

    def test_error_message_lists_valid_modes(self):
        with pytest.raises(InvalidScenarioMode) as exc:
            coerce_mode("xyz")
        msg = str(exc.value)
        # All three values must appear in the message so the operator
        # sees the contract immediately.
        assert "guided" in msg
        assert "autonomous" in msg
        assert "game_theoretic" in msg


# ──────────────────────────────────────────────────────────────────
# load_scenario_state
# ──────────────────────────────────────────────────────────────────

class TestLoadScenarioState:
    def test_returns_state_with_default_mode(self):
        db = _make_db(room=_room_row(mode="guided"), round_count=0)
        state = load_scenario_state(db, "room-1")
        assert state.war_room_id == "room-1"
        assert state.mode is ScenarioMode.GUIDED
        assert state.round_count == 0
        assert state.mode_changed_at is None

    def test_returns_state_with_explicit_mode_and_changed_at(self):
        now = datetime(2026, 5, 30, 12, 0, tzinfo=timezone.utc)
        db = _make_db(
            room=_room_row(mode="autonomous", mode_changed_at=now),
            round_count=3,
        )
        state = load_scenario_state(db, "room-1")
        assert state.mode is ScenarioMode.AUTONOMOUS
        assert state.round_count == 3
        assert state.mode_changed_at == now

    def test_raises_scenario_not_found_on_missing_room(self):
        db = _make_db(room=None)
        with pytest.raises(ScenarioNotFound) as exc:
            load_scenario_state(db, "missing-room")
        assert "missing-room" in str(exc.value)

    def test_raises_on_corrupt_mode_value(self):
        # A row that somehow violates the CHECK constraint must NOT be
        # silently coerced to a default. Surfaces the corruption.
        db = _make_db(room=_room_row(mode="not_a_real_mode"))
        with pytest.raises(InvalidScenarioMode):
            load_scenario_state(db, "room-1")

    def test_does_not_swallow_db_errors(self):
        # Mirrors the A2a/facts_ledger anti-pattern: a thrown DB error
        # must propagate, not get rewritten as "room not found".
        db = MagicMock()
        db.fetch_one = MagicMock(side_effect=RuntimeError("connection lost"))
        with pytest.raises(RuntimeError, match="connection lost"):
            load_scenario_state(db, "room-1")


# ──────────────────────────────────────────────────────────────────
# transition_mode — the validated, idempotent chokepoint
# ──────────────────────────────────────────────────────────────────

class TestTransitionMode:
    def test_writes_mode_and_returns_updated_state(self):
        db = _make_db(room=_room_row(mode="guided"))
        new = transition_mode(db, "room-1", ScenarioMode.AUTONOMOUS)
        assert new.mode is ScenarioMode.AUTONOMOUS
        assert new.war_room_id == "room-1"
        # The UPDATE must have been issued.
        assert db.execute.called, "transition_mode did not write to DB"
        sql = " ".join(str(c.args[0]).lower() for c in db.execute.call_args_list)
        assert "update war_rooms" in sql
        assert "mode = " in sql
        assert "mode_changed_at" in sql, (
            "mode_changed_at must be stamped on transition"
        )

    def test_accepts_string_input_via_coerce(self):
        db = _make_db(room=_room_row(mode="guided"))
        new = transition_mode(db, "room-1", "game_theoretic")
        assert new.mode is ScenarioMode.GAME_THEORETIC

    def test_rejects_invalid_string_at_door(self):
        db = _make_db(room=_room_row(mode="guided"))
        with pytest.raises(InvalidScenarioMode):
            transition_mode(db, "room-1", "nope")
        # Must NOT have touched the DB after rejecting input.
        assert not db.execute.called

    def test_idempotent_same_mode_no_write(self):
        db = _make_db(room=_room_row(mode="autonomous"))
        state = transition_mode(db, "room-1", ScenarioMode.AUTONOMOUS)
        assert state.mode is ScenarioMode.AUTONOMOUS
        # Same-mode transition is a no-op; no UPDATE issued.
        assert db.execute.call_count == 0

    def test_raises_scenario_not_found(self):
        db = _make_db(room=None)
        with pytest.raises(ScenarioNotFound):
            transition_mode(db, "missing-room", ScenarioMode.GUIDED)
        # And no DB write attempt.
        assert not db.execute.called


# ──────────────────────────────────────────────────────────────────
# ScenarioState dataclass invariants
# ──────────────────────────────────────────────────────────────────

class TestScenarioStateDataclass:
    def test_is_frozen(self):
        s = ScenarioState(
            war_room_id="r1",
            mode=ScenarioMode.GUIDED,
            round_count=0,
            mode_changed_at=None,
        )
        with pytest.raises(Exception):
            # Frozen dataclasses raise FrozenInstanceError on assignment.
            s.mode = ScenarioMode.AUTONOMOUS  # type: ignore[misc]

    def test_round_count_cannot_be_negative(self):
        with pytest.raises(ValueError, match="round_count"):
            ScenarioState(
                war_room_id="r1",
                mode=ScenarioMode.GUIDED,
                round_count=-1,
                mode_changed_at=None,
            )


# ──────────────────────────────────────────────────────────────────
# Acceptance test — the SPEC_W1 5-step contract in one shot
# ──────────────────────────────────────────────────────────────────

def test_acceptance_w1_full_contract():
    # 1. Default mode for a new war room is guided.
    room = _room_row(mode="guided")
    db = _make_db(room=room, round_count=0)
    state = load_scenario_state(db, "room-1")
    assert state.mode is ScenarioMode.GUIDED

    # 2. Mode transition persists and returns the updated state.
    new = transition_mode(db, "room-1", ScenarioMode.AUTONOMOUS)
    assert new.mode is ScenarioMode.AUTONOMOUS
    assert new.war_room_id == "room-1"
    assert db.execute.call_count == 1  # one UPDATE issued

    # Simulate the DB now reflecting the new mode for the next read.
    room["mode"] = "autonomous"

    # 3. Idempotent — same mode returns unchanged state, no extra DB write.
    same = transition_mode(db, "room-1", ScenarioMode.AUTONOMOUS)
    assert same.mode is ScenarioMode.AUTONOMOUS
    assert db.execute.call_count == 1, "same-mode transition must be a no-op"

    # 4. Invalid mode (string from untrusted input) is rejected at the door.
    with pytest.raises(InvalidScenarioMode):
        transition_mode(db, "room-1", "nope")
    # The bad input must NOT have triggered a DB write.
    assert db.execute.call_count == 1

    # 5. Nonexistent room raises typed error (not a swallow-leak).
    db_empty = _make_db(room=None)
    with pytest.raises(ScenarioNotFound):
        load_scenario_state(db_empty, "missing-room")
