# WP-12 Egress Assurance — Bounded Redesign

**Status: PROPOSAL — pending independent (A&I) proposal-review + external owner ratification.** This
supersedes the completeness-claiming approach in `SPEC_WP12_assurance_kernel.md` §WP12#3. Nothing here
is a ratified bar until the *externally-ratified* version lands on the protected baseline (§9) after
the bootstrap in §9 Phase 0 — writing a status string on a candidate branch is **not** ratification.

## 0. Correction log

**Round 1 — over-claim of the runtime boundary; self-certification:** (1) runtime backstop is only the
enumerated SDK path, not raw/dynamic HTTP → §2/§3c/§10; (2) detect-by-argument is *candidate* detection
with a precise rule → §3a/§4; (3) ratification external → §5/§9; (4) corpus independent → §6; (5)
`run_id` removed → §5.

**Round 2 — three sequencing contradictions + boundary precision:** (6) a BLOCKING risk cannot coexist
with APPROVE — boundary implemented+validated before approval → §10/§11; (7) seed/verify corpus before
ratifying its digest → §11; (8) one external source = the protected baseline branch → §5/§9; (9) the
boundary is a *separate gateway* the app process cannot bypass → §10.

**Round 3 — A&I proposal review (empirically grounded):**

| # | Correction | Where |
|---|---|---|
| 10 | **#328 guards are OPT-IN adapters, not a transport backstop.** A direct/aliased/inherited SDK call bypasses them and sends **raw PII** (proven: a direct `client.chat.completions.create` alias transmitted an unredacted email; only `guard_openai_chat` redacted). So **every scanner-MISSED egress form — SDK *or* HTTP — is `backstop=NONE` and BLOCKING**; a documented `strict-xfail` must **not** permit approval; the scanner is a lint/migration/inventory aid, **not** the approval gate. | §2, §3(c), §10 |
| 11 | The provider-host set and the real-tree dispositions must be **externally ratified, digested, and conservation-checked** — a canonical **provider registry** (not a builder-hardcoded `PROVIDER_URL_MARKERS`) and a complete **candidate-disposition ledger** with exact scanner↔ledger conservation. | §7 |
| 12 | Structural authority must be **bootstrapped before ratification**: provision a non-author CODEOWNER, protect the baseline **with the checks that already exist** (staged — the WP-12 checks become required only once they are built and green, §9 Stage 0a/0b), **probe** enforcement, *then* merge the ratified bar. | §9 (Phase 0) |
| 13 | The **ratification record** is fully specified: canonical path/schema, **canonical structured-JSON criterion digests** (no ambiguous Markdown normalization), **non-self-referential baseline resolution** (the record does not embed the SHA of its own commit), registry + ledger digests, and a retained/replaced migration mapping for every WP12 control. | §8 |
| 14 | The network boundary needs a **separately-ratified executable acceptance contract** (all process types, secret isolation, default-deny, bypass vectors, fail-closed, negative runtime probes proving zero direct provider calls). | §10 |

## 1. Why the loop happened (root cause)

A hand-written AST matcher cannot satisfy "closes every statically-resolvable egress form" — the form
space is unbounded, so an adversarial mutation reviewer always finds the next form. Worse (Round 3): we
also mis-modeled the *runtime* — assuming an opt-in sanitizing adapter was a global backstop. Both are
the same error: **claiming a guarantee a mechanism cannot hold.** The fix is to move each guarantee to
a layer that can actually hold it, and to name honestly what is *not yet* controlled.

## 2. Principle — where each guarantee actually lives (corrected)

| Layer | What it actually does today | Guarantee it can hold |
|---|---|---|
| **#328 `guard_*` adapters** | Opt-in helpers that sanitize `messages`/`input` **then** call the SDK — only when a call site chooses to use them (`services/llm_gateway.py`) | Protects **only the sites that call a guard**. **Not** a transport interceptor: a direct/aliased/inherited `client….create(...)` bypasses it and sends raw data. |
| **Static scanner (#327)** | AST inventory + lint | Best-effort **candidate** detection to *find* raw call sites so they can be migrated to a guard. **Not** completeness, **not** enforcement, **not** the approval gate. A miss = an unmigrated raw site = uncontrolled egress. |
| **A genuine network/credential boundary (§10)** | **Does not exist yet** | The **only** control that makes egress safe regardless of scanner coverage or whether a site called a guard. |
| **Acceptance record** | The bar | Approves only when externally owner-ratified on the protected baseline, bound to content digests, server-enforced. |

**Honest consequence:** the guards + scanner are *migration and defense-in-depth aids*. They **cannot**
support an egress-safety APPROVE on their own, because any scanner miss (SDK or HTTP) is raw egress.
**Only the §10 boundary can support approval**, and it must exist + be validated first (§11 Phase D).

## 3. Change 1 — Re-scope WP12#3 (THE BAR — externally ratified, not self-certified)

**Old (unsound):** "the scanner closes every statically-resolvable egress form."

**New (bounded, honest):**
- **(a) Direct provider HTTP/urllib — CANDIDATE detection by argument.** Flag any call passing a
  statically-resolvable provider URL as a **candidate** (it will also flag `logger.info(url)` /
  `validate_url(url)`; every candidate needs an explicit ratified disposition — §7). Rule: positional
  **and keyword** args; nested `Request(...)`; URL **parsed**, hostname **case-insensitive**, matched by
  **exact host/subdomain** (not substring) against the ratified **provider registry** (§7); `+`/`%`/
  `.format`/f-string construction; **malformed/ambiguous → fail closed** (flagged).
- **(b) SDK-chain candidate detection** (`client.chat.completions.create`/`.stream`/`.parse`,
  `.messages…`) via best-effort AST alias resolution — to *find* raw sites for migration to a guard.
- **(c) Residuals — corrected. There is no runtime backstop for a miss.**
  | Residual class | Backstop | Status |
  |---|---|---|
  | Any scanner-missed SDK-chain form (inherited / class-body / cross-receiver / runtime-dispatch / container-subscript) | **NONE** — a direct SDK call bypasses the opt-in guards | **BLOCKING** |
  | Dynamically constructed direct HTTP (no static provider host) | **NONE** | **BLOCKING** |

  A `strict-xfail` may **document** a known static-analysis limit, but it **does not** make the form
  acceptable for approval. **`backstop=NONE` blocks APPROVE** (§11 Phase D). The only thing that clears
  these is the §10 boundary (or a genuinely non-bypassable SDK transport interception, which is the same
  isolation requirement).

## 4. Change 2 — Scanner implementation (builder; a lint/inventory aid)

- **Direct-HTTP → detect-by-argument (candidate).** Flag any `Call` with a provider URL resolvable in
  positional **or keyword** args or a nested `Request(...)`. `HTTP_VERBS` demoted to a metadata label.
- **Parsed, case-insensitive, exact host/subdomain** matching against the ratified provider registry
  (§7); malformed → fail closed.
- SDK-chain alias resolution stays; missed forms are `KNOWN_RESIDUAL` **and BLOCKING** (§3c) — not
  "non-fatal."
- Re-baseline the inventory into the **disposition ledger** (§7): every real-tree candidate gets an
  externally-ratified disposition; none silently ignored or benign-labeled by the builder.

## 5. Change 3 — Governance gate logic (builder; reads the bar externally)

- **Ratification-state gate.** `run_merge_gate` fails closed unless the ratified record (§8) is
  confirmed from the **protected baseline** — not the candidate manifest, not a CI variable.
  `owner-review-pending`/missing/unknown/builder-written "ratified" → exit 1. + mutation tests.
- **Content binding.** The gate verifies the candidate spec's criterion text, the provider registry,
  the disposition ledger, and the corpus against their **baseline-ratified digests** (§8). Any semantic
  change with a preserved ID → digest mismatch → red.
- **`run_id` removed** from the validator's security claim + manual interface; CI binds via same-run
  `needs.*.result` with a workflow-wiring test.

## 6. Change 4 — Independent frozen mutation corpus

`assurance/contract/egress_corpus.jsonl`, owner-owned via `protected-surface.txt` + CODEOWNERS, over:
HTTP method × import × alias × URL construction × host case × positional/keyword × nested `Request` ×
scope × inheritance × assignment order × runtime indirection.
- Builder **proposes**; an **independent reviewer seeds/verifies adversarial cases before** the digest
  is ratified (§11).
- Each case tagged `EXPECTED_DETECTED` or `KNOWN_RESIDUAL`; every `KNOWN_RESIDUAL` references a
  **machine-verifiable control ID** and an executable negative test, and **`backstop=NONE` blocks
  approval**. No case may be silently pruned or re-tagged (a sync test + the ratified digest enforce it).

## 7. Change 5 — Provider registry + candidate-disposition ledger (externally governed) — NEW (finding #2)

Two conservation-checked, externally-ratified, digested artifacts (owner-owned via protected-surface):
- **Provider-host registry** (`assurance/contract/provider_hosts.json`): the canonical set of provider
  hosts/subdomains. The scanner reads it (no hardcoded `PROVIDER_URL_MARKERS`). **Removing a provider
  fails the gate** (digest mismatch).
- **Candidate-disposition ledger** (`assurance/contract/egress_dispositions.jsonl`): every real-tree
  candidate, keyed by a **stable identity** (relpath::qualified-scope::kind::ordinal), with a
  **closed-set disposition** (`EGRESS_VIA_GUARD` / `EGRESS_BLOCKING` / `LOGGING` / `VALIDATION` /
  `CONFIG` / `TEST_FIXTURE`), an **evidence/reason**, a **control/backstop ID**, and an **owner**.
- **Exact scanner ↔ ledger conservation:** every scanner candidate appears in the ledger and vice
  versa. **Dropping a candidate, duplicating an identity, removing a provider, or reclassifying an
  egress site as benign fails the gate.** Benign dispositions are **owner-ratified**, never
  builder-chosen. A `disposition = EGRESS_BLOCKING` with no gateway backstop **blocks APPROVE**.

## 8. Change 6 — Canonical ratification record (fully specified) — NEW (finding #4)

`assurance/contract/ratification.json` on the protected baseline, schema-pinned. The record — and every
structured artifact it digests — is serialized with **one canonical encoding**: RFC 8785 JSON
Canonicalization Scheme (JCS) — UTF-8, lexicographically sorted object keys, no insignificant
whitespace, canonical number/string forms. Every digest below is SHA-256 over those canonical bytes.
- `spec_blob_sha256` — digest of the exact ratified `SPEC_WP12_bounded_redesign.md` file, byte-for-byte
  (no normalization; the whole blob carries the human-readable rationale).
- `criteria[]` — the load-bearing criteria are ratified as **canonical structured JSON objects, not
  Markdown prose**. Each entry is `{ id, statement, … }` carrying **plain-UTF-8 string / enum fields
  only** (no Markdown markup, no embedded formatting) — `statement` plus any enumerated attributes the
  criterion already defines. `criterion_sha256` is SHA-256 over the **JCS-canonical** bytes of that
  object. There is **no** "strip-Markdown-markup" step: stripping markup is parser-dependent and
  non-deterministic, so two implementers could digest the same criterion differently. The ratified unit
  is the structured JSON object itself — one canonical representation, no ambiguity.
- `provider_registry_sha256`, `corpus_sha256`, `disposition_ledger_sha256` — JCS-canonical digests of
  the §7 registry, the §6 corpus, and the §7 disposition ledger.
- `baseline_ref` — the **name** of the server-protected baseline ref the gate reads this record from.
  The record does **not** embed the SHA of the commit that contains it (a commit cannot digest itself,
  and the record must never point at its own baseline commit). The gate resolves *which* commit is the
  ratified tip **out-of-band** — from the server's branch-protection state for `baseline_ref` (§9), not
  from a SHA written inside the record and not from a CI variable. Integrity of *what* sits on that tip
  is bound by the content digests above, not by a self-referential commit pointer.
- `status` — a recognized enum; only `ratified` approves; `owner-review-pending`/unknown/missing → red.
- `supersedes[]` — a **retained/replaced mapping for every current WP12 control (WP12#1..#7)**: which
  old `SPEC_WP12_assurance_kernel.md` clause and old `owner-review-pending` manifest each new record
  replaces, so the old bar cannot be silently retained or re-presented.
Fail closed on: a semantic criterion edit, a missing record, an old manifest version, or a digest
substitution.

## 9. Change 7 — External ratification + bootstrap-before-ratification (owner) — amended (finding #3)

Branch protection is bootstrapped in **two stages**, because the three WP-12 status checks do **not yet
exist** at bootstrap — they are built in Phase B (§11). Requiring an unbuilt check either wedges every
PR on a required context that never reports, or reads as a vacuous "required" gate that never actually
runs. So existing checks are required first; the WP-12 checks are promoted to required only after they
exist and pass.

**Phase 0 — Stage 0a: bootstrap the structural authority with the checks that exist today, BEFORE any
ratification merge:**
1. Provision an **eligible non-author** human/team reviewer with **write** access.
2. Update `scripts/gen_codeowners.py` so CODEOWNERS is **not** solely the author (`@cryogenic22`);
   regenerate CODEOWNERS.
3. **Protect the actual baseline** (branch protection / ruleset), requiring **only checks that exist and
   can report today**: code-owner review by the non-author, the existing Lane-1
   `Conservation Gate (Lane 1 — deterministic)` check, require-branches-up-to-date, dismiss stale
   approvals, forbid self-approval/bypass. **Do not list the not-yet-built WP-12 checks as required** at
   this stage.
4. **Probe** enforcement with server-side API evidence (protection present; non-author owner eligible;
   the required-check set is exactly the existing checks — no phantom required context that never runs).
5. **Only then** may ratified artifacts be merged (Phase A).

**Stage 0b — promote the WP-12 checks to required, only after they exist and pass** (after Phase B,
§11): once the scanner / governance / registry-ledger conservation checks are implemented and have a
green run on the protected baseline, add exactly those three contexts to the required-check set. Until
that promotion, the WP-12 assurance floor is enforced by code-owner review — **not yet** by required
status checks; state that plainly rather than claiming a floor that is not wired.

**Single external source = the protected baseline branch** (versioned, auditable) — the gate reads
every ratified digest (§8) from there.

## 10. Change 8 — The genuine boundary + its executable acceptance contract — amended (findings #1, #5)

Static lint + opt-in guards cannot control direct/aliased/dynamic provider access. **A genuine
boundary:** provider credentials held **only** by a **separate gateway** (a distinct process/trust
domain) performing **authenticated, policy-enforcing** egress; the application processes have **no
provider credentials and no direct outbound path** to provider hosts and therefore **cannot bypass** it.
An in-process shared proxy is insufficient.

**It requires its own separately-ratified, executable acceptance contract** covering:
- all process classes — **web, worker, scheduler, operator/CLI**;
- **provider-secret absence** everywhere outside the gateway;
- **default-deny** direct provider egress (network policy);
- explicit **bypass vectors** — DNS/IP pinning, redirects, alternate HTTP clients, proxy env vars;
- gateway **authentication + PII policy + fail-closed** behavior;
- **negative runtime probes** demonstrating **zero** direct provider calls from each process class.

Until this contract passes, **`backstop=NONE` residuals remain BLOCKING and APPROVE is not permitted.**

## 11. Sequence (bootstrap → proposal-review → ratification → build → boundary → one dual review)

**Phase 0 — Bootstrap (owner, §9 Stage 0a):** non-author CODEOWNER + baseline protection requiring
**only the checks that exist today** (code-owner review + the Lane-1 conservation gate) + probe.
*Before* any ratification merge. The three WP-12 checks are **not** required yet — they do not exist
until Phase B, and are promoted to required in Stage 0b (step 8).

**Phase A — Proposal ratification (external):**
1. Amend this proposal *(this round)*; keep it on the spec-only branch off `da6887c` (not #327); push a
   new SHA.
2. **A&I reviews the proposal only** at the exact SHA.
3. The **independent reviewer seeds/verifies** the corpus, provider registry, and initial disposition
   ledger — these **exist before** any digest is taken.
4. Owner ratifies the **exact** spec **and** the exact digests of the seeded artifacts (§8).
5. The ratified record + artifacts **merge into the protected baseline** and are added to
   `protected-surface.txt` + regenerated CODEOWNERS.

**Phase B — Implementation (against the immutable bar):**
6. Rebase #327 onto the ratified baseline; builder implements the scanner (§4) + governance (§5) + the
   registry/ledger conservation checks (§7) in **one bounded commit**, **without editing the bar**.
7. Rerun the frozen corpus + focused suites + CI; reconcile/rebase #328.
8. **Stage 0b — promote branch protection (owner, §9):** now that the three WP-12 checks exist and have
   a green run on the protected baseline, add exactly those contexts to the required-check set. Only
   after this promotion is the WP-12 assurance floor enforced by required status checks, not just by
   code-owner review.

**Phase C — Migration:** migrate every `EGRESS_BLOCKING` ledger site to a guard (or eliminate it), so
the ledger has no builder-side raw-egress site outstanding.

**Phase D — The genuine boundary, then approval:**
9. Implement + **validate** the §10 boundary against its executable contract (negative probes prove zero
   direct provider calls). This is what actually clears the `backstop=NONE` BLOCKING residuals.
10. **Only then** does one fresh **dual** review run at the exact SHA against the frozen corpus; only
    then may the bot APPROVE. **No APPROVE while any `backstop=NONE` risk is open.**

## 12. Builder vs owner (authorship separation)

- **Builder:** detect-by-argument scanner, governance gate logic, registry/ledger conservation checks,
  corpus/registry/ledger cases *as proposals*, tests. Implements against an externally-ratified bar;
  never edits it to pass; never assigns a benign disposition or a `backstop` claim on its own.
- **Owner + independent reviewer:** bootstrap the structural authority (§9 Phase 0), seed/verify the
  corpus + registry + ledger before digest, ratify the record externally, own + authorize and ratify
  the §10 boundary contract, and grant final approval only after Phase D.
