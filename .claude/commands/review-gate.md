# /review-gate — independent, adversarial pre-merge review

A **structurally separate** review before merge. Not self-review: the agent that
wrote the diff shares its own blind spots, so this MUST run as a different
lineage / fresh agent (spawn one via the Agent tool, or the `/code-review`
skill). "Looks okay" is not a review — work the checklist and try to *refute*
the success claim.

Read `docs/REVIEWER_BRIEF.md` and `.claude/rules/conservation-gates.md` first.
Review the **pinned commit range / PR diff**, not the dirty working tree. If the
builder handed off through `docs/REVIEW_LOG.md`, write the verdict back there.

## Adversarial checklist (report a verdict + evidence per item)

1. **Protected surface untouched.** Did the diff edit anything in
   `protected-surface.txt` (gates, thresholds, eval gold, scorers, SLAs, CI,
   rules)? If yes — is there an explicit owner-approved reason in the PR, or did
   the builder quietly move its own bar? `git diff --name-only <range>` ∩ the
   surface. Flag [BAR-MOVED].
2. **Gates genuinely ran (not vacuous).** Did Lane-1 actually execute real
   assertions — not pass by skipping/empty/0-files? Confirm skips are only the
   Lane-2 live tests (no `DATABASE_URL`), nothing else. Flag [VACUOUS-GREEN].
3. **Conservation held.** For any data path: were rows/fields/provenance dropped
   silently? Demand the soft-delete / drop-manifest / logged count. Re-probe
   prod where relevant (`probe_substrate.py` / a SELECT) and compare to the PR's
   claimed before→after. Flag [SILENT-LOSS].
4. **Claims are grounded.** Every number / "done" / "verified" traces to pasted
   output, not memory. Re-run the headline command yourself if cheap. Flag
   [UNGROUNDED].
5. **RED→GREEN is real.** Does a test fail without the change? For a bug fix,
   does it reproduce the user-visible failure (not tests-only)? Flag
   [TESTS-ONLY].
6. **No weakening.** No deleted/skipped/xfail'd tests, softened assertions, or
   new silent `except: pass`. Flag [TEST-WEAKENED] / [SILENT-CATCH].

## Output

Use the verdict language from `docs/REVIEWER_BRIEF.md`:
`PASS_NO_RESIDUAL`, `PASS_REVIEW_REQUIRED`, `FINDINGS`, or `BLOCKED`.

For a handoff packet, append the verdict to `docs/REVIEW_LOG.md` Section B. For
an ad hoc PR review, leave a short verdict with flagged items, each citing a
file:line or pasted command output. If findings are open, the builder fixes and
re-submits; never self-approve over the findings.
