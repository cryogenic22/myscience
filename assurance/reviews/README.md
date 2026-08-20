# The review of record: a typed payload in the trusted bot's review body

A Markdown table in a PR body is **not** a machine-checkable review, and a review's **own values
are not external truth**. The review of record is a **typed JSON payload placed in the trusted
reviewer bot's GitHub review body** — either the whole body as JSON, or inside a ` ```json `
fenced block (copy `TEMPLATE.json` for the shape). It is validated by the WP-12B validator
(`assurance/review_artifact.py`) against external truth.

## Why the body, not a committed file (the self-reference fix)

Earlier designs committed `assurance/reviews/PR-<n>.json` to the branch. That is **circular**:
the artifact must name the SHA of the commit that *contains* it, and adding the file changes the
head. The fix removes the file entirely:

1. The head `H` already exists on the PR (nothing is committed for the review).
2. `codexindependentreviewer[bot]` submits a GitHub **review on `H`** whose **body** carries the
   typed payload with `reviewed_sha = pr_head_sha = H`.
3. GitHub independently records that review's `commit_id == H` (external truth). The merge gate
   checks `commit_id == the live head` (`REVIEW_STALE_SHA` otherwise) and
   `payload.reviewed_sha == the live head` (`STALE_REVIEW_SHA` otherwise) — same fact, two
   independent sources, **no committed artifact and no self-reference**.

Because the payload lives in the review (not a commit), a later push does not need a new
commit to invalidate it: the pushed head differs from the review's `commit_id`, so the gate
returns to red until the bot re-reviews the new head.

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
  · `REVIEWER_NOT_INDEPENDENT`. The payload's declared `reviewer` must match the observed actor
  (`REVIEWER_MISMATCH`).

## The evidence flow (end to end)

1. The PR head `H` exists. CI (`assurance-kernel`, `conservation-lane1`) runs on `H`. **Nothing
   is committed for the review** — the builder does not author or approve it.
2. The **Codex independent reviewer** validates `H` against this WP-12B contract (dogfooded).
3. **`codexindependentreviewer[bot]`** submits a GitHub **APPROVED** review **on `H`** whose
   **body carries the typed JSON payload** (`reviewed_sha == pr_head_sha == H`). This is the
   review of record; the merge-gate parses and reconciles it.
4. **Any later push** moves the head to `H'`; the review's `commit_id` still points at `H`, so
   `REVIEW_STALE_SHA` fails closed and the merge-gate is RED until the bot re-reviews `H'`. A
   dismissal (`pull_request_review` dismissed event) does the same.

> **Not a substitute for native approval.** This custom gate does NOT count as, and never
> replaces, GitHub-native branch-protection approval by a human/machine user (WP-12E). It is an
> additional, machine-checkable reconciliation, not the merge authority.

## Verdicts

`APPROVE` / `CHANGES-REQUIRED` / `BLOCK` only (the canonical set in
`.claude/commands/review-gate.md`). Interim dispositions like `LAND-WITH-NITS` are rejected —
that non-verdict is the exact PRIV-001 escaped defect (see `assurance/incidents/`). An `APPROVE`
requires: zero open MUSTs, zero unmet ratified criteria, the full criterion set enumerated,
every required gate real-`success`, every `met` criterion citing a resolvable evidence id, a
fully-reconciled independent review (above), and `reviewed_sha == the live head`. An `APPROVE`
with no external truth fails closed (`UNVERIFIABLE_APPROVE`).

## How it is checked

- Push / PR / **review** (`assurance-gate.yml` → `assurance-kernel` + `conservation-lane1`
  jobs): run on the **exact PR head**. The workflow also triggers on `pull_request_review`
  (submitted / dismissed). The `merge-gate` job fetches the **live GitHub review**, parses the
  typed payload from its **body**, and reconciles it against the live head + those jobs' real
  results — and **fails closed until a valid independent APPROVE on the exact head exists** (a
  skipped job is not a passed merge gate).
- Manual: `python -m assurance.check --merge-gate --pr <n> --repo <owner/repo>
  --kernel-result <r> --conservation-result <r> [--require-verdict APPROVE]`.
