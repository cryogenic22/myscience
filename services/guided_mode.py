"""W2 — Guided-mode gate for the war room.

The F11 WarRoomPage exposes three modes (Guided / Autonomous / Game-
theoretic). W1 added the `ScenarioMode` enum and persisted the toggle.
This module adds the *structural* invariant: round submission and move
suggestion are Guided-mode-only. Calling them in autonomous or game-
theoretic mode raises `GuidedModeBlocked` (HTTP 409 at the route layer).

Without this gate, the mode toggle is advisory — the operator can flip
to "autonomous" and still submit human moves, breaking the F11 promise
that the three modes are first-class, not skins.

W3 will add `assert_autonomous` next to this; W4 `assert_game_theoretic`.
Each is a one-line state check; the engines stay separate.
"""
from __future__ import annotations

from typing import Union

from services.scenario_state import (
    ScenarioMode,
    coerce_mode,
)


class GuidedModeBlocked(Exception):
    """Raised when a Guided-only operation is attempted on a non-Guided room.

    Carries `current_mode` so HTTP routes (or future structured-error
    handlers) can render mode-aware messages without re-parsing the
    exception string.
    """
    def __init__(self, current_mode: ScenarioMode):
        self.current_mode = current_mode
        super().__init__(
            f"this operation is Guided-mode-only; room is currently in "
            f"{current_mode.value!r} mode — switch to guided to proceed"
        )


def assert_guided(mode: Union[str, ScenarioMode]) -> None:
    """Raise GuidedModeBlocked if `mode` is not GUIDED.

    Accepts a string or enum so callers can use whichever they have on
    hand. Untrusted strings still flow through `coerce_mode` first; a
    typo there raises `InvalidScenarioMode` (a different remediation than
    a mode-mismatch).
    """
    current = coerce_mode(mode)
    if current is not ScenarioMode.GUIDED:
        raise GuidedModeBlocked(current_mode=current)
