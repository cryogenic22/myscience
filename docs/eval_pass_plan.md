# Passing the pharma specialist eval — diagnosis, loops, and the data-team share

*Author: data/intelligence lane. Date: 2026-06-13. Grounded against the
`eval_pharma_v1.yaml` run (19 cases, in-process, llm_judge) + a prod probe.*

> **Bottom line:** the eval does not fail because the system is *wrong* or because
> the *substrate is missing provenance*. It fails because the **synthesis layer
> does not cite its sources or state its coverage limits in the prose.** The fix
> is dominated by the answer/synthesis (platform) lane; the data lane's leverage
> is real but narrower than it looks.

## 1. Where we are (pasted, not claimed)
```
PHARMA-EVAL: 1/19 items pass (5%), graded mean 2.68/12
gate pass-rates:  G1 provenance 5% | G2 closed-world-honesty 10% | G3 no-count-fallacy 68% | G4 domain-correctness 90%
by data-reality:  reachable_reasoning 0% | missing_data 20% | ingested_unreachable 0%
```
Prod probe (the part that reframes everything):
```
facts (live): 15048; with source_doc_id: 15047 (100%)   evidence_records: 12395
fact_class: corporate 11064 / reference 3160 / inferred 582 / signal 242
```

## 2. What the numbers MEAN (the binding constraints)
- **G4 90% / G3 68%** — answers are mostly *correct* and avoid the count fallacy. Correctness is **not** the blocker.
- **G1 5% / G2 10%** — the prose **doesn't attribute claims to a named source + freshness**, and **doesn't state coverage limits / hedges** when data is thin. Item-pass needs *all four* gates, so G1+G2 cap everything at 5%.
- **reachable_reasoning 0%** is the tell: even where the data is fully there, the strict bar fails → the gap is **how answers are written**, not what data exists.
- **Provenance already exists** (100% `source_doc_id` → evidence_records): the system *can* cite truthfully; it just doesn't surface it. So G1 is a **surfacing** problem, not a backfill.
- The lone G4 outlier is **CLIN-02** (compare): wrong mechanism because resolution landed on a churned tirzepatide row — a **resolution-stability** bug, not a knowledge gap (#217 already curated the dual mechanism).

## 3. The pass path (ordered by leverage)
1. **Surface per-claim provenance (G1) + closed-world honesty (G2) in synthesis** — flips the 0% reachable items, uses provenance the facts already carry.
2. **Stabilize the judge** — #215 found binary pass is judge-noise-limited on G1; majority-vote so real gains show.
3. **Resolution stability (G4 outliers).**
4. **Reachability + richer facts (data)** — expand the answerable set.
5. **Measure against the stronger specialist bar** (runner extension).

## 4. Loops by lane

### Track A — Synthesis / answer quality  (**Platform lane — DOMINANT for eval-pass**)
- **A1 — finish/merge #215** (closed-world guard + count de-bias + provenance legend) → G1/G2/G3. The in-flight start; it was held on judge-noise (do A3 with it).
- **A2 — per-claim citations**: take each fact's `source_doc_id → evidence_record → source name + freshness` and render it inline per material claim (not a footer). The data is there (100%); this is prompt + assembly work in `services/llm.py` / `unified_handler` / `ctx_context`.
- **A3 — stabilise the llm judge** (majority vote / self-consistency) in `benchmark/pharma_eval.py` so G1 binary pass reflects real quality, not judge variance.
- **A4 — serialize the response contract** (decomposition / facts / signals / gaps / citations) in the chat API — this is platform **P1** (the QuestionMatrix is computed then discarded). Unlocks the structured specialist dimensions *and* makes the answer structurally honest (gaps/limitations become first-class, not prose afterthoughts).

### Track B — Substrate enablers  (**Data team — narrower than expected, but real**)
> Provenance backfill is **NOT** needed (already 100%). Focus where the data
> lane actually moves an eval gate:
- **B1 — source-coverage + freshness METADATA queryable at answer time.** G2 (closed-world honesty) needs the synthesis to say *"FAERS = 2,562 records, updated weekly; labels = 191"* — accurately. That per-source `landed / freshness / reach` state already exists in `pharma_source_contracts.yaml` (#224) + `connector_health`; expose it to the answer path so the guard states limits from data, not guesses. **This is the #1 data-lane lever for G2.**
- **B2 — reachability**: several sources LAND data no chat path reaches (`regulatory_milestones`, Orange Book patents, SEC structured pipeline) — the `ingested_unreachable` items (0%). Wire retrieval (predicate route / search config) so the honest "can't retrieve" becomes an actual answer. Each one flips its eval item.
- **B3 — richer facts via the D1 emitters** (RegulatoryMilestone / TrialOutcome / Investigator / PublicationClaim / CompanyFinancial): lifts dossier domains `gap→covered`, expanding the set of items that are answerable at all (more `reachable_reasoning`).
- **B4 — domain-correctness on the RESOLVED row**: ensure curated facts (tirzepatide dual GIP/GLP-1, etc.) sit on the row resolution actually lands on — couples with C1. (#217 curated it; the churn moved resolution off it.)
- **Not on the eval-pass path (don't over-invest for evals):** payer/pricing/epi/sales connectors. The eval is *calibrated* — those are `missing_data` items whose correct answer is an honest refusal (a **G2/synthesis** behaviour), so they're passed by Track A, not by ingesting the data. Ingesting them is a *product* win, not an *eval-pass* lever.

### Track C — Resolution + measurement  (**mine — D-intel**)
- **C1 — canonical-resolution stability**: the detector (#236) + heal + absorb the residual + the deferred `_exact_lookup` `excluded` filter once the attributable rows are absorbed → fixes the G4 CLIN-02-class outliers (right row → right mechanism).
- **C2 — eval runner extension**: apply the specialist model's **hard-fail caps** + the prose-scorable dimensions (source-hierarchy, identity-level, decision-quality) now; defer the contract-dependent dims (decomposition, evidence-chain) to A4. So we *measure* progress against the stronger bar as A/B land.

## 5. What "passing" looks like
- **Near-term:** once A1+A2+A3 land, the `reachable_reasoning` items (currently 0%) should pass G1+G2 and rise toward the G3/G4 ceiling — i.e. item-pass climbs from 5% toward a realistic 50–80% of the reachable subset. `missing_data` items pass via honest refusal (Track A). `ingested_unreachable` items pass via honesty now, or convert to answered as B2 lands.
- **Release bar (from the specialist pack):** automated ≥ 0.85, **0 critical hard-fails**, citation-validity ≥ 0.90, source-hierarchy ≥ 0.85 — plus SME calibration.

## 6. Sequencing (who starts what)
| # | Loop | Lane | Unblocks |
|---|---|---|---|
| 1 | A1 #215 + A3 judge stability | Platform | G1/G2/G3 across all reachable items |
| 2 | A2 per-claim citations | Platform | G1 specifically (uses 100% source_doc_id) |
| 3 | C1 resolution stability | D-intel (me) | G4 outliers (CLIN-02) |
| 4 | B1 coverage/freshness metadata at answer time | Data | G2 accuracy (closed-world) |
| 5 | A4 response contract (P1) + C2 runner extension | Platform + me | structured gates + measurement |
| 6 | B2 reachability, B3 emitters, B4 resolved-row facts | Data | expands the answerable set |

**The single most important message for the data team:** *the substrate is in good
shape for the eval — provenance is 100%, answers are 90% domain-correct. The eval
fails in synthesis (cite + hedge), which is platform. Your highest-leverage eval
loops are B1 (surface coverage/freshness so the honesty guard is accurate) and B2
(reachability), not more ingestion.*
