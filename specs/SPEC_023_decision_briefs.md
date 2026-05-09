✓ Signed off by Claude
✓ Signed off by Antigravity (data contract for Decision Workspace)

# SPEC_023: Decision Briefs — first-class framing object

## Goal
Promote the framing layer of the Decision Flywheel into a first-class object
with a state machine, structured options, evidence references, and stakeholder
metadata. The Decision Brief is the canonical handoff from sensing →
simulation per `specs/CI_Agent_Reimagined_Spec.md` §6.2.2.

This unblocks frontend's Decision Workspace (5-panel surface in spec §9.1.2)
and is a prerequisite for Framing Triggers (SPEC_029), War-Game Adversaries
(SPEC_028), Counter-recommendation enforcement, and Decision signing.

## Why now
Today, `decisions` capture commitment but skip the framing step entirely.
War rooms surface options but don't carry the structured brief metadata
(stakeholders, success criteria, time horizon, evidence refs, confidence-to-
proceed). Without this object, automatic framing (SPEC_029 triggers) has no
target to write into, and the frontend Decision Workspace has nothing
structured to render.

## Data contract

### Table: `decision_briefs`
| Column | Type | Notes |
|---|---|---|
| `brief_id` | UUID PK | gen_random_uuid() |
| `question` | TEXT NOT NULL | The decision being asked, plain language |
| `trigger_kind` | TEXT NOT NULL | `manual` \| `threshold` \| `cluster` \| `calendar` |
| `trigger_signal_ids` | UUID[] | Signals that originated the brief (empty for manual/calendar) |
| `trigger_metadata` | JSONB | Free-form trigger context (e.g., calendar event id, cluster window) |
| `stakeholders` | TEXT[] | Roles that must weigh in: `commercial`, `medical`, `pricing_access`, `rd`, `regulatory` |
| `time_horizon_days` | INTEGER | When the decision must be made; nullable for open-ended |
| `evidence_refs` | JSONB | `[{type: 'kbq_view'\|'signal'\|'entity'\|'document', id, snapshot_at}]` |
| `constraints` | TEXT[] | Hard constraints: regulatory, contractual, ethical, resource |
| `success_criteria` | TEXT | How we'll know after the fact whether the decision was right |
| `confidence_to_proceed` | REAL | Framing Agent's self-assessment 0-1; null for human-created |
| `state` | TEXT NOT NULL | One of 8 states (see state machine) |
| `owner_user_id` | UUID | Assigned strategist; null until assigned |
| `war_room_id` | UUID | Optional link to war room used for option discovery |
| `decision_id` | UUID | Set when state transitions to `committed` |
| `archived_at` | TIMESTAMPTZ | NULL unless archived |
| `created_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW() |
| `updated_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW() |

### Table: `decision_brief_options`
| Column | Type | Notes |
|---|---|---|
| `option_id` | UUID PK | gen_random_uuid() |
| `brief_id` | UUID NOT NULL | FK decision_briefs ON DELETE CASCADE |
| `ordinal` | INTEGER NOT NULL | Per-brief position 1..N. UNIQUE(brief_id, ordinal) |
| `label` | TEXT NOT NULL | Short option label ("Accelerate Phase 3 readout") |
| `description` | TEXT | Longer description |
| `predicted_outcome` | TEXT | Quantified prediction ("expect competitor share 8-12% growth over 18mo") |
| `cost_estimate` | TEXT | Free-form ("$5-8M incremental DevOps + 4 months delay") |
| `risk_notes` | TEXT | Tail risks |
| `created_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW() |

Constraint: brief in `draft` or `human_review` state may have any number of
options; transitioning OUT of `human_review` requires ≥2 options (validated
by service, not DB constraint).

### Table: `decision_brief_state_log`
Append-only audit trail of state transitions.
| Column | Type | Notes |
|---|---|---|
| `log_id` | UUID PK | gen_random_uuid() |
| `brief_id` | UUID NOT NULL | FK decision_briefs ON DELETE CASCADE |
| `from_state` | TEXT | Null for initial state |
| `to_state` | TEXT NOT NULL | |
| `actor_user_id` | UUID | Who transitioned (system if null) |
| `reason` | TEXT | Optional rationale |
| `transitioned_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW() |

## State machine

```
              ┌───────────────────────────────────────────┐
              │                                           │
              ▼                                           │
draft ──► human_review ──► simulation_pending ──► simulation_complete
                                  │                       │
                                  │                       ▼
                                  │                 decision_pending
                                  │                       │
                                  │                       ▼
                                  └─────► (back) ◄── committed ──► in_review ──► closed
```

Legal transitions (enforced in service layer; rejected with 409 if illegal):
| From | Allowed → |
|---|---|
| `draft` | `human_review`, `closed` (abandon) |
| `human_review` | `draft` (edit more), `simulation_pending`, `closed` |
| `simulation_pending` | `simulation_complete`, `human_review` (re-frame on sim fail) |
| `simulation_complete` | `decision_pending`, `human_review` (re-frame after seeing sims) |
| `decision_pending` | `committed`, `human_review` |
| `committed` | `in_review` (auto when review_at hits) |
| `in_review` | `closed` |
| `closed` | (terminal) |

Special rules:
- Transitioning to `simulation_pending` requires `options.count >= 2`.
- Transitioning to `committed` requires `decision_id` to be set.
- `archived_at` is orthogonal to state — any non-terminal brief can be archived.

## API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/decision-briefs` | Create draft (manual) |
| GET | `/decision-briefs` | List with filters: `state`, `owner_user_id`, `trigger_kind`, cursor pagination |
| GET | `/decision-briefs/{brief_id}` | Get one with options + state log |
| PATCH | `/decision-briefs/{brief_id}` | Edit fields (only legal in `draft` or `human_review`) |
| DELETE | `/decision-briefs/{brief_id}` | Archive (set archived_at; brief becomes read-only) |
| POST | `/decision-briefs/{brief_id}/options` | Add an option |
| PATCH | `/decision-briefs/{brief_id}/options/{option_id}` | Edit an option |
| DELETE | `/decision-briefs/{brief_id}/options/{option_id}` | Remove an option (only in draft/human_review) |
| POST | `/decision-briefs/{brief_id}/transitions` | Transition to a target state |

All endpoints require auth (`viewer` for GET, `editor` for mutations).
Standard error envelope per `api/exception_handlers.py`.
Cursor pagination per `api/pagination.py`.

## Frontend impact

Antigravity will build the Decision Workspace (`[FRONTEND] Decision Workspace`
backlog item, blocked on this) consuming:
- `GET /decision-briefs/{id}` for the full Brief panel + options
- `PATCH` endpoints for editable-while-draft fields
- `POST /transitions` to advance the state machine
- The state log for the "Reasoning trace" drawer (showing who transitioned when)

## Open questions
- Q1: Should `evidence_refs` be a denormalized JSONB array, or a separate
  `decision_brief_evidence` join table? **Decision: JSONB for now** —
  evidence is heterogeneous (KBQ views, signals, entities, docs) and the
  per-brief count is bounded (~10-20). Will normalize if we need joins for
  evidence-quality reporting later.
- Q2: Should we enforce stakeholder roles against an enum? **Decision: no
  enum** — start with TEXT[] to allow custom roles per org; tighten later.
- Q3: Where do auto-created briefs (from triggers) get assigned? **Decision:
  defer to SPEC_029** — briefs created by triggers land with `owner_user_id`
  null and an `unassigned` virtual queue. SPEC_029 will define routing.

## Out of scope (deferred to follow-up specs)
- Framing trigger evaluation (SPEC_029)
- War-game simulation handoff (SPEC_028)
- Decision signing + immutable evidence_snapshot (rolls into SPEC_024 +
  SPEC_026)
- Multi-tenant compartmentalization (deferred until needed)

## Success criteria for this loop
- [ ] Migration 052 applies clean against local dev DB
- [ ] All 8 states reachable through legal transitions; illegal transitions
      return 409 with explanatory error
- [ ] Cursor pagination works on list endpoint
- [ ] State log captures every transition with actor + reason
- [ ] Backwards compat: existing decisions/war_rooms unaffected
- [ ] All new tests pass; full suite has zero regressions
- [ ] OpenAPI snapshot regenerated; API_CHANGELOG entry appended
- [ ] Red-team review documented inline in the test file

## Land order
Backend first (this PR). Frontend Decision Workspace consumes after merge.
