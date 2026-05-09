✓ Signed off by Claude
Pending sign-off by Antigravity (War-Room mode UI consumes the run + transcript)

# SPEC_028: Multi-Agent War-Game Adversaries

## Goal
Replace the current single move-suggester with a structured **adversary panel**
per spec §6.3.2: Competitor, Payer, Regulator, KOL agents that react to each
Decision Brief option across N rounds. Every adversary action MUST be tagged
with evidence from the knowledge graph or evidence ledger — "a war-game where
the competitor agent does whatever the prompt suggests is theater, not
analysis."

## Why now
SPEC-023 Decision Briefs gave us structured framing with options. SPEC-024
Evidence Ledger gave us groundable evidence. SPEC-026 LLM Gateway gave us
versioned prompts + telemetry. War-game adversaries can now be built on
top: each adversary's persona is sourced from the KG/ledger, prompts come
from the registry, every action ties back to evidence. This is the spec's
"most distinctive capability" and the input to SPEC-025 game-theoretic
upgrades.

## Non-goals (deferred to follow-up)
- **Real LLM-driven adversary text**. This loop ships the data model +
  orchestrator skeleton + grounding-rule enforcement + a default
  `StubReactor` that produces structured records. The actual LLM-driven
  reactor is a thin follow-up that swaps in `LLMGateway.invoke` for the
  reactor's `react()` method.
- Bayesian / Stackelberg / POMDP upgrades — those are SPEC-025.
- Real-time multi-user war-room UI — that's the frontend's job.

## Data contract

### Table: `war_game_runs`
| Column | Type | Notes |
|---|---|---|
| `run_id` | UUID PK | gen_random_uuid() |
| `brief_id` | UUID NOT NULL | FK decision_briefs(brief_id) ON DELETE CASCADE |
| `status` | TEXT NOT NULL | `pending` \| `running` \| `complete` \| `failed` |
| `num_rounds` | INTEGER NOT NULL DEFAULT 3 | CHECK 1-10 |
| `started_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |
| `completed_at` | TIMESTAMPTZ | NULL until complete |
| `failure_reason` | TEXT | NULL unless status=failed |
| `summary_jsonb` | JSONB NOT NULL DEFAULT '{}' | per-option roll-up after completion |
| `started_by_user_id` | UUID | actor |

### Table: `war_game_adversaries`
| Column | Type | Notes |
|---|---|---|
| `adversary_id` | UUID PK | gen_random_uuid() |
| `run_id` | UUID NOT NULL | FK war_game_runs ON DELETE CASCADE |
| `kind` | TEXT NOT NULL | `competitor` \| `payer` \| `regulator` \| `kol` |
| `name` | TEXT NOT NULL | e.g. "Pfizer", "CVS Caremark", "FDA Oncology Division", "Dr. X" |
| `entity_type` | TEXT | KG entity type, when bound to a real entity |
| `entity_id` | UUID | KG entity_id, when bound |
| `persona_jsonb` | JSONB NOT NULL DEFAULT '{}' | persona profile |
| `grounding_evidence_ids` | UUID[] NOT NULL DEFAULT '{}' | initial grounding evidence (from ledger) |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

### Table: `war_game_actions`
| Column | Type | Notes |
|---|---|---|
| `action_id` | UUID PK | gen_random_uuid() |
| `run_id` | UUID NOT NULL | FK war_game_runs ON DELETE CASCADE |
| `adversary_id` | UUID NOT NULL | FK war_game_adversaries |
| `option_id` | UUID NOT NULL | FK decision_brief_options |
| `round_num` | INTEGER NOT NULL CHECK >= 1 | |
| `action_kind` | TEXT NOT NULL | `react` \| `escalate` \| `wait` \| `concede` (extensible) |
| `action_text` | TEXT NOT NULL | Plain language description |
| `grounding_evidence_id` | UUID NOT NULL | **REQUIRED** — FK evidence_records(evidence_id) |
| `grounding_precedent` | TEXT | Free-form citation (the historical precedent or stated strategy) |
| `confidence` | REAL CHECK (0-1) | adversary's self-assessed likelihood |
| `llm_call_id` | UUID | Optional FK llm_call_log when LLM-generated |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |
| UNIQUE | (run_id, adversary_id, option_id, round_num) | one action per panel slot |

**The grounding rule is enforced at the DB level**: `grounding_evidence_id`
is `NOT NULL` and FK-constrained. Code that creates an action without
ledger backing is rejected by the DB. This is the spec's discipline rule
encoded in the schema.

## API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/war-games` | Start a new run on a brief (uploader+); body: `{ brief_id, num_rounds?, adversaries? }` |
| GET | `/war-games` | List recent runs (viewer+); filter by `brief_id`, `status` |
| GET | `/war-games/{run_id}` | Get run + adversary panel + summary (viewer+) |
| GET | `/war-games/{run_id}/transcript` | Full chronological action transcript (viewer+) |
| POST | `/war-games/{run_id}/cancel` | Cancel a running game (uploader+) |

## Orchestrator contract

```python
class WarGameOrchestrator:
    def __init__(self, reactor: AdversaryReactor):
        """Reactor is a strategy interface. Default: StubReactor.
        Future: LLMGatewayReactor that uses SPEC-026."""

    def run(self, db, brief_id: str, *, num_rounds=3,
            adversaries: list[AdversarySpec], started_by_user_id) -> WarGameRun:
        """For each option × adversary × round, call reactor.react()
        which MUST return (action_text, grounding_evidence_id, ...). The
        orchestrator validates the grounding rule, persists the action,
        and updates run status."""
```

The orchestrator is **synchronous** for this loop (good enough for tests
and small runs). Long-running multi-round games would benefit from async +
queue (deferred).

## Adversary persona spec

```json
{
  "kind": "competitor",
  "name": "Pfizer Oncology",
  "entity_type": "company",
  "entity_id": "uuid",
  "strategy": "fast-follower in checkpoint inhibitors",
  "recent_moves": ["accelerated PRGN-2009 readout 2026-Q3"],
  "financial_position": {"cash_runway_months": 36, "rd_intensity": 0.12},
  "known_red_lines": ["will not concede 1L NSCLC"],
  "evidence_grounding": ["evidence_id-1", "evidence_id-2"]
}
```

For payer/regulator/KOL similar shapes with kind-specific fields.

## Red-team

| # | Vector | Mitigation |
|---|---|---|
| R1 | Action without grounding evidence | DB CHECK + FK NOT NULL on grounding_evidence_id; code path rejected at insert |
| R2 | Run on brief in wrong state | Validate brief.state ∈ {simulation_pending, simulation_complete} before start |
| R3 | DoS via huge num_rounds | CHECK 1-10 in DB; route caps at 10 |
| R4 | Adversary impersonation (fake competitor) | name + entity_id are persisted; later analytics can flag mismatches |
| R5 | Cross-run contamination | (run_id, adversary_id, option_id, round_num) UNIQUE prevents duplicate writes |
| R6 | Cost runaway from N×M×R LLM calls | Stub reactor in this loop; LLM reactor will respect SPEC-021 D2 rate limit + SPEC-026 cost guard |
| R7 | Grounding evidence belonging to a different brief | Caller's responsibility (the spec); future: validate evidence.evidence_id is in brief.evidence_refs |
| R8 | Race on start (two POSTs for same brief) | No idempotency in this loop; consider future UNIQUE partial index on (brief_id, status='running') |
| R9 | Cancel races a complete | service-level guard: cancel only if status='running' or 'pending' |
| R10 | SQL injection via adversary kind/name | parameterized; kind enum-checked |

## Success criteria
- [ ] Migration 056 applies clean
- [ ] Brief in wrong state rejected with 409
- [ ] num_rounds outside 1-10 rejected with 400/422
- [ ] StubReactor produces grounded actions for every panel slot
- [ ] Action without grounding_evidence_id raises (DB rejects with FK violation)
- [ ] Cancel transitions running → cancelled (or treats cancelled as failed)
- [ ] Transcript endpoint returns rows ordered by round, then adversary
- [ ] Tests cover orchestrator + DB grounding rule + auth + red-team
- [ ] Full suite green; no regressions
- [ ] OpenAPI snapshot regenerated; API_CHANGELOG appended

## Out of scope
- Real LLM-driven adversary reactor (follow-up: ~50 lines wiring LLMGateway)
- Bayesian/Stackelberg upgrades (SPEC-025)
- Multi-user real-time war-room (frontend)
- Async orchestration with queue (deferred until brief-state-blocked
  scenarios become real)
