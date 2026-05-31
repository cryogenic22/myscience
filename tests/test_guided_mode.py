"""W2 — unit tests for the Guided-mode gate.

The gate is one exception + one function. Tests cover:
- accepts ScenarioMode.GUIDED (str + enum)
- rejects ScenarioMode.AUTONOMOUS (str + enum)
- rejects ScenarioMode.GAME_THEORETIC (str + enum)
- error message contains current mode AND target ('guided')
- exception carries the current_mode attribute for callers that want
  to render mode-aware messages without re-parsing the string
"""
from __future__ import annotations

import pytest

from services.guided_mode import GuidedModeBlocked, assert_guided
from services.scenario_state import ScenarioMode


class TestAssertGuided:
    def test_passes_for_guided_enum(self):
        # Must not raise.
        assert_guided(ScenarioMode.GUIDED)

    def test_passes_for_guided_string(self):
        assert_guided("guided")

    def test_blocks_autonomous_enum(self):
        with pytest.raises(GuidedModeBlocked) as exc:
            assert_guided(ScenarioMode.AUTONOMOUS)
        assert exc.value.current_mode is ScenarioMode.AUTONOMOUS

    def test_blocks_autonomous_string(self):
        with pytest.raises(GuidedModeBlocked):
            assert_guided("autonomous")

    def test_blocks_game_theoretic_enum(self):
        with pytest.raises(GuidedModeBlocked) as exc:
            assert_guided(ScenarioMode.GAME_THEORETIC)
        assert exc.value.current_mode is ScenarioMode.GAME_THEORETIC

    def test_blocks_game_theoretic_string(self):
        with pytest.raises(GuidedModeBlocked):
            assert_guided("game_theoretic")

    def test_error_message_is_operator_actionable(self):
        # Must name the current mode AND the target ('guided') so the
        # operator knows what to do without reading the source.
        with pytest.raises(GuidedModeBlocked) as exc:
            assert_guided(ScenarioMode.AUTONOMOUS)
        msg = str(exc.value)
        assert "autonomous" in msg
        assert "guided" in msg

    def test_rejects_invalid_mode_string_with_typed_error(self):
        # Untrusted strings get the same chokepoint as elsewhere; the
        # error here is `InvalidScenarioMode` (from coerce_mode), not
        # `GuidedModeBlocked` — different cause, different remediation.
        from services.scenario_state import InvalidScenarioMode
        with pytest.raises(InvalidScenarioMode):
            assert_guided("nope")


class TestGuidedModeBlockedException:
    def test_carries_current_mode_attribute(self):
        try:
            assert_guided(ScenarioMode.GAME_THEORETIC)
        except GuidedModeBlocked as exc:
            assert hasattr(exc, "current_mode")
            assert exc.current_mode is ScenarioMode.GAME_THEORETIC
        else:
            pytest.fail("GuidedModeBlocked was not raised")

    def test_is_an_exception_subclass(self):
        # Catchable by `except Exception`. Routes that wrap with
        # try/except Exception (defensive) still see it.
        assert issubclass(GuidedModeBlocked, Exception)
