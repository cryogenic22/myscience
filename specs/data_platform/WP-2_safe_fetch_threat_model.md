# WP-2 — Safe-fetch & secret-boundary threat model (Phase B)

**Status:** Design activity, **revision C.4**. Spec-only — no runtime wiring, no executable tests
in this branch.
**Baseline:** `claude/handoff/h0-baseline` @ `da6887c`, read-only.
**Date:** 2026-08-15

### Revision log

| Rev | Change | Cause |
|---|---|---|
| C.1 | **T-07 corrected** — the response cursor does *not* drive the next request's origin; it is a query parameter on the configured URL. Re-scoped to T-07a/b/c. | Independent review; verified at `rest_connector.py:386-397` |
| C.1 | **C-06 re-scoped** — a blanket grep of `connectors/` would be RED against 23 of 30 modules at the baseline. Replaced with a hard gate for contract-driven connectors plus a shrink-only allowlist for the bespoke fleet. | Independent review; verified by grep |
| C.1 | **C-02 extended** — TLS SNI/hostname verification under IP pinning, actual-peer verification, all DNS answers, IPv4-mapped IPv6, environment proxies. | Independent review |
| C.1 | **C-03/C-04 tightened** — cross-origin redirect terminates the run; auth binding covers header, API-key header *and* API-key query param. | Contract/mutation-case mismatch |
| C.1 | **C-11/C-12 reconciled** — reject at admission, project at persistence, in that order. | The two rules read as contradictory |
| **C.2** | **C-10 rewritten** — it still mandated `credential_ref` after C.1 replaced that model with `FetchGrant` + credential slots in the control-plane spec. | Independent review: the two documents contradicted each other |
| **C.2** | **C-10a added** — query-placed credentials forbidden by default; under an owner-approved exception the value is **excluded, not hashed**, from every persisted artefact. | Independent review: "secrets never enter URLs" contradicted both `RestConfig.api_key_param` and the proposed value-hashing |
| **C.3** | **"ships fixtures" corrected to fixture *designs*** (§7) | Contradicted the test spec, which correctly says none exist |
| **C.4** | **Safe-fetch variants given stable IDs `SF-02a`…`SF-06a`** so the protected manifest enumerates variants | A control-keyed manifest would let 7 of 8 vanish while green |
| **C.3** | **8 new C-02/C-06 mutation cases** — mixed DNS answers, IPv4-mapped IPv6, SNI/cert-hostname mismatch, peer verification, env proxy, same-size allowlist substitution, exception/grant expiry, alternate HTTP stacks (`http.client`, `Session`) | The C.2 set tested the happy path; several control clauses had no failing case |

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
| **T-07** | Response-supplied pagination cursor influences the next request | **Open, but NOT as an SSRF vector — see the correction below** |

### T-07 — corrected in revision C.1

**The first version of this document was wrong.** It claimed the response-body cursor "drives the
next fetch" and could redirect the request to an attacker-chosen host. Re-read at
`connectors/rest_connector.py:386-397`, the loop always fetches **`cfg.url`** — the contract's
configured URL — and places the cursor in a *query parameter*:

```python
elif cfg.pagination == "cursor" and cursor is not None:
    params[cfg.cursor_param] = cursor
resp = self._fetch_with_retry(cfg.url, params=params)
```

So a hostile cursor **cannot change the origin**. The host never varies within a REST fetch loop.
The residual threat is real but smaller and differently shaped:

- **T-07a — parameter injection.** A hostile cursor value is echoed back into the next request's
  query string, where it may alter server-side query semantics, widen a result set, or carry an
  injection payload to the upstream API.
- **T-07b — poisoned pagination.** A source can drive duplicate or unbounded page traversal within
  `max_pages`. The stuck-cursor guard at `:428` catches only the *identical-cursor* case; an
  alternating or cycling cursor defeats it.
- **T-07c — a future next-URL adapter.** If a later connector kind takes an absolute `next` link
  from the payload (a common REST idiom, and one this contract model would permit), the original
  SSRF framing becomes correct. The control must therefore exist **before** such an adapter, not
  after.

**Consequence for the controls:** C-05 stays, but its justification changes — it is a *forward*
guard for T-07c and a typing/bounding guard for T-07a/b, not a fix for a live SSRF hole. The
corresponding mutation case is rewritten in the test specification: a hostile-next-URL case cannot
reproduce a current failure and must not be presented as if it does.

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
- **C-02 — Resolve-then-validate-then-pin.** Resolve the hostname, reject **every** returned
  address (not just the first) in private / loopback / link-local / unique-local / multicast /
  reserved ranges **including IPv4-mapped IPv6 forms**, then **connect to the validated IP**. This
  is the only defense that closes T-05; a hostname-string check does not. Pinning has consequences
  the first revision omitted and which the implementation must specify:
  - **TLS must still verify against the *hostname*,** not the pinned IP — set SNI and the
    certificate-verification hostname explicitly, or pinning silently degrades TLS.
  - **Verify the actual peer** after connect; a connection-level assertion, not a pre-flight one.
  - **Environment proxies (`HTTP_PROXY`/`HTTPS_PROXY`/`NO_PROXY`) must be disabled or explicitly
    allowlisted** — a proxy makes the pinned IP meaningless because the proxy re-resolves.
- **C-03 — Per-hop revalidation.** Redirects disabled by default; if a contract opts in, every hop
  re-runs C-01 + C-02, with a hop cap. **A cross-origin redirect terminates the run with
  `egress_refused` — it is not followed with credentials stripped.** (The first revision's
  contract text said "fail" while its mutation case only asserted header removal; the contract is
  authoritative and the case is rewritten to match.)
- **C-04 — Credentials never survive an origin change.** Auth material is bound to the validated
  origin. This covers **every** auth placement, not just `Authorization`: bearer headers, arbitrary
  API-key headers (`api_key_header`), **and query-parameter keys** (`api_key_param`) — all three
  exist in `RestConfig` today (`connectors/rest_connector.py:88-95`).
- **C-05 — Derived requests are requests.** Every request whose URL, origin, or parameters derive
  from response data re-runs C-01 + C-02 + C-04, and cursor values are type- and length-bounded
  before being echoed into a query string (T-07a/b). Forward-guards T-07c.
- **C-06 — Single choke point, scoped honestly.** All of the above live in **one** fetch primitive.
  **The first revision specified a blanket Lane-1 grep of `connectors/` for direct
  `requests.`/`httpx`/`urlopen` use. That gate would be RED against the baseline: 23 of the 30
  connector modules make direct HTTP calls today.** A gate that is red on day one gets weakened or
  excluded — the exact failure this harness exists to prevent. Corrected scope:
  - the gate is **hard** for contract-driven connectors (the generic Rest/Csv/Rss adapters, the
    fetch primitive, and any new connector);
  - the 23 bespoke modules sit on an **explicit, enumerated, expiring allowlist** with a named
    owner, and the gate asserts the allowlist **only shrinks** — a monotonic ratchet, the same
    shape as `ORPHAN_CEILINGS`;
  - adding a file to the allowlist is a protected-surface change routed through the owner.
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

- **C-10 — credential *slots* bound by a grant; not a `credential_ref` locator.**
  **Corrected in C.2.** C.1 replaced `credential_ref` with a `FetchGrant` in the control-plane spec
  but left this control still mandating `credential_ref` — the two documents contradicted each
  other. There is one model:
  - the contract declares a **slot** — `{"slot": "primary_token", "placement": "header:Authorization"}`
    — a name and a placement, never a value and never a store locator;
  - a **`FetchGrant`** (control-plane spec §7) binds that slot to a specific credential *version*
    and permits exactly one placement;
  - the config dataclasses lose their plaintext `auth_token` / `auth_password` / `api_key` fields
    entirely, so the contract grammar has no field capable of holding a secret.

  A locator was insufficient because it named *where* a secret lives without binding *who* may
  resolve it, *for which origin*, or *until when*.

- **C-10a — query-placed credentials: forbidden by default, never persisted, never hashed.**
  **New in C.2.** C.1 asserted "resolved secrets never enter URLs" while `RestConfig.api_key_param`
  exists and the control-plane spec proposed persisting a *hash* of query-parameter values. Both
  contradicted the rule. Resolved:
  1. `placement: query:<name>` is **rejected by default** (`CREDENTIAL_PLACEMENT_FORBIDDEN`);
     header placement is the only default-permitted binding.
  2. Where an upstream genuinely offers no header auth, the contract must carry an explicit
     owner-approved `query_credential_exception` naming the parameter and the reason — recorded on
     the protected surface, never self-granted.
  3. Under that exception the secret exists **only in the in-flight request**. It is excluded —
     **not hashed** — from every persisted or emitted artefact: `etl_runs`, `source_acquisitions`,
     `source_stream_executions`, `control_plane_events`, logs, errors, API responses, catalog
     payloads.
  4. **A hash of a credential is still a credential artefact.** Low-entropy or structured tokens are
     offline-recoverable from a hash, so value-hashing is permitted only for
     **non-credential-bound** parameters. A credential-bound parameter persists as its *name* plus
     the literal marker `REDACTED:credential`, with no value-derived material of any kind.

  Honest residual: an upstream requiring query auth will see the secret in *its own* access logs.
  That is outside our boundary, and is a reason to prefer a header-auth source — recorded as a
  certification consideration rather than silently accepted.
- **C-11 / C-12 — Reject at admission; project at persistence. In that order.** The first revision
  stated these as competing rules ("dropped by construction" vs "reject, don't strip"); they are
  one ordered pair:
  1. **Validation rejects** — an unknown field, an inline credential, or URL userinfo returns a
     typed diagnostic and the contract is **not stored**. Silent cleaning teaches authors that
     inline secrets work, and is exactly how T-12/T-13 hid behind a passing test.
  2. **Persistence projects** — the stored row is then built by copying *declared, non-secret*
     fields only. This is defence in depth: if validation is ever bypassed or a new field is added
     to a config dataclass without a validator update, the undeclared value still cannot reach
     storage.

  Both are required. Rejection is the user-visible contract; projection is the containment.
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
| T-11…T-14 | C-10, C-10a, C-11, C-12, C-13 | a resolver-side compromise still yields the secret (out of scope); an upstream's own logs under a query-auth exception (C-10a residual) |
| T-15, T-16 | C-14, C-11 | — |
| T-17, T-18 | C-15 | streaming ingestion proper is WP-9 |
| T-19, T-20 | — | **explicitly deferred** to WP-8 / WP-5; recorded so they are not assumed covered |

**No silent caps:** T-19 and T-20 are named and unaddressed here on purpose. A threat model that
quietly omits them would read as coverage.

## 7. Test specifications (Phase C artifacts — NOT executable in this branch)

Per COORDINATION §13.3, this branch ships **specifications and fixture *designs*** — **no fixture
files and no executable tests exist in this branch** (C.3 correction: the earlier wording said the
branch ships fixtures, contradicting the test specification, which correctly says none exist).
Executable tests and their fixtures are introduced inside the implementation PR that makes them
GREEN.

**Mutation cases** — each must be RED before the control lands:

1. Contract with `url: http://169.254.169.254/latest/meta-data/` → rejected at validation (C-02).
2. Contract with `url: file:///etc/passwd` → rejected (C-01).
3. Public hostname whose DNS answer is `127.0.0.1` → rejected at resolve, and the connection is
   made to the validated IP (C-02). Asserted with a stubbed resolver, no live DNS.
4. 302 from an allowlisted host to `http://10.0.0.5/` → run terminates with `egress_refused`;
   **no** request is issued to the private address, and no hop-2 request is made at all (C-03).
5. Cross-origin redirect → the run **fails**; assert no second request was issued, *and*
   separately assert that no auth material (bearer header, API-key header, **or API-key query
   param**) is present on any attempted follow-up (C-04, all three placements).
6. **Rewritten in C.1** — the original case ("cursor is an absolute URL to a private host") cannot
   reproduce a current failure, because the REST loop always fetches `cfg.url` and puts the cursor
   in a query param (`rest_connector.py:386-397`). Replaced by three honest cases:
   6a. an over-long / wrong-typed cursor value → rejected before it is echoed into the query
       string (T-07a);
   6b. an alternating two-value cursor cycle → bounded and reported as truncation, not looped
       (T-07b — the existing identical-cursor guard does not catch this);
   6c. a *hypothetical* next-URL adapter fed an absolute private-host link → rejected by C-05.
       Marked explicitly as a **forward guard for T-07c**, not a live-defect reproduction.
7. A **contract-driven** connector calling `requests.get` directly → the choke-point gate is RED.
   Separately: the bespoke allowlist grows by one entry → RED (monotonic-ratchet assertion). The
   gate is **not** a blanket grep of `connectors/`, which would be red against 23 of 30 modules at
   the baseline (C-06).

**C-02 / C-06 mutation gaps closed in C.3; given stable IDs in C.4** so the protected case
manifest (test spec M-40) can enumerate *variants* rather than controls — a manifest keyed on
controls would let seven of these eight vanish while the gate stayed green.

**Original wording:** The C.2 set tested the happy path of pinning and one
bypass of the choke point. Each control clause now has a case that can fail:

**SF-02a.** **Mixed DNS answers** — a hostname resolving to one public and one private address. RED: *every*
    answer is validated, not the first (C.2 asserted this in prose only).
**SF-02b.** **IPv4-mapped IPv6** — `::ffff:169.254.169.254` and `::ffff:10.0.0.1`. RED.
**SF-02c.** **SNI / certificate-hostname mismatch under pinning** — connect to the pinned IP with TLS
    verification still bound to the hostname; a certificate valid for the *IP* but not the host
    must fail. This is the clause most likely to be silently dropped when pinning is implemented.
**SF-02d.** **Peer verification** — assert the connected peer *is* the validated IP, not merely that
    validation ran before connecting (the TOCTOU that pinning exists to close).
**SF-02e.** **Environment proxy** — set `HTTPS_PROXY`; the pinned address must not be silently re-resolved
    by a proxy. RED unless the proxy is explicitly allowlisted.
**SF-07a.** **Same-size allowlist substitution** — replace an allowlisted origin with a different one,
    keeping the array length identical. RED — a length or count assertion is not a set assertion.
**SF-07b.** **Allowlist / exception expiry** — a `query_credential_exception` past `effective_to`, and a
    grant past `expires_at`. RED at the request boundary.
**SF-06a.** **Alternate HTTP stacks** — the same bypass attempted via `httpx`, `urllib.request.urlopen`,
    `http.client`, and a `requests.Session`. All RED for contract-driven connectors. C.2's gate
    named only `requests.`/`httpx`/`urlopen`, so `http.client` and Session-based calls would have
    passed.
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
