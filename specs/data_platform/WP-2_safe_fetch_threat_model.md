# WP-2 — Safe-fetch & secret-boundary threat model (Phase B)

**Status:** Design activity. Spec-only — no runtime wiring, no executable tests in this branch.
**Baseline:** `claude/handoff/h0-baseline` @ `da6887c`, read-only.
**Date:** 2026-08-15
**Grounded in:** `WP-2_findings_reverification.md` (Phase A) — every "today" claim below is a
verified file:line finding from that record, not a restatement of the 2026-08-07 review.

**Ordering rule this document operates under** (COORDINATION §13.3, reconciled in Phase A §7):

> The safe-fetch threat model is the **first design activity**. Source identity and immutable
> contract foundations **may land first with execution disabled**. Safe fetch and secret
> resolution are **mandatory before any probe, preview or scheduled outbound request can execute**.

---

## 1. What changes about the threat model when WP-2 lands

Today every outbound request originates from **reviewed code**: a connector class in `connectors/`
with a hardcoded endpoint, merged through CODEOWNERS. The URL is a constant chosen by a developer.

WP-2 makes the endpoint **user-authored data** — a contract row (`source_onboarding.config`,
migration 099) written through a wizard or chat, then executed by the scheduler. That single change
moves the URL from the trusted side of the boundary to the untrusted side, and it is the entire
reason this document exists.

**The invariant this preserves** (COORDINATION §13.4): *AI may propose declarative contracts;
deterministic validators control network access, persistence and production promotion.* Every
control below is a deterministic validator. None may be satisfied by an LLM judgement, a
confidence score, or a reviewer's assurance.

## 2. Trust boundaries

| # | Boundary | Untrusted side | Trusted side |
|---|---|---|---|
| **B1** | Contract authoring | wizard input, chat-proposed contract, imported spec YAML | the validated, persisted contract row |
| **B2** | Contract execution | contract `config` (URL, path, headers, params) | the process making the request |
| **B3** | Egress | the resolved IP the request actually reaches | the application's network position (VPC, metadata service, DB, localhost) |
| **B4** | Secret material | contract body, DB row, git-tracked spec, logs, API responses, UI | the secret store |
| **B5** | Response ingestion | fetched bytes | the parser, pipeline, and LLM synthesis path |

Phase A established that **B2, B3 and B4 have no enforcement today** and B1 has partial enforcement
(three stripped keys). B5 is WP-5's Document IR scope and is out of scope here except where noted.

## 3. Assets

- **A1** — the application's network position: cloud metadata endpoints (`169.254.169.254`),
  internal services, the Postgres instance, `localhost` admin surfaces.
- **A2** — the server filesystem readable by the application user (`.env`, `DATABASE_URL`,
  `OPENAI_API_KEY`, key material, other tenants' uploads).
- **A3** — third-party credentials supplied for a source (`auth_token`, `api_key`, basic auth).
- **A4** — the integrity of ingested data (a poisoned source becomes facts).
- **A5** — availability of the ingestion runtime (a contract that never returns, or returns 40 GB).

## 4. Threats

Naming: **T-nn**. Each carries the *verified* current state from Phase A.

### 4.1 Network egress (SSRF family) — target A1

| ID | Threat | State today |
|---|---|---|
| **T-01** | Contract URL points at cloud metadata (`169.254.169.254`) → credential theft | **Open.** No allowlist/denylist; `connectors/base.py:284` `requests.get(url, …)` unrestricted |
| **T-02** | Contract URL points at private/loopback/link-local ranges → internal service access | **Open.** No `ipaddress` check anywhere in the connector tree |
| **T-03** | Non-HTTP scheme (`file://`, `gopher://`, `ftp://`) → local read / protocol smuggling | **Open.** No scheme validation on `RestConfig.url` (`:71`, only non-empty is checked at `:114-115`) |
| **T-04** | Public URL 302-redirects to a private address | **Open.** `requests` follows redirects by default; no re-validation per hop |
| **T-05** | DNS rebinding — hostname resolves public at validation, private at fetch (TOCTOU) | **Open.** No pinning; validation and fetch would resolve independently |
| **T-06** | Credentials attached to a redirect target — token leaks to an attacker host | **Open.** `_build_auth()` (`rest_connector.py:333-342`) sets headers once; `requests` forwards on same-host redirect |
| **T-07** | Pagination cursor/`next` URL from the *response body* drives the next fetch | **Open.** `rest_connector.py:428` reads `cursor_path` out of the payload; a hostile source controls the next request |

**T-07 is the subtle one and it is specific to this codebase.** The stuck-cursor guard added at
`:428` prevents an infinite loop but not a *redirection* — the cursor is attacker-influenced data
that feeds the next request. Any egress control that validates only the contract's declared URL and
not each derived request is bypassed by T-07.

### 4.2 Local file disclosure — target A2

| ID | Threat | State today |
|---|---|---|
| **T-08** | `CsvConfig.path` set to `/etc/passwd`, `.env`, or another tenant's upload | **Open.** `csv_connector.py:197-204` checks only `os.path.exists`, then `open()` |
| **T-09** | Path traversal / symlink escape from an intended upload root | **Open.** No canonicalization, no confinement root |
| **T-10** | Disclosed file content is ingested as records, then surfaced in chat answers | **Open.** Downstream of T-08; the pipeline treats it as any other source |

**T-10 is why this is not merely a read.** A disclosed secret does not stay in a log — it becomes
rows, embeddings, and eventually LLM context. The blast radius is the product surface, not the file.

### 4.3 Secret handling — target A3

| ID | Threat | State today |
|---|---|---|
| **T-11** | Credential persisted into `source_onboarding.config` | **Partially mitigated.** `_strip_secret_config()` (`connector_taxonomy.py:356-366`) removes exactly `auth_token`, `auth_password`, `api_key` |
| **T-12** | Credential persisted via a **nested** field (`headers.Authorization`, `query_params.api_key`) | **Open — reproduced in Phase A.** Only top-level keys are examined |
| **T-13** | Credential persisted in **URL userinfo** (`https://user:pass@host/`) | **Open — reproduced.** `url` is not parsed at all |
| **T-14** | Credential under an **unrecognised key** (`auth_secret`, `token`, `x_api_key`) | **Open — reproduced.** The strip list is a closed 3-tuple |
| **T-15** | Credential echoed into logs / error messages / the catalog UI | **Open.** e.g. `rest_connector.py:362,366,371` interpolate `config.url` — which may carry userinfo (T-13) — into `ConnectorError` messages |
| **T-16** | Credential committed to git via a spec file | **Open by the same mechanism** — `connectors/spec.py` serializes `config`; the strip list is the only defense |

**The structural point:** T-12 → T-16 are all the same defect — *a denylist of three names standing
in for a type system.* No `credential_ref` model exists, so there is nothing that makes a secret
*unrepresentable* in a persisted contract. That is the fix, not a longer denylist.

### 4.4 Resource & integrity — targets A4, A5

| ID | Threat | State today |
|---|---|---|
| **T-17** | Response body unbounded (decompression bomb, 40 GB CSV) | **Open.** `fetch()` accumulates a full `list[RawRecord]` in memory (Phase A, G-10) |
| **T-18** | Slowloris / never-returning source occupies the scheduler | **Partial.** `timeout=getattr(self, "timeout", 30)` is per-request, not per-run; no lease exists to bound a run (G-10) |
| **T-19** | Hostile source poisons facts (A4) | Out of scope here — WP-8 quality-as-gate + trust_tier (099) |
| **T-20** | Fetched content reaches LLM synthesis as instructions, not data | Out of scope here — WP-5 untrusted-content handling; **noted as a dependency** |

## 5. Controls (the deterministic validators)

Each control is stated so a test can falsify it. **C-nn ↔ T-nn** mapping in §6.

### 5.1 Egress

- **C-01 — Scheme allowlist.** Only `https` (and `http` only for an explicitly flagged internal
  contract). Enforced at contract validation *and* at fetch.
- **C-02 — Resolve-then-validate-then-pin.** Resolve the hostname, reject any answer in
  private / loopback / link-local / unique-local / multicast / reserved ranges, then **connect to
  the validated IP** (host header preserved). This is the only defense that closes T-05; a
  hostname-string check does not.
- **C-03 — Per-hop revalidation.** Redirects disabled by default; if a contract opts in, every hop
  re-runs C-01 + C-02, with a hop cap.
- **C-04 — Credentials never survive a host change.** Auth headers are bound to the validated host;
  a cross-host redirect drops them and fails the run.
- **C-05 — Derived requests are requests.** Every URL built from response data (T-07 cursors,
  `next` links) passes C-01 + C-02 + C-04. No "the contract was validated once" shortcut.
- **C-06 — Single choke point.** All of the above live in **one** fetch primitive that
  `connectors/base.py` uses, so a new connector cannot opt out by calling `requests` directly. A
  Lane-1 gate greps the connector tree for direct `requests.`/`urllib`/`httpx` use.
- **C-07 — Optional egress allowlist per contract.** A deployed contract declares its hosts; the
  deployed *version* pins them, so a later contract edit cannot silently widen egress without a new
  version + approval.

### 5.2 Local files

- **C-08 — Remove local-path fetch from user-authored contracts entirely.** A wizard/chat contract
  may not set `CsvConfig.path`. Uploads arrive through the existing upload path with an
  application-owned identifier, never a server path.
- **C-09 — If a path is retained for operator-authored specs**, confine it: canonicalize with
  `realpath`, require containment inside a configured root, reject symlinks crossing the root.
  Default-deny when the root is unset.

### 5.3 Secrets

- **C-10 — `credential_ref`, not credentials.** The contract carries a *reference*
  (`{"credential_ref": "src/<source_instance_id>/token"}`). The config dataclasses lose their
  plaintext `auth_token` / `auth_password` / `api_key` fields; a runtime resolver injects the value
  at request time and it never enters the contract object graph.
- **C-11 — Persistence is allowlist-shaped, not denylist-shaped.** The persisted contract is built
  by *projecting declared, non-secret fields*, so an unknown key (T-14) is dropped by construction
  rather than by name matching.
- **C-12 — Reject, don't strip, at the boundary.** A contract submitted with inline credentials is
  **rejected with a diagnostic**, not silently cleaned. Silent stripping teaches authors that inline
  secrets work, and it is exactly how T-12/T-13 hid behind a passing test.
- **C-13 — URL userinfo is a validation error** (T-13), checked by parsing, not substring search.
- **C-14 — Redaction at every egress of the *contract itself*:** logs, `ConnectorError` messages,
  API responses, catalog UI. One redaction helper, applied at the boundary.

### 5.4 Resource

- **C-15 — Byte cap + decompressed-size cap + per-run wall clock**, all contract-declared with a
  hard ceiling. Exceeding a cap is a **terminal run outcome**, not a warning — consistent with the
  Phase A truncation finding (a detected condition must reach the outcome).

## 6. Threat → control coverage

| Threat | Controls | Residual |
|---|---|---|
| T-01, T-02 | C-02, C-07 | egress via an allowlisted host that itself proxies (accepted; contract-version-gated) |
| T-03 | C-01 | — |
| T-04 | C-03 | — |
| T-05 | C-02 (pinning) | — |
| T-06 | C-04 | — |
| T-07 | C-05 | — |
| T-08, T-09, T-10 | C-08, C-09 | operator-authored specs remain trusted input (explicit) |
| T-11…T-14 | C-10, C-11, C-12, C-13 | a resolver-side compromise still yields the secret (out of scope) |
| T-15, T-16 | C-14, C-11 | — |
| T-17, T-18 | C-15 | streaming ingestion proper is WP-9 |
| T-19, T-20 | — | **explicitly deferred** to WP-8 / WP-5; recorded so they are not assumed covered |

**No silent caps:** T-19 and T-20 are named and unaddressed here on purpose. A threat model that
quietly omits them would read as coverage.

## 7. Test specifications (Phase C artifacts — NOT executable in this branch)

Per COORDINATION §13.3, this branch ships *specifications and fixtures*; executable RED tests are
introduced inside the implementation PR that makes them GREEN.

**Mutation cases** — each must be RED before the control lands:

1. Contract with `url: http://169.254.169.254/latest/meta-data/` → rejected at validation (C-02).
2. Contract with `url: file:///etc/passwd` → rejected (C-01).
3. Public hostname whose DNS answer is `127.0.0.1` → rejected at resolve, and the connection is
   made to the validated IP (C-02). Asserted with a stubbed resolver, no live DNS.
4. 302 from an allowlisted host to `http://10.0.0.5/` → run fails; **no** request is issued to the
   private address (C-03).
5. Cross-host redirect → `Authorization` header absent on hop 2 (C-04).
6. Response body supplies a cursor that is an absolute URL to a private host → rejected (C-05).
7. A new connector calling `requests.get` directly → the choke-point gate is RED (C-06).
8. `CsvConfig.path` present on a wizard-authored contract → rejected (C-08); a path escaping the
   root via symlink → rejected (C-09).
9. **The Phase A probe, inverted into a gate:** the exact config that survived stripping
   (`headers.Authorization`, `query_params.api_key`, URL userinfo, `auth_secret`) must now be
   **rejected**, and nothing credential-shaped may appear in the persisted projection (C-11…C-13).
10. `ConnectorError` message for a userinfo URL contains no credential (C-14).
11. Oversized / over-long response → terminal outcome recorded on the run, not a log line (C-15).

**Golden fixtures:** a valid minimal REST contract; a valid CSV upload-backed contract; and one
rejected fixture per mutation case above, each with its expected diagnostic code.

**Conservation cases:** rejecting a contract must not delete or mutate a previously deployed
contract version; a failed validation leaves the last-good deployed version serving.

## 8. Dependencies and sequencing consequences

- **Blocks execution, not authorship.** Per the §13.3 rule, source identity + immutable versioned
  contracts (evolving migration 099, `list_runnable_sources`, `build_connector_from_spec` — Phase A
  §1.1) may land **with execution disabled**. The scheduler consumer that today does not exist is
  precisely the thing that must not be wired until C-01…C-15 are green.
- **Shares outcome vocabulary with WP-0.** C-15 and the Phase A truncation finding both require a
  detected condition to reach the terminal run outcome. WP-2 must not invent a second outcome
  enum — it extends `classify_run_outcome`.
- **WP-5 dependency recorded:** T-20 (fetched content reaching synthesis as instructions) is not
  closed by anything here.
- **New hard gates ⇒ protected surface.** C-06's choke-point gate and the credential-projection
  gate are success-definition surfaces; when either becomes HARD it is added to
  `protected-surface.txt` with CODEOWNERS regenerated in the same change (CLAUDE.md), and its
  acceptance criteria are owner-ratified before implementation, never self-authored.
