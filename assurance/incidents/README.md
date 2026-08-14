# Escaped-defect learning registry (WP-12D)

One file per **escaped miss** — a defect that got past review/gates and was caught later.
The registry is the "learn automatically" half of the assurance loop; the linked regression
test is the "never regress" half.

## Rules

1. **Stable ID:** `ESC-YYYY-MM-DD-<slug>`.
2. Every entry names its **root cause** and **class**, not just the symptom.
3. Every entry **links a regression/meta-test that reproduces it** (fails before the fix,
   passes after). An incident with no linked test is **not closed** — it is `OPEN`.
4. The fix is a **structural gate** where possible (a protected test/CI check), not a
   promise to be more careful.
5. Recording an incident never edits a protected gate to make the incident "go away" — the
   kernel proposes; the owner approves protected-surface changes.

## Index

| ID | Class | Status | Regression test |
|---|---|---|---|
| ESC-2026-08-13-priv001-spec-conformance | review-not-reconciled-against-ratified-criteria | MITIGATED (gate green + tested; not yet merged/enforced) | `tests/test_wp12b_review_validator.py::test_priv001_land_with_nits_is_rejected` |
