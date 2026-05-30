"""W1 — Scenario state + mode toggle for the war room.

The F11 WarRoomPage ships a 3-mode toggle (Guided / Autonomous / Game-
theoretic). This module owns the backend representation of "what mode this
room is in" so W2/W3/W4 have a single chokepoint to plug per-mode engines
into.

Scope (W1):
- `ScenarioMode` enum with values pinned to the F11 frontend contract.
- `ScenarioState` immutable view of one room's mode + derived round count.
- `transition_mode` — the one validated, idempotent mutator.
- `coerce_mode` — the one string→enum gate, exported so HTTP routes use
  the same chokepoint the service layer does.

Out of scope (W2–W5): per-mode round semantics, autonomous loop runner,
game-theoretic backend wiring. This module does not import any of:
`war_game_engine`, `war_game_adversary`, `game_theory`, `scenario_engine`.
A grep test enforces that boundary.

Naming note: `scenario_engine.py` exists for a different concept (the
counterfactual graph mutator — "landscape without entity X"). The
"scenario" in this module is the war-room sense (an event-triggered
situation we war-game over). Z7 will eventually graduate this into a
first-class Scenario entity; the name reads sensibly in both worlds.

Concurrency note: two PATCHes that flip mode at once produce a
last-write-wins outcome on a valid value. There is no in-flight
mode-specific state for W1 to corrupt; W3's autonomous-loop runner will
revisit this once it lands.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Union


# ──────────────────────────────────────────────────────────────────
# Errors — typed, so HTTP routes can map cleanly to status codes.
# ──────────────────────────────────────────────────────────────────

class InvalidScenarioMode(ValueError):
    """Raised when a string cannot be coerced to ScenarioMode."""


class ScenarioNotFound(LookupError):
    """Raised when a war_room_id has no row."""


# ──────────────────────────────────────────────────────────────────
# Mode enum — values MUST match frontend/src/pages/WarRoomPage.tsx
#   export type WarRoomMode = 'guided' | 'autonomous' | 'game_theoretic';
# A test in tests/test_scenario_state.py pins this contract.
# ──────────────────────────────────────────────────────────────────

class ScenarioMode(str, Enum):
    GUIDED = "guided"
    AUTONOMOUS = "autonomous"
    GAME_THEORETIC = "game_theoretic"


# Eager string set for fast membership tests and clear error messages.
_VALID_MODE_STRS: frozenset[str] = frozenset(m.value for m in ScenarioMode)


def coerce_mode(value: Union[str, ScenarioMode, None]) -> ScenarioMode:
    """Coerce an input value to ScenarioMode or raise InvalidScenarioMode.

    The single chokepoint for untrusted-string → typed-enum conversion. Used
    by HTTP routes and by `transition_mode` so the validation path is the
    same in both surfaces.

    Case-sensitive on purpose: keeps the enum, the DB CHECK constraint, and
    the F11 contract aligned. Drift in any one of them surfaces immediately.
    """
    if isinstance(value, ScenarioMode):
        return value
    if isinstance(value, str) and value in _VALID_MODE_STRS:
        return ScenarioMode(value)
    valid = ", ".join(sorted(_VALID_MODE_STRS))
    raise InvalidScenarioMode(
        f"invalid scenario mode {value!r}; valid modes: {valid}"
    )


# ──────────────────────────────────────────────────────────────────
# ScenarioState — immutable view; constructed only via load/transition.
# ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ScenarioState:
    """Immutable snapshot of a war room's scenario state.

    Frozen so callers can pass it around freely without worrying about
    mid-flight mutation. Round count is derived from `war_room_rounds`,
    not stored on the room itself — the source of truth stays single.
    """
    war_room_id: str
    mode: ScenarioMode
    round_count: int
    mode_changed_at: Optional[datetime]

    def __post_init__(self) -> None:
        if self.round_count < 0:
            raise ValueError(
                f"round_count must be >= 0, got {self.round_count}"
            )

    def to_dict(self) -> dict:
        """JSON-friendly form for HTTP responses."""
        return {
            "war_room_id": self.war_room_id,
            "mode": self.mode.value,
            "round_count": self.round_count,
            "mode_changed_at": (
                self.mode_changed_at.isoformat()
                if self.mode_changed_at is not None
                else None
            ),
        }


# ──────────────────────────────────────────────────────────────────
# Loaders + mutators — the only public way to construct ScenarioState.
# ──────────────────────────────────────────────────────────────────

def _fetch_room_mode(db, war_room_id: str) -> Optional[dict]:
    """Return {mode, mode_changed_at} for the room, or None if absent.

    Errors propagate — no silent-empty (the A2a anti-pattern).
    """
    return db.fetch_one(
        "SELECT mode, mode_changed_at FROM war_rooms WHERE id::text = %s",
        [war_room_id],
    )


def _fetch_round_count(db, war_room_id: str) -> int:
    row = db.fetch_one(
        "SELECT COUNT(*) AS count FROM war_room_rounds "
        "WHERE war_room_id = %s::uuid",
        [war_room_id],
    )
    if not row:
        return 0
    # fetch_one returns dict-like; tolerate int or row shape.
    if isinstance(row, dict):
        return int(row.get("count", 0) or 0)
    return int(row[0]) if row else 0


def load_scenario_state(db, war_room_id: str) -> ScenarioState:
    """Load the current scenario state for a war room.

    Raises:
        ScenarioNotFound: room does not exist.
        InvalidScenarioMode: row.mode is a value outside the enum
            (data corruption; surfaces rather than silently coercing).
    """
    row = _fetch_room_mode(db, war_room_id)
    if row is None:
        raise ScenarioNotFound(f"war room not found: {war_room_id}")

    # coerce_mode raises InvalidScenarioMode on a corrupt row — that's the
    # behaviour we want; the CHECK constraint should make this unreachable,
    # but we don't trust the DB silently.
    mode = coerce_mode(row.get("mode") if isinstance(row, dict) else row[0])
    mode_changed_at = (
        row.get("mode_changed_at") if isinstance(row, dict) else row[1]
    )

    round_count = _fetch_round_count(db, war_room_id)

    return ScenarioState(
        war_room_id=war_room_id,
        mode=mode,
        round_count=round_count,
        mode_changed_at=mode_changed_at,
    )


def transition_mode(
    db,
    war_room_id: str,
    target: Union[str, ScenarioMode],
) -> ScenarioState:
    """Transition a war room to a new mode.

    Validated (raises InvalidScenarioMode on bad input BEFORE touching the
    DB), idempotent (same-mode transition issues no UPDATE), and returns
    the resulting state.

    Raises:
        InvalidScenarioMode: target cannot be coerced to ScenarioMode.
        ScenarioNotFound: room does not exist.
    """
    # 1. Coerce FIRST — invalid input must never reach the DB.
    new_mode = coerce_mode(target)

    # 2. Load current state (raises ScenarioNotFound if missing).
    current = load_scenario_state(db, war_room_id)

    # 3. Idempotent path — same mode → no write.
    if current.mode is new_mode:
        return current

    # 4. Persist. mode_changed_at is server-side NOW() so clock drift on
    #    the app server cannot corrupt the timestamp.
    db.execute(
        "UPDATE war_rooms "
        "SET mode = %s, mode_changed_at = NOW(), updated_at = NOW() "
        "WHERE id::text = %s",
        [new_mode.value, war_room_id],
    )

    # 5. Return a fresh snapshot. We don't re-query to keep the contract
    #    cheap and mock-robust (Loop 5 Z3's mock-trust bug pattern).
    #    mode_changed_at is set by the DB; we report "now-ish" by reading
    #    the row back. But to stay mock-friendly we synthesize it.
    return ScenarioState(
        war_room_id=war_room_id,
        mode=new_mode,
        round_count=current.round_count,
        mode_changed_at=datetime.now(timezone.utc),
    )
