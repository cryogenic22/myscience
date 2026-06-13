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

**Frontend (Antigravity):** see `docs/PRODUCT_BACKLOG.md` (feature/UI board).

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
| **D2 — NADAC pricing revival** (dead Socrata→DKAN CSV; idempotent history mig 095; weekly scheduler; geo-extensible) | D-ingest `claude/data/nadac-pricing-revival` | in-flight (2026-06-13) |
| FS-3 readiness panel, FS-4 as-of UI, H-a temporal edges | unclaimed | open |
| DataHub Phase 0 — catalog lenses L1–L1d (read-only UI over existing APIs) | dedicated agent `claude/datahub/phase0-lenses` | in-flight — review-gated, no self-merge |
| DataHub Phase 1+ — L2 taxonomy/lifecycle → L3 generic connectors → … L12 | D-intel — interleaved w/ eval loops | open — sequential, reserves mig 096+ |

### 7.4 Migration registry (reserve a number here before authoring)
- `090` fact_governance · `091` crosswalk_records — MERGED.
- `092` = **`scenario_probability_history`** (#231, MERGED). ⚠️ a duplicate
  `092_scenario_calibration_history` (#228) also applied to prod — two redundant
  tables; cleanup debt (close #228 backend, keep one).
- `093` = `facts_epistemic_timestamps` (#233, MERGED).
- `094` = `scenario_prob_history_stance_counts` (#237, MERGED).
- `095` = **`drug_pricing_idempotent_history`** — RESERVED (NADAC revival, D2, in-flight `claude/data/nadac-pricing-revival`): unique `(ndc_code,price_type,effective_date,source_api)` for upsert-idempotent price history.
- `096` = **NEXT FREE** — reserve here before use.

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
