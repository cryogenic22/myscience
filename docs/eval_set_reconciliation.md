# Eval Set Reconciliation — draft v0.1 → calibrated v1.0

**Date:** 2026-06-11
**Author:** data lane (Claude)
**Inputs:** `docs/eval_set_draft.md` (team draft) · live prod probe (`etl_runs`, table counts, chat-handler reachability trace)
**Output:** `benchmark/eval_pharma_v1.yaml` (machine-readable, judge-ready)

> The team's draft is excellent and its *gates, gold_must_include, traps and
> pass_criteria are preserved verbatim* in v1.0. This note records only the
> **calibration** changes — the world the eval is scored against — so the team
> can confirm them. Per the conservation rule, I calibrate the world; I do not
> move the bar.

## TL;DR — three things the team should know

1. **The `connector_state` in the draft does not match what we actually ingest.**
   Most numbers are off, and the biggest (CT.gov "11.5M") is the *upstream source
   size*, not our ingest (we hold **5,636** trials). Calibrated table below.
2. **None of the six "missing" connectors have a dedicated table.** They write
   into shared canonical tables — and several land data that **no chat path can
   reach**. The draft folds this into "closed-world honesty," but it is a
   distinct, third failure mode worth measuring separately.
3. **Only 7 of 19 items are pure reasoning-layer tests.** The rest are gated by
   missing data (5) or unreachable-but-ingested data (7). The baseline will be
   low for *two different reasons*; the eval now tags each item so we fix the
   right layer.

## Calibrated connector state (probed 2026-06-11)

`landed` = rows in the **queryable** table a chat query can reach (the truth),
not `etl_runs.records_processed` (scanned, not retained).

| connector | draft `records` | **landed (prod)** | queryable table | chat-reachable |
|---|---|---|---|---|
| clinicaltrials_gov | 11,533,457 | **5,636** | clinical_trials | yes |
| ema | 88 | ~88 **trials** | clinical_trials | EUCTR *trials* only — **no EMA product info / labels** |
| pubmed | 15,756 | **4,548** | pubmed_articles | yes |
| pubmed_central | 386 | 386 | pmc_articles | yes |
| openfda_drug_labels | 191 | 191 | drug_labels | yes |
| openfda_faers | 2,562 | 2,562 | adverse_events | yes |
| fda_shortages | 37,754 | events → market_events | market_events | **partial** — no filterable "in shortage" status |
| fda_orange_book | 235 | → drugs / patents / regulatory_milestones | (mixed) | drugs yes · patents partial · **regulatory_milestones unreachable** |
| sec_edgar | 6 | → companies / knowledge_chunks | (mixed) | companies yes · **filing pipeline disclosures RAG-only** |
| chembl_bioactivity | 830 | **671** | bioactivities | partial (not in primary search config) |
| pubchem_compounds | 21 | ~5 (merged onto drugs) | drugs | yes |
| cms_nadac_pricing | 0 | **0** | drug_pricing | none — genuinely empty |
| open_targets_genetics | 0 | **0** | (none) | none — genuinely empty |
| mesh_ontology | 147 | 147 (49 MoA) | therapeutic_areas / mechanisms_of_action | yes |

## The third failure mode: ingested-but-unreachable

The draft's G2 assumes the world is binary: data is present (answer it) or absent
(flag it). Prod has a third state — **data was ingested but no chat retrieval
path exposes it**:

- **`regulatory_milestones`** (Orange Book submission/exclusivity) — landed, but
  no intent, no search config, no graph edge reads it. A user cannot retrieve it.
- **EMA product information** — the EMA connector loads EUCTR *trials* into
  `clinical_trials`; it does **not** ingest EMA labels. So **REG-01's premise
  (compare EMA product info vs FDA label) is unsatisfiable** — the honest answer
  is "EMA product information isn't ingested."
- **SEC filing pipeline narratives** — sit in `knowledge_chunks`, reachable only
  by RAG embedding on the company, not as structured pipeline claims. So
  **CI-01 / BD-01** (reconcile investor-claimed pipeline vs trials) have no
  structured retrieval path.

This matters because it splits "the answer is bad" into two fixes with different
owners: **reasoning-layer** (synthesis — closed-world guard, verdict scoping) vs
**retrieval-layer** (platform — expose ingested tables to chat). v1.0 tags every
item with `data_reality.mode ∈ {reachable_reasoning, missing_data, ingested_unreachable}`.

| mode | count | items | what a failure means |
|---|---|---|---|
| reachable_reasoning | 7 | CLIN-01, CLIN-02, CLIN-03, CI-02, DISC-02, HON-02, HON-03 | the reasoning layer can and should do better — **fixable in synthesis** |
| missing_data | 5 | REG-01, BD-02, MAX-01, DISC-01, HON-01 | only correct answer is "source unavailable" — empty-connector honesty |
| ingested_unreachable | 7 | PV-01, PV-02, REG-02, CI-01, BD-01, MAX-02, SUP-01 | data exists but chat can't reach it — needs a **retrieval path**, not better prose |

## Open questions for the team

1. **CT.gov calibration:** the draft's gold for CLIN-01 cites "PubMed ~15.7k / PMC
   386." Real PubMed is 4,548. Should the gold quote the *real* sample sizes, or
   keep the draft's numbers as illustrative? (v1.0 keeps gold verbatim; the judge
   is given the *real* connector_state as ground truth, so it grades against 4,548.)
2. **REG-01 viability:** EMA product info isn't ingested. Keep REG-01 as a
   `missing_data` honesty test (correct answer = "EMA labels unavailable"), or
   retire it until an EMA-label connector exists? (v1.0 keeps it, mode=missing_data.)
3. **Scoring model:** the judge defaults to `gpt-4o` (the synthesis model is
   `gpt-4o-mini`, too weak to grade). Confirm that's acceptable, or pin a specific
   judge model for reproducibility.

## What's built alongside this

- `benchmark/eval_pharma_v1.yaml` — calibrated, machine-readable, 19 items.
- `benchmark/pharma_eval.py` — LLM-judge harness (fail-closed, quote-required for
  G2 on missing/unreachable items). Lane-2 (live system + judge), never a PR gate.
- `tests/test_pharma_eval_harness.py` — Lane-1 deterministic tests of the scoring
  logic (no LLM, no DB).
- `benchmark/reports/pharma-eval-baseline.json` — the first honest baseline.
