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
- **STILL BROKEN (not fixed by #220):** canonical re-demotion **RECURS** — **34
  names orphaned on prod** (live evidence, 0 active row: valsartan 83, sitagliptin
  phosphate 80, ivabradine 33…). New fail-loud detector
  `scripts/check_orphaned_canonicals.py` + Lane-2 invariant
  (`tests/test_orphaned_canonical_invariant.py`) ship with this change. **Live
  root-cause diagnosis = D-intel (this session), in progress.**

### 7.3 Backlog — CLAIMS (append before building; commit the claim first)
| Loop | Owner / branch | Status |
|---|---|---|
| Orphaned-canonical detector + Lane-2 invariant | D-intel `claude/data/coord-sync-protocol` | in-flight (this PR) |
| Diagnose the live re-demotion vector | D-intel | in-flight |
| Excluded-config absorb (combo-guarded tool ready) | D-intel | **BLOCKED** on canonical stability |
| FS-* frontend salvage (timeline + badge on #231/#227) | unclaimed | open |
| D1 emitters: TrialOutcome / Investigator / PublicationClaim / CompanyFinancial | D-ingest (other session has #232) | open — claim individually |
| FS-3 readiness panel, FS-4 as-of UI, H-a temporal edges | unclaimed | open |

### 7.4 Migration registry (reserve a number here before authoring)
- `090` fact_governance · `091` crosswalk_records — MERGED.
- `092` = **`scenario_probability_history`** (#231, MERGED). ⚠️ a duplicate
  `092_scenario_calibration_history` (#228) also applied to prod — two redundant
  tables; cleanup debt (close #228 backend, keep one).
- `093` = `facts_epistemic_timestamps` (#233, MERGED).
- `094` = **NEXT FREE** — reserve here before use.
