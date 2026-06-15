# Independent Cross-Lane Review - 2026-06-15

Review ID: MZ-XREVIEW-20260615-001  
Reviewer stance: independent reviewer; pharma SME, AI/data systems, platform/API, frontend contract reviewer  
Scope: latest mainline Platform work plus active Data/Platform/Frontend branches after `git fetch --all --prune`  
Mode: code and diff inspection from Git refs; no product-code edits

## Executive Verdict

The recent Platform/Data work is directionally good and mostly disciplined:

- `/healthz` deploy-verifiability is small, DB-free, and tested.
- `decomposition_matrix` is now emitted on the unified live chat path, matching the frontend CanvasPanel contract.
- The cross-lane protocol in `docs/COORDINATION.md` is a useful guardrail after the Design A/B fact-class fork.
- D-Q1 source-based fact-classing appears correctly wired through `resolve_fact_class()` in `emit_one()` and in the backfill path.
- The coverage-quality planner branch is aligned with the agreed Design A: `reference` is substantive, weak/context classes are not hard coverage.

One active Frontend branch has an actionable regression in the graph path finder: editing a selected path endpoint no longer clears the committed entity, so the UI can display one query while executing a path for a different, stale entity.

Verdict: `FINDINGS_OPEN` for the frontend branch only. No blocker found in the reviewed merged Platform commits.

## Review Log

| Finding ID | Severity | Owner | Status | Summary |
|---|---|---|---|---|
| MZ-XR-20260615-001 | High | Frontend | Open | Graph Explorer path search can execute against stale From/To entities after the visible input text is edited. |

## Artifacts Reviewed

- `origin/main` at `d41ad9b`
- Commit `f850ee7` - `/healthz` deployed commit SHA
- Commit `6b31e85` - unified handler emits `decomposition_matrix`
- Commit `d0fa62a` - cross-lane coordination protocol + fact-class Design A
- Branch `origin/claude/platform/coverage-quality` at `78378a1`
- Branch `origin/claude/data/dq1-factclass-reference` at `92db850`
- Branch `origin/claude/frontend/graph-explorer-simpler` at `6e951b1`

## Findings

### MZ-XR-20260615-001 - Path Finder Can Execute Stale Entities

Owner: Frontend  
Severity: High  
Area: `frontend/src/components/GraphExplorer.tsx`, `frontend/src/components/graph/EntitySearch.tsx`  
Branch: `origin/claude/frontend/graph-explorer-simpler`

Evidence:

- `EntitySearch.handleChange()` updates only local query text and suggestions. It does not notify the parent that an already-picked entity is now invalid.
- In the path finder, the parent passes `value={pathFromEntity?.label ?? ''}` and `selected={!!pathFromEntity}` for From, and equivalent props for To.
- `selectPathFrom()` / `selectPathTo()` only run when a suggestion is picked.
- The `Show Path` button is enabled solely from `pathFromEntity` / `pathToEntity`.
- `executePath()` sends `pathFromEntity.id/type` and `pathToEntity.id/type`, regardless of the current visible input text.

Why it matters:

A user can pick From=`semaglutide`, then type `tirzepatide` into the From box without choosing a suggestion. The input visibly changes, but `pathFromEntity` still points at semaglutide, the selected border remains, and `Show Path` can run a path for semaglutide. In a graph/provenance tool this is a trust issue because the displayed query and executed entity diverge.

Required direction:

- Add an `onQueryChange` / `onClearSelection` callback to `EntitySearch`, or make the path finder own the visible input value.
- When text changes after a committed selection, clear `pathFromEntity` / `pathToEntity` and clear path result/error.
- Add a frontend test that picks a From and To entity, edits one selected input without choosing a new suggestion, and verifies `Show Path` disables and `api.graphPath` is not called.

Exit criteria:

- A visible path endpoint label always matches the entity id/type that will be submitted.
- Path execution cannot proceed after endpoint text is edited until the user commits a new suggestion.

## Cleared Observations

### Unified Chat Matrix Contract

Commit `6b31e85` fixes the live-path field mismatch by emitting `data.decomposition_matrix` from `UnifiedChatHandler`. Frontend code reads `data?.decomposition_matrix`, and the added test pins the canonical key. I found no blocking issue in this narrow change.

### Deploy Commit Health Check

Commit `f850ee7` keeps `/healthz` DB-free and returns a 12-character commit from Railway/Git env vars, with tests for env-present and env-absent cases. This is a pragmatic deploy-verifiability improvement.

### D-Q1 Fact-Class Contract

Branch `origin/claude/data/dq1-factclass-reference` correctly applies `resolve_fact_class(fact.source_id, fact.fact_class)` inside `emit_one()` and uses the same resolver in the backfill path. The source-first contract matches coordination Design A. I did not find the initially suspected forward-path mismatch.

### Coverage-Quality Planner

Branch `origin/claude/platform/coverage-quality` changes coverage from raw fact count to substantive fact count and changes compare rollup from "covered if any entity" to "covered only when all entities are covered." That is the right direction for closed-world answer honesty. It should still be landed after the D-Q1 source-classing branch, as coordination already states.

## Caveats

- I did not run frontend or backend tests during this review because the reviewed frontend/data/platform work lives on separate refs, not the dirty checked-out branch.
- The working tree is dirty with many pre-existing untracked docs/reports; this review used pinned refs and `git show`, not unstaged local product files.
