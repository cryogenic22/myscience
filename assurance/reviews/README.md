# Structured review artifacts (the artifact of record)

A Markdown table in a PR body is **not** a machine-checkable review. The review of record for
a PR is a structured JSON artifact here, named `PR-<number>.json`, validated by the WP-12B
validator (`assurance/review_artifact.py`) against:

- the **WP-12A contract** (`assurance/contract/review_contract.json`) — structural rules, and
- the **ratified acceptance manifest** (`assurance/contract/acceptance_manifest.json`) — the
  canonical criterion + required-gate set, supplied as `TrustedInputs`, **not** taken from the
  artifact, and
- **external truth** for the head SHA + commit time (git / `gh` / the GitHub event), so a
  reviewer cannot self-attest which SHA they reviewed.

## Verdicts

`APPROVE` / `CHANGES-REQUIRED` / `BLOCK` only (the canonical set in
`.claude/commands/review-gate.md`). Interim dispositions like `LAND-WITH-NITS` are rejected —
that non-verdict is the exact PRIV-001 escaped defect (see `assurance/incidents/`).

An `APPROVE` requires: zero open MUSTs, zero failing gates, zero unmet ratified criteria, the
full criterion set enumerated, every required gate `pass`, every `met` criterion citing a
resolvable evidence id, and `reviewed_sha == the live PR head`. An `APPROVE` with no external
truth to reconcile against **fails closed** (`UNVERIFIABLE_APPROVE`).

## Who writes it

The **independent** reviewer (not the PR author) produces the verdict artifact. A
builder-authored artifact is at most a self-assessment and can never mark the
independent-review criterion `met`.

## How it is checked

- Push / PR: `tests/test_wp12_assurance_gate.py` reconciles every committed artifact against
  its manifest (hermetic — structural + criteria + gates + evidence).
- Merge time (owner-dispatched): `python -m assurance.check --artifact assurance/reviews/PR-<n>.json
  --pr <n> --repo <owner/repo> [--require-verdict APPROVE]` reconciles it against the **live**
  PR head SHA from `gh` / git.
