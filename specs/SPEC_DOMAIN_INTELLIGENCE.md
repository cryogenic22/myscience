# SPEC — Domain Intelligence Layer

*Status: design consolidated 2026-06-09 · owner: data lane · supersedes the scattered HTML design notes as the canonical written spec.*

This spec consolidates the semantic-resolution + query-understanding + search/graph
+ ontology work into one architecture, reconciled with the live code and the SME
inputs. It is the durable reference; the HTML docs are the narrative companions.

**SME source docs (authoritative pack content):**
`docs/domain_pack_raw.md` · `docs/YAML_pack1.md` · `docs/chat_domain.md` ·
`docs/graph_search_yaml.md` · `docs/pharmcore_atc.md` · `docs/data-intelligence-strategy.html`.

**Design companions (HTML):** `docs/semantic-resolution-design.html` ·
`docs/domain-intelligence-end-to-end-design.html`.

---

## 1. The thesis

A "match" is not one thing, and an "answer" is not one thing. The system must
**decompose the need before it answers**, **resolve mentions to an identity level**
(not a bare id), **preserve uncertainty**, **explain**, route to **governed objects**,
and **learn from steward corrections**. All pharma judgement lives in **versioned,
SME-authorable domain packs** driving a **generic engine** — not in resolver/handler
code. "The domain pack is the brain; search is the hands; graph is the nervous
system; the chatbot is just the mouth."

## 2. The spine + two governed gateways

```
Source → Evidence → Extraction → [Resolution+Ontology] → Fact → Signal → Insight
         → Gap → Scenario → Decision → Outcome → Learning
```

- **Ingest gateway — semantic resolution** (mention → entity @ identity level, with
  confidence, ambiguity flags, auto/review/escalate routing). Decides what may
  become a Fact. *Phase 1 engine shipped.*
- **Query gateway — the PLAN stage** (ask → decompose into dimensions → route to
  predicates/links/sources → grounded answer-matrix with coverage + gaps →
  answer contract). Decides what intelligence the question needs. *~90% built in
  `services/domain_intelligence/`, NOT wired into `UnifiedChatHandler`.*

Both gateways share one shape and one mechanism (packs + generic engine). Chat,
search, graph and the CI app are four entry points to the **same** PLAN stage.

## 3. Identity levels (canonical — `pharma_core` §1)

`mention → canonical_entity → substance_level → product_level →
configuration_level → market_authorisation_level`, plus `regimen_level`
(treatment instruction, NOT identity). A match's **level is capped by the
attributes actually confirmed**; a contradiction caps it at substance/ingredient.
The cardinal sins the levels prevent: mL-as-strength, mg/mL-as-dose, mono-as-combo,
brand-as-generic, ATC-class-as-exact-product, news-as-clinical-fact.

## 4. The domain-pack suite (10 packs)

| # | Pack | Drives | Owner lane | State |
|---|------|--------|-----------|-------|
| 1 | `pharma_core` | entity types, identity levels, core predicates, resolver policies, external-id priority | Data (ontology) | SME-authored → `docs/pharmcore_atc.md` |
| 2 | `pharma_rxnorm_atc_crosswalk` | RxNorm (IN/PIN/MIN/BN/SCD/SBD/GPCK/BPCK/DF) + ATC (L1–L5) → internal, as evidence-backed crosswalk records | Data (ontology) | SME-authored → `docs/pharmcore_atc.md` |
| 3 | `pharma_semantic_resolution` + `eval` | mention→entity@level matching, lexicon, policy, combo-only | Data | **✅ shipped (#194)** |
| 4 | `pharma_question_playbooks` | PLAN stage: question classes, lenses, dimensions→predicate routes, ambiguity policy, persona overlays, answer contract | Platform wires · Data owns predicates | proposal (#197) |
| 5 | `pharma_search_graph_views` | search modes (evidence/fact/signal/gap/scenario) + graph views (lineage/decomposition/entity/competitive/scenario-impact) + overlays | Platform + Frontend | SME-spec'd → `docs/graph_search_yaml.md` |
| 6 | `pharma_source_contracts` | trust tiers A–D, allowed_uses, must_capture, may_emit, review_triggers | Data (Loop 10) | SME-spec'd → `docs/YAML_pack1.md` |
| 7 | `pharma_fact_signal_gap_contracts` | Evidence/Fact/Signal/Insight/Gap/CalibrationEvent object contracts | Data (Loops 5/6/9) | SME-spec'd → `docs/YAML_pack1.md` |
| 8 | `pharma_confidence_stewardship_eval` | confidence dims, bands, stewardship queues, curator UI, eval, learning | Data (Loop 11) + Frontend | SME-spec'd |
| 9 | `obesity_metabolic_playbooks` | therapy-area dimensions, mechanisms, endpoints, comparators | Data / Forge (LAST) | SME-spec'd |
| 10 | `eval_semantic_resolution` | red-team golden set (runs on every change) | Data | **✅ shipped (#194)** |

**Crosswalk discipline (non-negotiable, `pharma_rxnorm_atc_crosswalk`):** load RxCUI
from RxNorm releases (never hand-maintain); ATC for class reasoning, never product
identity; mappings are records with `relation ∈ {exact, narrower, broader, related,
inferred, rejected}` + `scope` + `confidence` + `source_version` + `review_status`;
**never overwrite internal entity identity**; many-to-many always visible to a
curator; bridge path is RxNorm→internal→ATC (ATC is never the primary resolver).

## 5. Engine ↔ existing code (anti-slop map)

| Capability | Lives in | Action |
|---|---|---|
| typed attribute parser | `domain/pharma/drug_mention_parser.py` | ✅ built (#194) |
| governed resolution model | `services/semantic_resolution.py` | ✅ built (#194); Phase 2 = wire into `integration/entity_resolver.py` |
| PLAN / decompose | `services/domain_intelligence/{playbook,planner,synthesis}.py`; `CTXQueryPipeline.plan_decomposition()` | **built, UNWIRED** — wire into `UnifiedChatHandler` |
| ambiguity detection | — (`chat_handlers/intent.py` is flat regex) | **build** (ambiguity gate) |
| predicate coverage | `scripts/playbook_predicate_coverage.py` | ✅ built (#197) |
| ontology_support score | `semantic_resolution._score` (placeholder 0.6) | **build** — make real via crosswalk (Loop 1) |

## 6. Grounded reality (prod, 2026-06-09)

Fact ledger: 21 predicates; top = `market_event` 5010, `clinical_trial` 4201,
`efficacy_endpoint` 4062. `ask_success_rate` 5-lens coverage:
**trial_endpoint COVERED · regulatory COVERED · development PARTIAL** (phase_transition
/discontinuation/approval_event all missing — 4201 rows are generic clinical_trial
inflation) **· commercial PARTIAL** (launch_event/uptake_signal missing) **·
market_access GAP** (formulary_status/prior_auth/step_edit/hta_decision all missing).
Ontology thin (TAs ~98, mechanisms ~49 post-MeSH; `drugs.chembl_id`=0).

> A perfect decomposition over an empty ledger is structured emptiness. The
> coverage gaps **are** the data-lane build order.

---

## 7. PRIORITY LOOPS (ordered by leverage × dependency; lane-tagged; conservation-gated)

Each loop: own branch off `main` in a `../mz-<topic>` worktree; TDD RED→GREEN
(pasted) → live prod probe (pasted before→after) → independent adversarial review
→ PR. Migrations: data lane reserves the next number (latest applied **090**;
next **091**). `dossier_kb._PREDICATE_DOMAIN` edits stay small + announced.

### Data lane — MINE, do in this order

- **L1 · Ontology spine + RxNorm/ATC crosswalk** *(HIGHEST — unblocks resolution
  quality + class reasoning).* Formalize `pharma_core.yaml` + `pharma_rxnorm_atc_crosswalk.yaml`
  from `docs/pharmcore_atc.md` into `domain/pharma/packs/`; migration **091**
  `crosswalk_records` (relation/scope/confidence/source_version/review_status,
  evidence-backed, never overwrites identity); RxNorm IN/SCD/SBD/MIN loader + ATC
  L1–L5 loader (emit candidate crosswalk records + eval cases on ambiguity);
  backfill `drugs.atc_codes` + `rxnorm_rxcui`; make `ontology_support` real in
  `semantic_resolution._score`. Gate on the SME eval cases (SCD≠ATC-L5, ATC-L4≠exact
  product, metformin-combo, ATC-class≠payer-class). *Also unblocks the inert
  bioactivity relink (chembl_id).*

- **L2 · Phase-transition / development-lens emitter** *(makes `ask_success_rate`
  real).* New `FactEmitter` from `clinical_trials` phase+status history →
  `phase_transition` / `discontinuation` / `approval_event` predicates (+ add to
  `_PREDICATE_DOMAIN`). Re-run `playbook_predicate_coverage.py`: development_success
  PARTIAL→COVERED. Same emitter pattern + governance; idempotent; bounded.

- **L4 · Resolution Phase 2 — persist + wire into ingest.** Migration:
  `resolution_decisions` (the contract); wire `drug_mention_parser` into
  `integration/entity_resolver.py`; route escalate/review into `unresolved_entities`.
  Then the contract packs: `pharma_source_contracts` (Loop 10 — trust tier →
  `source_reliability`), `pharma_fact_signal_gap_contracts` (Loops 5/6/9 — first-class
  Gap, ScenarioCalibrationEvent log, extraction-run audit), `pharma_confidence_stewardship`
  (Loop 11 — bands/queues/steward telemetry + curation queue).

- **L5 · Payer/access emitter** *(market_access GAP → fillable; SOURCE-BLOCKED)* —
  needs a payer-policy ingest first; then `formulary_status`/`prior_authorisation`/
  `step_edit`/`hta_decision` facts.

- **L6 · Sales/launch emitter** *(commercial PARTIAL→COVERED; SOURCE-BLOCKED)* —
  `product_sales`/`launch_event`/`uptake_signal` from filings + launch trackers
  (deferred financial/deal emitters; prod sources mostly empty).

### Platform lane — COORDINATE (not mine to build)

- **L3 · Wire the PLAN stage into chat** *(biggest single UX lever).* Wire
  `plan_decomposition()` into `UnifiedChatHandler` between understand/retrieve;
  ambiguity gate; adopt `pharma_question_playbooks.yaml`; question-decomposition
  panel. Data provides the playbook + the predicates (L2).
- **L8 · Search/graph governed-object views + overlays** per `graph_search_yaml.md`.

### Frontend lane — COORDINATE

- **L7 · Curator cockpit** (crosswalk review card, attribute-comparison, lineage)
  + four-panel answer UI + Domain Forge round-④ pack editing.

### Sequencing summary

Mine, next: **L1 (ontology crosswalk) → L2 (phase-transition emitter)** — both
in-lane, high-leverage, unblock resolution quality + the headline question.
L3/L8 (Platform) and L7 (Frontend) proceed in parallel via coordination. L5/L6
wait on source ingestion. L9 (therapy playbooks) is last, per SME sequencing.
