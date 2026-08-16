# Structured review artifacts (the artifact of record)

A Markdown table in a PR body is **not** a machine-checkable review, and a review artifact's
**own values are not external truth**. The review of record for a PR is a structured JSON
artifact here, named `PR-<number>.json` (copy `TEMPLATE.json`), validated by the WP-12B
validator (`assurance/review_artifact.py`) against external truth.

## The self-reference rule (why this is an evidence-only commit)

A review artifact committed **inside the reviewed branch cannot equal the resulting head** —
adding the artifact changes the head. So the artifact is added in an **evidence-only commit**
whose **parent is the reviewed code SHA**:

1. The independent reviewer checks out the PR head `H` they reviewed.
2. They add `assurance/reviews/PR-<n>.json` with `reviewed_sha = H` and commit it — the commit's
   parent is `H`, and it changes **nothing outside `assurance/reviews/`**.
3. The PR head becomes that evidence commit `E`; `parent(E) == reviewed_sha == H`.

The merge gate verifies `reviewed_sha == parent(review-commit)` (`EVIDENCE_COMMIT_UNBOUND` if
not) and that `reviewed_sha..head` touches only `assurance/reviews/` (`CODE_CHANGED_AFTER_REVIEW`
if code changed after the review). (Alternatively, review evidence may be stored fully outside
the branch and passed to the CLI with `--head-sha`; then `reviewed_sha == head`.)

## External truth, not self-attestation

- **Head SHA + commit time** — from `gh pr view` / the GitHub event, never the artifact.
- **Gate results** — the REAL check conclusions (GitHub `needs.*.result` / check-runs), passed to
  the CLI as `--kernel-result` / `--conservation-result`. A self-declared `pass` that contradicts
  the real conclusion is rejected (`GATE_CONCLUSION_MISMATCH`); an APPROVE requires every
  required gate to have a real `success`.
- **Independent review** — from GitHub's review API (`gh api repos/<repo>/pulls/<n>/reviews`),
  NOT the artifact. An APPROVE is believed ONLY when the review by the ONE trusted reviewer
  (`trusted_independent_reviewer` in `review_contract.json` = `codexindependentreviewer[bot]`)
  is `state == APPROVED`, not dismissed, targets the **exact live head** (`commit_id ==
  pr_head_sha`), and its actor `!=` the PR author. Failures fail closed:
  `REVIEW_MISSING` · `REVIEWER_NOT_TRUSTED` · `REVIEW_NOT_APPROVED` (COMMENTED /
  CHANGES_REQUESTED) · `REVIEW_DISMISSED` · `REVIEW_STALE_SHA` (approval left on a previous SHA)
  · `REVIEWER_NOT_INDEPENDENT`. The artifact's declared `reviewer` must match the observed actor
  (`REVIEWER_MISMATCH`).

## The evidence flow (end to end)

1. **Builder** commits evidence artifact **E** (`assurance/reviews/PR-<n>.json`, verdict per the
   reviewer) whose **parent is the reviewed code SHA H**, changing nothing outside
   `assurance/reviews/`. (The builder does NOT self-approve — the artifact is the machine record.)
2. The **Codex independent reviewer** validates E and H (this WP-12B contract, dogfooded).
3. **`codexindependentreviewer[bot]`** submits a GitHub **APPROVED** review on the **exact live
   head E**. This bot approval is what the merge-gate reconciles against.
4. **Any later push** moves the head; the prior approval's `commit_id` no longer matches
   (`REVIEW_STALE_SHA`) and the merge-gate returns to RED until the **new** head is
   independently re-approved. A dismissal (`pull_request_review` dismissed event) does the same.

> **Not a substitute for native approval.** This custom gate does NOT count as, and never
> replaces, GitHub-native branch-protection approval by a human/machine user (WP-12E). It is an
> additional, machine-checkable reconciliation, not the merge authority.

## Verdicts

`APPROVE` / `CHANGES-REQUIRED` / `BLOCK` only (the canonical set in
`.claude/commands/review-gate.md`). Interim dispositions like `LAND-WITH-NITS` are rejected —
that non-verdict is the exact PRIV-001 escaped defect (see `assurance/incidents/`). An `APPROVE`
requires: zero open MUSTs, zero unmet ratified criteria, the full criterion set enumerated,
every required gate real-`success`, every `met` criterion citing a resolvable evidence id, a
fully-reconciled independent review (above), and the evidence-commit binding. An `APPROVE` with
no external truth fails closed (`UNVERIFIABLE_APPROVE`).

## How it is checked

- Push / PR / **review** (`assurance-gate.yml` → `assurance-kernel` + `conservation-lane1`
  jobs): run on the **exact PR head**. The workflow also triggers on `pull_request_review`
  (submitted / dismissed). The `merge-gate` job reconciles the review artifact + the **live
  GitHub review** against the live head + those jobs' real results — and **fails closed until a
  valid independent APPROVE on the exact head exists** (a skipped job is not a passed merge gate).
- Manual: `python -m assurance.check --merge-gate --pr <n> --repo <owner/repo>
  --kernel-result <r> --conservation-result <r> [--require-verdict APPROVE]`.
