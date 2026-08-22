# Coordination — Market Zero (canonical board)

> **This file is the single living coordination surface.** It supersedes
> `docs/archive/AGENT_BACKLOG.md` (stale, 2026-05-11, framed backend↔frontend
> only). If another doc disagrees with this one about lanes or process, this one
> wins. Last updated: 2026-06-13.

## 0. TIV2 controller transition (2026-08-22)

For Trusted Intelligence v2 work, the protected task graph at
`coordination/contracts/work_graph.json` supersedes the manual `CLAIMS` tables below. TIV2 feature
builders must not edit this file or the graph in the PR that benefits from the change. Once activated,
they consume only a dependency-ready item emitted by the controller and report evidence through its
linked GitHub issue and PR. The Codex reviewer then consumes the controller's exact-SHA review queue.

The historical sections below remain the coordination record for legacy work until separately
retired. The TIV2 controller is not active merely because its files exist. The protected graph now
encodes the complete rollout as `V2-GOV-001` through `V2-GOV-007`: reviewed kernel, bound read-only
GitHub adapter, disposable lifecycle proof, nudge-mode hooks, serialized controller, observed merge
gates, then two full lifecycles plus owner activation. Core and Data both depend on the observed
`V2-GOV-007`; until then, no fixture or hand-authored "live" JSON may assign real work. Only
`V2-GOV-001` is executable now; every later node is a non-eligible contract placeholder with a
predeclared protected test path.

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

**Eval tiers (MZ-XR-20260613-005) — do not conflate them.** Two evals, two roles
(declared in code as `EVAL_TIER`, pinned by `tests/test_eval_tiers.py`):
- **Smoke / regression** — `benchmark/eval_runner.py` (`EVAL_TIER="smoke"`) +
  `benchmark/scorers.py`. Heuristic: intent match, grounding, numeric coincidence,
  evidence count, citation well-formedness. Catches route breakage. A green run
  here is **NOT** evidence of content quality.
- **SME content-quality gate** — `benchmark/pharma_eval.py`
  (`EVAL_TIER="content_gate"`) + `eval_pharma_v2.yaml`, LLM-judge. Judges
  provenance (G1), closed-world honesty (G2), count-fallacy (G3), domain
  correctness (G4). This is the bar for "is the answer SME-grade", tracked by gate
  (not just mean score). Promotion of this to a HARD CI gate is owner-gated
  (protected `.github/workflows/`).

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

**Data (data session), 2026-06-13 — L4a SHIPPED (MERGED #257).** Next
generic connector after L3's `CsvConnector` (#247) — config-driven RSS/Atom feed
ingestion: point an `RssConfig` at a feed URL, declare the `RecordType` + an
element→field map, and it emits the universal `RawRecord` with full `Provenance`,
zero pipeline/schema change (the `BaseConnector` contract is the seam). Additive
`SourceType.RSS = "rss"`; **no migration**. stdlib `ElementTree` (no new dep;
`feedparser` is absent) handling both RSS 2.0 and Atom. **NOT a dup of bespoke
`connectors/news.py`** (hardcoded FDA/Google feeds → EVENT) — this is the generic,
any-feed→any-type version, same relationship as `CsvConnector` vs bespoke CSV;
not added to `CONNECTOR_REGISTRY` (instantiated by the onboarding flow).
- **Why one connector per loop (L4 split into L4a RSS / L4b WebScrape / L4c
  Warehouse):** the DoD needs RED→GREEN **+ a real prod probe** per connector. RSS
  is dependency-free + probeable against a live public pharma feed → shippable now.
  WebScrape needs an HTML/CSS-selector dep (`bs4` is present) + robots handling;
  Warehouse needs Snowflake/Databricks/BigQuery drivers **+ live credentials** and
  **cannot be prod-probed here** — bundling all three would force vacuous green on
  two of them. L3 likewise shipped exactly one connector. L4b/L4c are claimed
  separately when each can be genuinely proven.

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
| DataHub L4a — generic `RssConnector` (+ `SourceType.RSS`) | D-intel | **MERGED #257** — RSS 2.0/Atom on stdlib ElementTree; prod-probed FDA RSS (20) + arXiv Atom (5); independent review APPROVE |
| DataHub L4b — generic `RestConnector` (+ `SourceType.REST`) | D-intel `claude/data/a1-rest-connector` | **PR #269** — auth/pagination/dotted-extraction; 29 tests; prod-probed openFDA+CT.gov; review APPROVE-WITH-NITS (applied). **Prioritized ahead of WebScrape per the 14-Jun strategy audit (REST = most common kind + strong borrow).** |
| DataHub L4c — generic `WebScrapeConnector` | D-intel — `bs4` present; needs robots handling | **DEFERRED** per audit (wire-before-build: detection spine before more coverage) |
| DataHub L4d — generic `WarehouseConnector` | D-intel — needs warehouse drivers + live creds | **DEFERRED** (probe constraint + wire-before-build) |
| **DataHub D-API-1** — expose L2 service as REST (`/hub/connector-types`, `/hub/onboarding/{id}`) | D-intel | **MERGED #254** — new `/hub` router; F5-swap handoff in §6 |
| **DataHub D-API-2** — source-level FAIR aggregate (`fair_overall` on `/catalog/datasets` rows + `GET /catalog/datasets/{key}/fair`) | **Platform** (api/) — **frontend F1 dependency** | **MERGED #256** — derived from dataset_catalog cols; honest null-when-absent, **0-row ⇒ RED**; independent review APPROVE; prod-probed 12 datasets. ▶ FE wiring follow-up: `CatalogPage.tsx` still proxies `fair_overall←quality_score_avg` + `SourceDetail.fair=null` (stale "no endpoint" comment) — wire to per-row `fair_overall` + `GET /catalog/datasets/{key}/fair` |
| DataHub **frontend F1–F7** — the Catalog UX (see `docs/SPEC_DATA_HUB_FRONTEND.md`) | Frontend agent | see §7.6 |
| **Loop 0 (debt)** — `pipeline.py:351` ON_NEW_ENTITY `NameError` (auto-create path) | D-intel `claude/data/loop0-pipeline-nameerror` | **PR #270** — RED→GREEN regression |
| **Data+Intel STRATEGY AUDIT** (20-agent) — sensing dead at 2 joints; WIRE-BEFORE-BUILD; maturity scorecard + roadmap | D-intel `docs/data-intel-strategy-audit` | **PR #272** — `docs/DATA_INTEL_STRATEGY_AUDIT.md`. ⚠️ supersedes connector-coverage-first plan |
| **audit-C1** — FK-orphan floor: pubmed RED→GREEN (20.07→15.83%) + high-precision trial relink + self-healing in auto_curate | D-intel `claude/data/c1-orphan-floor` | **PR #271** — pubmed gate GREEN; trial gate held RED on purpose (metric mis-spec, see owner item) |
| **OWNER bar-decision** — re-scope `clinical_trials.drug_id` orphan ceiling | **protected-surface owner** | OPEN — among drug-intervention trials orphan = 0.04% (2/5178); 10.57% is 678 legitimately drug-less trials. Proposal: scope denominator to drug-intervention trials / exclude observational `study_type`. NOT silent-edited (Principle #1). PR #271 + audit doc. |
| **audit-C2 (NEXT)** — durable #242 brand_name de-smear (root-cause ETL re-smear + idempotent POST_RUN + alias backfill + Lane-2 re-smear invariant) | D-intel | open — claimed |
| **audit S-track** — wire the dead detection spine (promote filter+cadence, trust/tier, ImpactRouter, framing cron, Lane-2 sensing gates) | shared scheduler/Platform seam — claim §6 first | open — highest sensing leverage |

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
- `097` = `open_targets` recovery — in-flight, branch `claude/data/open-targets-disease-recovery` (#303).
- `098` = `etl_runs` skip-visibility — in-flight, branch `claude/data/dlq-etl-runs-skip-visibility` (#307).
- `099` = **`source_onboarding_contract`** (Connector Press Phase 1a — persist the
  wizard/agent connector contract: config/field_mappings/record_type/trust_tier/
  must_capture/license/cadence) — RESERVED, branch `claude/data/connector-press-phase1`.
- `100` = **NEXT FREE** — reserve here before use.

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

#### 7.5a PLATFORM→DATA HANDOFF (15 Jun — measured, post synthesis-grounding loops)

Platform shipped the synthesis-side grounding (PRs #265/#268/#273/#276, live on main).
**Measured on `eval_pharma_v2` (3-sample MV, prod data):** G1 4.9→**12.2%**, G2 17.1→**36.6%**,
G3 65.9→**68.3%**, G4 90.2%, graded 3.68→**5.02**, item-pass 1→2/41. The synthesis lane is
now largely harvested — **the remaining ceiling is DATA.** Per-item decomposition shows
**21/41 items are `missing_data`/`ingested_unreachable`** — winnable only as honest refusals
(synthesis now emits those), and `item_pass` also needs all-gates + graded≥8, which an
empty-ledger lens cannot supply. **These are the data-team levers, in priority order:**

- **D-Q1 · Fact-CLASS quality (NEW — highest leverage for the lens matrix + grounding).**
  `dossier_kb._coerce_fact_class` collapses clinical/regulatory/trial/outcome → `signal`
  (lossy), and news-sourced clinical items are classed `corporate`. Net: synthesis **cannot
  distinguish a real trial readout from a news mention** by fact_class — so the new
  coverage-quality lens table (#276) treats ONLY curated `reference` facts as "covered" and
  everything else as "partial" (correct *today* because the non-mechanism facts ARE news, but
  it caps efficacy/safety/regulatory at "partial" forever). **ASK:** preserve a richer,
  honest fact_class through ingestion (a registry trial readout ≠ a news headline); class
  news-derived facts distinctly (`corporate`/`news`) from registry/curated (`clinical`/
  `regulatory`/`reference`). This is what lets efficacy/safety show "covered" when real data
  exists. Couples with B4.
- **D-Q2 · Pricing events→facts bridge (cheap, verify-first — NOT a new connector).**
  `services/event_emitters/pricing_observation.py` emits CMS ASP/NADAC as EVENTS, but **no
  fact_emitter writes `wac_usd`/`net_price`**, so the planner sees a pricing gap. Probe prod
  for NADAC/ASP event rows; if present, a thin events→facts emitter lifts the pricing content
  ceiling (MAX-01/HON-01/HE-01). ⚠️ Also: the eval's `connector_state_actual` says
  `cms_nadac=0` (calibrated 2026-06-13) but prod now has ~290 NADAC rows → **stale-bar**;
  owns the freshness re-probe (see B1).
- **D-Q3 · Reachability (= B2).** `regulatory_milestones` UNREACHABLE from chat, Orange-Book
  patents PARTIAL, SEC filings RAG-only → REG-02/CI-01/BD-01 fail. Wire chat retrieval.
- **D-Q4 · Source-blocked emitters (B3 cont.):** payer-policy (`formulary_status`/`prior_auth`/
  `step_edit`/`hta_decision`), commercial (`launch_event`/`uptake_signal`/`product_sales`),
  structured epidemiology/market-size, genetics (`open_targets`=0)/bioactivity (`chembl` not
  indexed). Each needs a connector ingested FIRST — do NOT expect synthesis to fill; platform
  already emits honest source-named refusals for these (G2).
- **D-Q5 · Mechanism granularity (G4):** `mechanism_of_action` is coarse (dual GIP/GLP-1 not
  distinct) — ontology enrichment. PR **#217** open covers this.

Full diagnosis + sequencing: memory `project_eval_stuck_path` + the 8-agent workflow output.
Re-run after data loops: `python -m benchmark._run_v2 <name> 3` (loads `.env`); decomp:
`python -m benchmark._decomp <name>`.

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
**D-API-2 is now MERGED (#256)** → F1 can wire the real FAIR ring (`fair_overall`
per `/catalog/datasets` row + `GET /catalog/datasets/{key}/fair`); the catalog
page currently still proxies `quality_score_avg` + nulls the dossier breakdown.

---

## 8. Cross-lane coordination protocol (binds Platform + Data; owner-ratified 15 Jun)

The crossed-message incident (Platform "froze" Design B in chat while the owner picked
Design A in a parallel prompt → two authorities, a contested fork) showed the failure
mode. The fix is structural, not goodwill:

**P1 — COORDINATION.md is the ONLY source of truth for cross-lane decisions.** A contract/
decision is real *only* when written here. Chat/terminal messages are PROPOSALS until
recorded. If it isn't in this file, do not build on it.

**P2 — Strict lanes; never edit across the seam.**
- **Platform:** synthesis/chat (`services/llm.py`, `unified_handler.py`, `ctx_pipeline.py`,
  `chat_handlers/`, `domain_intelligence/{planner,synthesis}` coverage/lens logic), API
  (`api/`), search, eval-harness (`benchmark/`), dossier read-path, all `frontend/`.
- **Data:** connectors/emitters/ingestion, migrations, **the fact vocabulary**
  (`fact_class`, predicates, `_coerce_fact_class`, `VALID_FACT_CLASSES`, DB CHECKs),
  schema, resolution.
- Need something in the other lane? Write an **ASK** (P3) — don't reach in.

**P3 — Cross-lane ASKs (§8.1 below):** one row each — requesting lane · need · why ·
status `REQUESTED→ACK'D→DONE`. The owning lane ACKs + builds (or declines with reason).

**P4 — Shared CONTRACTS (interfaces both touch) (§8.2 below):** one row — contract · OWNER
(authors the source of truth) · consumers · status `PROPOSED→AGREED→LANDED`. **AGREED only
when BOTH lanes' sign-off is recorded here.** Changes route through the OWNER.

**P5 — One decision authority, recorded once.** Owner (human) decisions are captured here by
the lane that asked; the other lane READS them here. **No parallel owner-prompts that fork
authority.** Conflicting directives ⇒ **HOLD, reconcile in this file, do not build** (Data
did this correctly in the B/A incident).

**P6 — Sequencing is explicit.** Write deps as "X gated on Y"; the gating lane posts "Y
cleared" here when done. The gated lane does read-only prep meanwhile.

**P7 — Each lane verifies its OWN surface.** Data verifies the substrate (e.g. facts get the
right class, pasted prod probe); Platform verifies the consumer (e.g. lens/eval flips). No
cross-seam verification claims.

### 8.1 Cross-lane ASKs
| # | From | Need | Why | Status |
|---|---|---|---|---|
| A1 | Platform/FE → **Data** | Persist the F5 wizard's full source **contract** — extend `source_onboarding` (or a related table) to store `config` / `mappings` / `trust_tier` / `must_capture` / `license`. `StartOnboardingBody` (`hub.py:57`) currently keeps only owner/contact/connector_type/go_live_date/escalation and **silently ignores** the rest (default pydantic). | Gates the real F5 write-path. Until storage exists the wizard stays an honest **preview** (PR #285) — a naive POST would 201 while silently dropping the contract the wizard exists to enforce (conservation violation, fails *silently*). The `source_onboarding` schema is Data's. | **OPEN** (15 Jun) |
| A2 | Platform/FE → **Data** | On `GET /catalog/datasets/{key}/profile`: expose **per-entity-type record counts** (records per entity_type a source feeds), null-when-unknown. (The `license` half Platform can add itself from `_dataset_fair`'s `license_name` — a Platform follow-up, not a Data ask.) | The F1 dossier renders `coverage: []` today (kept honestly empty). Per-type counts make the dossier's coverage section real instead of a permanently-empty block. | **OPEN** (15 Jun) |
| A3 | Platform/FE → **Data** | Stop the 6-strategy resolver merging a **branded product with a development-code product on shared INN alone** (`integration/entity_resolver.py` + `domain/pharma/mention_normalizer.py`): require corroboration beyond the shared INN (e.g. same sponsor or same NCT) before a brand↔dev-code merge, and **de-pollute the already-merged stored labels** (e.g. drug name literally `"Ozempic (TQF3510 (Semaglutide Injection))"` — a nested alias concatenation). Conservation: soft-delete/record, don't silent-drop. | Intelligence review **F5** (24 Jun): the live answer labelled `Ozempic (TQF3510 (Semaglutide Injection))`, conflating Ozempic (Novo) with TQF3510 (a Qilu generic semaglutide dev code) — a factual error AND an unreadable label that every downstream answer inherits. The conflated label is the **stored entity name**, not a chat-render artifact, so there is no honest platform-side fix — a cosmetic label-truncation would *mask* a real data conflation (conservation: no theatre). Resolver + canonical name are Data's surface. | **OPEN** (24 Jun) |
| A4 | Synthesis/Platform → **Data/Intel** | Carry `clinical_trials.start_date` into the **decomposition matrix trial facts** (the `DecompositionPlanner` cell facts surfaced via `unified_handler._matrix_to_evidence`, which today expose only `claim`/`predicate`/`id`/`fact_class`), and ideally into the **corpus entity trial lists**, so each trial's date travels with the trial fact into the synthesis context. Conservation: additive, don't drop existing fact fields. | Intelligence review **F10 / TICKET-8** (recency): decade-old trials (e.g. NovoMix 30, NN5401) were narrated as "recent." Root cause is **upstream of synthesis** — the matrix trial facts + retrieved corpus sections that surface OLD trials carry no `start_date`, so synthesis can neither ground nor guard "recent": the corpus `trials.yaml` holds only the 200 most-recent (all 2026+), and a whole-narrative recency guard is defeated by ever-present corpus dates. Once dates travel with the facts, Platform adds a synthesis-side recency label/guard as a fast-follow. **Prod probe (30 Jun):** `clinical_trials.start_date` = **94.5%** coverage (5,554/5,880); 721 trials ≤24mo, **4,127 >5yr old** — the old trials exist and reach the model dateless. Like F5/F7 (synthesis symptom, data/intel root). | **OPEN** (30 Jun) |

**BLOCKED surfaces — do NOT build over empty data (conservation, no theatre):** F5 write-path (until **A1**); the **F7 governance board** (prod `source_onboarding` = 0 rows — a permanently-empty board); and lenses **F2/F3/F4/F6** (their **D-API-3/4/5/6** backends don't exist — already tracked on the §7.6 F-board / §4). Surfaced by the 15 Jun DataHub frontend audit; the two correctness/honesty fixes that had NO data dependency shipped as **PR #284** (dossier /fair 404 + grid dup-key) and **PR #285** (SPA deep-link + F5 de-theatre + search copy/connectors link).

### 8.2 Shared CONTRACTS
| Contract | Owner | Consumers | Status | Definition |
|---|---|---|---|---|
| **fact_class taxonomy** | Data | Platform coverage/lens (`planner._is_substantive`) | **AGREED — Design A (15 Jun)** | **Keep the 4-class vocab** `{reference, corporate, signal, inferred}` — NO migration, NO new classes. Classify by **SOURCE not predicate**: registry/regulatory facts (CT.gov, FDA/EMA) → `reference` (substantive); pharma-news → `corporate`; FAERS → `signal`; derived → `inferred`. Substantive set stays **`{reference}`**. Also: fix `_coerce_fact_class` default `signal`→`corporate` (honest contextual default). `internal`→contextual is a scoped follow-up. Rejected Design B (add clinical/regulatory classes + migration 097) — same goal, more machinery, more sync-point risk, zero current consumer reads the split (Platform's own minimalism test). |

**fact_class contract — sequencing (P6):**
- **Data (A, off current `main`):** emitter source-classing + source-keyed backfill of the
  existing ~15.7k + coercion-default fix + spec + tests + prod re-probe. **#276-INDEPENDENT —
  ships first.** Verifies its OWN surface (facts now carry honest class).
- **Platform:** `_is_substantive` needs **NO change** (substantive already `{reference}`);
  optional my-lane hardening = convert `_WEAK` denylist → explicit `{reference}` allowlist.
  Then rebase **#276** (coverage-weighting, currently held — draft) onto A-inclusive `main`,
  add the **lens-table source fix** (partial lenses show their real named source, not
  "platform data"), and re-verify G1 (A's classing should flip real-registry lenses to
  "covered | <source>", recovering the G1 the held #276 lost). Platform verifies the lens +
  eval flip.
