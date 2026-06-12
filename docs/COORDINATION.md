# Coordination — Market Zero (canonical board)

> **This file is the single living coordination surface.** It supersedes
> `docs/archive/AGENT_BACKLOG.md` (stale, 2026-05-11, framed backend↔frontend
> only). If another doc disagrees with this one about lanes or process, this one
> wins. Last updated: 2026-06-08.

There are now **three** concurrent agent lanes, not two. The old board assumed a
single backend agent; it didn't, and two backend sessions sharing one working
tree collided (a MeSH-connector fix was swept into an unrelated benchmark PR,
#190). This file fixes that with explicit lanes + a worktree convention.

---

## 1. Source of truth (where the harness/context lives)

Both backend lanes inherit and defer to these — do **not** fork or duplicate them:

| Concern | Canonical file(s) |
|---|---|
| Operating rules / architecture / conventions | **`CLAUDE.md`** (auto-loaded every session) |
| The harness floor (conservation gates, two lanes, DoD) | **`.claude/rules/conservation-gates.md`** |
| Anti-duplication index, test + commit conventions | `.claude/rules/anti-slop.md`, `test-requirements.md`, `commit-conventions.md` |
| The success-definition surface (the "bar") | **`protected-surface.txt`** → `.github/CODEOWNERS` |
| Active specs (everything else in `specs/` is archived) | `specs/SPEC_001…`, `SPEC_002…`, `SPEC_DATA_001…`, `specs/data_strategy.md`, `specs/README.md` |
| Coordination (this) | **`docs/COORDINATION.md`** |

Anything in `specs/archive/` is **history**, not current intent. Don't plan from it.

---

## 2. Lanes (ownership)

| Lane | Owner | Owns (primary) |
|---|---|---|
| **Platform / Harness** | backend session "platform" | harness + CI gates (`tests/test_conservation_gates.py`, `test_schema_completeness.py` **ceilings**, `test_backend_smoke_manifest.py`, `protected-surface.txt`, `.github/workflows/`, `scripts/connector_health.py`, `scripts/gen_codeowners.py`); **agentic orchestration** (`services/agent/`, `services/unified_handler.py`, `services/ctx_pipeline.py`); **API layer** (`api/`); **domain/chat** (`api/routes/chat.py`, `services/chat_handlers/`, `domain/`); **search** (`services/search.py`, `services/ask_engine.py`); **benchmark/live-eval** (`benchmark/`); **dossier read-path** (`resolve_asset` in `services/dossier_kb.py`); **CI UI** (`apps/ci/`, frontend CI surfaces) |
| **Data / Sensing / Intelligence** | backend session "data" | the layer that surfaces data + sensing: `connectors/`, `integration/` (ETL), `services/fact_emitters/`, `services/fact_signals.py`, `services/scenario_calibration.py`, `services/intelligence_feed.py`, ontology, `schema/migrations/`, `scheduler/config.py` (`FRESHNESS_SLA_DAYS`), and `services/dossier_kb.py` **`_PREDICATE_DOMAIN` / fact-routing** |
| **Frontend** | Antigravity | `frontend/` (app shell, design system, non-CI surfaces) |

**Roadmap reassignment (2026-06-08):** the platform session's old data-substrate
loops — connector status-emission, ChEMBL `bioactivities.drug_id` linkage,
pricing-source replacement, domain-intelligence fact-routing (KBQ-2/4/5) — are
**data-lane work** and belong to the data session, not platform.

---

## 3. Isolation — git worktrees per session (the structural fix)

Two agents must **never** share one working tree + HEAD. Each session works in
its own worktree:

```bash
# from the main checkout, once per session:
git worktree add ../mz-<lane> -b claude/<lane>/<topic> origin/main
# work, commit, push, PR from ../mz-<lane>; remove when merged:
git worktree remove ../mz-<lane>
```

This makes HEAD collisions structurally impossible. Branch-per-PR still applies.

---

## 4. Seam files (touched by both backend lanes — coordinate)

| File | Platform owns | Data owns | Rule |
|---|---|---|---|
| `services/dossier_kb.py` | `resolve_asset` / snapshot read-path | `_PREDICATE_DOMAIN` / fact-routing / emitter-facing logic | small PRs; announce in §6 before a large edit |
| `tests/test_schema_completeness.py` | `ORPHAN_CEILINGS` + gate logic (protected) | adds `FRESHNESS_SLA_DAYS` entries via `scheduler/config.py` (different file) | ceilings are a monotonic ratchet — only tighten, owner-reviewed |
| `schema/migrations/` | (rarely) | normally | **data lane reserves the next migration number**; platform asks in §6 before adding one |

---

## 5. Definition of Done & gates (both lanes)

Per `.claude/rules/conservation-gates.md`: RED→GREEN with pasted output; Lane-1
gate green; no conservation regression; no protected-surface edit-to-pass; data
work needs a real prod probe; an independent reviewer pass. Branch protection
requires 5 checks: *Backend conservation invariants (DB-free)*, *Frontend
typecheck (no vacuous green)*, *Schema drift static checks*, *benchmark*,
*Backend unit smoke (DB-free)*.

---

## 6. In-flight / recently shipped (keep this current)

**Platform (this session), 2026-06-08:** shipped #187 (ratchet conservation
ceilings), #188 (backend unit-smoke gate + 5th required check), #190 (live-eval
capture+score gate, baseline 73.4%), #191 (real entity resolution in dossier
read-path). Open follow-ups: connector_health→alert; the `/chat` "Novavax"
attribution bug; `Decimal` serialize crash in `services/workspace.py:225`.

**Data (data session):** MeSH ontology fix (descriptors' descendants; shipped on
main via #190, originally #189). Owns the reassigned substrate loops above. See
`specs/data_strategy.md` + `specs/SPEC_DATA_001`.

**Frontend (Antigravity):** see `docs/PRODUCT_BACKLOG.md` (feature/UI board).

---

## 7. Strategy-doc gap analysis → loop backlog (2026-06-12)

Source: `docs/raw_notes.md` (6 expert memos — search+graph-from-domain-layer,
`pharma_core` ontology, RxNorm/ATC crosswalk, OntoWiz/Domain-Forge, Helix
CI+wargaming demand spec, temporal/decision-memory). Throughline: **govern
intelligence objects, not documents.** Grounded probe verdict: **~80% of the
spine already exists** (bitemporal facts ledger, 8-domain dossier+readiness,
signals+impact, scenarios+EWMA calibration, war-game adversaries, decision
briefs+signing+outcome+learning, `DecompositionPlanner→QuestionMatrix` ~90%,
RxNorm/ATC crosswalk+semantic resolution, `PhaseTransitionEmitter`). ⚠️ verify
"missing" vs `origin/main`, not a stale local branch.

### Platform lane loops (highest-leverage first)
| # | Loop | Why |
|---|---|---|
| **P1** | Serialize `QuestionMatrix` into the chat/ask API | matrix is computed then thrown away — "MVP 2 = 3x smarter" at ~zero data cost; API contract for the 4-panel UI |
| **P2** | Wire PLAN stage into `UnifiedChatHandler`/CTX pipeline | planner runs beside CTX, not inside it |
| **P3** | Add `ask_success_rate` question class + playbook | the doc's flagship example |
| **P4** | Governed-object search modes (facts/signals/gaps/evidence/scenario) | search returns chunks today |
| **P5** | Question/persona-aware graph + evidence-lineage view + overlays | generic 1-hop neighbourhood today |
| **P6** | Helix readiness checklist as API contract | readiness computed, not surfaced |
| **P7** | Temporal as-of + decision-replay API | `ReplayBundle` exists, unexposed |

### Data lane loops
| # | Loop | Status |
|---|---|---|
| **D1** | 5 "data-we-hold" emitters (TrialOutcome, RegulatoryMilestone, Investigator/KOL, PublicationClaim, CompanyFinancial) | open |
| **D2** | Payer/pricing pillar — NADAC+CMS-ASP→`PricingEmitter` + minimal payer-policy schema | open (contract drafted in §7.1 H-e / pack #2) |
| **D3** | Bioactivity `drug_id` linkage backfill (BioactivityEmitter dormant) | open |
| **D4** | Contradiction handling + scenario downward-calibration | ✅ **shipped #223** (signal stance) — see §7.2 |
| **D5** | Extend crosswalk to configuration-level identity (SCD/SBD) | open |
| **D6** | Bitemporal epistemology (`known_to_team_at`/`detected_at`) | open |

### Cross-cutting gates (both lanes)
Promote the doc's `fail_if` clauses to Lane-1/Lane-2 checks:
`payer_class_not_applied_to_specific_product`, `news_creates_signal_not_fact`
(✅ encoded in source-contracts #224), `every_scenario_probability_change_has_a_calibration_row`,
`NPV_requires_assumptions+sensitivity` (keep NPV `None`), `ATC_alone_cannot_create_exact_product_fact`.

### 7.1 Helix CI+wargaming deep-dive — net-new gaps (verified vs `origin/main`)

Grounded: facts ledger has `valid_from/valid_to/asserted_at/superseded_by`;
`fact_class∈{reference,corporate,signal,inferred}`; `tenant_scope` on facts;
signal review-lifecycle `candidate→reviewed→shipped`; `news→signal` via
`SIGNAL_WORTHY`; decision `state_log` + `/replay`; `pharma_core.yaml` +
`pharma_question_playbooks.yaml`. Real gaps:

| # | Net-new gap | Lane / status |
|---|---|---|
| **H-a** | Temporal graph edges — `entity_links` has no `valid_from/valid_to/evidence_fact_ids` (graph "lies by omission") | Data / open |
| **H-b** | Scenario probability *history* — calibration recomputes + stores only a note; no `scenario_probability_history` time-series | Data / open (next after D4) |
| **H-c** | Decision *memory* snapshot ≠ state_log — no `context_at_time/facts_available_at_time/assumptions/what_we_learned` | Platform / open |
| **H-d** | Dossier readiness states — only `complete/in_progress/gap`; need `contradicted/stale/internal_only` | Platform+Data / open |
| **H-e** | 3 of 5 Helix packs missing → `pharma_source_contracts` ✅ **shipped #224**; `pharma_fact_signal_gap_contracts` + `pharma_wargame_playbooks` open | Data+Platform |
| **H-f** | Actor model freeform (`persona_jsonb`); no optimise/trust/constraints/countermoves; reactor is a stub | Platform / open |
| **H-g** | Signal *operational* lifecycle + stance — stance ✅ **shipped #223**; `new/triaged/escalated/dismissed/stale` open | Data |
| **H-h** | 4 missing epistemic timestamps (`observed_at/detected_at/known_to_team_at`) + `contradicts_fact_ids` (= D6) | Data / open |

### 7.2 Loop execution log + data-team handoffs (2026-06-12, data lane)

**Shipped this session (data lane, all PRs open, reversible/prod-probed):**
- **#222** — Loop A: restored **22 demoted canonicals** spine-wide (the #218/#220
  follow-up). `resolve_asset('drug:Mounjaro'/'tirzepatide')`→`9da2b55d` (269 live
  facts, active); valsartan/sitagliptin phosphate/finerenone/metformin restored.
  Reversible, idempotent, 10 tests.
- **#223** — Loop B / D4 / H-g: scenario-relative **signal stance** → downward
  calibration. Negative rival signal now refutes a competitive-pressure scenario
  (toward floor); zero-regression. 11 tests. Prod `signals.direction` = 408 pos /
  108 neg / 109 neutral.
- **#224** — Loop C / H-e: **`pharma_source_contracts.yaml`** — enforceable
  source→object contracts (all 15 connectors governed; `may_emit`∈real
  predicates; fails closed). 7 tests.

**Open follow-ups (tracked):**
- **Excluded-config absorb** — 24 names whose richest row is `record_status='excluded'`
  (1261 facts+trials, e.g. `ivabradine oral tablet` 114 facts) out-rank the
  canonical because `_exact_lookup` excludes merged/superseded but not excluded.
  Fix = ABSORB (repoint), not a naive filter (would silently hide real facts).
  Reuse `scripts/consolidate_junk_drug_rows.py`.
- **H-b** scenario_probability_history; **D1/D2/D3/D5/D6** per §7.

**Data-team handoff — scheduled TA population (oncology → other TAs):** MVP anchor
stays **obesity/metabolic + CagriSema** (richest existing substrate, reuses all CI
code). **Next TA = oncology**, then immunology/other in sequence. Build per-TA seed
lists (drugs/companies/trials) and schedule ingestion via `scheduler/runner.py`
(parameterize the connector/enrichment post-tasks by a TA cohort, bounded per
tick) so coverage advances automatically rather than by hand. Don't expand a TA
until its connectors emit governed facts (per the source contracts in #224) — more
sources without emitters is "a premium swamp" (raw_notes).
