"""W3 / PB-H13 — autonomous war-game play engine tests (pure, no DB)."""
from __future__ import annotations

import pytest

from services.war_game_autonomous import DEFAULT_MOVES, MAX_ROUNDS, autoplay


def _stub_reactor(move_type, round_num, history):
    """Two rivals; the second is higher-confidence so it leads narration."""
    return [
        {"competitor_company_name": "RivalA", "reaction_type": "hold_position",
         "headline": f"A holds vs {move_type}", "confidence": 0.4},
        {"competitor_company_name": "RivalB", "reaction_type": "counter_launch",
         "headline": f"B counters {move_type}", "confidence": 0.8},
    ]


class TestAutoplay:
    def test_plays_n_rounds_with_narration(self):
        out = autoplay(our_moves=["trial_readout", "price_cut"], reactor=_stub_reactor, rounds=3)
        assert out["summary"]["rounds_played"] == 3
        assert len(out["rounds"]) == 3
        assert len(out["narration"]) == 3
        # Each round carries its move + reactions + a narration line.
        assert all(r["narration"] for r in out["rounds"])
        assert all(len(r["reactions"]) == 2 for r in out["rounds"])

    def test_cycles_through_the_move_catalog(self):
        out = autoplay(our_moves=["a", "b"], reactor=_stub_reactor, rounds=3)
        assert out["summary"]["moves"] == ["a", "b", "a"]

    def test_dominant_reaction_leads_narration(self):
        out = autoplay(our_moves=["trial_readout"], reactor=_stub_reactor, rounds=1)
        # RivalB (0.8) beats RivalA (0.4) → it leads the line.
        assert "RivalB" in out["narration"][0]
        assert "RivalA" not in out["narration"][0]

    def test_empty_moves_falls_back_to_defaults(self):
        out = autoplay(our_moves=[], reactor=_stub_reactor, rounds=2)
        assert out["summary"]["moves"] == list(DEFAULT_MOVES[:2])

    def test_no_reactions_yields_honest_line(self):
        out = autoplay(our_moves=["price_cut"], reactor=lambda *a: [], rounds=1)
        assert "no rival reaction" in out["narration"][0].lower()
        assert out["summary"]["total_reactions"] == 0

    def test_rounds_bounds_validated(self):
        with pytest.raises(ValueError, match=r"\[1, 8\]"):
            autoplay(our_moves=["a"], reactor=_stub_reactor, rounds=0)
        with pytest.raises(ValueError, match=r"\[1, 8\]"):
            autoplay(our_moves=["a"], reactor=_stub_reactor, rounds=MAX_ROUNDS + 1)

    def test_total_reactions_summed(self):
        out = autoplay(our_moves=["a"], reactor=_stub_reactor, rounds=4)
        assert out["summary"]["total_reactions"] == 8  # 2 per round × 4
