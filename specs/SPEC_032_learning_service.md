✓ Signed off by Claude
Pending sign-off by Frontend Claude (Insights surface consumes learning-run summaries)

# SPEC_032: Learning Service — close the flywheel

## Goal
Close the spec's Stage 5 (LEARN) loop. For every committed Decision past
its `review_at` with an `actual_outcome`, attribute the prediction
accuracy back to:

1. **Sources** — update `sources.predictive_accuracy` via EWMA from
   per-decision calibration_scores (raises sources whose evidence backed
   correct predictions; demotes those that didn't)
2. **Prompts** — flag `prompt_registry` versions whose recent calibration
   mean is below threshold for human review
3. **Adversary models** (deferred — wires SPEC-028 War-Game Adversaries
   later)

Per `specs/CI_Agent_Reimagined_Spec.md` §6.5 + game-theory addendum:
"this is the flywheel rotating" — without it, the platform captures
outcomes but doesn't compound from them.

## Why now
SPEC-027 Source Registry has a `predictive_accuracy` column with default
0.5 — explicitly placeholder until this loop. SPEC-026 LLM Gateway logs
prompt_id on every call. SPEC-024 Evidence Ledger links claims to
sources. The decision outcome capture path (SPEC-021 D MVP) writes
calibration_score on every closed decision. This loop wires them.

## Non-goals (deferred)
- **Recommendation calibration retraining**. The spec lists this as a
  4th update target. Today's recommendations don't yet have a
  centralized calibration model — that's its own follow-up.
- **War-game adversary model updates**. Defer until SPEC-028 lands and
  we have adversary action ↔ outcome attribution.
- **Auto-retire bad prompts**. This loop *flags*; a follow-up can demote
  flagged prompts in the active-prompt selection logic.
- **APScheduler nightly cron wiring**. Manual `POST /learning/run` for
  now; cron added when we know stable timing.

## Data contract

### Table: `learning_service_runs`
Append-only; one row per run.

| Column | Type | Notes |
|---|---|---|
| `run_id` | UUID PK | gen_random_uuid() |
| `started_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |
| `completed_at` | TIMESTAMPTZ | |
| `status` | TEXT NOT NULL | `running` \| `complete` \| `failed` |
| `since_cursor` | TIMESTAMPTZ | the `since` watermark used (decisions with actual_outcome captured after this) |
| `decisions_processed` | INTEGER NOT NULL DEFAULT 0 | |
| `sources_updated` | INTEGER NOT NULL DEFAULT 0 | distinct source_ids updated |
| `prompts_flagged` | INTEGER NOT NULL DEFAULT 0 | |
| `failure_reason` | TEXT | |
| `summary_jsonb` | JSONB NOT NULL DEFAULT '{}'::jsonb | full run report |
| `started_by_user_id` | UUID | |

### Table: `source_attribution_log`
Append-only; per-(decision, source) attribution event with the calibration
delta that drove the source's accuracy update. Useful for audit.

| Column | Type | Notes |
|---|---|---|
| `attribution_id` | UUID PK | |
| `run_id` | UUID NOT NULL | FK learning_service_runs ON DELETE CASCADE |
| `decision_id` | UUID NOT NULL | loose pointer (no FK; decision may be archived) |
| `source_id` | TEXT NOT NULL | the source that contributed |
| `calibration_score` | REAL NOT NULL | the decision's calibration; in [0, 1] |
| `prior_accuracy` | REAL | the source's accuracy before this update |
| `posterior_accuracy` | REAL | the source's accuracy after EWMA |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

### Table: `prompt_quality_flag`
Append-only; per-prompt rolling-window quality flag. Flagged prompts are
shown to admins for review.

| Column | Type | Notes |
|---|---|---|
| `flag_id` | UUID PK | |
| `run_id` | UUID NOT NULL | FK learning_service_runs ON DELETE CASCADE |
| `prompt_id` | UUID NOT NULL | loose pointer to prompt_registry |
| `prompt_name` | TEXT | denormalized for display |
| `decisions_observed` | INTEGER NOT NULL | how many decisions in window |
| `mean_calibration` | REAL NOT NULL | mean across observed decisions |
| `flag_reason` | TEXT NOT NULL | `low_calibration` \| `low_volume_high_var` |
| `created_at` | TIMESTAMPTZ NOT NULL DEFAULT NOW() | |

## EWMA update math

```
posterior_accuracy = alpha * calibration_score + (1 - alpha) * prior_accuracy
```

Default `alpha = 0.10` — slow learner; one decision contributes 10% of
the new value, blending in 90% of prior. Tunable via env / future config
table.

When a source has no prior (NULL `predictive_accuracy`), use the
calibration_score directly as the first observation.

If multiple decisions update the same source in one run, apply EWMA
sequentially in chronological order (deterministic given input order).

## Prompt flagging rules

A prompt is flagged when, within the last 30 days:
- `decisions_observed >= 5` AND `mean_calibration < 0.45` → `low_calibration`
- (Future) `decisions_observed in [3, 4]` AND `std > 0.3` → `low_volume_high_var`

Decisions are linked to prompts via the brief workflow: each decision's
brief used some prompts (recorded in `llm_call_log.prompt_id` with
`caller='llm_gateway'`). For the MVP we look at any llm_call within the
brief's lifecycle window (`brief.created_at` to `brief.updated_at`)
linked by `user_id` matching `decision.owner_user_id` — not perfect, but
attributes within a reasonable confidence radius.

(A follow-up SPEC will add explicit `llm_call_log.brief_id` for tighter
attribution.)

## How sources are extracted from a decision

Two paths, MVP tries the first available:

1. **Evidence ledger chain** (preferred, when SPEC-024 + decision signing
   are wired): `decisions → evidence_snapshots(decision_id) →
   body.claims[].evidence_ids → evidence_records.source_id`
2. **Brief evidence_refs fallback** (when SPEC-024 isn't wired yet): if
   the decision links to a brief, look at `brief.evidence_refs[]` for
   `{type: 'signal', id}` entries → `signals.source` for source_id.
3. **Last-resort**: if the decision has a `source_signal_id` (set when
   promoted from a war-room round), use `signals.source` directly.

The service iterates these and uses the FIRST that yields source_ids.
Records which path it used in `summary_jsonb.attribution_method` so an
admin can see which decisions used which path.

## API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/learning/run` | Run learning service now (uploader+); body: `{ since? }` (default: last successful run's started_at, else 30 days ago) |
| GET | `/learning/runs` | List recent runs (viewer+) |
| GET | `/learning/runs/{run_id}` | Run detail + summary (viewer+) |
| GET | `/learning/source-attributions` | Recent attributions (viewer+); optional `source_id`, `since` filters |
| GET | `/learning/prompt-flags` | Currently-flagged prompts (viewer+) |

## Red-team

| # | Vector | Mitigation |
|---|---|---|
| R1 | Runaway accuracy moves on small N | EWMA alpha = 0.10 (small step); per-source moves are bounded |
| R2 | Re-running on same decisions inflates updates | `since_cursor` is decision's `actual_outcome_recorded_at`, monotonically increasing per decision; service idempotent if since is correctly advanced |
| R3 | Decision missing calibration_score | service skips it (NULL guard in WHERE clause) |
| R4 | Source IDs not in `sources` table | service inserts a fallback row OR skips (configurable via `auto_register_unknown_sources`) — defaulting to skip with a counter, surfaced in summary |
| R5 | Cost runaway from massive decision backlog | capped at MAX_DECISIONS_PER_RUN (default 1000); summary reports if cap hit |
| R6 | Failed run leaves DB in partial state | each decision processed in isolation; failures logged in summary, don't abort run |
| R7 | Flagging based on too few observations | `decisions_observed >= 5` minimum |
| R8 | Auth bypass on /learning/run | uploader+ required |
| R9 | Stale prior_accuracy concurrent updates | each source update is a single UPDATE statement; OK for MVP. Strict serialization deferred. |

## Success criteria
- [ ] Migration 060 applies clean
- [ ] EWMA correctly updates source.predictive_accuracy
- [ ] First observation (NULL prior) seeds with raw calibration_score
- [ ] Decisions without calibration_score are skipped
- [ ] Cap at MAX_DECISIONS_PER_RUN
- [ ] Source attribution log captures (decision, source, prior, posterior)
- [ ] Prompt flags created when ≥5 decisions in window with mean < 0.45
- [ ] /learning/run returns the run_id + summary
- [ ] Auth: run requires uploader+; reads viewer+
- [ ] Tests cover the math + run + auth + red-team

## Out of scope
- Recommendation calibration model retraining
- Auto-retiring flagged prompts
- War-game adversary model updates
- Nightly APScheduler wiring (manual trigger only this loop)
- llm_call_log.brief_id column (follow-up SPEC)
