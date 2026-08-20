# WP-12 Egress Assurance — Bounded Redesign

**Status: PROPOSAL — pending independent (A&I) proposal-review + external owner ratification.** This
supersedes the completeness-claiming approach in `SPEC_WP12_assurance_kernel.md` §WP12#3. Nothing here
is a ratified bar until the *externally-ratified* version lands on the protected baseline (§7) —
writing a status string on a candidate branch is **not** ratification.

## 0. Correction log

**Round 1 (five findings) — over-claim of the runtime boundary and self-certification:**

| # | Correction | Where |
|---|---|---|
| 1 | Runtime backstop is **only** the enumerated SDK `.create()` wrap; raw/dynamic direct HTTP is **not** backstopped and stays **BLOCKING** until a real network/credential boundary exists | §2, §3(c), §8 |
| 2 | Detect-by-argument is **candidate** detection; precise rule (kw args, nested `Request`, **parsed** case-insensitive **exact host/subdomain** not substring, `+`/`%`/`.format`/f-string, malformed→fail-closed); every candidate gets an explicit disposition | §3(a), §4 |
| 3 | Ratification moves **outside** the candidate branch — from an owner-controlled external source | §5, §7 |
| 4 | The frozen corpus is **independent** — reviewer seeds/verifies adversarial cases; each residual names its **actual** backstop | §6 |
| 5 | `run_id` removed from the validator's security claim + manual interface | §5 |

**Round 2 (three sequencing contradictions + boundary precision):**

| # | Correction | Where |
|---|---|---|
| 6 | A known **BLOCKING** risk cannot coexist with APPROVE — the network/credential boundary must be **implemented and validated before final approval**, not after | §8, §9 (Phase C) |
| 7 | The sequence must **seed/verify the corpus before ratifying its digest** (a digest of a non-existent corpus is meaningless) | §9 (Phase A) |
| 8 | **One** external ratification source: the **protected baseline branch** (versioned, auditable) — **not** a mutable CI variable | §5, §7 |
| 9 | The genuine boundary is defined precisely: a **separate gateway** holding provider credentials with authenticated/policy-enforcing egress the **application process cannot bypass**; a proxy shared by the same process is insufficient | §8 |

## 1. Why the loop happened (root cause)

A hand-written AST matcher **cannot** satisfy "closes every statically-resolvable egress form" — the
form space (HTTP verb × import × alias × URL construction × host case × arg position × nested Request
× scope × inheritance × assignment order × runtime indirection) is unbounded, so an adversarial
mutation reviewer always finds the next form and one-fix-per-example never converges. Compounding it:
the manifest can approve while `owner-review-pending`, criterion parity checks only IDs/headings, and
nothing is server-enforced — the system tries to certify its own authority.

## 2. Principle — put each guarantee where it can actually be held

| Layer | What it actually does today | Guarantee it can hold |
|---|---|---|
| **In-process SDK wrap (#328)** | Wraps the **enumerated** OpenAI/Anthropic SDK `.create()` calls in-process | Backstops **SDK-chain** forms only. **Not** a network boundary: it does **not** see raw `requests`/`httpx`/`urllib`. |
| **Static scanner (#327)** | AST inventory + lint | Best-effort **candidate** detection over an enumerated corpus + the by-argument rule. **Not** completeness, **not** enforcement. |
| **A genuine network/credential boundary (§8)** | **Does not exist yet** | The *only* complete egress control. |
| **Acceptance manifest** | The bar | Approves only when **externally** owner-ratified (protected baseline), bound to criterion **content**, server-enforced. |

**Honest consequence:** with only #327 (static lint) + #328 (in-process SDK wrap), **dynamically
constructed direct HTTP has no complete control** — a disclosed **BLOCKING** risk (§8) that must be
closed **before** the kernel can be approved (§9 Phase C).

## 3. Change 1 — Re-scope WP12#3 (THE BAR — externally owner-ratified, not self-certified)

**Old (unsound):** "the scanner closes every statically-resolvable egress form."

**New (bounded, honest):**

- **(a) Direct provider HTTP/urllib — CANDIDATE detection by argument.** Flag any call that passes a
  statically-resolvable provider URL as a **candidate** egress site. "Candidate," not "proven egress":
  it will also flag `logger.info("https://api.openai.com")` / `validate_url(...)`. Acceptable for a
  conservative inventory, but **every candidate needs an explicit disposition — nothing silently
  ignored.** The rule must cover:
  - positional **and keyword** arguments;
  - a provider URL nested inside a `Request(...)` argument;
  - the URL **parsed**, hostname compared **case-insensitively**;
  - **exact host / subdomain** matching (`host == provider` or `host.endswith("." + provider)`), **not**
    substring;
  - URLs built via `+`, `%`, `.format()`, f-strings (static prefix decisive);
  - **malformed / ambiguous URLs fail closed** (flagged, never dropped).
- **(b) SDK-chain calls** — best-effort AST alias resolution, backstopped in-process by #328's
  `.create` wrap; residuals here are non-fatal (backstop named per case, §6).
- **(c) Residuals — each names its ACTUAL backstop:**
  | Residual class | Backstop | Status |
  |---|---|---|
  | Inherited / class-body / cross-receiver SDK-chain alias (terminal is still `.create`) | #328 in-process SDK wrap | documented `strict-xfail` |
  | Runtime dispatch / container-subscript indirection terminating in SDK `.create` | #328 in-process SDK wrap | documented `strict-xfail` |
  | **Dynamically constructed direct HTTP** (no static provider host resolvable) | **NONE** | **BLOCKING** — closed only by §8; blocks APPROVE (§9 Phase C) |

## 4. Change 2 — Scanner implementation (builder)

- **Direct-HTTP → detect-by-argument (candidate).** Flag any `Call` with a provider URL resolvable in
  its positional **or keyword** args, or in a nested `Request(...)`. `HTTP_VERBS` demoted to a metadata
  label, not the detection gate — closing all-verbs / uppercase host / `urlopen`-alias /
  imported-renamed-verb in one rule.
- **Parsed, case-insensitive, exact host/subdomain** matching (replace the substring
  `_is_provider_url`). Malformed URL → fail closed (candidate).
- **SDK-chain** alias resolution stays; inherited / class-body / order residuals become documented
  `strict-xfail` (backstop named per §3(c)).
- Re-baseline the pinned inventory; each new real-tree candidate gets an explicit disposition
  (egress vs logging/validation/config), recorded — none silently ignored.

## 5. Change 3 — Governance hardening (builder gate logic; ratification is external)

- **Ratification-state gate (fixes BLOCK #2).** `run_merge_gate` **fails closed** unless the ratified
  status/digest is confirmed from the **protected baseline branch** (§7) — *not* the candidate
  branch's manifest, *not* a mutable CI variable. `owner-review-pending` / missing / unknown /
  builder-written "ratified" → exit 1. + mutation tests proving each cannot exit 0.
- **Criterion-meaning binding (fixes BLOCK #3).** Each criterion carries a normalized-text **digest**;
  the gate verifies the candidate spec's criterion text against the **baseline-ratified** digest.
  Meaning changed while ID preserved → mismatch → red. + a meaning-change mutation test.
- **`run_id` removed (fixes BLOCK #5).** Dropped from the validator's security claim and the manual
  `--merge-gate` interface. CI binds gate conclusions via same-run `needs.*.result`; a workflow-wiring
  test asserts that binding directly.

## 6. Change 4 — Independent frozen mutation corpus (owner owns; reviewer seeds; builder implements against)

A frozen corpus (`assurance/contract/egress_corpus.jsonl`), **owner-owned** via `protected-surface.txt`
+ CODEOWNERS, enumerating:

> HTTP method × import form × alias form × URL construction × host case ×
> positional/keyword × nested `Request` × scope × inheritance × assignment order × runtime indirection

- The **builder proposes** cases but does **not solely choose** the initial set; an **independent
  reviewer seeds/verifies adversarial cases** — and this happens **before** the corpus digest is
  ratified (§9 Phase A).
- Each case is tagged `EXPECTED_DETECTED` or `KNOWN_RESIDUAL`; every residual **names its actual
  backstop** (§3(c)). **Dynamic direct HTTP may not be tagged runtime-backstopped.**
- The builder may add implementation but **cannot silently prune or re-tag** a case — a sync test
  fails on corpus↔scanner drift, and the corpus digest is checked against the baseline-ratified one.

## 7. Change 5 — External ratification (single source) + owner enforcement (owner only)

The bar lives where the builder cannot write it, and there is **one** such place:

- **Single external source = the protected baseline branch** — versioned and auditable (not a mutable
  CI variable). The gate reads the ratified spec + corpus digest from the baseline.
- **Two-stage landing.** (1) The ratified spec + frozen corpus + their digests are merged into the
  **protected baseline** (owner merges, CODEOWNERS-reviewed) and added to `protected-surface.txt` +
  regenerated CODEOWNERS. (2) The builder rebases onto that immutable bar and implements without
  editing it.
- **Native enforcement (fixes BLOCK #4 / WP12#7).** A non-author human/team CODEOWNER with **write**
  access; require code-owner approval + the three WP-12 checks on the protected branch; dismiss stale
  approvals; forbid self-approval/bypass; protect the actual landing branch.

## 8. The genuine boundary (precise; a prerequisite to APPROVE)

Static lint + in-process SDK wrapping **cannot** close dynamically-constructed direct HTTP: a function
in the same process can construct any URL at runtime and call `requests`/`urllib` directly, with
nothing intercepting it. An ordinary proxy *shared by the same process* is **insufficient** — the
process could bypass it.

**A genuine boundary means:** provider credentials are held **only** by a **separate gateway**
(a distinct process / trust domain), which performs **authenticated, policy-enforcing** egress, and
the application process has **no provider credentials and no direct outbound network path** to provider
hosts — so it **cannot bypass** the gateway. Only then is dynamic direct HTTP actually controlled.

**Consequence for approval:** a known BLOCKING risk cannot coexist with APPROVE. The boundary must be
**implemented and validated** (dynamic direct HTTP demonstrably un-bypassable) **before** the kernel's
final dual review and bot APPROVE (§9 Phase C). Building it is a separate owner/devops workstream that
this spec **names** rather than pretends away.

## 9. Sequence (proposal-review → external ratification → bounded build → boundary → one dual review)

**Phase A — Proposal ratification (external, on the protected baseline):**
1. Amend this proposal with the §0 corrections *(done)*.
2. Commit **only** this proposal to a **dedicated spec-only branch off `da6887c`** (not #327); push,
   open a spec-only PR, provide the exact SHA.
3. **A&I reviews the proposal only**, against that SHA.
4. The **independent reviewer seeds/verifies** the initial frozen corpus (adversarial cases) — the
   corpus exists **before** any digest is taken.
5. Owner ratifies the **exact** spec **and** the **exact digest of the seeded corpus**.
6. The ratified spec + corpus + digests **merge into the protected baseline**; added to
   `protected-surface.txt` + regenerated CODEOWNERS. Owner protects the baseline + adds a non-author
   CODEOWNER (§7).

**Phase B — Implementation (against the immutable bar):**
7. Rebase #327 onto the ratified baseline; builder implements the scanner (§4) + governance (§5) in
   **one bounded commit**, **without editing the bar**; the gate reads the ratified digest from the
   baseline.
8. Rerun the frozen corpus + focused suites + CI on the new SHA.
9. Reconcile / rebase #328.

**Phase C — The genuine boundary, then approval:**
10. Implement + **validate** the network/credential boundary (§8) so dynamic direct HTTP is
    demonstrably un-bypassable — the BLOCKING risk is closed.
11. **Only then** does one fresh **dual** review run at the exact SHA against the frozen corpus; and
    only then may the bot APPROVE. No APPROVE while the §8 risk is open.

## 10. Builder vs owner (authorship separation)

- **Builder:** detect-by-argument scanner, governance gate logic, corpus cases *as proposals*, tests.
  Implements against an externally-ratified bar; never edits it to pass.
- **Owner + independent reviewer:** ratify the re-scoped claim externally (protected baseline), seed
  and verify the corpus before digest, ratify the manifest digests, configure branch protection, and
  own + authorize the §8 network/credential-boundary workstream.
