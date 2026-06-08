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
