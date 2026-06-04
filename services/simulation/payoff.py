"""BE-8 — 2x2 payoff matrix composer.

PB-501 renders a 2x2 cell grid showing delta% / confidence per
(our_move, adversary_state) pair plus a recommended-cell highlight.
Underlying simulation is ``services.game_theory.run_bayesian`` —
this composer just shapes its output for the UI.

Output shape::

    {
      "cells": [
        [{"delta_pct": 6.4, "confidence": 0.71, "recommended": True},
         {"delta_pct": -2.1, "confidence": 0.62, "recommended": False}],
        [{"delta_pct": 1.2, "confidence": 0.55, "recommended": False},
         {"delta_pct": -3.4, "confidence": 0.48, "recommended": False}],
      ],
      "recommended_cell": [0, 0]
    }
"""

from __future__ import annotations

import logging
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)


def _cell_from_run(run_payload: dict) -> dict:
    """Pluck (delta_pct, confidence) out of a single run_bayesian
    result."""
    delta = run_payload.get("delta_pct")
    if delta is None:
        # game_theory often returns expected_utility / posterior_mean —
        # convert to a percent change vs the baseline.
        baseline = run_payload.get("baseline_utility")
        scenario = run_payload.get("scenario_utility") or run_payload.get("expected_utility")
        if baseline not in (None, 0) and scenario is not None:
            try:
                delta = (float(scenario) - float(baseline)) / abs(float(baseline)) * 100.0
            except Exception:
                delta = 0.0
        else:
            delta = 0.0
    confidence = run_payload.get("confidence")
    if confidence is None:
        confidence = run_payload.get("posterior_confidence", 0.5)
    return {
        "delta_pct":   round(float(delta), 2),
        "confidence":  round(float(confidence), 3),
        "recommended": False,
        "nash":        False,
    }


MAX_DIM = 5  # bound the grid; 3x3 is the PB-H12 target, 2x2 the legacy default.


def build_payoff_matrix(
    *,
    our_moves: list[str],
    adversary_states: list[str],
    bayesian_runner,
    war_room_id: str,
    samples: int = 1200,
) -> dict:
    """Run the simulation N=samples per cell and return the N×N grid.

    ``bayesian_runner`` is a callable: (war_room_id, our_move,
    adversary_state, samples) -> dict. Defaults supplied by the caller
    (the route uses services.game_theory.run_bayesian).

    PB-H12 generalised this from a hard 2×2 to any [2, MAX_DIM] grid (3×3
    is the benchmark target). Two picks are returned:

    - ``recommended_cell`` — the optimistic expected-value pick
      (max delta_pct × confidence). Unchanged.
    - ``nash_cell`` — a security (maximin) equilibrium over the SAME
      grounded deltas: assuming the rival best-responds to suppress our
      gain, the move whose worst case is best. No NPV is fabricated (a
      real NPV-pair Nash needs the value model deferred in PB-H10); this
      is a robustness read on the Bayesian deltas the cells already carry.
    """
    if not (2 <= len(our_moves) <= MAX_DIM) or not (2 <= len(adversary_states) <= MAX_DIM):
        raise ValueError(
            f"payoff matrix requires 2..{MAX_DIM} our_moves and 2..{MAX_DIM} "
            f"adversary_states (got {len(our_moves)}×{len(adversary_states)})"
        )

    cells: list[list[dict]] = []
    best_score = float("-inf")
    best_idx = (0, 0)
    for i, mv in enumerate(our_moves):
        row: list[dict] = []
        for j, st in enumerate(adversary_states):
            try:
                run = bayesian_runner(
                    war_room_id=war_room_id,
                    our_move=mv,
                    adversary_state=st,
                    samples=samples,
                ) or {}
            except Exception as exc:
                logger.warning("payoff cell sim failed (%s,%s): %s", mv, st, exc)
                run = {}
            cell = _cell_from_run(run)
            # Score cell by delta_pct * confidence so a high-confidence
            # modest gain beats a wild low-confidence swing.
            score = cell["delta_pct"] * cell["confidence"]
            if score > best_score:
                best_score = score
                best_idx = (i, j)
            row.append(cell)
        cells.append(row)

    # Mark the expected-value winner.
    bi, bj = best_idx
    cells[bi][bj]["recommended"] = True

    # Security (maximin) equilibrium over the grounded deltas. For each of
    # our moves, the rival's best response is the column that minimises our
    # delta; we pick the move whose worst case is best.
    nash_i, nash_j = 0, 0
    best_security = float("-inf")
    for i in range(len(our_moves)):
        j_min = min(
            range(len(adversary_states)),
            key=lambda j: cells[i][j]["delta_pct"],
        )
        sec = cells[i][j_min]["delta_pct"]
        if sec > best_security:
            best_security = sec
            nash_i, nash_j = i, j_min
    cells[nash_i][nash_j]["nash"] = True
    nash_reasoning = (
        f"Security equilibrium: {adversary_states[nash_j]!r} is the rival's "
        f"gain-minimising response to {our_moves[nash_i]!r}, and {our_moves[nash_i]!r} "
        f"maximises our worst case at {best_security:+.1f}% vs baseline. "
        f"(Robustness pick over the Bayesian deltas — not an NPV-pair Nash.)"
    )

    return {
        "cells": cells,
        "recommended_cell": [bi, bj],
        "nash_cell": [nash_i, nash_j],
        "nash_reasoning": nash_reasoning,
        "samples_per_cell": samples,
    }
