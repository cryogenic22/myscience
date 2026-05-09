✓ Signed off by Claude
Pending sign-off by Frontend Claude (Inbox surfaces auto-framed briefs)

# SPEC_029: Framing Triggers — auto-create draft Decision Briefs

## Goal
Close the signal-to-decision latency gap by auto-creating draft Decision
Briefs from three trigger kinds per `specs/CI_Agent_Reimagined_Spec.md`
§6.2.1:

1. **Threshold trigger** — single signal scoring above N (default 80) on
   materiality
2. **Cluster trigger** — ≥M signals related to the same entity within a
   rolling window
3. **Calendar trigger** — pre-scheduled review points (quarterly portfolio
   review, pre-conference prep)

Each fired trigger creates a draft `decision_briefs` row with
`trigger_kind` set, signal references attached as `trigger_signal_ids`,
and lands in the assignee's inbox (or unassigned queue).

## Why now
SPEC-023 Decision Briefs gave us the structured framing object. SPEC-031
Materiality Scoring gave us the score that thresholds fire on. Without
SPEC-029, briefs only get created when a human opens a war room — i.e.
the spec's <24h target latency is unreachable. This loop closes that gap.

## Non-goals (deferred)
- LLM-generated brief questions (the trigger uses a templated question;
  follow-up: invoke SPEC-026 Gateway to generate a context-aware question)
- Auto-routing to specific strategists by entity ownership (uses
  trigger.assignee_user_id directly today)
- Real-time push notifications when a trigger fires (frontend pulls the
  inbox; future: WebSocket push)

## Data contract

### Table: `framing_triggers`
| Column | Type | Notes |
|---|---|---|
| `trigger_id` | UUID PK | gen_random_uuid() |
| `name` | TEXT NOT NULL | Human-friendly name ("High-materiality FDA actions") |
| `kind` | TEXT NOT NULL | `threshold` \| `cluster` \| `calendar` |
| `config_jsonb` | JSONB NOT NULL | Per-kind config (see below) |
| `assignee_user_id` | UUID | Optional owner for auto-created briefs |
| `is_active` | BOOLEAN NOT NULL DEFAULT TRUE | |
| `last_evaluated_at` | TIMESTAMPTZ | Last tick time; service uses this as the "since" cursor for threshold/cluster |
| `next_fire_at` | TIMESTAMPTZ | For calendar triggers only |
| `created_by_user_id` | UUID | |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |
| `updated_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

### Per-kind config_jsonb shapes

**threshold**:
```json
{
  "min_materiality_score": 80,                       // signal.materiality_score >= this
  "claim_types": ["clinical_readout", "regulatory_action"],   // optional whitelist
  "entity_types": ["drug", "company"],               // optional whitelist
  "question_template": "Material {claim_type} on {entity}: how do we respond?"
}
```

**cluster**:
```json
{
  "min_cluster_size": 3,                             // ≥N related signals
  "rolling_window_days": 14,
  "entity_field": "entity_id",                       // group key (entity_id or claim_type)
  "min_total_materiality": 150,                      // sum of scores threshold (optional)
  "question_template": "Cluster of {n} signals on {entity}: framing needed"
}
```

**calendar**:
```json
{
  "interval_days": 90,                               // recur every N days
  "question_template": "Quarterly portfolio review",
  "default_options_count": 0                         // briefs land with no options for human framing
}
```

### Table: `framing_trigger_fires`
Append-only event log: every trigger evaluation that produced a brief.

| Column | Type | Notes |
|---|---|---|
| `fire_id` | UUID PK | gen_random_uuid() |
| `trigger_id` | UUID NOT NULL | FK framing_triggers ON DELETE CASCADE |
| `fired_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |
| `signal_ids` | UUID[] NOT NULL DEFAULT '{}' | Signals that matched (empty for calendar) |
| `brief_id` | UUID | The brief that was created (NULL on skip/failure) |
| `status` | TEXT NOT NULL | `success` \| `skipped_no_match` \| `skipped_dedup` \| `failed` |
| `failure_reason` | TEXT | |

## API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/framing-triggers` | Create a trigger (uploader+) |
| GET | `/framing-triggers` | List triggers (viewer+); filter by kind, active |
| GET | `/framing-triggers/{trigger_id}` | Get one (viewer+) |
| PATCH | `/framing-triggers/{trigger_id}` | Update fields (uploader+) |
| DELETE | `/framing-triggers/{trigger_id}` | Delete (uploader+) |
| POST | `/framing-triggers/tick` | Evaluate ALL active triggers now (uploader+); returns per-trigger results |
| POST | `/framing-triggers/{trigger_id}/evaluate` | Evaluate ONE trigger now (uploader+) |
| GET | `/framing-triggers/{trigger_id}/fires` | List recent fires (viewer+) |

## Orchestrator contract

```python
class FramingOrchestrator:
    def tick(self, db) -> list[FireResult]:
        """Evaluate all active triggers. For each match, create a draft
        DecisionBrief via SPEC-023 service, log a fire row, advance
        last_evaluated_at / next_fire_at."""

    def evaluate_one(self, db, trigger_id: str) -> FireResult:
        """Evaluate one trigger; same logic, single trigger."""
```

## Dedup rule (R-key)

A naive evaluator would re-fire on every tick. To prevent runaway briefs:
- **Threshold**: each signal can fire at most once across the trigger's
  history. Service tracks via `framing_trigger_fires.signal_ids` —
  signals already in a prior fire for this trigger are skipped.
- **Cluster**: a cluster fires once per (trigger, entity) per
  rolling_window. Service checks: any prior fire for this trigger touching
  any of the cluster's signal_ids? If yes, skip.
- **Calendar**: fires only when `NOW() >= next_fire_at`; service advances
  `next_fire_at += interval_days` on success.

## Red-team

| # | Vector | Mitigation |
|---|---|---|
| R1 | Runaway brief creation (loop misfires) | Dedup rules above + per-trigger fire limit (max 100 per tick) |
| R2 | Threshold tuned too low → spam | Validate `min_materiality_score >= 50` (sane floor) |
| R3 | Calendar trigger creating duplicate briefs on rapid ticks | next_fire_at advance is atomic; second tick within window finds NOW < next_fire_at |
| R4 | Failed brief creation crashes whole tick | Each evaluation wrapped in try; failed evaluations logged but don't abort |
| R5 | SQL injection via question_template | Server-side template substitution; user-supplied template values escaped |
| R6 | Evaluator races on last_evaluated_at | UPDATE last_evaluated_at = greatest(last, NOW()) — read-modify-write under transaction |
| R7 | Expensive cluster query on huge signals table | LIMIT + index on (created_at, materiality_score); cluster query bounded |
| R8 | Trigger config injection (eval-style) | Config is JSONB read; never eval'd; whitelist of allowed keys per kind |

## Success criteria
- [ ] Migration 059 applies clean
- [ ] Threshold trigger fires on signal with materiality >= configured threshold
- [ ] Threshold trigger respects claim_types / entity_types whitelists
- [ ] Threshold trigger dedup: same signal doesn't re-fire
- [ ] Cluster trigger fires when ≥min_cluster_size signals match in window
- [ ] Cluster trigger dedup: same entity doesn't re-fire within window
- [ ] Calendar trigger fires when NOW >= next_fire_at; advances next_fire_at
- [ ] Calendar trigger doesn't fire when NOW < next_fire_at
- [ ] Each fire creates a brief in 'draft' state via SPEC-023 service
- [ ] Failed fires don't abort the tick (error isolation)
- [ ] Auth: configure requires uploader+; tick requires uploader+
- [ ] Tests cover the math + tick logic + dedup + auth + red-team

## Out of scope
- LLM-generated brief questions (use template; follow-up wires SPEC-026)
- Per-entity assignment routing (single trigger.assignee_user_id today)
- Real-time push notifications
