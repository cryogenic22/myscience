✓ Signed off by Claude
Pending sign-off by Antigravity (Decision Workspace Simulation panel consumes outputs)

# SPEC_025: Game-Theoretic Simulation — Bayesian / Stackelberg / POMDP

## Goal
Add formal game-theoretic structure to the simulation layer. Three composable
services that turn the war-game from "narrative role-play" into "principled
strategic analysis":

1. **Bayesian war-game upgrade** — adversaries carry a *type distribution* over
   private states (aggressive / defensive / cash_constrained). For each option,
   sample the type and produce a belief-distribution over outcomes, not a
   point estimate.
2. **Stackelberg sequencing** — for any timing-sensitive option, compute the
   leader-follower-optimal opponent counter-move on a timing grid. Surface as
   "if you launch on date T, the Stackelberg-optimal Pfizer response is X."
3. **POMDP value-of-information** — frame the brief as a partially observable
   MDP. Compare expected utility of "decide now with current belief" vs "wait
   W days for upcoming signal, decide with updated belief minus W·discount."
   Surface as "Wait vs Decide" recommendation.

Per the user's game-theory analysis: these add rigor without theatrical
sophistication, because each output is paired with the historical/empirical
parameters that informed it.

## Why now
SPEC-028 War-Game Adversaries gave us grounded role-play. SPEC-025 turns the
panel into structured strategic analysis. SPEC-023 Decision Briefs are the
consumer surface (Decision Workspace Simulation panel). Without SPEC-025,
strategists get narrative; with SPEC-025, they get distributions.

## Non-goals (deferred)
- Full RL self-play for adversaries (spec-discipline-violating; deferred)
- Mean-field games for crowded TAs (premature)
- Evolutionary dynamics on market share (low actionability)
- Multi-stage extensive-form games (this loop ships normal-form
  Bayesian + sequential Stackelberg + 1-step POMDP value-of-info)

## Three subsystems

### 1. Bayesian war-game

Each adversary carries a `type_distribution: dict[type_name, prob]`
summing to 1.0. Each type has parameters that determine reaction strength
on a per-option basis.

**Inputs**:
```python
BayesianAdversaryConfig(
    name="Pfizer Oncology",
    kind="competitor",
    type_distribution={"aggressive": 0.6, "defensive": 0.3, "cash_constrained": 0.1},
    type_response_strengths={
        "aggressive":       {"share_pp_swing": 8.0, "delay_months": -2},
        "defensive":        {"share_pp_swing": 3.0, "delay_months":  0},
        "cash_constrained": {"share_pp_swing": 1.0, "delay_months":  3},
    },
)
```

**Algorithm**:
- For each option, sample N times (default 1000) from the type distribution
- For each sample, compute the response on each output dimension
- Aggregate to a posterior distribution: mean, std, p10, p50, p90
- Return `BayesianOutcome(option_id, posterior_per_dim, sample_count)`

**Output shape**:
```json
{
  "option_id": "opt-1",
  "posterior_per_dim": {
    "share_pp_swing": {"mean": 5.4, "std": 2.6, "p10": 1.0, "p50": 5.5, "p90": 8.0},
    "delay_months": {"mean": -1.0, "std": 1.4, "p10": -2.0, "p50": -2.0, "p90": 3.0}
  },
  "sample_count": 1000,
  "by_type_contribution": {"aggressive": 0.6, "defensive": 0.3, "cash_constrained": 0.1}
}
```

### 2. Stackelberg sequencing

For each option that is timing-sensitive, compute the opponent's
best-response on a discrete timing grid. We choose timing T (leader),
opponent optimizes over their response set R given T (follower).

**Inputs**:
```python
StackelbergConfig(
    timing_grid=[0, 30, 60, 90, 120],   # days from now
    opponent_responses=["fast_follow", "hold", "concede_segment", "litigate"],
    our_payoff_matrix={                 # payoff to US given (timing, opponent_response)
        (0,   "fast_follow"):     5.0,
        (0,   "hold"):           12.0,
        (30,  "fast_follow"):     6.0,
        # ... full matrix
    },
    opponent_payoff_matrix={            # payoff to OPPONENT given (timing, response)
        (0,   "fast_follow"):     8.0,
        (0,   "hold"):            2.0,
        # ... full matrix
    },
)
```

**Algorithm**:
- For each timing T: opponent chooses response R that maximizes
  `opponent_payoff_matrix[T, R]`
- Our payoff under that R is `our_payoff_matrix[T, R]`
- Optimal T = argmax over T of our payoff under opponent's best response

**Output**:
```json
{
  "optimal_timing": 90,
  "opponent_best_response": "concede_segment",
  "our_payoff": 14.5,
  "opponent_payoff": 7.0,
  "by_timing": [
    {"timing": 0,  "opp_best": "fast_follow",     "opp_payoff": 8.0,  "our_payoff": 5.0},
    {"timing": 30, "opp_best": "fast_follow",     "opp_payoff": 7.5,  "our_payoff": 6.0},
    {"timing": 60, "opp_best": "hold",            "opp_payoff": 6.0,  "our_payoff": 9.0},
    {"timing": 90, "opp_best": "concede_segment", "opp_payoff": 7.0,  "our_payoff": 14.5},
    {"timing": 120,"opp_best": "concede_segment", "opp_payoff": 6.5,  "our_payoff": 13.0}
  ]
}
```

Tie-breaking on opponent's side: lex-first response wins (deterministic).
Caller controls payoff matrices; this is the "rigor without theater" — the
service computes the equilibrium, the human supplies the priors.

### 3. POMDP value-of-information

For a pending decision, decide whether to commit now or wait W days for
an upcoming signal.

**Inputs**:
```python
POMDPConfig(
    options={"opt-1": 8.0, "opt-2": 6.0, "opt-3": 10.0},  # current expected utility per option
    upcoming_signals=[
        {"name": "Q3_earnings", "arrival_days": 14,
         "expected_info_value": 1.2, "posterior_shifts": {"opt-1": +1.5, "opt-2": -0.5, "opt-3": +0.0}},
        {"name": "FDA_AdComm", "arrival_days": 42,
         "expected_info_value": 3.0, "posterior_shifts": {"opt-1": -2.0, "opt-2": +0.5, "opt-3": +4.0}},
    ],
    discount_rate_per_day=0.005,  # 0.5%/day delay penalty
)
```

**Algorithm**:
- `decide_now_utility = max(options.values())`
- For each signal:
  - Apply posterior shifts to options → updated_options
  - `wait_utility = max(updated_options.values()) − discount_rate × arrival_days × decide_now_utility`
  - `delta = wait_utility − decide_now_utility`
- Recommendation: `wait` if any signal has positive delta, else `decide`. Pick
  the signal with largest delta as the "wait_for" recommendation.

**Output**:
```json
{
  "recommendation": "wait",
  "wait_for_signal": "FDA_AdComm",
  "decide_now_utility": 10.0,
  "best_wait_option": "opt-3",
  "best_wait_utility": 11.9,
  "delta_vs_decide_now": 1.9,
  "per_signal": [
    {"signal": "Q3_earnings", "wait_utility": 9.81, "delta": -0.19, "verdict": "decide"},
    {"signal": "FDA_AdComm",  "wait_utility": 11.9, "delta":  1.9,  "verdict": "wait"}
  ]
}
```

## Data contract

### Table: `game_theory_runs`
Append-only record of every run. Loose-FK to brief_id (no DB FK because briefs
table may not exist in all deploy orders).

| Column | Type | Notes |
|---|---|---|
| `run_id` | UUID PK | gen_random_uuid() |
| `brief_id` | UUID | optional pointer back to a Decision Brief |
| `kind` | TEXT NOT NULL | `bayesian` \| `stackelberg` \| `pomdp` |
| `inputs_jsonb` | JSONB NOT NULL | the config the caller passed |
| `outputs_jsonb` | JSONB NOT NULL | the computed result |
| `compute_ms` | INTEGER | wall-clock |
| `started_by_user_id` | UUID | actor |
| `created_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW() |

## API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/game-theory/bayesian` | Run Bayesian war-game; persist + return result (uploader+) |
| POST | `/game-theory/stackelberg` | Run Stackelberg sequencing (uploader+) |
| POST | `/game-theory/pomdp` | Run POMDP value-of-info (uploader+) |
| GET | `/game-theory/runs` | List recent runs (viewer+) |
| GET | `/game-theory/runs/{run_id}` | Get one run (viewer+) |

## Red-team

| # | Vector | Mitigation |
|---|---|---|
| R1 | Type distribution doesn't sum to 1 | Validate `abs(sum-1.0) < 1e-6` (400) |
| R2 | Negative probabilities | Validate min ≥ 0 (400) |
| R3 | DoS via massive sample_count | Cap at 100,000 (400 above) |
| R4 | Missing payoff cells in Stackelberg | Validate full matrix coverage (400) |
| R5 | Discount rate out of [0, 1) | Validate (400) |
| R6 | Posterior shifts referencing unknown options | Validate keys ⊆ options.keys() (400) |
| R7 | Massive timing_grid → DoS | Cap at 500 grid points (400) |
| R8 | NaN/inf in payoffs | Validate finite (400) |

## Success criteria
- [ ] Migration 057 applies clean
- [ ] Bayesian: deterministic with fixed seed; posterior matches expected mean
      to within sampling tolerance
- [ ] Stackelberg: known small example produces correct optimal_timing +
      opponent best-response (tie-broken deterministically)
- [ ] POMDP: positive-delta signal triggers `wait`; negative-delta triggers
      `decide`; discount_rate correctly degrades wait_utility
- [ ] All run records persisted; GET endpoints return them
- [ ] Auth: compute requires uploader+; reads viewer+
- [ ] Tests cover the math + API + red-team
- [ ] Full suite green; OpenAPI snapshot regenerated

## Out of scope
- Coupling to war_game_runs (will integrate after both branches merge)
- Frontend Simulation Panel rendering (Antigravity's job)
- Adaptive sampling / VOI for Bayesian (premature optimization)
