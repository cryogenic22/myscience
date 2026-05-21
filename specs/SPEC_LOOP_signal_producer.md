# SPEC — Signal Producer (events → signals)

**Status:** In build · **Date:** 2026-05-22 · **Loop:** events→signals producer

## Problem
`/ci`'s vision surfaces (Signals DB, Reviewer, materiality drawer, evidence
cards, agent activity) read the `signals` table, which is **empty in prod**.
569 `market_events` exist but nothing promotes them. Migration 037 says "the
intelligence layer writes to here" — that producer was never built. The only
`INSERT INTO signals` in the repo is in a test.

## Goal
A deterministic producer that promotes `market_events` → `candidate` signals,
satisfying every `signals` schema invariant, wired to the scheduler and
runnable as a one-shot backfill. Lights up the empty surfaces with real data.

## Source → target mapping

`market_events` (source) → `signals` (target):

| signals column | source / rule |
|---|---|
| `event_id` | `market_events.id` (FK) |
| `headline` | `description` truncated to 120, else humanized `event_type` |
| `summary` | `description` truncated to 500 |
| `direction` | reuse `impact_router.classify_impact_direction(event_type)` |
| `confidence_tier` | `source_tier`: tier_1→confirmed, tier_2→reported, tier_3→inferred; downgrade to `disputed` if trust_score < 0.3 |
| `trust_score` | `market_events.trust_score` (already 0–1), clamp [0,1] |
| `impact_score` | `_impact_score(event_type, trust_score)` → 0–1 (event-type base × trust blend) |
| `impact_tier` | from impact_score: ≥0.66 high, ≥0.33 medium, else low |
| `kbq_tags` | `_classify_kbq(event_type, description)` → ≥1 of {regulatory, clinical, access, financial, ma, product, strategic} |
| `rule_version_id` | `"signal_promoter_v1"` |
| `primary_entity_type/id/name` | from `market_events`; fall back to `drug`/`drug_id` |
| `related_entity_ids` | `{}` (v1) |
| `evidence_document_ids` | `[event_id]` — cites the source event; satisfies cardinality ≥1 (no FK), honest provenance |
| `status` | `candidate` |

## Rules

- **kbq classification** (`_classify_kbq`): event_type first
  (approval/regulatory_setback→regulatory; trial_readout→clinical;
  safety_signal→clinical; ma_deal→[ma,strategic]; supply_disruption→[access,product]),
  then for `general` events keyword-scan the description
  (fda/approval/label→regulatory; trial/phase/endpoint/readout→clinical;
  price/wac/formulary/access/payer→access; revenue/guidance/earnings→financial;
  acquisition/merger/deal→ma). Default `[strategic]`. Always ≥1 tag.
- **idempotent**: skip any `market_events.id` already present as `signals.event_id`.
- **quality gate**: skip events with no resolvable primary entity
  (both `primary_entity_id` and `drug_id` null) — count + report, don't fabricate.
- **headline never empty**: NOT NULL + ≤120; fall back to humanized event_type.
- **deterministic**: same event row → same signal fields (no LLM, no randomness).

## Reuse (anti-slop)
- `services/impact_router.py::classify_impact_direction` + `IMPACT_DIRECTION_MAP`
- `services/materiality.py` left for the existing UPDATE path (producer sets a
  base impact_score; materiality scoring stays a separate concern)

## Interface
`services/signal_promoter.py`:
- `classify_kbq(event_type: str, description: str | None) -> list[str]`
- `confidence_tier_for(source_tier: str | None, trust_score: float) -> str`
- `impact_for(event_type: str, trust_score: float) -> tuple[float, str]`  # (score, tier)
- `build_signal_row(event: dict) -> dict | None`  # None = skipped (quality gate)
- `promote_events(db, *, limit: int = 1000, since_days: int | None = None) -> PromoteResult`
  - selects market_events not already in signals, builds rows, bulk-inserts, returns counts

`PromoteResult`: `{scanned, promoted, skipped_existing, skipped_no_entity}`.

## Integration
- Scheduler: add a `signal_promotion` step in `scheduler/runner.py` (after ingestion).
- Backfill: `scripts/promote_signals.py` one-shot for the 569 prod events.

## Acceptance
1. `build_signal_row` produces a row satisfying all NOT NULL / CHECK constraints
   for representative events (approval, safety_signal, ma_deal, general).
2. Idempotent: re-running `promote_events` inserts 0 on the second pass.
3. Quality gate: event with no primary entity → skipped, counted.
4. Every produced signal has ≥1 kbq_tag and ≥1 evidence_document_id.
5. confidence_tier / impact_tier respect the documented thresholds.
6. After backfill, prod `/signals` returns count > 0 and Signals DB / Reviewer render data.
