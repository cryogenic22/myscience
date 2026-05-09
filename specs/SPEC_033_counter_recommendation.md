✓ Signed off by Claude
Pending sign-off by Frontend Claude (Dissent View consumes the response shape)

# SPEC_033: Counter-Recommendation Enforcement

## Goal
Implement the spec's "A unanimous AI is a suspicious AI" rule (§6.4.1):
the platform always presents at least one well-argued counter-rec
alongside its primary pick. Without this, the recommendation surface
collapses into yes-man theatre.

## Why now
Frontend Claude task #7 ("Dissent View Panel") is blocked on this
contract. Decision Workspace can't render structured dissent without a
backend that produces it. Plus: every prior loop (war-game, game-theory,
materiality) produces option scores; we already have what we need to
synthesize a primary + counter without an LLM call.

## Non-goals (deferred)
- LLM-generated rationale text. This loop ships heuristic templated
  rationales. A follow-up wires SPEC-026 LLMGateway for natural-language
  dissent that cites evidence.
- Auto-promotion of the primary if the user accepts. The Decision flow
  remains: synthesize → human reviews → human commits via existing
  `/decisions/from-round`.
- Multi-counter ensembles (>1 counter). Single counter is sufficient for
  the spec's invariant; richer dissent is a follow-up.

## Data contract

### Table: `recommendation_synthesis_runs`
Append-only audit log. Stores the exact synthesis output so an admin can
reproduce what the user saw.

| Column | Type | Notes |
|---|---|---|
| `recommendation_id` | UUID PK | gen_random_uuid() |
| `brief_id` | UUID | optional pointer to a Decision Brief |
| `inputs_jsonb` | JSONB NOT NULL | the option payload + scores the synthesizer received |
| `primary_option_id` | UUID NOT NULL | the chosen primary option |
| `primary_rationale` | TEXT NOT NULL | |
| `counter_option_id` | UUID NOT NULL | the chosen counter option (≥1 enforced) |
| `counter_rationale` | TEXT NOT NULL | |
| `dissent_score` | REAL NOT NULL CHECK (0-1) | how meaningfully different the counter is |
| `synthesis_method` | TEXT NOT NULL | `score_based` \| `dimension_split` \| `llm_v1` (future) |
| `started_by_user_id` | UUID | |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

## Synthesis algorithm

### Inputs
```python
SynthesizeRequest(
    brief_id: Optional[str],
    options: list[{
        option_id: str,
        label: str,
        score: float,             # 0-1; combined score (caller-supplied)
        predicted_outcome: Optional[str],
        risk_notes: Optional[str],
        # Optional per-dimension scores (allows dimension-split counter)
        dimension_scores: Optional[dict[str, float]],
    }],
)
```

### Algorithm
1. **Validate**: ≥2 options required. If <2 → 422 Unprocessable Entity
   ("counter-rec rule cannot be enforced; brief needs more options").
2. **Pick primary**: the option with the highest `score`.
3. **Pick counter**:
   - Default (`score_based`): the option with the LOWEST score that is
     not the primary. This is the natural dissent.
   - Optional (`dimension_split`, when caller provides
     `dimension_scores`): pick the option that wins the most *other*
     dimensions besides the primary's strongest one. This surfaces a
     counter framed as "different priorities, different winner."
4. **Compute `dissent_score`**:
   - `score_based`: `abs(primary.score - counter.score) / max(0.01, primary.score)`,
     clamped [0, 1].
   - `dimension_split`: `1 - dot(primary.dim_scores, counter.dim_scores) /
     (||primary|| × ||counter||)` (cosine distance, treats dim vectors as
     similarity).
5. **Build rationales**:
   - Primary: `"Top-scoring option ({primary.score:.2f}). {predicted_outcome}"`.
   - Counter: `"Dissent: {counter.label} scored {counter.score:.2f} but
     surfaces {risk_notes or 'a different risk profile'}. Worth weighing."`.
6. **Persist** to `recommendation_synthesis_runs`.

### Counter-rec rule enforcement
The hard rule: the response MUST contain a counter. The synthesizer never
returns `counter=None`. If after all attempts no counter can be selected
(only one option, or all options identical), the route returns 422 with
the failure reason — surfacing the violation rather than faking dissent.

## API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/recommendations/synthesize` | Run synthesizer (uploader+); persists + returns recommendation |
| GET | `/recommendations/{recommendation_id}` | Get one (viewer+) |
| GET | `/recommendations` | List with `brief_id` filter (viewer+) |

### Response shape
```json
{
  "recommendation_id": "uuid",
  "brief_id": "uuid|null",
  "primary": {
    "option_id": "uuid",
    "label": "Accelerate Phase 3 readout",
    "score": 0.82,
    "rationale": "Top-scoring option (0.82). Expected competitor share growth 8-12%."
  },
  "counter": {
    "option_id": "uuid",
    "label": "Hold and observe",
    "score": 0.45,
    "rationale": "Dissent: Hold and observe scored 0.45 but surfaces capital preservation. Worth weighing."
  },
  "dissent_score": 0.45,
  "synthesis_method": "score_based",
  "created_at": "..."
}
```

## Red-team

| # | Vector | Mitigation |
|---|---|---|
| R1 | Caller passes only 1 option to suppress dissent | 422 Unprocessable; cannot satisfy invariant |
| R2 | All options have identical scores → fake dissent | Counter chosen but `dissent_score = 0`; surfaced explicitly so the UI can render "no genuine disagreement available" |
| R3 | Score injection (negative, NaN) | Validation: `0 ≤ score ≤ 1`, finite |
| R4 | Massive payload (DoS via 10k options) | Cap at 20 options |
| R5 | SQL injection via brief_id | Parameterized; UUID-cast |
| R6 | Bypass auth via direct DB write | Route requires uploader+; persistence only via service |
| R7 | Counter same as primary (degenerate) | Service logic enforces `counter_id != primary_id` |
| R8 | LLM-generated rationales leak PII | Out of scope this loop; templated only |

## Success criteria
- [ ] Migration 061 applies clean
- [ ] Synthesizer enforces ≥2 options (422 with <2)
- [ ] Counter is always different from primary
- [ ] Score-based synthesis picks lowest-scoring counter
- [ ] Dimension-split synthesis picks dimensionally-different counter when caller provides dim scores
- [ ] dissent_score correctly reflects gap (0 when scores equal)
- [ ] Persistence captures the full input + output for audit
- [ ] Auth: synthesize requires uploader+; reads viewer+
- [ ] Tests cover the math + enforcement rules + persistence + auth + red-team

## Out of scope
- LLM-generated natural-language rationales (follow-up via SPEC-026)
- Multi-counter ensembles
- Auto-injection into Decision commit flow
- Adversarial counter (taking war-game adversary outputs as the counter)
