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
| Independent review handoff + reviewer seat | **`docs/REVIEW_LOG.md`**, **`docs/REVIEWER_BRIEF.md`**, `.claude/commands/review-gate.md` |
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
work needs a real prod probe; an independent reviewer pass recorded in
`docs/REVIEW_LOG.md`. Branch protection
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
`pharma_core` ontology, RxNorm/ATC crosswalk, OntoWiz/Domain-Forge SME
codification, Helix CI+wargaming demand spec, temporal/decision-memory). The
throughline: **govern intelligence objects, not documents** — decompose
questions into dimensions, make gaps/uncertainty/provenance first-class, keep
temporal + decision memory.

**Verdict after a grounded codebase probe: most of the spine already exists.**
The doc is ~80% validation/sharpening, ~20% real new build. Already built on
`origin/main` (NOT all visible in a stale checkout — verify against `origin/main`,
not the local branch): bitemporal facts ledger (`valid_from/to`, `as_of`,
anticipatory, `superseded_by`), 8-domain dossier w/ readiness scoring, signals +
KBQ + impact, scenarios + EWMA calibration, grounding-enforced war-game
adversaries, decision briefs + signing + outcome detection + learning (EWMA
source-accuracy), `DecompositionPlanner→QuestionMatrix` (~90%, 5 YAML playbooks),
**RxNorm/ATC crosswalk + identity-level semantic resolution** (`services/{rxnav_crosswalk,ontology_crosswalk,crosswalk_loader,semantic_resolution}.py`,
`#199/#200/#205`), `PhaseTransitionEmitter` (`#202`).

### Platform lane loops (highest-leverage first)
| # | Loop | Why | Touches |
|---|---|---|---|
| **P1** | **Serialize `QuestionMatrix` into the chat/ask API** (dimensions × entities × facts + per-cell coverage gap/thin/covered) | The matrix is computed then **thrown away** — surfacing it is the doc's "MVP 2 = 3x smarter" at ~zero data cost; it's the API contract for the 4-panel UI | `api/routes/chat.py`, `api/schemas.py`, `services/unified_handler.py` |
| **P2** | **Wire PLAN stage into `UnifiedChatHandler`/CTX pipeline** (understand→plan→retrieve→reason) | Planner runs *beside* CTX today, not *inside* it; this is the platform L3 next-loop already on the roadmap | `services/unified_handler.py`, `services/ctx_pipeline.py`, `services/domain_intelligence/` |
| **P3** | **Add `ask_success_rate` question class + playbook** (development/trial/regulatory/access/commercial lenses + explicit denominator-missing gap) | The doc's flagship example ("success rate for diabetes drugs"); cheap, high demo value | `domain/pharma/packs/`, `services/domain_intelligence/playbook.py` |
| **P4** | **Governed-object search modes** (facts/signals/gaps/evidence/scenario) returning confidence·source_class·freshness·review_status, not chunks | Doc's "MVP 1"; search today returns generic entities — the "RAG soup" the memos warn against | `services/search.py`, `services/ask_engine.py`, `api/routes/search.py` |
| **P5** | **Question/persona-aware graph + evidence-lineage view + overlays** (confidence/freshness/review/contradiction) | Graph today is generic 1-hop neighbourhood ("Wikipedia wearing a stethoscope"); make it a lens on the answer | `services/graph.py`, `api/routes/graph.py`, `apps/ci/` |
| **P6** | **Helix readiness checklist as an API contract** (per-domain readiness + contradiction count + calibration completeness + internal-data restriction flags) | Readiness already computed in dossier; surface it so "beautiful but unsupported" output fails loud | `services/dossier_kb.py`, `api/routes/` |
| **P7** | **Temporal as-of + decision-replay API** (`GET /decisions/{id}/replay`, `/intelligence/as-of`, `/scenarios/{id}/probability-history`) | `ReplayBundle` + bitemporal ledger exist; expose them so "what did we know then?" is answerable | `api/routes/decisions.py`, `services/decision_signing.py` |

### Data lane loops (reinforce / build)
| # | Loop | Why | Touches |
|---|---|---|---|
| **D1** | **Build the 5 "data-we-already-hold" emitters**: TrialOutcome, RegulatoryMilestone, Investigator(KOL), PublicationClaim, CompanyFinancial | Source tables exist but never become facts — `fact_emitters/base.py` names this "the single biggest gap-fill"; PhaseTransition already done (#202) | `services/fact_emitters/`, `services/dossier_kb.py` `_PREDICATE_DOMAIN` |
| **D2** | **Payer/pricing pillar** — wire NADAC + CMS-ASP (parser exists, unused) into a `PricingEmitter`; stand up minimal payer-policy schema (formulary_status/PA/step_edit) even before a paid feed | "Payer access is often the game"; launch wargames die in prior-auth without it | `connectors/cms_asp.py`, `connectors/nadac.py`, `services/fact_emitters/`, `schema/migrations/` |
| **D3** | **Bioactivity `drug_id` linkage backfill** — `BioactivityEmitter` is built but dormant (all `bioactivities.drug_id` NULL) | Switches on the molecular/target lens already coded; ChEMBL connector linkage fix | `connectors/chembl.py`, `integration/`, `services/fact_emitters/mechanisms.py` |
| **D4** | **Contradiction handling + scenario downward-calibration** — add signal→scenario stance (supports/contradicts) so a contradicting signal can *refute*, not just corroborate | Calibration only moves probability UP today; "don't average contradictions away — they're often the insight" (conservation-adjacent) | `services/scenario_calibration.py`, `services/fact_signals.py` |
| **D5** | **Extend crosswalk to configuration-level identity** (SCD/SBD → product_configuration) + `mapping_relation`/review states + `crosswalk_records` governance | Substance-level crosswalk shipped; identity levels (substance→product→config→market-auth) are what unblock *correct* pricing/pack/payer facts | `services/crosswalk_loader.py`, `domain/pharma/packs/`, `schema/migrations/` |
| **D6** | **Bitemporal epistemology** — add `known_to_team_at`/`detected_at` distinct from world-validity `valid_from/to` | Enables *fair* hindsight ("nobody could have known yet"); operational bitemporal exists, epistemic doesn't | `schema/migrations/`, `services/facts_ledger.py` |

### Cross-cutting (codify as gates — both lanes)
The doc's `quality_gates`/`fail_if` clauses map onto our conservation-gate
philosophy. Promote a handful to Lane-1 eval cases / Lane-2 checks:
`payer_class_not_applied_to_specific_product` (crosswalk eval already specifies
`PAYER_POLICY_CLASS_NOT_EQUAL_ATC_CLASS`), `news_creates_signal_not_fact`,
`every_scenario_probability_change_has_a_calibration_row`,
`NPV_requires_assumptions+sensitivity` (we currently leave NPV `None` on
purpose — keep that), `ATC_alone_cannot_create_exact_product_fact`.

### 7.1 Helix CI+wargaming deep-dive — net-new gaps (verified vs `origin/main`)

A line-by-line check of the Helix + temporal/decision-memory section
(`raw_notes.md` §3733-5278) surfaced concrete schema-level gaps the P/D table
above named only loosely. **Grounded facts:** facts ledger has
`valid_from/valid_to/asserted_at/superseded_by` (operational bitemporal ✓);
`fact_class∈{reference,corporate,signal,inferred}` ✓; `tenant_scope` on facts ✓
(internal-data hook exists); signal review-lifecycle `candidate→reviewed→shipped`
✓; `news→signal` discipline via `SIGNAL_WORTHY` ✓; decision `state_log` table ✓;
decision `replay` endpoint ✓; `pharma_core.yaml` + `pharma_question_playbooks.yaml`
✓. The gaps below are real on `main`:

| # | Net-new gap (Helix-specific) | Evidence on main | Lane / sharpens |
|---|---|---|---|
| **H-a** | **Temporal graph edges** — `entity_links` has only `confidence/created_at/link_type`; no `valid_from/valid_to/evidence_fact_ids/superseded_by_edge_id`. Graph "lies by omission" (shows things as simultaneously true that were true at different times). | `schema/migrations/002_entity_links.sql` | Data; sharpens P5/P7 |
| **H-b** | **Scenario probability *history*** — `scenario_calibration` recomputes current_prob from prior each run (idempotent) and persists only a `calibration_note`; no `scenario_probability_history` time-series (prev→new→delta→triggering_signal→method→reviewer→ts). | `services/scenario_calibration.py` | Data; sharpens D4/P7 |
| **H-c** | **Decision *memory* snapshot** ≠ state_log — we have `decision_brief_state_log` (transitions) but no `context_at_time / facts_available_at_time / gaps_known_at_time / assumptions / options_considered / variance / what_we_learned`. Can't answer "what did we believe then?" | `052_decision_briefs.sql`, `049_decisions.sql` | Platform; sharpens P7 |
| **H-d** | **Dossier readiness states incomplete** — only `complete/in_progress/gap`; Helix needs `contradicted / stale / internal_only` too. No domain-level contradiction or staleness surfacing. | `services/dossier_kb.py` | Platform+Data; sharpens P6/D4 |
| **H-e** | **3 of 5 Helix domain packs missing** — have `pharma_core` + `pharma_question_playbooks`; missing `pharma_source_contracts` (source→trust-tier→must-capture→may-emit), `pharma_fact_signal_gap_contracts`, `pharma_wargame_playbooks` (scenario_types/actor_types/move_types + per-actor optimise/trust/constraints/countermoves). | `domain/pharma/packs/` | Data (contracts) + Platform (wargame) |
| **H-f** | **Actor model is freeform** — `war_game_adversary` persona is an unstructured `persona_jsonb`; no `what_they_optimise_for / what_evidence_they_trust / constraints / plausible_countermoves`; reactor is a templated stub (no LLM). | `services/war_game_adversary.py` | Platform |
| **H-g** | **Signal *operational* lifecycle + stance** — status is review-only (`candidate/reviewed/shipped`); no `new/triaged/escalated/dismissed/stale` and no supports/contradicts stance toward a scenario (blocks H-b downward calibration). | `services/fact_signals.py` | Data; sharpens D4 |
| **H-h** | **4 missing epistemic timestamps** — facts carry `asserted_at` (≈detected) but not `observed_at / detected_at / known_to_team_at` distinctly, and no `contradicts_fact_ids`. Blocks fair hindsight ("nobody could have known yet"). | `065_facts_ledger.sql` | Data; = D6 (now precise) |

**Red-team readiness (the doc's CagriSema test):** today we'd PASS "every
fact→evidence", "entity resolved at right level", "news≠clinical", "tenant-scoped
internal facts", "NPV not fabricated" (we leave it `None`). We'd FAIL "every
scenario probability change has audit" (H-b — note exists, history doesn't),
"contradiction surfaced not averaged" (H-g/D4), and "as-of reconstruction of an
engagement" (only decision-replay exists; no `/intelligence/as-of`).

---

## 8. Independent reviewer queue - 2026-06-13

Source report: `docs/independent-cross-lane-review-20260613.md`

Reviewer verdict: `FINDINGS_OPEN`. The F6 specialist eval is the right content
quality gate, but the Platform/Data/Frontend seams need tightening before the
system should be called SME-grade for pharma intelligence.

### Open findings by lane

| Finding ID | Owner | Severity | Required action |
|---|---|---|---|
| `MZ-XR-20260613-001` | Data | High | Make source coverage source-specific, not table-wide, before Platform consumes it. Shared tables like `clinical_trials`, `market_events`, and `drugs` need source filters. |
| `MZ-XR-20260613-002` | Platform | High | Replace hardcoded coverage-honesty caveats with Data's structured source-state summary once `001` is fixed; keep deterministic fallback only for true no-source domains. |
| `MZ-XR-20260613-003` | Data | Medium | Make NADAC rows point to the exact DKAN CSV artifact used, not the dead legacy Socrata URL; clarify attempted vs inserted row counts. |
| `MZ-XR-20260613-004` | Frontend | Medium | Rename proxy FAIR UI to quality until true source-FAIR dimensions exist; show profile-load failure as failure, not an empty dossier. |
| `MZ-XR-20260613-005` | Platform | Medium | Treat `benchmark/eval_runner.py` as smoke/regression; use F6 pharma eval as the SME content-quality gate once merged. |
| `MZ-XR-20260613-006` | Data | Low | Add inserted aliases and canonical-choice evidence to the brand alias manifest, not only de-smear reversals. |

### Platform instructions

- Own `MZ-XR-20260613-002` and `MZ-XR-20260613-005`.
- Do not broaden F6 pass claims until coverage honesty is source-state driven or
  the residual is explicitly accepted by the owner.
- After Data closes `MZ-XR-20260613-001`, wire structured source coverage into
  `services/unified_handler.py` and expose `limitations` / `review_flags` as an
  API-visible contract, not only narrative text.
- Keep the old eval runner as a regression/smoke layer; make the F6 pharma eval
  the decision-quality/content-richness gate.

### Data instructions

- Own `MZ-XR-20260613-001`, `MZ-XR-20260613-003`, and
  `MZ-XR-20260613-006`.
- Fix source coverage at the source-specific level before asking Platform to
  consume `coverage_brief`.
- For NADAC, store or expose the resolved DKAN CSV URL, dataset year/title, and
  retrieval timestamp. Do not cite the dead legacy endpoint for live rows.
- For brand aliases, keep conservation proof in the handoff: manifest rows,
  alias inserts, canonical-choice evidence, and reverse path.

### Frontend instructions

- Own `MZ-XR-20260613-004`.
- Use "Quality" language for dataset-level proxy scores until the API provides
  source-level FAIR dimensions.
- Add a visible source-profile failure/degraded state with retry.
- Prepare DataHub source dossiers to display structured `limitations` and
  `review_flags` when Platform/Data expose them.

### Closure protocol

Each lane should append a handoff packet to `docs/REVIEW_LOG.md` when addressing
one or more IDs. Include the finding IDs, branch/worktree, commit range, tests
run, non-vacuity proof, and lane-specific evidence:

- Data: row counts, source filters, freshness, provenance, manifest/idempotence.
- Platform: response-contract proof, eval gate deltas, and no protected-surface
  edit-to-pass.
- Frontend: API assumptions, visible UX states, and component/build evidence.

---

## 9. Independent DataHub reviewer queue - 2026-06-13

Source report: `docs/independent-datahub-review-20260613.md`

Reviewer verdict: `FINDINGS_OPEN`. The merged DataHub work is directionally
strong and should not be re-built, but the follow-up seams below should close
before more generic connectors depend on the same contracts.

### Open findings by lane

| Finding ID | Owner | Severity | Required action |
|---|---|---|---|
| `MZ-DH-20260613-001` | Platform | High | Fix `/catalog/datasets/{source_key}/fair` key semantics: query/aggregate by `source_type` if the route accepts source keys, or rename it to dataset-name semantics. Add route-level tests. |
| `MZ-DH-20260613-002` | Frontend | High | Wire Catalog/DataHub to D-API-2: use backend `fair_overall`, add FAIR API client, and populate source dossier FAIR dimensions. |
| `MZ-DH-20260613-003` | Data | Medium | Preserve onboarded generic connector `source_id` in downstream-visible provenance so multiple RSS feeds do not collapse under `rss`. |
| `MZ-DH-20260613-004` | Data / Platform | Medium | Distinguish newly created onboarding rows from idempotent replay (`201` vs `200`, or `created: true/false`). |
| `MZ-DH-20260613-005` | Data | Medium | Write the L4b `WebScrapeConnector` pre-build contract before implementation: robots, selector failure, source_id provenance, skip counts, live probe. |

### L4b pre-build gate

Before building `WebScrapeConnector`, Data should land or hand off a short design
contract covering:

- robots.txt handling and polite fetch limits;
- required selector schema and fail-closed behavior for empty selector matches;
- no-id skip counting, undated-row retention, and malformed HTML behavior;
- registered `source_id`, page URL, selector version, retrieval time, and content
  hash in provenance;
- one real public prod probe where robots permits scraping.

### Closure protocol

Each lane should close its IDs through `docs/REVIEW_LOG.md` with branch/worktree,
commit range, tests, and non-vacuity proof. Frontend closure must include API
wiring tests; Platform closure must include route-level FAIR tests; Data closure
must include conservation/provenance proof.

---

## 10. Independent current cross-lane reviewer queue - 2026-06-15

Source report: `docs/independent-cross-lane-review-20260615.md`  
Review log: `MZ-REVIEW-003`

Reviewer verdict: `FINDINGS_OPEN` for Frontend only. The reviewed Platform/Data
work was directionally sound; the active Graph Explorer frontend branch has one
trust-impacting path-finder issue to close before merge.

### Open findings by lane

| Finding ID | Owner | Severity | Required action |
|---|---|---|---|
| `MZ-XR-20260615-001` | Frontend | High | In Graph Explorer path mode, clear the committed From/To entity when the selected search input text is edited, and disable `Show Path` until a new suggestion is picked. Add a test proving `api.graphPath` cannot run against stale entity ids. |

### Frontend instructions

- Own `MZ-XR-20260615-001` on `origin/claude/frontend/graph-explorer-simpler`.
- Keep the shared `EntitySearch` component, but add an explicit selection invalidation path (`onQueryChange`, `onClearSelection`, or parent-owned input state).
- Test the real failure mode: pick From/To, edit one selected input without committing a new suggestion, verify the button disables and no stale path request is sent.

### Cleared in this pass

- `/healthz` commit SHA surface (`f850ee7`) - no blocker found.
- Unified live chat `decomposition_matrix` key (`6b31e85`) - no blocker found.
- D-Q1 source-first fact-classing branch (`origin/claude/data/dq1-factclass-reference`) - forward and backfill paths use `resolve_fact_class`.
- Coverage-quality planner branch (`origin/claude/platform/coverage-quality`) - aligned with Design A; should land after D-Q1 as already sequenced.
