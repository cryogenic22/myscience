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
- **Reviewer identity** — from `gh pr view --json reviews,author`. An APPROVE requires a
  reviewer (`MISSING_REVIEWER`) who is **not** the PR author (`REVIEWER_NOT_INDEPENDENT`); the
  artifact's declared `reviewer` must match (`REVIEWER_MISMATCH`).

## Verdicts

`APPROVE` / `CHANGES-REQUIRED` / `BLOCK` only (the canonical set in
`.claude/commands/review-gate.md`). Interim dispositions like `LAND-WITH-NITS` are rejected —
that non-verdict is the exact PRIV-001 escaped defect (see `assurance/incidents/`). An `APPROVE`
requires: zero open MUSTs, zero unmet ratified criteria, the full criterion set enumerated,
every required gate real-`success`, every `met` criterion citing a resolvable evidence id, an
independent reviewer, and the evidence-commit binding above. An `APPROVE` with no external truth
fails closed (`UNVERIFIABLE_APPROVE`).

## How it is checked

- Push / PR (`assurance-gate.yml` → `assurance-kernel` + `conservation-lane1` jobs): run on the
  **exact PR head**. The `merge-gate` job then reconciles the review artifact against the live
  head + those jobs' real results — and **fails closed until a valid independent-review artifact
  exists** (a skipped job is not a passed merge gate).
- Manual: `python -m assurance.check --merge-gate --pr <n> --repo <owner/repo>
  --kernel-result <r> --conservation-result <r> [--require-verdict APPROVE]`.
