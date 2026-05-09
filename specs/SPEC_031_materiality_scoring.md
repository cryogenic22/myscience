✓ Signed off by Claude
✓ Signed off by Frontend Claude (2026-05-09 — `materiality_factors` JSONB is the contract Sensing Feed v2 / SPEC_035 will consume; default factors `source_tier / entity_criticality / claim_type / recency` are sufficient for the factor-bar UI; admin surface to edit `materiality_weight_config` is deferred to a follow-up frontend spec, not blocking this one)

# SPEC_031: Materiality Scoring — factor-attributed

## Goal
Replace today's single-weight materiality scorer with a **factor-attributed
model** whose output is `(materiality_score: 0-100, materiality_factors:
dict)`. The frontend Sensing Feed (frontend Claude task #8) needs the factor
breakdown to render "why this signal is critical" tooltips.

Per `specs/CI_Agent_Reimagined_Spec.md` §6.1.2: "Inputs include source tier,
entity criticality (focal product = highest), claim type (clinical readout >
formulary tier change > earnings color commentary), and recency. Calibration
is reviewed quarterly."

## Why now
Frontend SensingFeed is shipping (per the handover). Their cards need to
show *which* factors drove a signal's score. A single number gives no
trust; an attributed breakdown does. Also: SPEC-029 Framing Triggers
(next loop) thresholds on `materiality_score >= 80` — factor-attribution
helps the user understand *why* a brief was auto-framed.

## Non-goals (deferred)
- **Learned weights from outcomes**. SPEC-028 Learning Service will tune
  weights from prediction-vs-outcome data. This loop ships *configurable
  defaults*, not a trained model.
- Per-tenant weight overrides (single-tenant for now).
- Re-scoring all historical signals (one-shot batch job, separate).
- NLP-based claim-type classification (caller supplies claim_type today;
  future LLM Gateway invocation can auto-classify).

## Data contract

### Augmentation to existing `signals` table
Add (additive, back-compat):
```sql
ALTER TABLE signals ADD COLUMN IF NOT EXISTS materiality_factors JSONB;
```
Existing `signals.materiality_score` (0-100) stays as-is. The new column
holds the factor breakdown for that score.

### Table: `materiality_weight_config`
Singleton config row for current weights + factor reference values. Editing
this is an admin operation; the frontend factor-explanation tooltip reads
from here so weights and UI stay in sync.

| Column | Type | Notes |
|---|---|---|
| `config_id` | UUID PK | gen_random_uuid() |
| `is_active` | BOOLEAN NOT NULL | Only one row may have `is_active = TRUE` |
| `weights_jsonb` | JSONB NOT NULL | `{source_tier: 0.30, entity_criticality: 0.30, claim_type: 0.25, recency: 0.15}` |
| `tier_values_jsonb` | JSONB NOT NULL | `{1: 1.0, 2: 0.7, 3: 0.4, 4: 0.6}` |
| `claim_type_values_jsonb` | JSONB NOT NULL | per-claim-type factor values |
| `criticality_values_jsonb` | JSONB NOT NULL | `{focal: 1.0, top_competitor: 0.7, watched: 0.5, other: 0.2}` |
| `recency_half_life_days` | REAL NOT NULL | Exponential decay parameter; default 30 |
| `created_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW() |
| `updated_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW() |

Partial unique index ensures only one active config row.

## Scoring formula

```
score = 100 × (
  weights.source_tier         × tier_values[source_tier_int] +
  weights.entity_criticality  × criticality_values[criticality_kind] +
  weights.claim_type          × claim_type_values[claim_type] +
  weights.recency             × exp(-ln(2) × age_days / half_life_days)
)
clamped to [0, 100]
```

Default weights:

| Factor | Weight |
|---|---|
| source_tier            | 0.30 |
| entity_criticality     | 0.30 |
| claim_type             | 0.25 |
| recency                | 0.15 |

Default factor values:

| Source tier | Value |
|---|---|
| 1 (authoritative public) | 1.0 |
| 2 (disclosure & news)    | 0.7 |
| 3 (scientific & conference) | 0.4 |
| 4 (licensed CI)          | 0.6 |

| Entity criticality | Value |
|---|---|
| focal              | 1.0 |
| top_competitor     | 0.7 |
| watched            | 0.5 |
| other              | 0.2 |

| Claim type | Value |
|---|---|
| clinical_readout    | 1.0 |
| regulatory_action   | 0.95 |
| pricing_change      | 0.8 |
| formulary_change    | 0.75 |
| safety_signal       | 0.85 |
| pipeline_update     | 0.6 |
| earnings_commentary | 0.4 |
| other               | 0.3 |

Recency: exponential decay with half-life of 30 days (configurable).
- 0 days old → 1.0
- 30 days old → 0.5
- 60 days old → 0.25

## Output shape

```json
{
  "materiality_score": 87,
  "materiality_factors": {
    "source_tier":           {"input": 1, "value": 1.0,  "weight": 0.30, "contribution": 30.0},
    "entity_criticality":    {"input": "focal", "value": 1.0, "weight": 0.30, "contribution": 30.0},
    "claim_type":            {"input": "regulatory_action", "value": 0.95, "weight": 0.25, "contribution": 23.75},
    "recency":               {"input_days": 5,  "value": 0.89, "weight": 0.15, "contribution": 13.35}
  },
  "score_method": "factor_attributed_v1",
  "weights_config_id": "uuid"
}
```

`contribution` is `100 × weight × value`. They sum to the materiality_score
(within rounding). The frontend renders this as a stacked bar or
breakdown list under each signal.

## API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/materiality/score` | Compute score for a payload (uploader+); optionally persists to `signals.materiality_factors` if `signal_id` provided |
| GET | `/materiality/weights` | Get the active weight config (viewer+) — for the frontend "what factors?" explanation |
| PUT | `/materiality/weights` | Replace the active weight config (uploader+) — admin tuning |

## Red-team

| # | Vector | Mitigation |
|---|---|---|
| R1 | Score gaming via inflated criticality | Criticality value is enum-bound; caller can't supply arbitrary numeric |
| R2 | Negative ages → unbounded recency value | Clamp `age_days >= 0`; future-dated signals get value 1.0 |
| R3 | Unknown claim_type → silent zero | Falls back to `other` (0.3); never 0 unless caller explicitly passes 'other' |
| R4 | Weights not summing to 1 (admin error) | Validate `abs(sum - 1.0) < 1e-6` on PUT |
| R5 | Weights with negative values | Validate min ≥ 0 |
| R6 | Multiple active configs | Partial unique index `WHERE is_active = TRUE` |
| R7 | DoS via batch scoring | This loop ships single-signal scoring only; batch is a follow-up endpoint |
| R8 | SQL injection via signal_id when persisting | Parameterized; UUID-cast |

## Success criteria
- [ ] Migration 058 applies clean
- [ ] Default weights sum to 1.0
- [ ] Pure scorer is deterministic; same inputs → same output
- [ ] Recency factor: 0 days → 1.0, half_life days → 0.5, exponentially decays
- [ ] Unknown claim_type falls back to 'other' (no exception)
- [ ] PUT /weights validates sum-to-1
- [ ] Persistence to signals.materiality_factors works when signal_id provided
- [ ] Auth: score requires uploader+; weights GET viewer+, PUT uploader+
- [ ] Tests cover the math + API + admin tuning + red-team

## Out of scope
- Learning Service tuning of weights (SPEC-028)
- Per-tenant weight customization (multi-tenant deferred)
- LLM-based claim_type auto-classification
- Batch re-scoring of historical signals
