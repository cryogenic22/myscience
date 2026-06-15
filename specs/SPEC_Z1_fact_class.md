# SPEC Z1 — `fact_class` column on the facts ledger

*Bucket 2 (Data model) loop 2. 30 May 2026.*

## Problem
The v7 design canon defines four fact classes — **◇ reference**, **◆ corporate**, **◈ signal**, **✦ inferred** — with differential agentic ceilings (L4 / L3 / L2 / L1 max). The facts table today has no `fact_class` column, so ceilings can only be enforced by convention, not structurally.

## Contract
- New column `fact_class TEXT NOT NULL` on the `facts` table with a `CHECK` constraint over the four valid values. Default `'corporate'` for backfill (the safest mid-ceiling class).
- `services/fact_ingest.event_to_fact` sets the class based on `predicate` (regulatory_* / trial_result / ma_deal → corporate · safety_signal / pricing_intent → signal · everything else default per a small map).
- `services/facts_ledger.assert_fact` accepts a `fact_class` parameter (defaults to `'corporate'` for back-compat).
- `services/facts_ledger.facts_as_of` and `services/context_layer.query_facts` both accept an optional `fact_class` filter.
- Backfill script `scripts/backfill_fact_class.py` walks existing facts and sets `fact_class` from the predicate via the same map.

## Acceptance tests
1. **Migration applies cleanly.** Column exists, CHECK constraint enforces the four values.
2. **`classify_predicate('regulatory_approval')` returns `'corporate'`.** Pure mapping function.
3. **`classify_predicate('safety_signal')` returns `'signal'`.** Pure mapping.
4. **`classify_predicate('unknown')` returns the default `'corporate'`.** Default semantics.
5. **`event_to_fact` includes `fact_class` on the FactDraft.** Z2 builds on this; Insight derived_from references must be facts whose `fact_class` is known.
6. **`assert_fact(fact_class='signal', …)` persists the class.** Round-trip.
7. **`query_facts(filter, fact_class='corporate')` filters correctly.** Read path.

## Out of scope (drift guard)
- No ceiling enforcement (Phase C).
- No UI surface for the glyph (frontend later).
- No automatic class change on supersession (a corrected fact keeps its original class semantics).

## Files
- NEW `schema/migrations/067_fact_class.sql`
- NEW `scripts/backfill_fact_class.py`
- MOD `services/fact_ingest.py` (set `fact_class` on draft)
- MOD `services/facts_ledger.py` (accept + persist + filter)
- MOD `services/context_layer.py` (accept + propagate filter)
- NEW `tests/test_fact_class.py`

## D-Q1 amendment — fact_class by SOURCE (15 Jun 2026, COORDINATION §8.2, Design A)

The four classes are an **agentic-ceiling / trust tier** (reference→L4 … inferred→L1), *not*
a domain taxonomy (domain lives on `predicate`). A prod probe (15 Jun) found 79.8% of facts
in the `corporate` bucket, of which **98.8% originate from authoritative registry/regulatory
sources** (ClinicalTrials.gov + FDA), not news — they had simply fallen into the
`DEFAULT 'corporate'`. That capped the coverage-quality lens (PR #276) at "partial" for
efficacy/safety/regulatory forever, since only `reference` counts as substantive.

**Resolution (no migration, no new classes):** `reference` now means *peer-reviewed
scientific truth* **OR** *authoritative registry/regulatory ground truth*, classified by
**SOURCE**:
- Authoritative sources (`AUTHORITATIVE_SOURCES` in `services/fact_emitters/base.py`:
  ClinicalTrials.gov, FDA Orange Book / SPL labels / shortages) → `reference`.
- News (`pharma_news`) → `corporate`; FAERS spontaneous reports (`openfda_faers`) →
  `signal`; derived/computed → `inferred`. **Only the `corporate` default catch-all is
  upgraded** — a deliberately-set class (`signal`/`inferred`) is never touched.

Forward: `resolve_fact_class()` applied in `emit_one`. Existing rows: source-aware
`scripts/backfill_fact_class.py` (idempotent; wired into `auto_curate` step 2.6 so it
self-heals). Also: `_coerce_fact_class` default aligned `signal`→`corporate` (honest
contextual default, matching `DEFAULT_FACT_CLASS`). The Platform lens substantive set stays
`{reference}` — no `_is_substantive` change required.

### D-Q1 files
- MOD `services/fact_emitters/base.py` (`AUTHORITATIVE_SOURCES` + `resolve_fact_class`, applied in `emit_one`)
- MOD `services/dossier_kb.py` (`_coerce_fact_class` default `signal`→`corporate`)
- MOD `scripts/backfill_fact_class.py` (source-first reconcile + callable `run()`)
- MOD `scripts/auto_curate.py` (step 2.6 reconcile)
- MOD `tests/test_fact_class.py`, `tests/test_dossier_kb.py` (D-Q1 assertions)
