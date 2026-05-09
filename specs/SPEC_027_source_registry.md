✓ Signed off by Claude
Pending sign-off by Antigravity (Source Health admin surface consumes this)

# SPEC_027: Source Registry + 5-Dimensional Quality Scoring

## Goal
Replace today's hard-coded connector list with a persisted **Source Registry**
that tracks each source's identity, license posture, and a computed
**5-dimensional quality score**. Per `specs/CI_Agent_Reimagined_Spec.md`
§8.3, every source is itself an entity with a tracked quality measure
that drives materiality scoring + evidence ranking + frontend Source
Health admin.

## Why now
Today's `connectors/` are static Python classes. There's no DB record
of which sources we currently rely on, no per-source quality history,
no surface that tells the user "the FDA Orange Book has degraded — last
3 fetches lagged the published timestamp by >24h." Without this:
- SPEC-028 Learning Service can't update `predictive_accuracy` per source
- SPEC-031 Materiality Scoring can't weight signals by source quality
- Frontend Source Health admin (spec §9.3) has nothing to render

## Non-goals (deferred)
- Replacing the `connectors/` Python classes themselves. Source Registry
  is metadata about those connectors; the connectors keep their
  fetch-and-normalize role.
- Auto-discovering new sources (Source Discovery Agent — spec §7.1).
- Real-time license-quota polling (just store the renewal date for now).
- Backfilling all existing connectors at registration time. Initial
  registry seeding is a one-shot script (not in this loop).

## Data contract

### Table: `sources`
Per-source identity + license posture. Stable identity for the lifetime
of the source. Dedup by `source_id` (canonical name like
`clinical_trials_gov`, `fda_orange_book`).

| Column | Type | Notes |
|---|---|---|
| `source_id` | TEXT PK | Canonical name; matches connectors' `source_type` |
| `display_name` | TEXT NOT NULL | Human-friendly name |
| `tier` | INTEGER NOT NULL | 1-4 per spec §6.1.1 (1 = authoritative, 4 = licensed CI) |
| `kind` | TEXT NOT NULL | `free` \| `paid` \| `internal` |
| `base_url` | TEXT | API or web base URL |
| `description` | TEXT | Free-form |
| `active` | BOOLEAN NOT NULL | `true` unless deactivated |
| `license_status` | TEXT | `active` \| `expired` \| `rate_limited` \| `not_applicable` |
| `license_renewal_at` | TIMESTAMPTZ | When the paid license expires; null for free sources |
| `rate_limit_per_min` | INTEGER | Optional; informational |
| `usage_profile` | JSONB | Per-source usage policy: `{bulk_extraction, persist_in_kg, derive_analytics, attribution_required}` |
| `latest_quality_id` | UUID | FK source_quality_history(quality_id); set after first compute |
| `created_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW() |
| `updated_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW() |

### Table: `source_quality_history`
Append-only time series of quality scores. The "latest" row is referenced
by `sources.latest_quality_id` for fast lookup; history retained for trend
visualization.

| Column | Type | Notes |
|---|---|---|
| `quality_id` | UUID PK | gen_random_uuid() |
| `source_id` | TEXT NOT NULL | FK sources(source_id) |
| `computed_at` | TIMESTAMPTZ NOT NULL | DEFAULT NOW() |
| `coverage` | REAL CHECK (0-1) | 0-1 of relevant entities the source covers |
| `latency_p95_ms` | INTEGER | Source freshness (lower = better) |
| `latency_score` | REAL CHECK (0-1) | Normalized 0-1 (1 = freshest) |
| `predictive_accuracy` | REAL CHECK (0-1) | Frac of decisions where this source's evidence proved correct |
| `stability_score` | REAL CHECK (0-1) | 1 - (recent breakage_rate) |
| `license_health_score` | REAL CHECK (0-1) | License posture score |
| `overall_score` | REAL CHECK (0-1) | Weighted average of the 5 dims |
| `inputs_jsonb` | JSONB | Snapshot of raw inputs that produced these scores |

### Optional table: `source_event_log` (out of scope for this loop)
Per-source operational events (fetch_success, fetch_failure, schema_break,
rate_limit_hit). Will be added when we wire connector lifecycle into the
quality scorer. For now, scorers fall back to placeholder defaults.

## Quality scoring

### Dimensions and weights (defaults)
| Dim | Weight | Source of input |
|---|---|---|
| `coverage`            | 0.25 | Heuristic until SPEC-028 wires real ground-truth comparisons. Default 0.7 for tier-1, 0.5 for tier-2, 0.3 for tier-3, 0.5 for tier-4. |
| `latency`             | 0.20 | Computed from `evidence_records.retrieved_at` p95 lag against current time, where available. Falls back to 0.5. |
| `predictive_accuracy` | 0.30 | Computed from decisions whose evidence_snapshot includes evidence from this source. SPEC-028 will populate this; default 0.5 here. |
| `stability`           | 0.15 | Frac of last 30 days with successful fetches. Stub = 1.0 unless deactivated (then 0). |
| `license_health`      | 0.10 | If `license_status = 'active'`: 1.0; if `expired`: 0; if `rate_limited`: 0.5; if `not_applicable`: 1.0. Reduced linearly within 30 days of renewal. |

`overall_score = Σ (weight × dimension_score)`. Range [0, 1].

### When scores are computed
- On `POST /sources/{source_id}/recompute` (manual trigger)
- Future: nightly batch job (deferred — not in this loop)

### What the scorer reads
- For latency: `evidence_records` filtered by `source_id` (last 1000 rows;
  bounded for cost). Falls back gracefully if `evidence_records` is empty
  (default 0.5).
- For predictive_accuracy: `decisions` joined with `evidence_snapshots`
  joined with `evidence_records` filtered by `source_id`. Same fallback.
- For other dims: source's own row + heuristics.

## API surface

| Method | Path | Purpose |
|---|---|---|
| POST | `/sources` | Register a source (uploader+); idempotent on `source_id` |
| GET | `/sources` | List sources with latest quality (viewer+) |
| GET | `/sources/{source_id}` | Get one source with latest quality (viewer+) |
| GET | `/sources/{source_id}/history` | Quality time series (viewer+) |
| POST | `/sources/{source_id}/recompute` | Recompute quality now (uploader+) |
| PATCH | `/sources/{source_id}` | Update license/active fields (uploader+) |
| GET | `/sources/health-summary` | Aggregate: how many sources active, mean overall_score, tail (lowest 5) (viewer+) |

## Red-team

| # | Vector | Mitigation |
|---|---|---|
| R1 | Score injection via `inputs_jsonb` | Server computes the JSONB; client can't write directly |
| R2 | Source impersonation by registering existing source_id | UNIQUE on source_id; second register is a no-op upsert (returns existing) |
| R3 | License-renewal timestamp manipulation to fake "active" | Validated as TIMESTAMPTZ; uploader role required |
| R4 | DoS via repeated recompute | Rate limit middleware (SPEC-021 D2) covers; per-source recompute bounded by 1000-row evidence query |
| R5 | SQL injection via source_id (TEXT PK) | Parameterized everywhere; PK constraint blocks weird values |
| R6 | Quality score laundering (overwrite history) | source_quality_history is append-only by convention (no UPDATE/DELETE in service) |
| R7 | Cross-tenant source registry contamination | Single-tenant for now; SPEC-030 will compartmentalize |
| R8 | Negative weight values blowing up overall_score | weights are server-side constants; not client-controllable |

## Success criteria
- [ ] Migration 055 applies clean
- [ ] Register is idempotent on source_id
- [ ] Recompute writes a new row to history + updates `sources.latest_quality_id`
- [ ] License-expiry math correctly degrades license_health_score linearly in
      the 30-day window before expiry; 0 after expiry
- [ ] Overall score is the sum of `weight × dimension`, clamped to [0, 1]
- [ ] Health-summary returns counts + mean + bottom-5 list
- [ ] Tests cover dimension scorers in isolation + full recompute flow + auth
- [ ] Full suite green; no regressions

## Out of scope
- Source Discovery Agent (spec §7.1)
- Connector lifecycle events feeding the scorer (deferred)
- Multi-tenant source visibility (SPEC-030)
- Real-time quota polling for paid licenses
