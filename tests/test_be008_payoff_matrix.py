"""BE-8 — payoff matrix composer tests."""

from __future__ import annotations

import pytest


# ════════════════════════════════════════════════════════════════════
# build_payoff_matrix
# ════════════════════════════════════════════════════════════════════

class TestBuildPayoffMatrix:
    def test_2x2_grid_shape(self):
        from services.simulation.payoff import build_payoff_matrix

        runs = {
            ("launch", "aggressive"):    {"delta_pct":  6.4, "confidence": 0.71},
            ("launch", "defensive"):     {"delta_pct": -2.1, "confidence": 0.62},
            ("hold",   "aggressive"):    {"delta_pct":  1.2, "confidence": 0.55},
            ("hold",   "defensive"):     {"delta_pct": -3.4, "confidence": 0.48},
        }

        def runner(*, war_room_id, our_move, adversary_state, samples):
            return runs[(our_move, adversary_state)]

        out = build_payoff_matrix(
            our_moves=["launch", "hold"],
            adversary_states=["aggressive", "defensive"],
            bayesian_runner=runner,
            war_room_id="wr-1",
        )
        assert len(out["cells"]) == 2
        assert all(len(r) == 2 for r in out["cells"])
        # Highest delta×conf is launch+aggressive (6.4 * 0.71 ≈ 4.54)
        assert out["recommended_cell"] == [0, 0]
        assert out["cells"][0][0]["recommended"] is True
        # Other cells must NOT be marked recommended
        assert out["cells"][0][1]["recommended"] is False
        assert out["cells"][1][0]["recommended"] is False

    def test_3x3_grid_shape_and_nash(self):
        """PB-H12 — 3×3 grid with a maximin Nash cell + reasoning."""
        from services.simulation.payoff import build_payoff_matrix

        # Row 'partner' has the best worst-case (its min is +1.0, beating
        # 'launch' min -2.0 and 'hold' min -3.0) → it's the security pick.
        runs = {
            ("launch",  "defend"):   {"delta_pct":  6.0, "confidence": 0.7},
            ("launch",  "cede"):     {"delta_pct":  4.0, "confidence": 0.7},
            ("launch",  "escalate"): {"delta_pct": -2.0, "confidence": 0.6},
            ("hold",    "defend"):   {"delta_pct":  1.0, "confidence": 0.6},
            ("hold",    "cede"):     {"delta_pct":  2.0, "confidence": 0.6},
            ("hold",    "escalate"): {"delta_pct": -3.0, "confidence": 0.6},
            ("partner", "defend"):   {"delta_pct":  3.0, "confidence": 0.8},
            ("partner", "cede"):     {"delta_pct":  2.0, "confidence": 0.8},
            ("partner", "escalate"): {"delta_pct":  1.0, "confidence": 0.8},
        }

        def runner(*, war_room_id, our_move, adversary_state, samples):
            return runs[(our_move, adversary_state)]

        out = build_payoff_matrix(
            our_moves=["launch", "hold", "partner"],
            adversary_states=["defend", "cede", "escalate"],
            bayesian_runner=runner,
            war_room_id="wr-3",
        )
        assert len(out["cells"]) == 3
        assert all(len(r) == 3 for r in out["cells"])
        # Security (maximin) pick = partner vs escalate (worst case +1.0).
        assert out["nash_cell"] == [2, 2]
        assert out["cells"][2][2]["nash"] is True
        assert "security equilibrium" in out["nash_reasoning"].lower()
        # Expected-value pick is still launch+defend (6.0 × 0.7 = 4.2).
        assert out["recommended_cell"] == [0, 0]

    def test_invalid_dim_raises(self):
        from services.simulation.payoff import build_payoff_matrix
        with pytest.raises(ValueError, match=r"2\.\.5"):
            build_payoff_matrix(
                our_moves=["a"],                       # < 2 → invalid
                adversary_states=["x", "y"],
                bayesian_runner=lambda **kw: {},
                war_room_id="wr",
            )
        with pytest.raises(ValueError, match=r"2\.\.5"):
            build_payoff_matrix(
                our_moves=["a", "b", "c", "d", "e", "f"],  # > 5 → invalid
                adversary_states=["x", "y"],
                bayesian_runner=lambda **kw: {},
                war_room_id="wr",
            )

    def test_runner_failure_yields_zero_cell(self):
        from services.simulation.payoff import build_payoff_matrix

        def boom(**kw):
            raise RuntimeError("sim failed")

        out = build_payoff_matrix(
            our_moves=["a", "b"],
            adversary_states=["x", "y"],
            bayesian_runner=boom,
            war_room_id="wr",
        )
        # All cells default to delta_pct=0, confidence=0.5
        for row in out["cells"]:
            for cell in row:
                assert cell["delta_pct"] == 0.0
                assert cell["confidence"] == 0.5

    def test_score_uses_delta_times_confidence(self):
        """A high-confidence modest gain beats a low-confidence wild swing."""
        from services.simulation.payoff import build_payoff_matrix

        runs = {
            ("modest", "x"): {"delta_pct": 3.0, "confidence": 0.95},   # score 2.85
            ("modest", "y"): {"delta_pct": 0.0, "confidence": 0.5},
            ("wild",   "x"): {"delta_pct": 9.0, "confidence": 0.30},   # score 2.70
            ("wild",   "y"): {"delta_pct": 0.0, "confidence": 0.5},
        }
        def runner(*, war_room_id, our_move, adversary_state, samples):
            return runs[(our_move, adversary_state)]

        out = build_payoff_matrix(
            our_moves=["modest", "wild"],
            adversary_states=["x", "y"],
            bayesian_runner=runner,
            war_room_id="wr",
        )
        # 'modest, x' wins (2.85 > 2.70)
        assert out["recommended_cell"] == [0, 0]
