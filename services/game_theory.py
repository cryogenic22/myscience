"""SPEC_025 — Game-Theoretic Simulation.

Three composable services that turn the war-game from narrative role-play
into structured strategic analysis:

  1. BayesianWarGame — adversaries with type distributions; samples produce
     posterior distributions over outcome dimensions.
  2. StackelbergSequencing — leader-follower equilibrium on a timing grid.
  3. POMDPValueOfInformation — decide-now vs wait-W-days for upcoming signals.

All three are pure Python; deterministic given a seed. Persistence to
`game_theory_runs` is the route layer's responsibility.
"""

from __future__ import annotations

import json
import logging
import math
import random
import statistics
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# Common validation helpers
# ────────────────────────────────────────────────────────────────────

EPS = 1e-6
MAX_SAMPLE_COUNT = 100_000
MAX_TIMING_GRID = 500


def _validate_distribution(dist: dict, name: str) -> None:
    if not isinstance(dist, dict) or not dist:
        raise ValueError(f"{name} must be a non-empty dict")
    total = 0.0
    for k, v in dist.items():
        if not isinstance(v, (int, float)) or not math.isfinite(v):
            raise ValueError(f"{name}[{k!r}] must be a finite number, got {v!r}")
        if v < 0:
            raise ValueError(f"{name}[{k!r}] must be ≥ 0 (got {v})")
        total += v
    if abs(total - 1.0) > EPS:
        raise ValueError(f"{name} must sum to 1.0 (got {total:.6f})")


def _validate_finite_number(v: Any, name: str) -> None:
    if not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError(f"{name} must be a finite number")


# ════════════════════════════════════════════════════════════════════
# 1) BAYESIAN WAR-GAME
# ════════════════════════════════════════════════════════════════════

@dataclass
class BayesianAdversaryConfig:
    name: str
    kind: str  # competitor|payer|regulator|kol — informational
    type_distribution: dict[str, float]
    type_response_strengths: dict[str, dict[str, float]]


@dataclass
class BayesianRunConfig:
    adversary: BayesianAdversaryConfig
    options: list[dict]                       # [{option_id, label}]
    sample_count: int = 1000
    seed: Optional[int] = None


def _validate_bayesian(cfg: BayesianRunConfig) -> None:
    a = cfg.adversary
    _validate_distribution(a.type_distribution, "type_distribution")
    if not a.type_response_strengths:
        raise ValueError("type_response_strengths required")
    # Each type in distribution MUST appear in strengths
    for t in a.type_distribution.keys():
        if t not in a.type_response_strengths:
            raise ValueError(f"type_response_strengths missing entry for type {t!r}")
        for dim, val in a.type_response_strengths[t].items():
            _validate_finite_number(val, f"type_response_strengths[{t}][{dim}]")
    if not cfg.options:
        raise ValueError("options must be non-empty")
    if cfg.sample_count < 1 or cfg.sample_count > MAX_SAMPLE_COUNT:
        raise ValueError(f"sample_count must be in [1, {MAX_SAMPLE_COUNT}]")


def run_bayesian(cfg: BayesianRunConfig) -> dict:
    """Sample N times from the type distribution; for each sample apply the
    type's response strength on each output dim. Aggregate to a posterior
    per dim per option.

    The reaction does NOT vary by option in this MVP — the type response
    represents the adversary's general posture. A future upgrade can take
    a per-(type, option) matrix from caller.

    Output:
      {
        "options": [
          {
            "option_id", "label",
            "posterior_per_dim": {dim: {mean, std, p10, p50, p90}, ...},
            "sample_count": N
          },
          ...
        ],
        "by_type_contribution": {type: prob, ...}
      }
    """
    _validate_bayesian(cfg)

    rng = random.Random(cfg.seed)  # deterministic when seed given
    types = list(cfg.adversary.type_distribution.keys())
    weights = list(cfg.adversary.type_distribution.values())
    strengths = cfg.adversary.type_response_strengths

    # All output dimensions: union across types
    all_dims: set[str] = set()
    for t_dims in strengths.values():
        all_dims.update(t_dims.keys())
    dims_sorted = sorted(all_dims)

    options_out: list[dict] = []
    for opt in cfg.options:
        # Sample
        samples_per_dim: dict[str, list[float]] = {d: [] for d in dims_sorted}
        for _ in range(cfg.sample_count):
            t = rng.choices(types, weights=weights, k=1)[0]
            t_strength = strengths[t]
            for d in dims_sorted:
                samples_per_dim[d].append(float(t_strength.get(d, 0.0)))

        # Aggregate
        posterior: dict[str, dict[str, float]] = {}
        for d, samples in samples_per_dim.items():
            sorted_s = sorted(samples)
            n = len(sorted_s)
            posterior[d] = {
                "mean": round(statistics.fmean(samples), 4),
                "std": round(statistics.pstdev(samples), 4) if n > 1 else 0.0,
                "p10": round(_percentile(sorted_s, 0.10), 4),
                "p50": round(_percentile(sorted_s, 0.50), 4),
                "p90": round(_percentile(sorted_s, 0.90), 4),
            }
        options_out.append({
            "option_id": str(opt.get("option_id", "")),
            "label": opt.get("label", ""),
            "posterior_per_dim": posterior,
            "sample_count": cfg.sample_count,
        })

    return {
        "kind": "bayesian",
        "adversary_name": cfg.adversary.name,
        "adversary_kind": cfg.adversary.kind,
        "options": options_out,
        "by_type_contribution": dict(cfg.adversary.type_distribution),
        "dims": dims_sorted,
    }


def _percentile(sorted_values: list[float], q: float) -> float:
    """Linear-interpolation percentile (q ∈ [0,1])."""
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    pos = q * (len(sorted_values) - 1)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_values[lo])
    frac = pos - lo
    return float(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


# ════════════════════════════════════════════════════════════════════
# 2) STACKELBERG SEQUENCING
# ════════════════════════════════════════════════════════════════════

@dataclass
class StackelbergConfig:
    timing_grid: list[float]                  # leader's choice space
    opponent_responses: list[str]             # follower's choice space
    our_payoff_matrix: dict                   # {(t, r): float}
    opponent_payoff_matrix: dict              # {(t, r): float}


def _validate_stackelberg(cfg: StackelbergConfig) -> None:
    if not cfg.timing_grid:
        raise ValueError("timing_grid must be non-empty")
    if len(cfg.timing_grid) > MAX_TIMING_GRID:
        raise ValueError(f"timing_grid too large; max {MAX_TIMING_GRID}")
    for t in cfg.timing_grid:
        _validate_finite_number(t, "timing_grid entry")
    if not cfg.opponent_responses:
        raise ValueError("opponent_responses must be non-empty")
    seen = set()
    for r in cfg.opponent_responses:
        if r in seen:
            raise ValueError(f"opponent_responses contains duplicate {r!r}")
        seen.add(r)
    # Validate full matrix coverage
    for t in cfg.timing_grid:
        for r in cfg.opponent_responses:
            for matrix_name, matrix in (("our_payoff_matrix", cfg.our_payoff_matrix),
                                        ("opponent_payoff_matrix", cfg.opponent_payoff_matrix)):
                key = (t, r)
                if key not in matrix:
                    raise ValueError(f"{matrix_name} missing cell {key!r}")
                _validate_finite_number(matrix[key], f"{matrix_name}[{key!r}]")


def run_stackelberg(cfg: StackelbergConfig) -> dict:
    """For each leader timing T, follower picks the response R maximizing
    opponent_payoff[T,R]. Tie-break: lex-first response wins (deterministic).
    Leader picks T maximizing our_payoff[T, follower_best(T)].
    """
    _validate_stackelberg(cfg)

    by_timing: list[dict] = []
    sorted_responses = sorted(cfg.opponent_responses)  # deterministic tie-break

    for t in cfg.timing_grid:
        best_r = None
        best_opp_pay = -math.inf
        for r in sorted_responses:
            opp_pay = float(cfg.opponent_payoff_matrix[(t, r)])
            if opp_pay > best_opp_pay + EPS:
                best_opp_pay = opp_pay
                best_r = r
        our_pay = float(cfg.our_payoff_matrix[(t, best_r)])
        by_timing.append({
            "timing": t,
            "opp_best_response": best_r,
            "opp_payoff": round(best_opp_pay, 4),
            "our_payoff": round(our_pay, 4),
        })

    # Pick leader-optimal timing
    optimal_idx = max(range(len(by_timing)), key=lambda i: by_timing[i]["our_payoff"])
    optimal = by_timing[optimal_idx]

    return {
        "kind": "stackelberg",
        "optimal_timing": optimal["timing"],
        "opponent_best_response": optimal["opp_best_response"],
        "our_payoff": optimal["our_payoff"],
        "opponent_payoff": optimal["opp_payoff"],
        "by_timing": by_timing,
    }


# ════════════════════════════════════════════════════════════════════
# 3) POMDP VALUE-OF-INFORMATION
# ════════════════════════════════════════════════════════════════════

@dataclass
class POMDPSignalConfig:
    name: str
    arrival_days: int
    expected_info_value: float       # informational only; included in output
    posterior_shifts: dict[str, float]  # {option_id: utility_shift}


@dataclass
class POMDPConfig:
    options: dict[str, float]                 # {option_id: current_expected_utility}
    upcoming_signals: list[POMDPSignalConfig]
    discount_rate_per_day: float = 0.005      # 0.5%/day default


def _validate_pomdp(cfg: POMDPConfig) -> None:
    if not cfg.options:
        raise ValueError("options must be non-empty")
    for k, v in cfg.options.items():
        _validate_finite_number(v, f"options[{k!r}]")
    if not (0.0 <= cfg.discount_rate_per_day < 1.0):
        raise ValueError("discount_rate_per_day must be in [0, 1)")
    if not cfg.upcoming_signals:
        raise ValueError("upcoming_signals must be non-empty")
    valid_keys = set(cfg.options.keys())
    for i, s in enumerate(cfg.upcoming_signals):
        if not s.name or not s.name.strip():
            raise ValueError(f"upcoming_signals[{i}].name required")
        if s.arrival_days < 0:
            raise ValueError(f"upcoming_signals[{i}].arrival_days must be ≥ 0")
        _validate_finite_number(s.expected_info_value, f"upcoming_signals[{i}].expected_info_value")
        for k, v in s.posterior_shifts.items():
            if k not in valid_keys:
                raise ValueError(
                    f"upcoming_signals[{i}].posterior_shifts references "
                    f"unknown option {k!r}; known: {sorted(valid_keys)}"
                )
            _validate_finite_number(v, f"upcoming_signals[{i}].posterior_shifts[{k!r}]")


def run_pomdp(cfg: POMDPConfig) -> dict:
    """For each upcoming signal: apply posterior shifts → updated_options;
    wait_utility = max(updated) − discount_rate × arrival_days × decide_now_utility.
    Pick best-positive-delta signal as the wait_for; fall back to 'decide'
    if no positive deltas."""
    _validate_pomdp(cfg)

    decide_now_option = max(cfg.options.items(), key=lambda kv: kv[1])
    decide_now_utility = decide_now_option[1]

    per_signal: list[dict] = []
    for s in cfg.upcoming_signals:
        updated = dict(cfg.options)
        for opt_id, shift in s.posterior_shifts.items():
            updated[opt_id] = updated.get(opt_id, 0.0) + shift
        best_after = max(updated.items(), key=lambda kv: kv[1])
        wait_utility = best_after[1] - cfg.discount_rate_per_day * s.arrival_days * abs(decide_now_utility)
        delta = wait_utility - decide_now_utility
        per_signal.append({
            "signal": s.name,
            "arrival_days": s.arrival_days,
            "expected_info_value": round(s.expected_info_value, 4),
            "best_wait_option": best_after[0],
            "wait_utility": round(wait_utility, 4),
            "delta": round(delta, 4),
            "verdict": "wait" if delta > 0 else "decide",
        })

    # Pick best wait_for
    positive = [p for p in per_signal if p["delta"] > 0]
    if positive:
        best = max(positive, key=lambda p: p["delta"])
        recommendation = "wait"
        wait_for_signal = best["signal"]
        best_wait_option = best["best_wait_option"]
        best_wait_utility = best["wait_utility"]
        delta_vs = best["delta"]
    else:
        recommendation = "decide"
        wait_for_signal = None
        best_wait_option = decide_now_option[0]
        best_wait_utility = decide_now_utility
        delta_vs = 0.0

    return {
        "kind": "pomdp",
        "recommendation": recommendation,
        "wait_for_signal": wait_for_signal,
        "decide_now_option": decide_now_option[0],
        "decide_now_utility": round(decide_now_utility, 4),
        "best_wait_option": best_wait_option,
        "best_wait_utility": round(best_wait_utility, 4),
        "delta_vs_decide_now": round(delta_vs, 4),
        "per_signal": per_signal,
    }


# ════════════════════════════════════════════════════════════════════
# Persistence helpers (called from route layer)
# ════════════════════════════════════════════════════════════════════

def persist_run(
    db,
    *,
    brief_id: Optional[str],
    kind: str,
    inputs: dict,
    outputs: dict,
    compute_ms: int,
    started_by_user_id: Optional[str],
) -> dict:
    """Insert a game_theory_runs row, return the inserted record."""
    row = db.fetch_one(
        """
        INSERT INTO game_theory_runs (
            brief_id, kind, inputs_jsonb, outputs_jsonb, compute_ms,
            started_by_user_id
        ) VALUES (%s, %s, %s::jsonb, %s::jsonb, %s, %s)
        RETURNING run_id, brief_id, kind, inputs_jsonb, outputs_jsonb,
                  compute_ms, started_by_user_id, created_at
        """,
        (
            str(brief_id) if brief_id else None,
            kind,
            json.dumps(inputs),
            json.dumps(outputs),
            compute_ms,
            started_by_user_id,
        ),
    )
    if not row:
        raise RuntimeError("persist_run: insert returned no row")
    return _row_to_dict(row)


def get_run(db, run_id: str) -> Optional[dict]:
    row = db.fetch_one(
        """
        SELECT run_id, brief_id, kind, inputs_jsonb, outputs_jsonb,
               compute_ms, started_by_user_id, created_at
          FROM game_theory_runs WHERE run_id::text = %s
        """,
        (str(run_id),),
    )
    return _row_to_dict(row) if row else None


def list_runs(
    db,
    *,
    brief_id: Optional[str] = None,
    kind: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    if limit < 1 or limit > 500:
        raise ValueError("limit must be in [1, 500]")
    if kind is not None and kind not in {"bayesian", "stackelberg", "pomdp"}:
        raise ValueError("kind must be in {bayesian|stackelberg|pomdp}")
    where = ["1=1"]
    params: list[Any] = []
    if brief_id is not None:
        where.append("brief_id::text = %s"); params.append(str(brief_id))
    if kind is not None:
        where.append("kind = %s"); params.append(kind)
    params.extend([limit, offset])
    rows = db.fetch_all(
        f"""
        SELECT run_id, brief_id, kind, inputs_jsonb, outputs_jsonb,
               compute_ms, started_by_user_id, created_at
          FROM game_theory_runs
         WHERE {' AND '.join(where)}
         ORDER BY created_at DESC
         LIMIT %s OFFSET %s
        """,
        tuple(params),
    ) or []
    return [_row_to_dict(r) for r in rows]


def _row_to_dict(row: dict) -> dict:
    inputs = row.get("inputs_jsonb") or {}
    outputs = row.get("outputs_jsonb") or {}
    if isinstance(inputs, str):
        try: inputs = json.loads(inputs)
        except (TypeError, ValueError): inputs = {}
    if isinstance(outputs, str):
        try: outputs = json.loads(outputs)
        except (TypeError, ValueError): outputs = {}
    return {
        "run_id": str(row["run_id"]),
        "brief_id": str(row["brief_id"]) if row.get("brief_id") else None,
        "kind": row["kind"],
        "inputs": inputs,
        "outputs": outputs,
        "compute_ms": row.get("compute_ms"),
        "started_by_user_id": str(row["started_by_user_id"]) if row.get("started_by_user_id") else None,
        "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
    }
