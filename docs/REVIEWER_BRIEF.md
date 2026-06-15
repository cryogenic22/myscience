# Independent Reviewer Brief - Market Zero

> Start here for the reviewer seat. Read, in order:
> `docs/REVIEWER_BRIEF.md` -> `docs/REVIEW_LOG.md` Section A ->
> `docs/COORDINATION.md` -> `CLAUDE.md` -> `.claude/rules/conservation-gates.md`.

This is a Market Zero adaptation of the cross-lineage review discipline used in
Content Medical Hub. It keeps the philosophy, not the exact machinery: Market
Zero does not use frozen contract packs or `contract_runner`; it uses protected
surfaces, conservation gates, API/UI changelogs, product backlog evidence, and
lane-specific worktrees.

## Who This Seat Is

The reviewer is a structurally separate auditor of builder claims. The reviewer
tries to refute the success claim before merge or promotion. The reviewer is not
the builder, not the final release owner, and not a rubber stamp.

The reviewer may inspect code, diffs, docs, tests, CI definitions, and generated
artifacts. When acting in this seat, do not implement fixes in product code. File
findings and let the owning lane fix and re-hand off.

## Hard Rules

- Review the pinned commit range or PR diff, not the dirty working tree.
- Re-run cheap, relevant checks. Do not trust builder-provided numbers without
  reproducing or explicitly caveating them.
- Treat "green" as suspect until non-vacuity is shown: no empty suites, all-skip
  passes, zero-file typechecks, weakened assertions, or hidden tolerances.
- Check the protected surface before trusting any gate result. Bar changes must
  be explicit owner-reviewed work, never a quiet self-edit.
- For data/sensing work, conservation comes before cleverness: no silent row,
  field, provenance, freshness, or linkage loss.
- Residuals are owner decisions. A reviewer can say the deterministic floor
  passes with named residuals, but cannot convert that into final sign-off.
- Status belongs in repo artifacts, not chat. Use `docs/REVIEW_LOG.md`.

## Review Modes

### Pre-build challenge

Use this when a spec, acceptance bar, or gate is proposed. Ask:

- Can a lazy builder satisfy every assertion while still disappointing the owner?
- Is the success surface protected in `protected-surface.txt` and CODEOWNERS?
- Are conservation invariants present for every transform that can drop data?
- Does the frontend/backend contract have an OpenAPI/changelog path?
- Is the review evidence observable from repo artifacts?

### Post-build audit

Use this for a builder handoff in `docs/REVIEW_LOG.md` Section A.

At the pinned range, verify:

- Protected surface untouched, or explicit owner-reviewed bar change.
- Work stayed in the declared lane and worktree.
- RED->GREEN evidence is real and relevant to the user-visible behavior.
- Lane-1 deterministic gate and touched-surface checks are non-vacuous.
- Lane-2/live checks are either run with pasted output or named as residuals.
- API changes updated `schema/openapi.json` and `docs/API_CHANGELOG.md`.
- Frontend changes updated `docs/UI_CHANGELOG.md` and followed token/design
  constraints.
- Cross-lane dependencies are logged in the appropriate backlog or spec.
- No tests, assertions, typechecks, or CI jobs were weakened to pass.

## Verdicts

- `PASS_NO_RESIDUAL`: deterministic floor sound; no material residual found.
- `PASS_REVIEW_REQUIRED`: deterministic floor sound; named residuals need owner
  accept/reject.
- `FINDINGS`: builder must fix and re-hand off.
- `BLOCKED`: reviewer cannot verify from the artifacts; name the missing
  artifact or access.

These are review verdicts only. The owner owns release and residual acceptance.

## Output Format

Write verdicts into `docs/REVIEW_LOG.md` Section B.

```markdown
### MZ-REVIEW-NNN verdict - <PASS_NO_RESIDUAL | PASS_REVIEW_REQUIRED | FINDINGS | BLOCKED> (reviewer, range <from>..<to>, YYYY-MM-DD)
- Re-verified: protected surface [Y/N] | lane ownership [Y/N] | RED->GREEN [Y/N] | non-vacuous checks [Y/N] | API/UI logs [Y/N/NA] | residual surfaced [Y/N]
- Commands run: `<command>` -> <result>; `<command>` -> <result>
- Findings: none | F1 <severity> `<file:line>` - <what> - <why it matters> - <suggested direction>
- Caveats / not verifiable here: <items>
- Verdict: <verdict>
- Not final sign-off; owner owns residuals and release.
```
