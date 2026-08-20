# SPEC WP-12 — Closed-Loop Assurance Kernel

**Status:** DRAFT — builder-PROPOSED, pending independent review + owner approval. Nothing here
is "owner-ratified" yet: the acceptance manifest (`assurance/contract/acceptance_manifest.json`,
`status: owner-review-pending`) becomes the ratified bar only when the owner approves this PR's
protected-surface change. Assurance-kernel PR builds WP-12A–D + the WP-12C scanner redesign;
WP-12E is owner/server-side only; WP-12F is a separate (non-security) PR.
**Base:** `claude/handoff/h0-baseline@da6887c` (rebased onto the H0.3 baseline so the reviewed
head + test evidence include the H0.3 reconciliation).
**Rev 1:** hardened after an independent review (2026-08-14) found the first pass trusted the
review artifact's own SHAs/criteria, and the egress scanner missed non-`.create` terminals,
callable aliases, direct provider HTTP, and collapsed duplicate/same-named call sites.
**Rev 2:** hardened again (2026-08-15) — gate results + reviewer identity now come from REAL
GitHub check conclusions / `gh`, not the artifact; (Rev-2 used an evidence-only commit whose
parent was the reviewed code — **SUPERSEDED by Rev 4's review-body model below; do not use**);
the CLI fails closed on an unresolvable `--pr` (no local-HEAD fallback); the scanner covers
call/subscript receiver bases and HTTP callable aliases; the CI workflow runs conservation + a
fail-closed merge-gate on the exact PR head with least-privilege permissions and pinned actions.
See §3.
**Rev 3:** owner independent-review calibration (2026-08-16). (a) The egress scanner now detects
**urllib** provider egress (`urlopen(url)` / `urlopen(Request(url))` / `req=Request(url);
urlopen(req)`, url as literal/constant/f-string/concat, across OpenAI/Anthropic/**Gemini** hosts,
through any qualified/imported alias) — the 13 previously-invisible `urlopen` calls across five
`ctxpack/benchmarks` provider files are reconciled, each individually classified `fixture-only`
(offline eval on fixture corpora, not production, not imported by `api`/`services` — proven per
entry; no broad directory allowlist). (b) The independent-review reconciliation is bound to the
owner-calibrated **`codexindependentreviewer[bot]`**: an APPROVE is believed ONLY when the
GitHub review is by that actor, `state == APPROVED`, not dismissed, targets the exact live head
(`commit_id == pr_head_sha`), and actor ≠ author — COMMENTED/CHANGES_REQUESTED/wrong-actor/
stale-SHA/dismissed/missing all fail closed; a later push returns the gate to red until the new
head is re-approved. The workflow also triggers on `pull_request_review` (submitted/dismissed).
(c) Corrected the earlier overclaim: the PRIV-001b **runtime** guard wraps the SDK client, so it
does NOT intercept hand-rolled `urllib`/`requests`/`httpx` HTTP — for those the STATIC scanner
is the sole control. This custom review gate does NOT replace GitHub-native branch approval.
**Rev 4:** owner follow-up (2026-08-16) — the evidence-only-commit design was itself still
self-referential (a committed artifact must name the SHA of the commit that contains it). The
review of record is now the **typed JSON payload in the trusted bot's GitHub review BODY**, never
committed to the branch: the reviewed SHA is the review's own `commit_id` (external, == the live
head), so the payload's `reviewed_sha` is checked directly against the head with no artifact-commit
parent. The `EVIDENCE_COMMIT_UNBOUND` / `CODE_CHANGED_AFTER_REVIEW` / `EVIDENCE_ONLY_UNVERIFIABLE`
violations and the `--artifact` path are removed; the CLI parses the payload from the review body.
The canonical model token is `review_model: github-review-body-payload` — the acceptance manifest,
this spec, and `review_contract.json` must all agree on it (a parity test enforces no drift), so
the manifest criterion text and the spec can never describe different review models.
**Origin:** the PRIV-001 escaped defect (2026-08-13) — a live LLM-egress *bypass* was
classified as a review "nit" and nearly landed under a non-canonical verdict
("LAND-WITH-NITS"), because **nothing machine-reconciled the review against the ratified
acceptance criteria** (`SPEC_HANDOFF_001 §H1.1.4`). See `assurance/incidents/`.

---

## 1. The core invariant (load-bearing — do not weaken)

> **The kernel learns automatically, but it must never autonomously weaken or rewrite its
> own success criteria.** Claude may *propose* a new rule and its regression test. Changes
> to **protected gates** (`protected-surface.txt`) still require **independent owner
> approval**. This prevents "self-healing" from becoming "the agent edits its own exam."

Concretely, the kernel is allowed to: detect an escaped miss, record it, author a *failing*
regression/meta-test that reproduces it, and open a PR proposing a new gate. The kernel is
**not** allowed to: relax a threshold, delete/skip/xfail a protected test, or add itself to
an allowlist, without an owner-reviewed change to the protected surface. WP-12C couples every
new gate to `protected-surface.txt` + CODEOWNERS in the same change, so a builder credential
cannot both add a gate and later quietly edit it.

## 2. The closed loop

```
escaped miss ─▶ recorded incident ─▶ failing regression/meta-test ─▶ protected gate
     ▲                (WP-12D)            (WP-12B / WP-12C)          (protected-surface)
     │                                                                     │
     └──────────────── monitored exceptions ◀── CI enforcement ◀──────────┘
                          (allowlist w/ reason)      (WP-12E, owner)
```

Every stage is a file, not a habit: the incident is a registry entry, the regression is a
test, the gate is a protected path, enforcement is a required CI check, and an exception is
an allowlist row **with a reason and an owner**. No stage is discretionary.

## 3. Sub-work-packages

### WP-12A — Machine-readable acceptance contract  *(this PR)*
`assurance/contract/review_contract.json` — the single source of truth the WP-12B validator
consumes (stdlib JSON, no undeclared YAML dependency — a gate must not depend on a package
absent from `requirements.txt`). It pins:
- `valid_verdicts`: the closed set from `.claude/commands/review-gate.md`
  (`APPROVE` / `CHANGES-REQUIRED` / `BLOCK`). Any other string (e.g. `LAND-WITH-NITS`,
  `APPROVE-WITH-NITS` as a *final merge* verdict) is invalid.
- `approve_requires`: `open_must_items == 0`, `failing_gates == 0`,
  `unmet_spec_criteria == 0`. An `APPROVE` with any open MUST or any unmet ratified
  criterion is a contract violation.
- `reviewed_sha_must_equal: pr_head` — a review of an older SHA than the PR head is stale.
- `evidence_not_before: final_commit` — evidence timestamps must be ≥ the final commit
  (blocks reuse of pre-nit output as final proof — a named DoD failure).
- `require_spec_conformance_matrix: true` — the review MUST enumerate each ratified
  acceptance criterion with a met/unmet verdict + evidence pointer. This is the exact gap
  the PRIV-001 miss fell through.

### WP-12B — Typed review-artifact validator  *(this PR)*
`assurance/review_artifact.py` — loads the contract + a structured review artifact (JSON) +
`TrustedInputs`, returns `VALID` or a list of typed violations. **The binding facts are NOT
taken from the artifact.** The real PR head SHA + final-commit time come from git/GitHub; the
canonical criterion set + required gates come from the acceptance manifest (owner-review-pending;
ratified on owner approval)
(`assurance/contract/acceptance_manifest.json`). It **rejects**: unknown verdicts,
`APPROVE`-with-open-MUST/failing-gate/unmet-criterion, `reviewed_sha != trusted head` and a
self-reported head that differs from the trusted head, malformed (non-40-hex) SHAs, an
incomplete or fabricated criterion set, `n/a` where the manifest does not permit it, a required
gate marked `skip`/`fail`/absent, empty evidence, an unresolved `evidence_ref`, evidence dated
before the final commit or in the future, and — fail-closed — an `APPROVE` with no
`TrustedInputs` to reconcile against (`UNVERIFIABLE_APPROVE`). Backed by
`tests/test_wp12b_review_validator.py`, whose first fixture is the real PRIV-001 review that
*must* be rejected (see WP-12D), and whose hardening fixture is the fabricated self-attested
`APPROVE` an independent review found the first pass accepted.

`assurance/check.py` is the **executable seam**: `--self-test` proves the gate is non-vacuous
on every CI run (a bundled fabricated `APPROVE` must be rejected AND a well-formed one
accepted); the merge gate parses the review of record — the typed JSON payload in the trusted
bot's GitHub review **body** (Rev 4; NOT a committed `assurance/reviews/PR-<n>.json`, which was
self-referential) — and reconciles it against the **live** PR head + real check conclusions.
Wired in `.github/workflows/assurance-gate.yml` (incl. `pull_request_review`
submitted/edited/dismissed) + `tests/test_wp12_assurance_gate.py`.

### WP-12C — Boundary inventory + mutation proof  *(this PR)*
A redesigned, **mutation-proven** egress scanner (`assurance/egress_scan.py`), superseding
the first-pass `tests/test_priv001b_egress_inventory.py`. It resolves local aliases and, after
the independent review, is hardened against every bypass class the earlier redesign still
missed: **callable aliases** (`f = client.chat.completions.create; f(...)`), **non-`.create`
terminals** (`.stream` / `.parse` and async twins), **direct provider HTTP** (a provider URL
literal — even behind a constant — on an HTTP verb), and the **intermediate-variable receiver**.
Call-site **identity** is now unique per site — `(relpath, qualified-scope, kind, source-ordinal)`
— so two egress calls in one function, or a same-named method in two different classes, no
longer collapse to one inventory key (the review's "hits=2, unique keys=1" defect); line/col
are carried as reporting metadata but kept OUT of the key so refactors don't churn the pin.
The skip-list is narrowed (apps/ and packages/ are scanned) and a test asserts it can never
grow to hide a production dir. Proven by `tests/test_wp12c_egress_mutation.py`, which injects
each bypass form and asserts the scanner turns **RED**. A scanner that cannot fail on a real
bypass is a vacuous gate (principle #3).
This PR ships the scanner + mutation proof + a complete current-site inventory (all passing);
the **RED "every egress site is guarded" acceptance driver** lands with **PRIV-001b GREEN**,
not here, so this PR is internally green and PRIV-001b is a clean RED→GREEN.
New gate files are added to `protected-surface.txt` and CODEOWNERS is regenerated in this
same change (`python scripts/gen_codeowners.py`).

### WP-12D — Escaped-defect learning registry  *(this PR)*
`assurance/incidents/*.md` — one file per escaped miss, with a stable ID
(`ESC-YYYY-MM-DD-<slug>`), the root cause, the class, and a **link to the regression test
that now reproduces it**. First entry: `ESC-2026-08-13-priv001-spec-conformance.md` — its
provenance is corrected (#326 head is `a66dbcba…`, not the later `5bc8806` WIP tip) and its
status is **MITIGATED, not CLOSED**: an incident is closed only when its fix is a *structural
gate that is actually enforced*, and this gate is green-but-unmerged. An incident without a
linked failing-then-passing test is not closed; a green-but-unmerged gate is not closed either.

### WP-12E — Structural GitHub enforcement  *(OWNER / server-side — not in this PR)*
Branch protection on `main`: require CODEOWNERS review, the conservation-gate check, and the
new assurance checks; disallow self-approval; the builder credential has **no** ability to
push to `main`, bypass rules, or alter branch protection. Documented as an owner action list;
the kernel cannot self-grant these.

### WP-12F — Repair `harness/measure.py`  *(SEPARATE, non-security PR — not bundled here)*
`count_test_files()` globs `apps/api/tests` / `apps/web/__tests__` (neither exists here) and
reports 0; `main()` infers quality from commit-message prefixes and never fails closed on
zero tests. Fix: point at real dirs (`tests/`, `frontend/__tests__/`), fail closed when the
discovered test count is 0. Tracked here for provenance; **shipped in its own PR** so it is
not entangled with a security review.

## 4. Scope boundaries (explicit)

- **Not in either security PR:** `harness/measure.py` (WP-12F) and `services/agent/harness.py`
  (the `status="completed"` optimistic-finalize false-green — belongs under **WP-0**
  truthful run outcomes). Per owner directive.
- **This (assurance-kernel) PR:** WP-12A, WP-12B, WP-12C (scanner + mutation proof +
  protected-surface coupling), WP-12D. Fully green.
- **PRIV-001b GREEN PR (separate, after this floor):** provider-agnostic egress guard +
  wiring + per-site capture tests + direct-vs-gateway parity + the RED "all guarded" driver.

## 5. Acceptance criteria (this PR)

The proposed, machine-checkable form of these lives in
`assurance/contract/acceptance_manifest.json` (`prs["327"]`, ids `WP12#1..#7`), which the
WP-12B validator reconciles a review against. Kept in sync (a test asserts 7 criteria):

1. **WP12#1** — `review_contract.json` exists and is loadable; its `valid_verdicts` matches
   `review-gate.md` exactly (a test asserts the two never drift).
2. **WP12#2** — WP-12B rejects the real PRIV-001 `LAND-WITH-NITS` fixture AND a synthetic
   `APPROVE`-with-unmet-criterion; accepts a well-formed `CHANGES-REQUIRED` and `APPROVE`.
   Hardened: a fabricated self-attested `APPROVE` (equal fake SHAs, invented criterion, empty
   evidence, required-gate `skip`) is rejected; an `APPROVE` with no external truth fails
   closed. RED→GREEN pasted.
3. **WP12#3** — WP-12C scanner is RED on injected raw egress across every bypass class
   (direct, callable-alias, intermediate-variable, `.stream`/`.parse`, direct provider HTTP,
   **factory-call receiver** `get_client().chat.completions.create`, **subscript receiver**
   `clients["openai"].messages.create`, and **HTTP callable alias** `send = requests.post;
   send(URL)`); GREEN on the clean tree; identity is unique per call site (duplicate calls and
   same-named methods in different classes do not collapse). Pasted.
4. **WP12#4** — Incident `ESC-2026-08-13-priv001-spec-conformance` links the WP-12B replay,
   records correct #326 provenance (`a66dbcba…`), and is `MITIGATED` (not `CLOSED`) while the
   gate is unmerged/unenforced.
5. **WP12#5** — New gate files (incl. the spec, incident registry, `review-gate.md`,
   `test_protected_surface_sync.py`) present in `protected-surface.txt`; sync test green;
   CODEOWNERS regenerated in the same commit; no protected threshold moved to pass.
6. **WP12#6** — An executable CI check (`assurance/check.py --self-test`, wired in
   `assurance-gate.yml`) is proven non-vacuous each run. The review of record is a **typed JSON
   payload in the trusted bot's GitHub review BODY** (Rev 4 — not a file committed to the branch,
   which was self-referential), not a Markdown table; the `merge-gate` job parses that body and
   reconciles it against the LIVE head + the REAL results of the `assurance-kernel` and
   `conservation-lane1` jobs and **fails closed** until a valid independent APPROVE on the exact
   head exists. Workflow uses least-privilege permissions + pinned actions + `pull_request_review`.
7. **WP12#7** — Independent review against these criteria (dogfooded via the WP-12B contract),
   with reviewer identity + state + commit_id taken from GitHub's review API, not the payload.
   **Merge-blocking and independent-only** — the author cannot mark it met, the reviewer must be
   `codexindependentreviewer[bot]` and must not be the author, and the approval must target the
   exact live head.
