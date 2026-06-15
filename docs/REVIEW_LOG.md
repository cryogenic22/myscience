# Build <-> Reviewer Log - Market Zero

This is the persistent handoff ledger for independent review. It adapts the
Content Medical Hub reviewer pattern to Market Zero's native controls:
`docs/COORDINATION.md`, `.claude/rules/conservation-gates.md`,
`protected-surface.txt`, CODEOWNERS, OpenAPI/API changelog, UI changelog, and
lane-specific worktrees.

Two sections are used:

- Section A - Build -> Reviewer: the owning lane appends a handoff packet when a
  work unit is ready for independent review.
- Section B - Reviewer -> Build: the reviewer appends verdicts, findings, and
  caveats. Builders fix findings and re-hand off; they do not self-approve.

Rules:

- Review the pinned range, not the dirty working tree.
- Status lives here, not only in chat.
- Builder numbers must be pasted from real command output.
- Reviewer verdicts are not final release sign-off; the owner accepts or rejects
  residuals.

## Section A - Build -> Reviewer

### Handoff Packet Template

```markdown
### MZ-REVIEW-NNN - <lane/task id> - <one line>
- Status: AWAITING REVIEW | FINDINGS-OPEN | OWNER-RESIDUAL | CLEARED
- Lane: Platform / Data / Frontend / Full-stack
- Branch / worktree: <branch> | <worktree path>
- Review this range: <from-SHA>..<to-SHA>
- Implementation files: <paths>
- Protected surface in range: UNTOUCHED | TOUCHED WITH OWNER BAR-CHANGE
  - Proof: `git diff --name-only <from>..<to> -- <protected paths>` -> <output>
- API contract impact: none | `schema/openapi.json` updated + `docs/API_CHANGELOG.md` entry
- UI contract impact: none | `docs/UI_CHANGELOG.md` entry
- RED-first evidence: <command + failing output summary>
- GREEN-after evidence: <command + passing output summary>
- Lane-1 deterministic gate: PASS | FAIL | NOT RUN (<why>)
- Lane-2/live evidence: PASS | FAIL | RESIDUAL | NOT APPLICABLE
- Conservation evidence: <row/field/provenance/freshness/linkage proof or NA>
- Non-vacuity evidence: <why checks could not pass empty/all-skipped/0-file>
- Residual review required: yes | no
- NOT claimed: <explicit caveats>
- Reviewer verdict: (filled in Section B)
```

### MZ-REVIEW-000 - reviewer protocol adoption
- Status: CLEARED
- Lane: Process
- Branch / worktree: `claude/data/adopt-coordination` | main checkout
- Review this range: docs-only local change introducing this log and reviewer brief
- Implementation files: `docs/REVIEWER_BRIEF.md`, `docs/REVIEW_LOG.md`, `docs/COORDINATION.md`, `.claude/commands/review-gate.md`
- Protected surface in range: UNTOUCHED
- API contract impact: none
- UI contract impact: none
- RED-first evidence: not applicable; process documentation only
- GREEN-after evidence: `python scripts\gen_codeowners.py --check` -> CODEOWNERS in sync; targeted protected-surface/smoke/conservation pytest slices passed
- Lane-1 deterministic gate: targeted slice PASS
- Lane-2/live evidence: NOT APPLICABLE
- Conservation evidence: no data path changed
- Non-vacuity evidence: targeted tests collected and executed non-zero assertions
- Residual review required: no
- NOT claimed: no full backend suite, no frontend build/typecheck, no live operational-health run
- Reviewer verdict: protocol bootstrap only; future substantive work should use this log

## Section B - Reviewer -> Build

### Verdict Template

```markdown
### MZ-REVIEW-NNN verdict - <PASS_NO_RESIDUAL | PASS_REVIEW_REQUIRED | FINDINGS | BLOCKED> (reviewer, range <from>..<to>, YYYY-MM-DD)
- Re-verified: protected surface [Y/N] | lane ownership [Y/N] | RED->GREEN [Y/N] | non-vacuous checks [Y/N] | API/UI logs [Y/N/NA] | residual surfaced [Y/N]
- Commands run: `<command>` -> <result>; `<command>` -> <result>
- Findings: none | F1 <severity> `<file:line>` - <what> - <why it matters> - <suggested direction>
- Caveats / not verifiable here: <items>
- Verdict: <verdict>
- Not final sign-off; owner owns residuals and release.
```

### MZ-REVIEW-001 verdict - FINDINGS (independent reviewer, cross-lane sampling, 2026-06-13)
- Re-verified: protected surface N/A | lane ownership Y | RED->GREEN N/A | non-vacuous checks N/A | API/UI logs N/A | residual surfaced Y
- Commands run: read-only inspection of `docs/COORDINATION.md`, `C:\Users\kapil\Documents\mz-f6`, `.claude/worktrees/data+source-coverage-freshness`, `.claude/worktrees/data+nadac-pricing-revival`, `.claude/worktrees/data+brand-alias-backfill`, and `C:\Users\kapil\Documents\mz-fe-datahub`.
- Findings: see `docs/independent-cross-lane-review-20260613.md` for `MZ-XR-20260613-001` through `MZ-XR-20260613-006`.
- Caveats / not verifiable here: no tests were run during this reviewer pass; several reviewed branches were behind their remotes/main and should rebase before final handoff.
- Verdict: FINDINGS_OPEN; Platform, Data, and Frontend owners should address or explicitly accept residuals through handoff packets.
- Not final sign-off; owner owns residuals and release.

### MZ-REVIEW-002 verdict - FINDINGS (independent reviewer, DataHub loops, 2026-06-13)
- Re-verified: protected surface N/A | lane ownership Y | RED->GREEN N/A | non-vacuous checks N/A | API/UI logs N/A | residual surfaced Y
- Commands run: read-only inspection of merged commits `9fe8f5f` (#254), `e8e54b6` (#256), `4dac947` (#257), and `a7ee278` (#258); inspected `api/routes/hub.py`, `api/routes/catalog.py`, `connectors/rss_connector.py`, `connectors/base.py`, `services/connector_taxonomy.py`, `integration/dataset_catalog.py`, `frontend/src/pages/CatalogPage.tsx`, `frontend/src/api.ts`, `tests/test_hub_api.py`, `tests/test_dataset_fair.py`, and `tests/test_rss_connector.py`.
- Findings: see `docs/independent-datahub-review-20260613.md` for `MZ-DH-20260613-001` through `MZ-DH-20260613-005`.
- Caveats / not verifiable here: no tests were run during this reviewer pass; review was grounded in merged code/diff inspection and contract analysis, not a live prod probe.
- Verdict: FINDINGS_OPEN; Platform, Data, and Frontend owners should close or explicitly accept residuals through handoff packets before more generic connectors build on these seams.
- Not final sign-off; owner owns residuals and release.

### MZ-REVIEW-003 verdict - FINDINGS (independent reviewer, current cross-lane sweep, 2026-06-15)
- Re-verified: protected surface N/A | lane ownership Y | RED->GREEN N/A | non-vacuous checks N/A | API/UI logs N/A | residual surfaced Y
- Commands run: `git fetch --all --prune` -> refreshed refs; read-only inspection of `origin/main` at `d41ad9b`, commits `f850ee7`, `6b31e85`, `d0fa62a`, and branches `origin/claude/platform/coverage-quality`, `origin/claude/data/dq1-factclass-reference`, `origin/claude/frontend/graph-explorer-simpler`.
- Findings: see `docs/independent-cross-lane-review-20260615.md` for `MZ-XR-20260615-001`.
- Caveats / not verifiable here: no tests were run during this reviewer pass; reviewed pinned refs with `git show` because the checkout is dirty and behind `origin/main`.
- Verdict: FINDINGS_OPEN for Frontend only; no blocker found in the reviewed merged Platform commits or the checked Data D-Q1 contract.
- Not final sign-off; owner owns residuals and release.
