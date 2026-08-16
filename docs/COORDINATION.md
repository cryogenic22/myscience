# Coordination — Market Zero (canonical board)

> **This file is the single living coordination surface** (SPEC_HANDOFF §H0.3.1 —
> canonical lane/active-task board). It supersedes `docs/archive/AGENT_BACKLOG.md`
> (stale, 2026-05-11, framed backend↔frontend only). If another doc disagrees with
> this one about lanes or process, this one wins. The repository-maturity & transfer
> program (SPEC_HANDOFF_001) is tracked in **§12**. Last updated: 2026-08-14.

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

> **⚠️ SUPERSEDED on team-count by §10 (2026-07-11):** the 3-lane model below was
> consolidated to **2 teams** — **Data / Substrate** and **Product-Platform** (which
> absorbs the old *Frontend* **and** *Platform / Harness* lanes). The per-file ownership
> rows below still map correctly onto the two teams (every *Frontend* row → Product-Platform).
> **§10 is the authoritative split.**

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
  (`api/`), search, eval-harness (`benchmark/`), dossier read-path, and the **CI-UI** surfaces (`apps/ci/`) **only** — **not** all `frontend/` (GOV-001 ruling 2026-07-10: the **Frontend** lane owns `frontend/`; §2 is canonical, see §9.1).
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
| A4 | Platform → **Data** | Add an authenticated-owner/tenant column (e.g. `owner_id` / `tenant_id`) to `chat_sessions` + `deep_research_jobs` + backfill; today they carry only a caller-supplied `scope_key` (mig 011) — **no ownership boundary**, so any caller can read/delete another scope's rows by guessing the key. Data reserves the migration (§7.4). | SEC-002 tenancy (red-team 2026-07-10, verified). **Stop-ship BEFORE any multi-tenant / customer-sensitive onboarding** — deployment is external-pilot / non-sensitive today (§9.1), so this is near-term, not 0-24h. | **OPEN** (10 Jul) |
| A5 | Frontend → **Platform** | After route-auth lands (§9.4), regenerate `schema/openapi.json` (currently 381 paths, `/hub /forge /dossier /eval` absent, ~2 mo stale) and add a **deterministic OpenAPI-drift CI gate**; the typed `frontend/src/api.ts` client update is Frontend-lane (mine). | API-001 (verified): the typed FE client cannot be trusted against a stale contract; a drift gate makes silent divergence fail closed. | **OPEN** (10 Jul) |
| A6 | Synthesis/Platform → **Data/Intel** | Carry `clinical_trials.start_date` into the **decomposition matrix trial facts** (the `DecompositionPlanner` cell facts surfaced via `unified_handler._matrix_to_evidence`, which today expose only `claim`/`predicate`/`id`/`fact_class`), and ideally into the **corpus entity trial lists**, so each trial's date travels with the trial fact into the synthesis context. Conservation: additive, don't drop existing fact fields. | Intelligence review **F10 / TICKET-8** (recency): decade-old trials (e.g. NovoMix 30, NN5401) were narrated as "recent." Root cause is **upstream of synthesis** — the matrix trial facts + retrieved corpus sections that surface OLD trials carry no `start_date`, so synthesis can neither ground nor guard "recent": the corpus `trials.yaml` holds only the 200 most-recent (all 2026+), and a whole-narrative recency guard is defeated by ever-present corpus dates. Once dates travel with the facts, Platform adds a synthesis-side recency label/guard as a fast-follow. **Prod probe (30 Jun):** `clinical_trials.start_date` = **94.5%** coverage (5,554/5,880); 721 trials ≤24mo, **4,127 >5yr old** — the old trials exist and reach the model dateless. Like F5/F7 (synthesis symptom, data/intel root). *(was **A4** on `origin/main`; renumbered to A6 here to resolve a divergent-branch ASK-ID collision with the SEC-002 tenant A4).* | **OPEN** (30 Jun) |

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

---

## 9. Architecture red-team review — 2026-07-10 (verified triage + owner rulings)

**Source:** `docs/market_zero_architecture_review_2026_07_10.html` (red-team rev 2; baseline
`38889b5`; **static — no live DB / deploy / edge probe**, by its own disclosure). It reorders
the stack to **security · tenancy · API-contract ahead of data-quality**. Per §8 P1 it was
advisory until recorded here — now recorded.

**Verification (DoD — not taken on the review's say-so):** two independent read-only sub-agents
re-checked every code-checkable claim against the current working tree (2026-07-10). **All
findings CONFIRMED** — cosmetic line-drift only (e.g. PRIV-001's real line is
`services/llm.py:1353`; the tree has ~294 not 297 `tests/test_*.py`) — **plus one NEW live
defect** the static pass could not see (§9.3). Nothing STALE / REFUTED. The one axis still
genuinely unverified is **deployed reachability** of `/debug/*` + `/zs` (edge/routing, not a
code fact) — §9.4 item 1.

### 9.1 Owner rulings (P5 — recorded once; every lane READS here)
- **Sequencing = CONTAIN + PULL-FORWARD** (not a full freeze). Edge-contain the acute unauth
  surface now (§9.4); move security / tenancy / contract to **P0 at the top of the product
  board**; **in-flight synthesis / FE / data loops continue**; only NEW feature-roadmap
  *expansion* pauses until the P0 gates have named owners + containment lands.
- **Deployment context = EXTERNAL PILOT** (few external users, non-sensitive data). ⇒ auth +
  per-user/IP rate/cost limits are **now**; SEC-002 tenant isolation + PRIV-001 mandatory PII
  egress are **stop-ship BEFORE any customer-sensitive or multi-tenant onboarding** — keep that
  blocked (§8.1 BLOCKED surfaces; DataHub `preview:true`).
- **GOV-001 lane ruling = the Frontend lane owns `frontend/`.** §8 P2 reconciled to §2:
  Platform owns the **CI-UI** surfaces (`apps/ci/`) + API + synthesis; Frontend owns
  `frontend/`. §2 stands as canonical. `PRODUCT_BACKLOG.md` is SoT for product/feature/bug
  work; **this file is SoT for lanes / cross-lane / process** (the backlog's stale
  `AGENT_BACKLOG.md` pointer is corrected).

### 9.2 Verified disposition
| Finding (all CONFIRMED in code unless noted) | Owner lane | Disposition / next |
|---|---|---|
| **SEC-001** unauth `/debug/*` (`api/app.py:427/445/479`), catalog/steward/enrichment mutations no `require_role`, `/zs` default creds (`zs.py:64`) | Platform + DevOps | **P0 contain** (§9.4): edge-deny, delete debug mutations + default-cred fallback, add `require_role` |
| **SEC-002** chat/session/research-job routes no ownership; only `scope_key`, **no tenant column** (mig 011) | Platform + Data | **P0**: auth + caller-ownership now; tenant column = **ASK A4** (before multi-tenant onboarding) |
| **API-001** `openapi.json` 381 paths, `/hub /forge /dossier /eval` absent (~2 mo stale) | Platform + **FE (mine)** | **P1** after auth: regen + drift gate (**ASK A5**); typed client = Frontend lane |
| **PRIV-001a** direct `llm.py` synthesis egress now redacted (#326; independent review **APPROVE-WITH-NITS**) | Platform/synthesis | Lands the direct slice; does **NOT** close H1.1 (see §12 / SPEC_HANDOFF §H1.1 disposition) |
| **PRIV-001b (P0)** platform-wide egress still raw: `extraction_llm.py` (OpenAI+Anthropic), `entity_resolver.py` (chat+embed), `embedder.py`, `search.py`, ops scripts | Platform/synthesis | **CHANGES REQUIRED (2026-08-13)** — one provider-agnostic guard + AST static no-bypass test + parity/capture tests; the H1.1 closure gate; onboarding **BLOCKED** until it lands |
| **MON-001** monitor crash → empty JSON → recovery branch closes the incident | DevOps + **mine** | Explicit healthy/degraded/monitor-failed states; **+ fix the live break §9.3 before #319/#307 merge** |
| **REL-001** fail-open migrations (`app.py:865`), dead `_cfg` job (`app.py:793`), process-local schedulers (no lease) | Platform + DevOps | Dead-`_cfg` = trivial now; `/readyz` + release migrator + worker leases = 2–6 wk |
| **DATA-001** unified handler `@lru_cache` pins handler-or-`None` for process life (`deps.py:295/317`) | **mine** (synthesis) | Versioned corpus publish outside requests; never cache failure; expose version/age |
| **CI-001** required CI = 28 curated suites + collect-only + 1 vitest; no full run/build | Platform + DevOps | **Sharpened**: curated DB-free is the *deliberate* Lane-1 design; the gap is *no sharded full-suite + full-FE+build gate exists* — add one |
| **LEDGER** `connector_health.py` still ignores `LEDGER_FRESHNESS_SLA_DAYS` | **mine** | **Land #319** (built, unmerged); the working-tree change here is the DLQ monitor, not ledger |
| **GOV-001** lane / planning-authority contradiction | owner | **RULED (§9.1)**; §8 P2 fixed; backlog pointer fixed |
| **IR-001** no RTO/RPO / restore drill / incident command | DevOps/owner | Owner-approved RTO/RPO + isolated restore drill (2–6 wk) — not static-checkable but real |
| **DATAHUB-001** persistence needs secrets/egress/versioning model | Data + Platform | Already §8.1 **A1** + BLOCKED surfaces; keep `preview:true` |
| **DATA-RESOLVE-001** resolver brand↔dev-code pollution | Data | Already OPEN §8.1 **A3** — no new row |
| **QUAL-001** source-quality false precision (0.5 defaults → one score) | Data + **FE (mine)** | Scoring method = Data; honest `measured / estimated / unknown` display = Frontend |
| **PIPE-001** embed before change-detection (`pipeline.py:364`) | Data | **Sharpened**: only embed-before-detection is live waste; `embed_batch` order/min-text bugs are **dead-path** (no app caller) — low-pri |

### 9.3 NEW live defect (working tree — beyond the static review)
**MON-LIVE.** The uncommitted `scripts/connector_health.py` change (DLQ monitor, +110/−2 vs
HEAD) reshaped `--json` from a bare list to `{"sources":[…],"dlq":{…}}`, but
`scripts/health_alert.py:39-40` still iterates the payload as a list → `AttributeError` on
**every** run → `operational-health.yml`'s `always()` recovery branch (`:82`) reads the empty
`should_alert` as "recovered" and **closes the open incident even when the check is healthy.**
This turns MON-001 from a failure-mode into an every-run break. **Owner: mine (#319/#307
lineage). Fix-before-merge:** make `health_alert.py` read `payload["sources"]` + add a Lane-2
contract regression test pinning the exact `--json` shape (RED→GREEN, pasted). Do **not**
hot-patch the shared dirty checkout without that test.

### 9.4 Contain-now (0–24 h — owner + DevOps + Platform)
1. **Probe deployed reachability** of `/debug/*`, `/zs*`, catalog/steward/enrichment
   mutations, chat/research at the edge/router — *without invoking a mutation*. This is the
   severity multiplier the static review could not check; if the edge already denies them, the
   SEC-001 acuteness drops.
2. Remove / env-guard+auth `/debug/migrate|seed-users|routes`; delete the `/zs` default-cred
   fallback (fail closed, no known-default).
3. Add `require_role` to catalog/steward/enrichment mutations + chat/session/research routes;
   bind sessions/jobs to the authenticated caller.
4. Keep customer-sensitive / multi-tenant onboarding **BLOCKED** until SEC-002 tenant column
   (A4) + PRIV-001 egress land (deployment = external pilot, §9.1).
5. **Do not scale the web tier** — schedulers + migrations are process-local (REL-001).

### 9.5 What is MINE (Frontend/synthesis lane) vs handed off
- **Mine, actionable now:** land **#319** (LEDGER); fix **MON-LIVE** (§9.3) before #319/#307
  merges; **DATA-001** corpus lifecycle; **QUAL-001** honest measured/estimated/unknown display;
  **API-001** typed-client half (A5).
- **Handed off (recorded, not grabbed — I do not edit across the seam):** SEC-001/002 route
  auth + tenant column → Platform + Data (A4); REL-001 runtime/worker → Platform + DevOps;
  IR-001 + edge containment → DevOps/owner; PIPE-001 + DATAHUB-001 persistence + A3 → Data.

---

## 10. Team consolidation — 2 teams (2026-07-11, owner-decided)

The multi-session sprawl (§7; GOV-001 in §9) is resolved by consolidating to **two teams
along the produce-facts / consume-facts-into-a-product seam** — leaving exactly **one**
Data⇄Product coordination boundary instead of an N-way mesh.

| Team | Owns | vs old §2 model |
|---|---|---|
| **Data / Substrate** | *Produce trustworthy facts:* `connectors/`, `integration/` (ETL), `services/fact_emitters/`, resolver, ontology, `schema/migrations/`, `scheduler/config.py` (`FRESHNESS_SLA_DAYS`), freshness / FAIR / dataset-defs, DLQ, sensing, `services/dossier_kb.py` fact-routing | old *Data / Sensing / Intelligence* lane, **unchanged** |
| **Product / Platform** *(this session)* | *Turn facts into a trustworthy, secure product + its UI:* **Platform** (`api/`, auth, middleware, `config.py`) · **Core dev** (`services/llm.py`, `ctx_pipeline`, `unified_handler`, `query_engine`, `search`) · **Agent dev** (`services/agent/`, `ctxpack/`, tools) · **Frontend** (`frontend/`) · **CI-gate authoring** (`.github/workflows/`, `protected-surface.txt`) | old *Platform / Harness* **+** *Frontend* lanes, **merged** |
| **Owner** *(not a team)* | Server-side floor only: branch protection, `DATABASE_URL` secret, CODEOWNERS enforcement | — |

### 10.1 Consequence for the §9 red-team disposition
Because Product-Platform now owns Platform + Core + Agent + Frontend, items §9.5 listed as
*handed off to Platform / DevOps* are now **this team's** (no longer cross-seam):

- **MINE now (were handed off):** SEC-001 route auth + `/debug/*` containment · PRIV-001 PII
  egress via `LLMGateway` · REL-001 runtime (fail-open migrations, dead `_cfg` event job,
  scheduler leases) · API-001 `openapi.json` regen + drift gate + typed client · MON-001 /
  CI-001 gate-authoring.
- **DATA's now (I stand down — built in prior data-hub sessions, they hand back):** **#319**
  (ledger freshness — a concurrent session is already landing it; I do **not** double-run),
  **#320** (FAIR honest), **#322** (dataset-defs), **DATA-001** corpus lifecycle, PIPE-001,
  DATA-RESOLVE-001, SEC-002 **tenant / owner column** (schema = Data; enforcement = me).
- **The one remaining seam (A4):** SEC-002 — Data adds `owner_id` / `tenant_id`; Product-Platform
  enforces it in the routes. Stays a coordinated ASK, not a merge.

### 10.2 MON-LIVE reconciliation (grounded 2026-07-11)
**#319 already carries the MON-LIVE fix** — its `health_alert.py` `_unwrap()` accepts both the
old bare list and the `{"sources","dlq","ledger"}` envelope, backed by a contract test
(`tests/test_health_alert.py`). So MON-LIVE is **not** a separate loop; it lands with #319 (now
Data-owned). The stray uncommitted DLQ reshape in the shared checkout must be neutralized — not
committed without the `health_alert.py` fix — which is Data's call as #319's owner. (This
corrects §9.3's "mine" framing: ownership moved to Data under §10.)

## 11. Data-platform hardening program — 2026-08-07 (owner-directed, cross-team)

A second independent red-team (`design-review-output/data_pipeline_deep_design_review_2026_08_07.md`),
reconciled with the ground-up analysis (`docs/data-pipeline-groundup-analysis-20260805.html`),
found that the connector/data-transformation stack is a solid *bounded-pharma ingestion app* but
**not yet** a lossless, replayable, source-configured, domain-pluggable platform. Four prerequisites:
deterministic identity (data-quality) + immutable raw capture + truthful run semantics + versioned
source-instance config (platform-integrity). Full program: **`specs/SPEC_003_data_platform_hardening.md`**.

**Owner ruling (2026-08-07):**
1. **Run as one program end-to-end** — for this program only, the §10 Data⇄Product seam is unified
   under a single driver (owner-merged). This is a scoped exception to §10, not a re-org: §10's
   two-team model stands for all other work. Most WP surface (`connectors/`, `integration/`, resolver,
   `scheduler/`, `schema/migrations/`, domain pack) is Data/Substrate; a few pieces (`api/upload.py`,
   the runtime-security boundary, synthesis/agent) are Product-Platform.
2. **P0 design specs first, no implementation until owner picks what to build.** The three P0-floor
   findings were **re-verified against current code** before speccing (SPEC-003 §2).
3. **Evolve, don't rewrite; no Kafka/Spark; pause net-new connector breadth** except raw-capture /
   deterministic-identifier work.

**P0 floor (specced, awaiting owner go-ahead to build):**
- **WP-0** truthful run outcomes — `specs/data_platform/WP-0_truthful_run_outcomes.md` (G-02 fail-open
  false-green confirmed: `pipeline_hooks.py:116-118` swallows hook exceptions; POST_STORE `has_block`
  never checked; `except: pass` at `pipeline.py:454`).
- **WP-1** immutable raw capture + replay + per-record atomicity — `.../WP-1_raw_capture_and_replay.md`
  (G-03/G-04: bytes hashed then dropped; `db.py` autocommit, `transaction()` unused per-record).
- **WP-4** deterministic identity spine — `.../WP-4_deterministic_identity_spine.md` (G-05: molecule IDs
  0% filled + stranded from `EXACT_LOOKUP_MAP`; drug identity name-based).

WP-2..WP-12 (source-contract control plane, domain plugin, Document IR, derived-job registry,
survivorship, quality-as-gate, cursors/leases, lineage/catalog, relationship normalization, assurance
harness) are sequenced in SPEC-003 §6, to be re-verified per WP when picked up. Board mirror:
`PRODUCT_BACKLOG.md` P0 section.

## 12. Repository maturity & dev-team transfer program — 2026-08-13 (owner-approved)

A **second** independent review (`design-review-output/market_zero_handoff_readiness_review_2026_08_13.md`)
assessed whether the repo can be handed to a fresh dev team **context-free**. **Verdict: conditional
NO-GO today** — strong architecture + test foundations, but a bounded **P0 integrity cycle** is
required first (unmerged/unreviewed security PRs #325/#326; prod demo-auth; 4 red sources / 22 stuck
runs / 1,547 pending DLQ; OpenAPI drift 381↔518; 306 FE lint incl. Rules-of-Hooks; a false "Saved"
autosave; 41 review-less PRs; 78 registered worktrees; branch protection lacks independent-approval +
up-to-date). Execution spec: **`specs/SPEC_HANDOFF_001_repository_maturity_and_transfer.md`** (H0–H8,
evidence protocol §4; baseline SHA `31d923a`).

**Owner ruling (2026-08-13):** the SPEC-003 data-platform direction (§11) is **APPROVED**, but it runs
**behind the handoff integrity floor** as **one combined program-of-record** — the floor is what
SPEC-003's replay / identity / truthful-run work stands on. Approved combined sequence:

1. **H0** — repository inventory + canonical baseline.
2. **H1** — land/review security PRs #325/#326; finish SEC-001b route-policy registry; remove prod
   demo-auth; ownership/tenancy policy.
3. **H2** — repair current operational RED sources, stuck runs, DLQ.
4. **WP-12** (assurance harness) — applies **immediately**, across every PR.
5. Delta-update **WP-0**, then implement **L0a–L0e**.
6. **WP-1** per-record atomicity → then raw capture + replay.
7. **H3/H4/H5** — reconcile OpenAPI, frontend truthfulness, full CI + branch protection.
8. Specify **WP-2** + implement its source-contract / source-identity floor.
9. Complete **L4a**, refresh the identity probe, then implement **WP-4**.
10. Continue **WP-5…WP-11** in dependency order.

**Standing status (replaces the prior "P0 specs done, holding for go-ahead"):**
> The data-platform direction is approved. WP-0, WP-1 and WP-4 have detailed draft designs, but
> implementation readiness requires a fresh baseline delta. WP-0 is the first data-platform build
> after the handoff baseline/security work begins; WP-12 applies immediately. WP-2 remains required
> and must be verified and specced before claiming the four-part platform floor is complete.

**Relationship to §11:** §11's holding state ("P0 specs done, awaiting owner go-ahead to build") is
**RESOLVED → approved-and-sequenced**. No WP-0 build starts until the handoff baseline (H0) + security
floor (H1) are underway **and** WP-0's current-state claims are delta-verified (SPEC_HANDOFF §H8.1 —
e.g. migration 098 already persists `records_skipped`/`records_failed` and `_finalize_etl_run()`
already writes them; do **not** re-spec them as absent).

**⚠ Planning-truth honesty (verified in the H0.1 inventory, 2026-08-13):** `SPEC_HANDOFF_001`,
`SPEC_003`, and `WP-0/1/4` are **UNTRACKED local drafts**; `COORDINATION.md` / `PRODUCT_BACKLOG.md` /
`CLAUDE.md` are **tracked-but-uncommitted**. Per SPEC_HANDOFF §H0.3, a board must not cite an untracked
doc as ratified truth — these are **drafts** until committed to the owner-selected canonical baseline
(H0.3). This §12 records the *direction*; ratification of the specs is the H0.3 commit.

**Governance (binds every lane, this program):** SPEC_HANDOFF §4 — session handshake +
verify-every-cited-claim-against-SHA + record drift; one bounded WP/PR; RED→GREEN evidence run **after
the final nit** (pre-nit output cannot ground a final claim); OpenAPI/changelog on API changes;
**independent review mandatory** for every security / contract / migration / branch-protection /
cleanup PR; **no self-merge**. This is a scoped merge of the §10 Data⇄Product seam **for this program
only** (as §11 already established); §10's two-team model stands for all other work.

**Current step:** H0.1 non-destructive inventory built under **`docs/handoff/`** (committed separately)
— repository / PR / worktree / untracked-artifact census + baseline recommendation. **Awaiting owner
review** of the canonical baseline + cleanup transaction + P0 PR sequence before H0.2 (cleanup) or any
H1 code. Kickoff protocol: SPEC_HANDOFF §17.

---

## 13. Connector-Platform lane (WP-2) — 2026-08-14, spec-only

A dedicated **Connector Platform** session is opened to specify **WP-2 (versioned
source-contract control plane + `source_id` + SSRF/secret boundary)** in parallel with the
handoff/hardening lane. This is a **parallelism-of-design, not of implementation**: two agents
must not concurrently modify the shared pipeline/scheduler, and §12's approved sequence puts
WP-2 *implementation* last — behind the full predecessor gate in §13.3.

| | |
|---|---|
| **Branch** | `claude/connector/wp2-source-contract-spec` |
| **Worktree** | `../mz-connector-platform` |
| **Base** | `claude/handoff/h0-baseline` @ `da6887c` (H0.3) — the only line where SPEC-003 / WP-0/1/4 / SPEC_INDEX are tracked, clean of #318 ancestry, and the same base #327/#328 are stacked on |
| **Mode** | **SPEC-ONLY.** No runtime wiring, no executable tests that leave CI red, no implementation until §13.3 clears |

### 13.1 Ownership (claimed by this lane)

**Owned — design/spec authorship now:**

```
specs/data_platform/WP-2*          (new — this lane authors)
tests/connector_platform/          (new — test SPECIFICATIONS + golden fixtures only; see §13.3)
services/connector_taxonomy.py
api/routes/hub.py
```

**`connectors/` — read/design now; implementation ownership only after predecessor gates and
collision clearance.** WP-1 will itself touch `BaseConnector` and the bronze-capture points, and
#66 is still open on that tree. This lane does not edit `connectors/` in the spec-only phase, and
adds no net-new connector breadth regardless (SPEC-003 §3).

**CONTESTED — read-only, do not edit until the blocking PR lands or H0.2 formally disposes it:**

| File(s) | Blocked by | State (verified 2026-08-14 via `gh`) |
|---|---|---|
| `services/source_registry.py` | **#324** QUAL-001 honest quality provenance (Data lane) | OPEN, active |
| `api/routes/sources.py` | **#320** FAIR honest + reachable (Data lane) | OPEN, active |
| `api/routes/sources.py` | **#56** BE-25 licence model | OPEN, 3 files, MERGEABLE — logged STALE-SCAFFOLD in `docs/handoff/PR_DISPOSITION.md` but **not yet closed** |
| `connectors/base.py` + `biorxiv/cms_partd/cms_pricing/epo/fda_opdp/uspto/va_dod/who_ictrp` | **#66** BE-27..34 Phase-1 connector skeletons | OPEN, 10 files, CONFLICTING — logged STALE-SCAFFOLD, **not yet closed** |

A PR being stale is not a disposal. These stay contested until H0.2 preserves/disposes them under
owner sign-off.

**Board-content landing risk:** **#317** and **#323** also modify `docs/COORDINATION.md`. The H0
baseline likely supersedes their board content, but whichever lands second rebases — this §13 is
append-only at EOF to keep that conflict trivial.

### 13.2 Protected from this lane (do not edit — hardening lane / owner)

```
integration/pipeline.py            integration/pipeline_hooks.py     (WP-0 / WP-1 surface)
scheduler/runner.py                                                  (WP-9 / hardening)
services/agent/harness.py          services/llm_gateway.py           (#327/#328 + WP-0 bug, separate PRs)
schema/openapi.json                                                  (H3 reconcile owns the regen)
frontend/                                                            (Frontend lane; §12 H4)
```

Plus the standing **protected surface** (`protected-surface.txt`) — notably
`scripts/connector_health.py`, `scheduler/config.py`, `tests/test_schema_completeness.py`,
`.github/workflows/`, `.claude/rules/`, `CLAUDE.md`. A WP-2 gate that must become HARD couples
protection with hardening **in the same change** (`protected-surface.txt` + `python
scripts/gen_codeowners.py`).

### 13.3 Sequence gate (what unblocks implementation)

Implementation unlocks only on the **complete** §12 predecessor gate — not a subset:

> **H0** (baseline) → **H1** (security floor) → **H2** (operational RED / stuck runs / DLQ) →
> **WP-12** (corrected, owner-ratified assurance protocol) → **WP-0** (truthful run outcomes) →
> **WP-1** (atomicity, then raw capture + replay) → **H3/H4/H5** (OpenAPI reconcile, frontend
> truthfulness, full CI + branch protection) → **WP-2**.

Changing that order is an owner decision recorded in §12, never a lane-local assumption.

**Phase A — re-verification (now, read-only).** Re-verify WP-2's findings (G-01, G-07, G-10, G-12,
G-14) against code at `da6887c`. SPEC-003 §6 marks WP-2 **"pending re-verify"** and §3 forbids
speccing from the review's citations alone. Drift is recorded, not silently corrected.

**Phase B — safe-fetch threat model (immediately after A, not instead of it).**

**Phase C — the spec-only WP-2 package:** design + API/OpenAPI delta + DB design + contract /
deployment / run / health state machines + **run-identity (job) model** + promotion, approval,
rollback and audit evidence + source identity/provenance design + preview response contract.
*(Corrected 2026-08-16, rev C.2: this line previously read "durable cursor/lease/job model".
**Durable cursors and leases are WP-9's** — SPEC-003 §6 row 10 — and WP-2's cursor/lease design is
withdrawn. WP-2 retains only per-stream job rows that **record** cursor positions. See ASK-WP2-2.)*

**Test artifacts in the spec-only phase are specifications, not executable red tests:** test
specifications, golden fixtures, expected invariants, mutation cases, and API examples. A
spec-only branch must not merge carrying tests that intentionally leave CI red — that is a
standing vacuous-red, the mirror of a vacuous green. Executable RED tests are introduced **inside
each implementation PR**: demonstrate RED, then GREEN in the same bounded slice.

**Phase D — implementation slices** (after the gate above): source identity + immutable contracts
→ safe-fetch/secret boundary → **grant-authorized discovery and preview** → semantic model +
identity integration → chat tools and frontend.

*(Corrected 2026-08-16, rev C.2. Two changes. (1) "durable scheduler/cursors" is **removed** — it
is **WP-9's** slice, not this lane's; WP-2 consumes an interface it does not design (ASK-WP2-2).
(2) "no-write discovery and preview" is **wrong as stated**: preview performs outbound egress, so
it **must** durably write a security-audit event and rate-limit accounting. What it must not write
is any domain fact, entity, `etl_runs` row, cursor advance, DLQ record or downstream pipeline
output. The correct phrasing is grant-authorized, no-domain-write.)*

### 13.4 Standing invariant for this lane (load-bearing)

> **AI may propose declarative contracts; deterministic validators control network access,
> persistence and production promotion.** No generation or execution of arbitrary connector code,
> and no arbitrary SQL/Python callables in user-editable runtime contracts (SPEC-003 §8).

**On assurance protocol:** once a corrected, owner-ratified WP-12 protocol lands, WP-2 work will
adopt that protocol. Acceptance criteria must be owner-ratified **before** implementation; the
builder must not self-author or modify its merge bar to pass. This lane makes no commitment to
#327's current artifact design, which is under review.

### 13.5 Cross-lane ASKs — WP-0 ⇄ WP-2 ⇄ WP-9 (BLOCKING, opened 2026-08-15)

Two boundaries must be ratified **before any of the three work packages lands**. Both were
discovered by an independent review of the WP-2 Phase C draft, which had asserted agreement that
does not exist and claimed ownership that SPEC-003 assigns elsewhere.

**ASK-WP2-1 — Run-outcome vocabulary (WP-0 owns; WP-2 proposes inputs).**
WP-2 needs `truncated`, `cursor_advanced`, `contract_validation_failed`, `credential_unresolved`
and `egress_refused` to reach a terminal outcome rather than a log line. `classify_run_outcome`
(`integration/pipeline.py:125-168`) is WP-0's. **Deliverable: one shared normative table** mapping
each input to a terminal outcome *and* a Lane-2 health consequence. A test that merely rejects
unknown strings does not prove semantic mapping, so the WP-2 suite carries **M-28a**, which stays
RED until this table exists. Do not mark it pending to make a suite green.

**ASK-WP2-2 — Cursor / lease ownership (WP-9 owns).**
SPEC-003 §6 row 10 assigns *"durable cursors, streaming batches, leases, cost controls"* to
**WP-9**. The WP-2 Phase C draft specified a cursor table, a lease and rollback semantics; that is
**withdrawn** in C.1. WP-2 retains only `source_jobs` run identity (recording `cursor_before` /
`cursor_after`). **Deliverable: one normative cursor/lease interface published by WP-9** before
either lane specs its side, covering: cardinality per `(source_instance_id, stream_key)`, cursor
typing, whether "empty page + advanced token" is legitimate (it is, for some sync APIs), advisory
lock **vs** TTL/heartbeat/fencing (alternatives, not a stack), and whether rollback is automatic
(WP-2's position: it must not be — safety depends on cursor kind and sink idempotency).

**ASK-WP2-3 — Rights/retention attachment point (WP-1 ⇄ WP-2; opened 2026-08-16, rev C.2).**
WP-1 places `retention_class` and `legal_hold` on the **content-addressed** `raw_artifacts` row
(`specs/data_platform/WP-1_raw_capture_and_replay.md:38`, insert is
`ON CONFLICT (sha256) DO NOTHING`), and exposes `apply_retention(source_type, before)` (`:23`).
Because the row is keyed by content hash, **identical bytes acquired under two different licences,
retention classes or tenants collapse to one row and one retention class — silently, in favour of
whichever acquisition arrived first.** That is a silent loss of a governance attribute.
WP-2 requires rights to attach to the **acquisition** (contract-version-scoped), not the blob.
**Deliverable: one acquisition-scoped rights/retention interface** — blob keeps bytes only;
per-acquisition rows carry rights; retention and legal hold resolve **most-restrictive across all
acquisitions** of a blob; `apply_retention` keyed by acquisition. **Neither lane may resolve this
unilaterally:** WP-2 cannot alter WP-1's schema, and WP-1's current design cannot carry WP-2's
rights model. Detail: `WP-2_source_contract_control_plane.md` §3.5.1.

**Provisional dependency (not an ASK, recorded for traceability):** WP-2's object names are
*aligned with* `specs/trusted_intelligence_v2/` (TIV2-020), which is **untracked and labelled
DRAFT with "Implementation authority: none until the owner records ratification"**. Per §12's own
rule that a board must not cite an untracked doc as ratified truth, the seam is **provisional**,
pinned by content digest in `WP-2_source_contract_control_plane.md` §2. If TIV2 ratifies with
different names, WP-2 renames; if it never ratifies, the names still stand on the Phase A finding
that a bare `source_id` collides with `cross_linker.py`'s graph-edge usage.
