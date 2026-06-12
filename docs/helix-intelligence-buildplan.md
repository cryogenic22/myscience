# Helix CI + Wargaming — Data/Intelligence Build Plan & Output-Quality Benchmark

*Author: data/intelligence lane. Date: 2026-06-12. Status: active plan.*

> **How to read this.** This is the data/intelligence lane's grounded build plan
> for making the system *generate* Helix-grade CI + wargaming output, plus the
> design for an **output-quality benchmark** that gates each loop. It
> **complements `docs/COORDINATION.md §7`** (the canonical loop backlog,
> P1–P7 / D1–D6 / H-a…H-h) — it does not restate it. Where §7 names a gap, this
> doc adds the *expert judgment, sequencing, and the eval that proves the loop
> moved real quality*. Every "exists / missing" claim below was verified against
> `origin/main`, not assumed.

---

## 1. The one reframe (and the proof)

The demand artefact (Helix v8) is a **Sense → Decide → Act → Learn** operating
model, not a UI. The instinct "to generate Helix we need more connectors" is
wrong. The blocker is the **emitter + contract + temporal** layers, and **most of
the spine already exists.** Stop rebuilding it; close named holes.

**Verified-present on `origin/main` (do NOT rebuild):**

| Capability | Evidence |
|---|---|
| 8 fact-emitters (source rows → governed facts) | `services/fact_emitters/` (ClinicalTrial, AdverseEvent, DrugLabel, Mechanism, Bioactivity, Literature, Competition, PhaseTransition) |
| **Bitemporal** fact ledger | `schema/migrations/065_facts_ledger.sql`: `valid_from/valid_to`, `asserted_at`, `superseded_by`, anticipatory future-dated facts, GIST range index |
| Fact governance | `fact_class ∈ {reference,corporate,signal,inferred}`, `tenant_scope` (internal-data hook), review state |
| Sensing | `services/fact_signals.py` (signals + KBQ + impact, `news→signal` discipline), `services/intelligence_feed.py` |
| Scenarios + calibration | `services/scenario_calibration.py` (EWMA corroboration) |
| Wargame adversaries (grounding-enforced) | `services/war_game_adversary.py` |
| Decisions | briefs + signing + state_log + outcome detection + `replay` endpoint |
| Question decomposition | `DecompositionPlanner → QuestionMatrix`, 5 YAML playbooks |
| Semantic resolution + RxNorm/ATC crosswalk | `services/{semantic_resolution,rxnav_crosswalk,ontology_crosswalk,crosswalk_loader}.py` |
| Cross-source answer eval (gates G1–G4, llm_judge) | `benchmark/eval_pharma_v1.yaml`, `benchmark/eval_runner.py` |

**Bottom line for the teams:** ~80% of the Helix object chain
(Source→Evidence→Fact→Signal→Insight→Gap→Scenario→Move→Decision→Outcome→Learning)
is built. The work is *filling specific gaps and wiring them to an output-quality
benchmark*, not green-field architecture.

---

## 2. Critical judgment — where the demand memo is right vs overweight

1. **"Emitters not connectors" — right, and further along than assumed.** See §1.
   The risk is the team reads the memo as green-field and re-litigates settled
   design.
2. **"Make payer/pricing a pillar" — UNDERSTATED. It is source-*blocked*, not
   unbuilt.** `connectors/nadac.py` + `connectors/cms_asp.py` exist but emit
   **0 rows** on prod (`eval_pharma_v1.yaml`: `cms_nadac_pricing landed: 0`,
   `open_targets_genetics: 0`). **This is a procurement/data-rights decision
   before it is an engineering task.** Decide the source (paid feed: Policy
   Reporter / MMIT / 46brooklyn; OR client payer-advisory data; OR honest
   WAC-list-price-only) *before* scheduling a `PricingEmitter`. Do not let
   "payer pillar" sit in a sprint while the real blocker is a contract. This is
   the single most likely place a Helix demo becomes fiction.
3. **The war-room is closer to "theatre" than the memo fears — but the evidence
   layer is real.** Actor model is a freeform `persona_jsonb`; reactor is a
   templated stub with no LLM (H-f). BUT we already *pass* the memo's worst
   fears: facts→evidence lineage is enforced, news≠fact, NPV is left `None` not
   fabricated. So the fix is **structured actor economics**
   (`pharma_wargame_playbooks.yaml` + typed persona), not "add provenance."
4. **Contradiction handling is the highest-value cheap win and is
   conservation-shaped.** Calibration only moves probability *up* today (H-g/D4).
   "Don't average contradictions away — they're often the insight" maps directly
   onto our conservation-gate philosophy (no silent reconciliation of conflicting
   evidence). This is loop **#1 in the execution order** below.
5. **Longitudinal/decision-memory — right, and the *epistemic* half is the gap.**
   The ledger is *operationally* bitemporal (`valid_from/to` + `asserted_at`).
   It is **not epistemically** bitemporal: `asserted_at` conflates
   "became true" / "source reported" / "team could have known". Without splitting
   `observed_at` / `detected_at` / `known_to_team_at`, **fair hindsight is
   impossible** (the system blames the team for a policy detected *after* the
   decision). This is loop **#2**.

---

## 3. Execution order (as directed) + therapy slice

**Loops, in order:** **(0) this doc + the output benchmark → (1) contradiction
handling + signal stance → (2) temporal / decision-memory → (3) D1 emitters.**
Each loop ships only when it moves a real number on the **Helix Output-Quality
Benchmark** (§5).

**Therapy slice order:** **obesity/CagriSema → oncology → immunology.** Obesity
first because the demo case is obesity and the semaglutide / tirzepatide /
CagriSema spines are the richest and just data-repaired (#218/#220).

### Loop 1 — Contradiction handling + signal stance  *(data lane; sharpens D4/H-g)*
- **What:** add a `stance ∈ {supports, contradicts, neutral}` from a signal toward
  a scenario; let a `contradicts` signal apply **downward** calibration; surface
  contradictions as a first-class object instead of averaging them away.
- **Files:** `services/fact_signals.py`, `services/scenario_calibration.py`,
  `schema/migrations/` (signal stance column; reserve next migration #).
- **DoD:** a contradicting competitor readout *lowers* a scenario probability
  with a logged calibration row; a contradiction is visible, not reconciled;
  benchmark `contradiction_surfaced` case flips RED→GREEN.

### Loop 2 — Temporal / decision-memory  *(data lane; sharpens D6/H-b/H-c/H-h)*
- **What (narrow v1, per the memo's own advice):**
  1. **Epistemic timestamps** — add `observed_at`, `detected_at`,
     `known_to_team_at` (nullable, additive) distinct from `asserted_at`, plus
     `contradicts_fact_ids`. (H-h)
  2. **Scenario probability history** — a `scenario_probability_history`
     time-series (`prev→new→delta→triggering_signal_ids→method→reviewer→ts`),
     persisted on every calibration. (H-b)
  3. **Decision-memory snapshot** — `context_at_time / facts_available_at_time /
     gaps_known_at_time / assumptions / options_considered / variance /
     what_we_learned` captured at decision time (≠ the existing transition
     state_log). (H-c) — *seam with platform; announce in COORDINATION §6.*
- **Files:** `schema/migrations/`, `services/facts_ledger.py`,
  `services/scenario_calibration.py`, `services/decision_*` (seam).
- **DoD + GUARDRAIL:** an **as-of regression gate** — "reconstruct engagement X at
  date D returns exactly the facts knowable then." Bitemporal rots silently; the
  gate is non-negotiable or it will be confidently wrong in six months.

### Loop 3 — D1 emitters (the data we already hold)  *(data lane)*
- **What:** convert already-ingested rows that never become facts:
  `RegulatoryMilestoneEmitter`, `TrialOutcomeEmitter` (endpoint/result, distinct
  from the design-level `ClinicalTrialEmitter`), `InvestigatorEmitter` (→ KOL),
  `PublicationClaimEmitter` (claim-level, distinct from the metadata-level
  `LiteratureEmitter`), `CompanyFinancialEmitter`. Register in
  `fact_emitters/base.get_emitters` + route predicates in
  `dossier_kb._PREDICATE_DOMAIN`.
- **DoD:** each emitter lifts its dossier domain from `gap/thin` → `covered` on
  the CagriSema slice, with a prod before/after probe; benchmark
  `domain_coverage` rises.

> Payer/pricing (D2) is **deferred pending the sourcing decision** (§2.2) — it is
> explicitly *not* in this sequence until the source exists. Flagging the
> dependency loudly is the honest move.

---

## 4. Reverse-engineering: source → object, anchored to reality

The memo's 8-source taxonomy is correct; the value-add here is **what each source
must EMIT, and its current state**. Every connector should justify itself by the
object it produces (this becomes `pharma_source_contracts.yaml`, H-e).

| Source class | Connector state on main | Must emit | Gap |
|---|---|---|---|
| Regulatory (FDA/EMA/labels) | labels ✓ (191), orange_book partial, EMA trials only | `regulatory_approval`, `label_indication/warning`, `regulatory_milestone` | **RegulatoryMilestone emitter (Loop 3)**; EMA product-info not ingested |
| Clinical trials | CT.gov ✓ (5,636), EUCTR ~88 | `clinical_trial_design` ✓, **`trial_outcome/endpoint`**, `phase_transition` ✓ | **TrialOutcome emitter (Loop 3)** |
| Publications/congress | PubMed ✓ (4,548), PMC ✓ (386) | `publication_claim`, `endpoint_result`, `evidence_limitation` | **PublicationClaim emitter (Loop 3)** — current `LiteratureEmitter` is metadata-level |
| Corporate filings | SEC partial (~6, RAG-only) | `corporate_revenue`, `pipeline_event`, `risk_factor` | **CompanyFinancial emitter (Loop 3)**; structured extraction from `knowledge_chunks` |
| News/PR | news ✓ (39k market_events) | `market_event`, `competitor_signal` (signal, **not** fact) | discipline ✓; stance gap (Loop 1) |
| **Payer/pricing** | **NADAC 0, CMS-ASP 0 (source-blocked)** | `formulary_status`, `PA`, `step_edit`, `wac/nadac_price` | **SOURCING DECISION FIRST** (§2.2), then schema + emitter |
| Internal client data | `tenant_scope` hook ✓; no ingestion path | `internal_fact`, `kol_position`, `payer_objection`, `decision_constraint` | ingestion + access-control + export-control (differentiator *and* liability) |
| RWD/consumer/channel | not ingested | `uptake/switching/persistence/channel` signals | future; depends on data rights |

**Internal client data — the differentiator, grounded:** the governance primitive
(`tenant_scope` on facts) **already exists**. The gap is the *ingestion path* +
access control + `internal_fact` class + export-control enforcement. The system
must be able to say "this insight uses internal Novo-scoped KOL evidence and
cannot be exported." Do not let internal facts leak across tenants — that is a
lawsuit, not a bug.

---

## 5. The Helix Output-Quality Benchmark (the eval upgrade)

**Problem the upgrade solves:** `eval_pharma_v1.yaml` benchmarks **chat-answer**
quality (a Q&A returns grounded prose). Helix output quality is about the
**intelligence OBJECTS** — does a competitor readout produce a *correctly-stanced
signal* that *moves a scenario with an audit row* that *yields a decision option
with evidence and no fabricated NPV*? That is a different test surface.

### 5.1 Design — extend, don't replace
A new sibling set **`benchmark/eval_helix_output_v1.yaml`** + a runner extension
`benchmark/helix_eval.py`, reusing the existing **binary-gate + graded** model and
`llm_judge`. A Helix case is not one Q&A; it is a **scenario fixture** (an
engagement state) scored on the object chain it produces.

### 5.2 The six output-quality dimensions (each a binary gate; all must pass)

| Gate | Asks | Fails if (from the memo's red-team) |
|---|---|---|
| **OQ1 sensing** | every signal links to facts; facts link to evidence; entity resolved at the right identity level | a signal with no fact; news masquerading as clinical fact |
| **OQ2 calibration-audit** | every scenario probability change has a `scenario_probability_history` row (prev→new→delta→trigger→method→reviewer→ts) | probability moved with no audit row |
| **OQ3 contradiction** | conflicting evidence is *surfaced*, and a `contradicts` signal can *lower* probability | contradiction averaged/reconciled away |
| **OQ4 decision-grounding** | every decision option carries evidence facts + assumptions; NPV (if shown) has assumptions+sensitivity | strategic prose w/o evidence; NPV without assumptions |
| **OQ5 provenance/closed-world** | insight→fact→evidence resolvable; gaps are first-class; payer-class not applied to specific product | hides missing evidence; class policy as product-specific |
| **OQ6 as-of integrity** | reconstruct the engagement at date D returns exactly facts knowable then | leaks current truth into the past |

### 5.3 Graded marks (0–4, llm_judge) — *quality*, not just pass
`sensing_richness`, `scenario_plausibility`, `decision_actionability`,
`evidence_strength`, `calibration_explainability`. These track whether output is
*good*, not merely *valid* — the difference between "a handsome storytelling
machine" and decision-grade intelligence.

### 5.4 The fixture (CagriSema vertical slice)
One scenario fixture drives the benchmark and the loops:
`competitor readout signal` + `payer signal` + `internal-KOL signal` →
`scenario` whose probability moves *with a logged row* → `decision option` with
evidence lineage. Per `COORDINATION.md §7.1`, today this fixture **passes**
OQ1/OQ4/OQ5 and **fails** OQ2 (history), OQ3 (contradiction), OQ6 (as-of) — and
those three failures are exactly Loops 1 and 2. **The benchmark is therefore the
acceptance test for the loop sequence.**

### 5.5 Wiring
- Lane-1 (deterministic, PR-hard): the **structural** OQ gates that don't need a
  live LLM/DB (a probability change *must* write a history row; a `contradicts`
  signal *must* be able to lower probability; an as-of query *must not* read
  current truth) — pin these as unit/regression tests so a future edit can't
  silently regress them.
- Lane-2 (scheduled/live): the full `llm_judge` graded run on the CagriSema
  fixture + the existing `eval_pharma_v1` answer set, reported as a scorecard
  (sensing / calibration / contradiction / decision / provenance / as-of), so a
  beautiful-but-unsupported output **fails loud**.

---

## 6. What would make this fail (heed these)

- **Building the screens before the evidence machinery is capable.** Gate every
  surface on the benchmark, not on visual polish.
- **Treating payer as engineering when it's procurement.** §2.2.
- **Bitemporal rot.** §3 Loop 2 guardrail — the as-of regression gate.
- **NPV theatre.** Keep NPV `None` until a defensible model with assumptions +
  sensitivity exists. (We already do this; don't regress it.)
- **Class-vs-product payer conflation.** Already specified as an eval trap
  (`PAYER_POLICY_CLASS_NOT_EQUAL_ATC_CLASS`); keep it.
- **Internal-data leakage across tenants.** Enforce `tenant_scope` + export
  control before any internal ingestion path ships.

---

## 7. Definition of done for the program

The program is "Helix-ready" for the CagriSema slice when the Output-Quality
Benchmark reports: OQ1–OQ6 all green on the fixture, graded marks ≥ 3.0 average,
and the as-of regression gate is in Lane-1. Each loop below ships against that
benchmark with a prod before/after probe, per `conservation-gates.md` DoD.
