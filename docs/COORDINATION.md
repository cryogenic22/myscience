# Coordination — Market Zero (canonical board)

> **This file is the single living coordination surface.** It supersedes
> `docs/archive/AGENT_BACKLOG.md` (stale, 2026-05-11, framed backend↔frontend
> only). If another doc disagrees with this one about lanes or process, this one
> wins. Last updated: 2026-06-13.

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
| **Frontend** | Frontend (Claude) agent | `frontend/` (app shell, design system, non-CI surfaces, the **DataHub Catalog UX**) |

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

**Data (data session), 2026-06-13 — Helix Loop 1/2 reconciliation + stance-count
follow-up.** Merged to main: **#227** (Loop 1 — signal polarity `signals.direction`
+ contradiction-aware downward calibration, D4/H-g/OQ3), **#231** (Loop 2a —
`scenario_probability_history` audit ledger, mig 092, H-b/OQ2), plus #232/#233/#234/#235.
This PR (`claude/data/scenario-stance-counts`) closes the structured-data gap left by
those: `calibrate_scenario_prob` computed the stance mix but discarded it, so a
contradiction-driven move was only recoverable by parsing the note prose. **Mig 094**
adds `n_supporting`/`n_contradicting` to the *existing* ledger (NOT a 2nd table) +
`latest_stance_mix()` reader — the structured OQ3 / dossier-`contradicted` (H-d) enabler.
- **Dup reconciliation (a parallel data session built the same loops):** PRs **#223**
  (stance math) and **#228** (prob-history backend) are now **dups of merged #227/#231**
  — being **closed**; **#228** also collided on mig number 092. **#230**'s *backend*
  (contradiction read) is superseded here; its **frontend** (scenarios timeline +
  `⚠ Contradicted` badge, `frontend/src/**`, `components/ci/**`) is **not the data lane**
  → handed to **Platform (CI UI)/Antigravity** — wire `latest_stance_mix()` / the
  ledger's stance cols onto the scenario read shape. **#224** (source-contracts pack,
  H-e) is clean data-lane → **merging**. **#222** (canonical-orphan restore) **deferred**
  pending a prod re-probe (memory: restores may be re-demoted post-#220).
- **PROTOCOL (stop the re-dup): claim a Helix loop in this §6 BEFORE starting it.**
  Data lane reserves the next migration number (next = **095**).

**Platform (this session), 2026-06-13 — CLAIM L0b: unified-handler entity
fan-out collapse.** `services/ctx_pipeline.py` `understand()` returns every CTX
section matching a drug token as a separate detected entity ("semaglutide" →
50+ injection/pen/oral/dose/combo fragments) → `retrieve()` + PLAN + synthesis
fan out per-fragment → 147s/query and a wall of near-duplicate noise (the E0x
grounding + perf root cause; makes the 59-q eval ~2.5h, un-runnable). Fixing in
`ctx_pipeline.py` only (platform-owned; no data-lane seam). Collapses config
fragments to the canonical base before retrieve hydrates. Unblocks clean eval
measurement + the #215 merge. **(MERGED #243.)**

**Platform (this session), 2026-06-13 — CLAIM H2: per-claim NAMED source-class
attribution (G1).** A hydrated CTX drug section bundles many field-claims
(mechanism, company, therapeutic area, supply) into ONE evidence snippet tagged
with one generic "platform knowledge base" bucket — so synthesis could not
attribute the mechanism claim (label/MeSH) separately from the company claim
(drugs@FDA). The SME saw mechanism AND trial counts tagged the same bucket
(judge G1 2% / source-transparency 2/10). Fix is `services/unified_handler.py`
only (platform-owned synthesis path; no data-lane seam): a `_FIELD_SOURCE` map +
`_annotate_section_sources` tags each CTX `KEY:value` field line inline with its
real source class; `_evidence_source` names the section footer by entity type
(via the `TYPE:` line) instead of the generic bucket. F6 v2 pack re-run to
measure the G1 lift. Follows #246 (F6) + #248 (H1).

**Data (data session), 2026-06-13 — CLAIM: DataHub program (layered hybrid).**
Spec = `docs/SPEC_DATA_HUB.md` (12 loops, 4 phases; ~80% reuse). Delivery model
chosen with the owner: **layered hybrid**, not one autonomous end-to-end team.
- **Phase 0 (catalog lenses L1–L1d)** = a **dedicated, parallel** agent, scoped
  **only** to the DataHub catalog surfaces — read-only UI over existing APIs
  (`source_registry`, `connector_health`, `source_coverage`, `schema_introspector`,
  `prompt_registry`). Touches `frontend/` so it overlaps **Antigravity's** lane →
  it stays inside the new catalog views, claims here, and opens a PR for review (no
  self-merge). No backend/migration seam ⇒ collision-safe to run in parallel.
- **Phase 1+ (generic connectors, AI onboarding, autonomous enrich, portability;
  L2–L12)** = **data lane (me), interleaved with the eval-pass loops** under the §7
  claim + §7.4 migration-reservation protocol — NOT a blind parallel backend
  session (this is the exact `connectors/` + `scheduler/` + `schema/migrations/`
  seam that caused the 092 collision). DataHub backend migrations reserve **096+**
  (095 is taken by #241 NADAC, held); none needed for Phase 0.

**Data (data session), 2026-06-13 (evening) — eval PRs reconciled + DataHub L2
started.** MERGED to main: **#240** (B1 source coverage+freshness for the answer
path), **#241** (NADAC pricing revival — DKAN CSV + mig 095 + idempotent history),
each rebased clean + independently reviewed. **#242** (brand-alias de-smear) is
**HELD — independent review BLOCK:** the Lane-2 invariant it claims to green is RED
vs prod (a one-shot field-clear of `brand_name` that ETL re-smears — durability,
not logic; disposition + fix-path on the PR). Now in-flight: **DataHub L2** (mig
096 — connector-type taxonomy + onboarding lifecycle), the first Phase 1 backend
loop, interleaved with the eval work per the layered-hybrid claim above.
- **Followups logged:** `connectors/nadac.py` still points at the dead Socrata
  endpoint (drop from registry or repoint to DKAN); source-level FAIR aggregate
  endpoint does not exist yet (only entity-level) — the DataHub catalog grid needs
  it (handoff surfaced by the Phase 0 L1 agent).

**Platform (this session), 2026-06-13 — CLAIM F6: land the specialist eval
runner.** The heuristic `benchmark/scorers.py` only measures mechanics (intent
match, keyword presence, number-coincidence, citation well-formedness) — NOT
decision quality. The LLM-judge runner `benchmark/pharma_eval.py` (G1-G4 gates +
Q1-Q4 graded, majority-voted) already exists but ran against the 19-item v1 pack
and was never wired as a gate. F6 adopts the normalized **41-item `eval_pharma_v2.yaml`**
(the single machine-readable specialist pack — supersets v1 + embeds the rubric)
as an **opt-in pack via `--eval`** (default stays v1 — promoting the default
measured bar is an owner decision), adds an additive well-formedness test for it,
and runs it on the post-L0b+#215 system for the first real decision-quality
scorecard (scorecard PENDING until the run completes + numbers are pasted). **NOTE: the
eval pack belongs to the platform eval-harness (`benchmark/`); `eval_pharma_v2.yaml`
was also added on data-lane PR #238 — #238 should keep only `docs/eval_pass_plan.md`
and drop the pack to avoid a duplicate. Lane-2 CI wiring of pharma_eval =
owner-gated (protected `.github/workflows/`).**

**Frontend (Claude agent):** general feature/UI board = `docs/PRODUCT_BACKLOG.md`.

**Data (data session), 2026-06-13 — D-API-1 SHIPPED (MERGED #254).** New
self-contained `api/routes/hub.py` router exposes the L2 connector-taxonomy +
onboarding service (`services/connector_taxonomy.py`, #245) over HTTP. Additive
only (a new file + one try/except registration block in `api/app.py`; no existing
route touched, no migration). Independently reviewed (APPROVE) + live prod probe
(read end-to-end through the ASGI app; write path proven against the real schema
inside a rolled-back txn). Endpoints:
- `GET /hub/connector-types` · `GET /hub/connector-types/{name}` — the 6-type
  taxonomy (viewer).
- `GET /hub/onboarding?status=` · `GET /hub/onboarding/{source_id}` — lifecycle
  records (viewer).
- `POST /hub/onboarding/{source_id}` — start onboarding in `draft` (uploader);
  body `{owner, contact, connector_type, go_live_date, escalation}`; idempotent.
- `POST /hub/onboarding/{source_id}/advance` — body `{to_status}`; runs the
  `draft→test→staged→prod→paused→retired` state machine (uploader).
- Status mapping: unknown-type / illegal-transition → 400; no-onboarding-row /
  unknown-source → 404.

**▶ HANDOFF to Frontend (F5 swap off the stub) — two real wiring gaps:** the
wizard's `registerSource()` (`frontend/src/lib/datahubOnboarding.ts`) conflates
*register* + *start onboarding*, but the backend keeps them separate (correctly —
the L2 `source_onboarding` table FKs onto `sources` and only stores the lifecycle
fields). So: **(1)** call `POST /sources` FIRST to create the source row (else
`POST /hub/onboarding/{id}` returns 404 by design — the FK-existence probe), THEN
`POST /hub/onboarding/{id}`. **(2)** the onboarding POST body is
`{owner, contact, connector_type, go_live_date, escalation}` — NOT the full
`OnboardingDraft`; the draft's `config`/`mappings`/`contract`/`trust_tier` belong
to source registration (`/sources` `usage_profile` + the #224 source-contracts
pack), not the onboarding row. The DTO/enum/lifecycle types already match
`OnboardingRecord.to_dict()` 1:1, so the response side is a clean swap.

**▶▶ FRONTEND: build the DataHub Catalog UX — `docs/SPEC_DATA_HUB_FRONTEND.md`.**
That spec is your full build brief: the lens model, **what already exists to reuse**
(the live `/catalog` + `/sources` APIs, the `api.ts` clients, `DataCatalogPanel`/
`SourceProfileCard`/`SourcesPage`, and the **F1 work already on branch
`claude/datahub/phase0-lenses`** — rebase+review+merge it, don't rebuild), the
**backend dependencies** you need from the data lane (§4: D-API-1 connector-types/
onboarding endpoints, D-API-2 source-level FAIR, …), and the **F1–F7 build loops**
with acceptance criteria. The **vision/north-star** is `docs/SPEC_DATA_HUB.md` (the
spec) + **`docs/data-hub-vision.html`** (open in a browser — the visual walkthrough).
**How to build:** reuse-first (anti-slop), CSS-variable styling (no Tailwind color
utilities / no dynamic class names — the v4/Railway gotcha), TDD, honest degradation
for missing fields, claim your loop in §7.6 first, independent `/review-gate` before
merge (no self-merge), `App.tsx`/shell edits additive + minimal.

---

## 7. ⛔ STOP-AND-SYNC — two Data sessions collided (2026-06-13)

**What happened.** Two concurrent sessions both acted as the **Data lane** and
worked the same Helix loops with **no claiming mechanism** → duplicate work + a
**migration-092 collision** (both authored a `092_*.sql`; prod applied *both*).
Duplicated loops: contradiction surfacing (#227 merged ↔ #230 open), probability
history (#231 merged, `092_scenario_probability_history` ↔ #228 open,
`092_scenario_calibration_history`), signal stance (#227 ↔ #223).

> **Both Data sessions: STOP starting new loops. Read §7.1–§7.4 first, then claim.**

### 7.1 The protocol (binds every Data session)
1. **One backlog.** §7.3 is the only loop list. Do **not** plan from the
   build-plan doc or `MEMORY.md` alone — they are not claim-aware.
2. **Claim before you build.** Before starting a loop, append a line under §7.3
   CLAIMS (`<loop> — <branch> — <date> — in-flight`) and **commit+push that
   one-line claim FIRST**. The other session greps CLAIMS before picking. No
   claim ⇒ unclaimed ⇒ fair game.
3. **Reserve migrations.** §7.4 is the migration registry. **Reserve the next
   number here (commit first)** before adding `schema/migrations/NNN_*.sql`.
   This is exactly what the 092 collision violated.
4. **Area-split when two Data sessions run concurrently.** **D-ingest** =
   connectors / emitters / `integration/` / ontology / crosswalk. **D-intel** =
   intelligence-objects (`scenario_*`, `fact_signals`, `dossier_kb` read) /
   `benchmark/` / FS-* frontend. Pick a letter at session start; record in CLAIMS.
5. **Frontend is a distinct deliverable.** The other Data session is
   backend-only; the FS-* frontend (timeline, contradiction badge, readiness
   panel) is unclaimed — take it via CLAIMS.

### 7.2 Reconciled state of the collision (authoritative)
- **MERGED on main — do NOT redo:** #220 canonical-guard, #226 build-plan, #227
  contradiction/polarity, #231 prob-history (`092_scenario_probability_history`),
  #232 regulatory-emitter, #233 epistemic-timestamps (`093`), #234 scorecard,
  #235 OQ1.
- **This session's open PRs — disposition:** **#224** source-contracts = KEEP
  (complementary → merge); **#228/#230/#223** = backend DUPS → close, salvage
  only the unique **frontend** onto the merged backend; **#222** = superseded by
  #220 (but see the live recurrence below); **#225** = superseded by this §7.
- **Canonical re-demotion — DIAGNOSED (13 Jun):** #220 (merged **21:42**) DID fix
  the vector; the orphaning observed at **21:46** was the *old* `consolidate_drugs`
  running its last cycle inside Railway's deploy window — not a bypass of the new
  guard. The 34 orphans were accumulated **residue**, not ongoing corruption. A
  best-effort restore healed the real-drug canonicals (**34 → 3** real orphans;
  ivabradine/valsartan/sitagliptin-phosphate/finerenone back to `active`). The
  fail-loud detector `scripts/check_orphaned_canonicals.py` (junk/combo-filtered,
  real-drug-only) + Lane-2 invariant `tests/test_orphaned_canonical_invariant.py`
  ship here and will catch any **new** recurrence. Residual 3 (sitagliptin,
  furosemide injection, metformin hcl) = targeted restore/absorb — the
  combo-guarded absorb tool is ready, HELD per §7.3.

### 7.3 Backlog — CLAIMS (append before building; commit the claim first)
| Loop | Owner / branch | Status |
|---|---|---|
| Orphaned-canonical detector + Lane-2 invariant | D-intel `claude/data/coord-sync-protocol` | in-flight (this PR) |
| Diagnose the live re-demotion vector | D-intel | in-flight |
| Excluded-config absorb (combo-guarded tool ready) | D-intel | **BLOCKED** on canonical stability |
| FS-* frontend salvage (timeline + badge on #231/#227) | unclaimed | open |
| D1 emitters: TrialOutcome / Investigator / PublicationClaim / CompanyFinancial | D-ingest (other session has #232) | open — claim individually |
| FS-3 readiness panel, FS-4 as-of UI, H-a temporal edges | unclaimed | open |
| DataHub Phase 0 — catalog lenses L1/L1b (CatalogHomePage + live container + `/hub/catalog`) | Frontend agent `claude/datahub/phase0-lenses` | **built, NOT merged — needs `/review-gate`** |
| DataHub L2 — connector-type taxonomy + onboarding lifecycle (mig 096) | D-intel | **MERGED #245** |
| DataHub L3 — generic config-driven `CsvConnector` (+ `SourceType.CSV_FILE`) | D-intel | **MERGED #247** |
| DataHub L4 — Rss / WebScrape / Warehouse connectors | D-intel — interleaved w/ eval loops | open — NEXT |
| **DataHub D-API-1** — expose L2 service as REST (`/hub/connector-types`, `/hub/onboarding/{id}`) | D-intel | **MERGED #254** — new `/hub` router; F5-swap handoff in §6 |
| **DataHub D-API-2** — source-level FAIR aggregate (`fair_overall` on `/catalog/datasets` rows + `GET /catalog/datasets/{key}/fair`) | **Platform** (api/) — **frontend F1 dependency** | **built, PR open** — derived from dataset_catalog cols; honest null-when-absent, **0-row ⇒ RED**; independent review APPROVE; prod-probed 12 datasets |
| DataHub **frontend F1–F7** — the Catalog UX (see `docs/SPEC_DATA_HUB_FRONTEND.md`) | Frontend agent | see §7.6 |

### 7.4 Migration registry (reserve a number here before authoring)
- `090` fact_governance · `091` crosswalk_records — MERGED.
- `092` = **`scenario_probability_history`** (#231, MERGED). ⚠️ a duplicate
  `092_scenario_calibration_history` (#228) also applied to prod — two redundant
  tables; cleanup debt (close #228 backend, keep one).
- `093` = `facts_epistemic_timestamps` (#233, MERGED).
- `094` = `scenario_prob_history_stance_counts` (#237, MERGED).
- `095` = `drug_pricing_idempotent_history` (#241 NADAC revival, MERGED).
- `096` = **`connector_taxonomy_onboarding`** (DataHub L2 — `connector_types` +
  `source_onboarding` lifecycle + `sources.connector_type`) — RESERVED, branch
  `claude/data/datahub-l2-taxonomy`.
- `097` = **NEXT FREE** — reserve here before use.

### 7.5 Eval-pass loops (data-team share — how we pass the evals)
Full plan + grounded diagnosis: **`docs/eval_pass_plan.md`** (PR #238).

**There are TWO eval suites — and they AGREE on the fix (read this to avoid cross-talk):**
| Suite | Runner / file | Latest | Scoring | Weakest |
|---|---|---|---|---|
| **General live-eval** (the standing CI bar) | `benchmark/live_eval.py` → `eval-20260613` | **73.4%** (59 q) | 0–1 per dimension, averaged | **citation 59.3%, factual 56.1%**; intent `general` 49.5% |
| **Pharma specialist** (the harsher rigor bar) | `benchmark/pharma_eval.py` → `eval_pharma_v1.yaml` | **5% item-pass** | binary gates (ALL must pass) + graded | **G1 provenance 5%, G2 honesty 10%** (G3 68 / G4 90) |
| Comprehensive (target) | `eval_pharma_v2.yaml` (#238) | not yet run | gates today + specialist model (target) | — |

**Both point to the SAME root cause: provenance/citation + factual grounding in
SYNTHESIS** (general `citation 59.3% / factual 56.1%` == specialist `G1 5%`). And the
general eval's **E0x cluster is ENTITY RESOLUTION** (E07 Januvia grounding 0.2, E01
"semaglutude" typo, E09 sema+tirz) → maps to **C1** (resolution stability) + **B4**
(resolved-row correctness). Its **G0x cluster** (factual 0.0) → synthesis **A1/A2**.

So `eval_pharma_v1` (5%): gates **G1 provenance 5% / G2 closed-world-honesty 10%** /
G3 68% / G4 domain-correct 90%; reachable_reasoning **0%**. **KEY REFRAME (prod-probed): the eval fails in SYNTHESIS, not the
substrate** — facts already carry provenance at **100%** (15047/15048
`source_doc_id` → 12,395 evidence_records) and answers are 90% correct, so G1/G2
are a *surfacing* (cite + hedge) problem = **platform**, not data.

**Data-team eval loops — your highest leverage (do NOT backfill provenance, do NOT
rush payer/pricing — those are calibrated `missing_data` → honest-refusal passes via
synthesis):**
| Loop | What | Unblocks | Status |
|---|---|---|---|
| **B1** | Surface per-source **coverage + freshness** (from `pharma_source_contracts.yaml` #224 + `connector_health`) to the answer path, so the closed-world guard states limits ACCURATELY ("FAERS 2,562 wk; labels 191") | **G2** (#1 data lever) | open — D-ingest |
| **B2** | **Reachability**: wire chat retrieval for landed-but-unreachable data (`regulatory_milestones`, Orange Book patents, SEC structured) | `ingested_unreachable` items (0%) | open — D-ingest |
| **B3** | **D1 emitters** (TrialOutcome / RegulatoryMilestone / Investigator / PublicationClaim / CompanyFinancial) → more `reachable_reasoning` answerable | item coverage | open (#232 = RegMilestone done) |
| **B4** | Domain-correctness on the **resolved** row (curated dual-mechanism etc. must sit where resolution lands) — couples with D-intel C1 | **G4** outliers (CLIN-02) | in progress (C1) |

**Platform loops (dominant for eval-pass):** A1 merge #215 (closed-world guard +
count de-bias + provenance legend) · A2 per-claim citations (data is 100% there) ·
A3 judge majority-vote · A4 response-contract serialization (P1).
**D-intel (mine):** C1 resolution stability (#236 detector + heal + excluded-absorb
+ `_exact_lookup` excluded-filter) → G4 · C2 eval-runner extension (hard-fail caps +
prose-scorable specialist dims) → measurement.

### 7.6 DataHub Frontend — CLAIMS (Frontend (Claude) agent lane)
**Build brief = `docs/SPEC_DATA_HUB_FRONTEND.md`** (lens model + reuse inventory +
the F1–F7 loops + acceptance criteria). **Vision = `docs/SPEC_DATA_HUB.md` +
`docs/data-hub-vision.html`** (open the HTML in a browser). Claim a loop here before
building; one PR per loop; **independent `/review-gate` before merge, no self-merge**.

| Loop | What | Depends on | Owner / branch | Status |
|---|---|---|---|---|
| **F1** | Catalog Home + Source dossier + DataHub nav entry | D-API-2 (degrade till then) | Frontend `claude/datahub/f1-finish` | **MERGED #250** (independent review APPROVE; nav `onDataHub`→`/hub/catalog`, honest FAIR degradation, 25 tests green) |
| **F5** | Connect wizard (5 source kinds → register + lifecycle) | **D-API-1** | Frontend `claude/datahub/f5-connect-wizard` | **shipped vs stub; D-API-1 REST now LIVE (MERGED #254). SWAP follow-up: NOT a one-liner — `registerSource()` must `POST /sources` THEN `POST /hub/onboarding/{id}` with `{owner,contact,connector_type,go_live_date,escalation}` (the FK-existence probe 404s on an unregistered source). See §6 D-API-1 handoff. Response DTO/enums already match 1:1.** |
| **F2** | Documents & vectors lens (+ enhance actions) | D-API-3 | unclaimed | open |
| **F3** | Ontology & data-model lens (read-only map + graph + MeSH) | D-API-4 | unclaimed | open |
| **F4** | Prompts & packs lens (observational impact — NO A/B platform) | D-API-5 | unclaimed | open |
| **F7** | Governance board (provenance/lineage/lifecycle/trust) | reuse ledgers | unclaimed | open |
| **F6** | AI co-pilot + autonomous-job timeline (Flow B) | D-API-6 (backend L9–L10) | unclaimed | BLOCKED on backend |

**Suggested order:** F1 (finish+merge) → F5 → F2 → F3 → F4 → F7 → F6. The data lane
owed **D-API-1** (REST for the L2 connector-taxonomy/onboarding service) +
**D-API-2** (source-level FAIR) first — they unblock F5 + F1 (tracked in §7.3).
**D-API-1 is now MERGED (#254)** → F5 can swap off its stub (see the §6 handoff).
**D-API-2 is still open** → F1 degrades the FAIR ring until it lands.
