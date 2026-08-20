# ESC-2026-08-13-priv001-spec-conformance

- **Date:** 2026-08-13
- **Class:** review not machine-reconciled against ratified acceptance criteria
- **Severity:** P0 (a live security bypass nearly landed)
- **Status:** **MITIGATED (not CLOSED)** — the regression tests reproduce the miss and pass
  (WP-12B validator + WP-12A contract), but the gate is **not yet merged or enforced** on
  `main`. Per this registry's own rule 4, an incident is CLOSED only when the fix is a
  *structural gate that is actually enforced*. It moves to CLOSED when (a) this PR merges and
  (b) branch protection requires the assurance check + CODEOWNERS review (WP-12E, owner).

## Provenance (corrected)

- **PR #326 = PRIV-001a**, head **`a66dbcba7337d9e28eef190823b90bb038a3856f`** (`gh pr view 326
  --json headRefOid`), state OPEN. This is the review that produced "LAND-WITH-NITS".
- An earlier draft of the regression fixture cited `5bc8806` as #326's head. That is wrong:
  `5bc8806` is the tip of the **later** `claude/platform/priv-001b-egress-guard` WIP branch,
  not #326. The fixture (`tests/test_wp12b_review_validator.py`) now uses the real `a66dbcba…`.

## What escaped

PR #326 (PRIV-001a) added PII redaction to the **four** direct `services/llm.py` synthesis
egress sites. An independent review verified that implementation slice and issued the verdict
**"LAND-WITH-NITS"**, treating the *remaining* raw provider egress as a nit.

But `SPEC_HANDOFF_001 §H1.1.4` ratified a stronger bar: **every** LLM egress path must pass
through the redaction/policy gateway, proven by a **static no-bypass test**. Live raw egress
still existed at `services/extraction_llm.py` (OpenAI *and* Anthropic),
`integration/entity_resolver.py`, `integration/embedder.py`, `services/search.py`, and
operational scripts. The residual was a **security bypass**, not a nit.

## Root cause

Two coupled failures:

1. **No canonical verdict enforcement.** "LAND-WITH-NITS" is not one of the review-gate's
   verdicts (`APPROVE` / `CHANGES-REQUIRED` / `BLOCK`). An ad-hoc verdict let a
   changes-required situation read as a near-approve.
2. **No spec-conformance reconciliation.** Nothing compared the review against the ratified
   acceptance criteria. The reviewer checked "is the diff good?" not "does the diff meet the
   ratified bar?". A criterion (`H1.1.4`) was `unmet`, and no machine objected.

This is not a people problem to fix with more diligence — it is a **missing gate**.

## The fix (structural)

- **WP-12A** `assurance/contract/review_contract.json` — pins the valid verdict set,
  `approve_requires {open_must=0, failing_gates=0, unmet_spec_criteria=0}`, and
  `require_spec_conformance_matrix=true`.
- **WP-12B** `assurance/review_artifact.py` — rejects unknown verdicts, APPROVE-with-open-MUST,
  APPROVE-with-unmet-criterion, stale SHA, and pre-final-commit evidence. **Hardened** after an
  independent review showed the first pass trusted the artifact's own values: the head SHA +
  commit time + ratified criterion/gate set now come from `TrustedInputs` (git/GitHub + the
  owner-ratified manifest), and a fabricated self-attested APPROVE (equal fake SHAs, invented
  criterion, empty evidence, a required gate `skip`) is rejected on every axis; an APPROVE with
  no external truth fails closed (`UNVERIFIABLE_APPROVE`).
- **WP-12A/CI** `assurance/check.py` — the executable seam. `--self-test` proves the gate is
  non-vacuous each CI run; the merge-gate reconciles a review artifact against the **live** PR
  head, not a self-attested SHA.

## Regression test (reproduces the miss)

- `tests/test_wp12b_review_validator.py::test_priv001_land_with_nits_is_rejected`
  — the exact review artifact is rejected (`UNKNOWN_VERDICT`).
- `tests/test_wp12b_review_validator.py::test_priv001_even_as_approve_is_rejected_on_unmet_criterion`
  — even coerced to `APPROVE`, it is rejected (`APPROVE_WITH_UNMET_CRITERION` + `APPROVE_WITH_OPEN_MUST`).
- `tests/test_wp12b_review_validator.py::test_fabricated_selfattested_approval_is_rejected`
  — the "trust the artifact" bypass the independent review found is closed.

## Follow-on

The bypass itself is remediated separately under **PRIV-001b** (provider-agnostic egress
guard + wiring + capture tests), gated by the redesigned, mutation-proven egress scanner
(WP-12C). This incident is about the *review process* that let it through. It stays **MITIGATED
until the WP-12B/WP-12A gate is merged and enforced** (branch protection requiring the
assurance check + independent CODEOWNERS review — WP-12E, owner). A green-but-unmerged gate is
not yet a floor.
