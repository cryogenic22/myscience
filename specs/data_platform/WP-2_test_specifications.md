# WP-2 — Test specifications, invariants and fixture designs (rev C.2)

**Status:** Specifications only, **revision C.2**. **No executable tests and no fixture files exist
in this branch** — a spec-only branch that merged intentionally-red tests would be a standing
*vacuous red*, the mirror of a vacuous green (COORDINATION §13.3). Each case becomes an executable
RED test **inside the implementation PR that turns it GREEN**.

> **Vocabulary rule (C.2).** Nothing in this document is RED. **RED means executed and observed to
> fail.** Every case here is an **unmet design criterion** — unwritten, unrun. No case may be cited
> as evidence in a RED→GREEN claim until it has actually been executed. C.1 violated this by
> labelling M-28a "RED at spec time"; that is corrected in §2.5.

> **C.1 correction:** the Phase C revision said fixtures "are committed under
> `tests/connector_platform/fixtures/`". **They are not, and must not be in a spec-only branch.**
> §3 below is a fixture *design*, not an inventory. Describing an artefact as existing when it does
> not is the ungrounded-claim failure this harness exists to catch.

**Companions:** `WP-2_source_contract_control_plane.md` (rev C.2) ·
`WP-2_safe_fetch_threat_model.md` (rev C.2, §7 owns the 11 safe-fetch cases — **not duplicated or
counted here**) · `WP-2_findings_reverification.md`.

**Lane:** every case is **Lane 1** (deterministic, DB-free or seeded, PR-blocking) unless marked
Lane 2. No live-source dependency may enter a PR gate.

### Revision log

| Rev | Cases changed | Cause |
|---|---|---|
| C.1 | M-06 rewritten — permitted "pre-reference mutation" of a supposedly immutable version | Immutability now begins at admission (spec §3.2) |
| C.1 | M-11 rewritten — tested a *supplied* disabled flag, not missing or forged authority | Grant model (spec §7) |
| C.1 | M-27 rewritten — assumed automatic cursor rollback is safe | Rollback is an audited explicit operation; cursors are WP-9 |
| C.1 | M-29 rewritten — forbade the mandatory security-audit write | Preview egress must be durably audited (spec §8.1) |
| C.1 | M-34 rewritten — treated two unequal strings as independent human principals | Typed actor kinds (spec §12) |
| C.1 | M-37 rewritten — required schedules for manual/event-driven sources | `cadence IS NULL` is legitimate |
| C.1 | L2-03 rewritten — treated every stationary cursor as failure | Some sync APIs legitimately hold position |
| C.1 | +11 new case groups | Coverage gaps named in review |
| **C.2** | **Vocabulary rule added** — nothing here is RED; every case is an *unmet design criterion* | "RED at spec time" claimed an observed failure that never ran |
| **C.2** | **M-28a relabelled** unmet-design-criterion | same |
| **C.2** | **Residual "recorded and committed" fixture claim removed** (§3) | C.1 fixed the header, missed the body |
| **C.2** | **M-20b rewritten** — credential-bound params persist as `REDACTED:credential`, never a value hash | A hash of a credential is still a credential artefact |
| **C.2** | **New cases** for relational streams, composite-FK validity, projection replay, per-stream outcomes, tenancy at four boundaries, legacy quarantine-not-admission | C.2 spec defects 2–7 |

---

## 1. Invariants

| ID | Invariant | Why |
|---|---|---|
| **INV-01** | Every post-cutover `etl_runs` row resolves to exactly one `source_instance_id`, one `source_contract_version_id` and one `stream_key` | G-01 |
| **INV-02** | No historical `etl_runs` row is orphaned by the identity migration; `legacy_source_key` resolves exactly once | Conservation; alias must be UNIQUE |
| **INV-03** | A `SourceContractVersion` is immutable **from admission**, and its stored body always re-hashes to its `canonical_hash` | Immutability must be verified, not asserted |
| **INV-04** | No outbound request occurs without a valid, unexpired, unrevoked `FetchGrant` | Authority, not advice |
| **INV-05** | No credential-shaped value reaches any persisted sink at any nesting depth | Phase A probe: the 3-key denylist leaks 4 ways |
| **INV-06** | An outcome that does not assert completeness never advances a completeness-derived watermark | G-10, narrowed in C.1 |
| **INV-07** | A deployment may only reference a contract version belonging to its own source instance | Composite FK |
| **INV-08** | Preview writes security/audit records and **no** domain, pipeline, cursor or DLQ rows | Egress must be audited; data must not leak |
| **INV-09** | Every dropped row in a preview is counted and reasoned, per stream | Conservation before correctness |
| **INV-10** | An approval is recorded by a `human` actor kind whose principal differs from the author's | Separation of authorship (visible, not enforceable — §6) |
| **INV-11** | Every effective deployment resolves to a registry entry, an active certification, and — **only if `cadence IS NOT NULL`** — a schedule | G-12 |
| **INV-12** | No code path derives a certification from a numeric score | Corrects the QUAL-001 `0.5`-filler class |
| **INV-13** | WP-2 emits no outcome outside the ratified WP-0 vocabulary, and every proposed input has a ratified mapping | Rejecting unknown strings ≠ semantic agreement |
| **INV-14** | The contract grammar is closed — no field accepts a callable, SQL, or arbitrary expression | SPEC-003 §8 |
| **INV-15** | A contract with 1..n output streams round-trips: admitted, deployed, executed and certified per stream | Multi-output connectors (spec §3.0) |
| **INV-16** | Rights attach to the acquisition, not the content blob: identical bytes under two contracts carry two envelopes | Spec §3.5 |
| **INV-17** | Revocation takes effect at the next request boundary, not the next run | `revocation_epoch`, spec §7.4 |
| **INV-18** | A grant is scoped to a tenant; no grant authorizes a cross-tenant fetch or read | Spec §12 |
| **INV-19** *(C.2)* | Every stream of a run carries its own outcome and counts; the run-level outcome is a deterministic rollup that never over-reports success | A scalar per-run outcome cannot describe a multi-output connector |
| **INV-20** *(C.2)* | `source_deployments` and `source_certifications` are rebuildable byte-identically by replaying `control_plane_events` | Makes "the event log is the authority" checkable |
| **INV-21** *(C.2)* | Every composite FK names a parent column list backed by a `UNIQUE`/`PK`, and the DDL applies cleanly to an empty database | C.1's composite FK was invalid SQL |
| **INV-22** *(C.2)* | Tenancy is enforced at route, service, repository **and** worker boundaries; an unresolvable tenant fails closed | Route-only enforcement leaves schedulers unscoped |

## 2. Mutation cases

Each case, **once written**, must be observed RED before its control lands and GREEN after. A case
that cannot be made to fail is not a test — report it as such rather than counting it. Per the
vocabulary rule above, the "Expected" column states the **intended** verdict; none has been
executed.

### 2.1 Identity, streams, legacy bridge

| # | Mutation | Expected |
|---|---|---|
| M-01 | Remove `source_instance_id` from `Provenance` | RED — INV-01 |
| M-02 | Write an `etl_runs` row with a null contract version or null `stream_key` | RED — INV-01 |
| M-03 | Two contract versions sharing one `(instance, version)` | RED — unique constraint |
| M-04 | Backfill a fixture where one `sources` row has no onboarding contract | GREEN, and the migration **reports** the skip with a reason |
| M-05 | Rename `source_instance_id` → `source_id` anywhere under `integration/` | RED — naming guard (`cross_linker.py` uses it for graph edges, 25 sites) |
| **M-05a** | Two `source_instances` rows sharing a `legacy_source_key` | RED — INV-02 |
| **M-05b** | Backfill a bespoke connector that has existing `etl_runs` history; assert every historical row still resolves to exactly one instance | RED without the alias, GREEN with it — INV-02 |
| **M-05c** | Admit a ClinicalTrials-shaped contract emitting `TRIAL`, `TRIAL_OUTCOME`, `TRIAL_LOCATION`, `INVESTIGATOR`; assert 4 addressable streams, 4 independent certifications | RED against a scalar `record_type` — INV-15 |
| **M-05d** | A contract declaring two streams with the same `stream_key` | RED — `STREAM_KEY_DUPLICATE` |
| **M-05e** | `connector_type: "rest"` (invented vocabulary) instead of `API_REST` | RED — `CONNECTOR_TYPE_UNKNOWN` |
| **M-05f** | A `WEB_SCRAPE` contract (valid taxonomy, non-runtime) | Storable and permanently `execution_enabled = FALSE` |
| **M-05g** *(C.2)* | Certify a `stream_key` the contract never declared | RED — the stream FK rejects it. Impossible to enforce under C.1's JSONB streams |
| **M-05h** *(C.2)* | A job asserting a `stream_id` not belonging to its contract version | RED — FK |
| **M-05i** *(C.2)* | Run a 4-stream contract where stream 1 lands and stream 3 returns zero rows | Per-stream outcomes recorded independently; `rollup_outcome` does **not** report `LANDED`. Unrepresentable under C.1's scalar outcome — INV-15, INV-19 |

### 2.2 Immutability, drafts, canonical hash

| # | Mutation | Expected |
|---|---|---|
| **M-06** *(rewritten)* | `UPDATE source_contract_versions` on **any** admitted row — referenced or not | RED. The Phase C case permitted pre-reference mutation, which is not immutability. Mutability lives only in `ContractDraft` |
| **M-06a** | Mutate a `ContractDraft` freely | GREEN — drafts are mutable by design and can never be executed |
| **M-06b** | Tamper with a stored version body so it no longer matches `canonical_hash`; then approve, then execute | RED at **both** checkpoints — `CANONICAL_HASH_MISMATCH`, INV-03 |
| **M-06c** | Serialize one logical contract twice with reordered keys, differing unicode normalization, and `1` vs `1.0` | Identical `canonical_hash`. A non-deterministic hash is not a control |
| **M-06d** | Admit two contracts with identical canonical bodies for one instance | RED — `UNIQUE (source_instance_id, canonical_hash)` |
| M-07 | Unknown top-level field | RED — `UNKNOWN_FIELD` |
| M-08 | Embedded Python/SQL expression in any field | RED — `NO_CALLABLE_IN_CONTRACT`, INV-14 |
| M-09 | `must_capture` naming an unmapped field | RED — `MUST_CAPTURE_UNMAPPED` |
| M-10 | Bump `validator_version`, revalidate all stored contracts | Each revalidates or is flagged — **never silently downgraded** |

### 2.3 Authority — grants, not booleans

| # | Mutation | Expected |
|---|---|---|
| **M-11** *(rewritten)* | Call the fetch primitive with **no grant**; then with an **expired** grant; then with a **forged/self-constructed** grant object; then with a grant whose `contract_canonical_hash` no longer matches | RED in all four — INV-04. The Phase C case only passed a disabled flag, which tests obedience, not authority |
| **M-11a** | Grant for origin A; request origin B (same contract) | RED — exact normalized origin match |
| **M-11b** | Grant valid at page 1; revoke mid-run; continue to page 2 | RED at the page boundary — INV-17 |
| **M-11c** | Grant issued for tenant T1; fetch attempted under tenant T2 | RED — INV-18 |
| **M-11d** | Exceed `max_requests` / `max_bytes` on a grant | RED, bounded, reported |
| M-12 | Enable execution with no active certification for the requested purpose **and stream** | RED — `PURPOSE_NOT_CERTIFIED` |
| M-13 | Enable execution with the safe-fetch boundary absent/disabled | RED — fail-closed |
| M-14 | Enable execution with an unresolvable credential slot | RED — distinct from "source down" |
| **M-14a** | Slot bound as `header:Authorization`; caller attempts query-param placement | RED — `CREDENTIAL_PLACEMENT_FORBIDDEN` |

### 2.4 Secrets — the Phase A probe inverted, plus canaries

The exact config that survived stripping at `da6887c` must now be **rejected at admission**
(spec §7.3, threat model C-11/C-12):

```python
{"url": "https://user:pass@example.com/data",       # M-15 URL_USERINFO_PRESENT
 "auth_token": "TOPLEVEL",                           # M-16 INLINE_CREDENTIAL_PRESENT
 "headers": {"Authorization": "Bearer NESTED"},      # M-17 nested — survives today
 "query_params": {"api_key": "QUERY"},               # M-18 nested — survives today
 "auth_secret": "UNRECOGNISED-KEY"}                  # M-19 unknown key — survives today
```

| # | Expected |
|---|---|
| M-15…M-19 | Each rejected with its typed code — **rejected, not stripped** |
| M-20 | The persisted projection contains no value from the above at any depth — INV-05 |
| M-22 | Add a **new** credential-shaped field to a config dataclass without updating the validator | RED — projection is allowlist-shaped, so it cannot reach storage. Proves the fix is structural, not a longer denylist |
| **M-20a — secret canary, every sink** | Inject a unique canary token as a resolved credential, run a full fetch + failure + preview, then grep for the canary across: `etl_runs`, `source_jobs`, `control_plane_events.payload`, application logs, `ConnectorError` messages, every API response body, catalog payloads, and any exported spec file. **Zero occurrences.** |
| **M-20b** *(rewritten C.2)* | Contract using query-placed auth. **(a)** Without an owner-approved exception → RED at admission (`CREDENTIAL_PLACEMENT_FORBIDDEN`). **(b)** With the exception → the persisted record contains the parameter *name* plus the literal `REDACTED:credential`, and **no value hash, length, or prefix**. C.1 permitted a value hash, which is still credential-derived material |
| **M-20c** *(C.2)* | Feed a low-entropy credential and attempt offline recovery from every persisted artefact | No value-derived material exists to attack |
| M-21 | `ConnectorError` on a userinfo URL contains no credential |

### 2.5 Outcomes and watermarks

| # | Mutation | Expected |
|---|---|---|
| **M-23** *(narrowed)* | Finish a run with `truncated = True` | The **completeness-derived watermark** does not advance, and truncation reaches the terminal outcome — not a log line. (Token advancement per se is WP-9's semantics.) INV-06 |
| **M-27** *(rewritten)* | Roll back a deployment | The prior version becomes effective; superseded rows stay queryable; **no cursor is automatically rewound.** Cursor rollback is a separate, explicitly-audited operation with a stated at-least-once/at-most-once guarantee — the Phase C case assumed automatic rollback is safe, which depends on cursor kind and sink idempotency |
| **M-28** | Emit an outcome outside the **ratified** WP-0 vocabulary | RED — INV-13 |
| **M-28a** | Assert every §5.3 proposed input has a ratified mapping row in the shared WP-0/WP-2 table | **UNMET design criterion** — see the status note below |

> **M-28a status (corrected in C.2).** C.1 called this "RED at spec time." **That was wrong, and it
> is the same error this harness exists to catch:** RED is an *observed* state — a test that was
> executed and failed. No executable test exists in this branch, so M-28a is an **UNMET DESIGN
> CRITERION**, not evidence. It cannot appear in any RED→GREEN claim until it has actually been run.
> Its function is unchanged — it gates ASK-WP2-1 and must not be marked pending or deleted to make
> a suite green — but the label must be honest about what has and has not been executed. The same
> rule applies to every case in this document: **none of them is RED; all of them are unwritten.**

> Cursor/lease mechanics (M-24…M-26 in the Phase C draft) are **withdrawn** — SPEC-003 §6 assigns
> durable cursors and leases to **WP-9** (spec §6.0). WP-2 keeps only per-stream job rows recording
> `cursor_before`/`cursor_after`, tested by M-30b.

### 2.6 Discovery and preview

| # | Mutation | Expected |
|---|---|---|
| **M-29** *(rewritten)* | Run preview; assert **zero** rows in `etl_runs`, entities, cursors, DLQ, embeddings — **and assert a `control_plane_events` row and rate-accounting row WERE written.** The Phase C case forbade the security write | INV-08 |
| M-30 | Preview a payload where 2 of 50 records lack an external id | `records_dropped: 2` with reasons, **per stream** — INV-09 |
| **M-30a** | Preview a multi-stream contract | Conservation reported independently per stream — INV-15 |
| **M-30b** | Run a production job | `source_jobs` records `cursor_before`/`cursor_after`, grant id and terminal outcome |
| M-31 | Preview a private-IP URL | Refused by the **same** primitive as production (threat model C-06) |
| M-32 | Preview a response exceeding the byte cap | Bounded, refused, reported — not silently truncated |
| **M-33** *(rewritten)* | Preview on a source with **no certification and `execution_enabled = FALSE`** | **GREEN** — a `PreviewGrant` authorizes it. The Phase C rule was circular. Separately: preview with **no grant** → RED; preview attempting a `decision`-purpose fetch → RED |
| **M-33a** | Preview response for a `licensed` contract | Values redacted by classification; principal without source-object entitlement → RED |
| **M-33b** | Cite a preview as the sole `certification_evidence` | RED — a preview is never certification evidence |

### 2.7 Promotion, tenancy, audit, catalog

| # | Mutation | Expected |
|---|---|---|
| **M-34** *(rewritten)* | Approve with `actor_kind = agent`; then approve with a `human` kind whose principal equals the author's; then two distinct self-declared strings from one identity | RED in all three. The Phase C case treated two unequal strings as independent principals — INV-10 |
| **M-34a — concurrent promotion** | Two approvals/enables race on one `(instance, environment)` | Exactly one effective deployment survives; the loser fails cleanly, no torn state |
| **M-34b — cross-instance reference** | Create a deployment pairing instance A with a contract version of instance B | RED — composite FK, INV-07 |
| **M-34c — idempotency** | Replay an identical mutating API call with the same idempotency key | One state change, one event, identical response |
| M-35 | Delete or update a `control_plane_events` row | RED — append-only |
| **M-35a** *(C.2)* | Drop `source_deployments` and `source_certifications` entirely, replay the event log | Both projections rebuild **byte-identical**. This is what makes "the event log is the authority" checkable rather than asserted — INV-20 |
| **M-35b** *(C.2)* | Update a projection row without emitting its event in the same transaction | RED — projection and log must not diverge |
| **M-35c** *(C.2)* | Apply the migration DDL to an empty database | Every composite FK is accepted. C.1's FK referenced a non-unique parent column list and would have failed here — INV-21 |
| **M-35d** *(C.2)* | Insert two contract-wide certifications (`stream_key = '*'`) for one version, purpose and `effective_from` | RED. Under C.1's nullable `stream_key` both were admissible, because NULLs are distinct in a UNIQUE |
| M-36 | Delete a certification instead of revoking | RED — supersede, don't delete |
| **M-36a** | Assert certification history is queryable after revocation, with prior decisions intact | GREEN |
| **M-37** *(rewritten)* | Effective deployment with **`cadence IS NOT NULL`** and no schedule → RED. Effective deployment with **`cadence IS NULL`** (manual/event-driven) and no schedule → **GREEN**. The Phase C rule failed legitimate manual sources | INV-11 |
| M-38 | Catalog entry pointing at a superseded deployment | RED — INV-11, both directions |
| M-39 | Derive a certification from a numeric quality score | RED — INV-12 |
| **M-39a — rights propagation** | Fetch identical bytes under two contracts with different licences/tenants; assert two distinct rights envelopes attached to the two acquisitions, and that the content-addressed blob carries none | RED against a blob-attached model — INV-16 |
| **M-39b — legacy quarantine** *(rewritten C.2)* | Backfill an onboarding row containing a nested `headers.Authorization` value | **QUARANTINED — no contract version is created at all.** The original row is preserved verbatim and reported. C.1 said the row was *both* quarantined *and* admitted as `legacy_unverified`; only clean rows are admitted |
| **M-39c** *(C.2)* | Backfill a clean legacy row | Admitted as `legacy_unverified`: disabled, uncertified, **no grant issuable** |
| **M-39d — tenancy at four boundaries** *(C.2)* | For each of route, service, repository and **worker/scheduler**: reach a WP-2 table with an unresolved or foreign tenant | RED at every one. Specifically: a scheduled job whose source instance has no resolvable tenant **fails closed** rather than running unscoped — the path that never passes through a route — INV-18, INV-22 |
| **M-39e** *(C.2)* | Call a control-plane service with an ambient/default/`None` tenant | RED — no implicit "all tenants" |

### 2.8 Anti-vacuous guards

Following `test_lane1_suite_is_not_vacuous()` in `tests/test_conservation_gates.py`:

| # | Case |
|---|---|
| M-40 | The suite asserts it is non-empty **and** that every INV-nn has ≥1 executing test — deleting a test turns the gate red |
| M-41 | The validator self-test proves it can still reject a known-bad fixture on every run, so a broken validator cannot read as "all contracts valid" |
| M-42 | The catalog integrity gate asserts it examined >0 effective deployments |
| **M-43** | The secret-canary sweep (M-20a) asserts it searched >0 sinks and that each named sink was reachable — an unreachable sink must fail, not pass |

## 3. Fixture designs (to be authored in the implementation PR — none exist today)

**Valid:** single-stream `API_REST`; **multi-stream `API_REST`** (4 streams, ClinicalTrials-shaped);
`CSV_FILE` via upload identifier with **no `path` field**; `RSS` public source, `discovery`
certification only; a `WEB_SCRAPE` contract (storable, never runnable).

**Rejected** — one per code in spec §10, each paired with its expected diagnostic, including
`CONNECTOR_TYPE_UNKNOWN`, `STREAM_KEY_DUPLICATE`, `CANONICAL_HASH_MISMATCH` and
`CREDENTIAL_PLACEMENT_FORBIDDEN`.

**Payloads:** a recorded upstream response per connector type; a multi-stream payload; an
alternating-cursor payload (threat model T-07b); an oversized payload; a `licensed`-classification
payload for redaction tests. **All to be recorded and committed in the implementation PR — none
exist today** (C.2: C.1 corrected this claim in the header but left it standing here). The binding
requirement is **no live network in any Lane-1 test**.

**Migration:** seeded `sources` + `source_onboarding` including a row with no contract (M-04), a
row with a nested embedded secret (M-39b), a duplicate-alias pair (M-05a), and a bespoke connector
with existing `etl_runs` history (M-05b).

**Canary:** a unique, greppable, non-guessable token used only by M-20a/M-43.

## 4. API examples

`POST /hub/sources/{id}/contracts` — admit a draft (idempotency key required):

```jsonc
{
  "connector_type": "API_REST",
  "transport": {"url": "https://api.example.org/v1/labels", "pagination": "cursor",
                "cursor_param": "next", "cursor_path": "meta.next",
                "page_size": 100, "max_pages": 50},
  "output_streams": [
    {"stream_key": "labels", "record_type": "drug_label", "records_path": "results",
     "external_id_field": "id", "field_map": {"brand_name": "brand_name"},
     "must_capture": ["external_id", "generic_name"]}
  ],
  "credential_slots": [{"slot": "primary_token", "placement": "header:Authorization"}],
  "egress_allowlist": ["https://api.example.org:443"],
  "rights_policy_version_id": "…",
  "cadence": {"hour": "*/12"},
  "sla_days": 2
}
```

**201** → `{"source_contract_version_id": "…", "version": 3, "canonical_hash": "sha256:…"}`

**422** → **all** diagnostics, never the first only — an author fixing one error per round-trip
across five attempts is how inline-credential habits form:

```jsonc
{"state": "rejected", "diagnostics": [
  {"code": "INLINE_CREDENTIAL_PRESENT", "pointer": "/transport/headers/Authorization"},
  {"code": "ORIGIN_NOT_ALLOWLISTED", "pointer": "/transport/url"},
  {"code": "STREAM_KEY_DUPLICATE", "pointer": "/output_streams/1/stream_key"}
]}
```

## 5. Lane 2 (scheduled, never PR-blocking)

| ID | Check |
|---|---|
| L2-01 | Every effective deployment with `sla_days` set has fetched within it, **per instance and stream** |
| L2-02 | No certification is past `review_due_at` without being expired |
| **L2-03** *(rewritten)* | A cursor stationary beyond its cadence **while runs report a completeness-asserting outcome and non-zero upstream change** is an anomaly. A stationary cursor alone is **not** a failure — some sync APIs legitimately hold position |
| L2-04 | *(withdrawn — leases are WP-9)* |
| L2-05 | Catalog integrity against the live DB |
| **L2-06** | No `legacy_unverified` contract has been executing |
| **L2-07** | Secret-canary sweep against production sinks (the Lane-1 version runs seeded) |

`scripts/connector_health.py` and `scheduler/config.py` are **protected surface**. Adding an SLA
entry is permitted strengthening; loosening a threshold to pass is not.

## 6. Coverage honesty

Stated so this document cannot read as more coverage than it provides:

- **Safe-fetch cases live in the threat model** (§7, rev C.2) — not restated, not counted here.
- **T-19** (source poisoning) and **T-20** (fetched content as instructions) have **no cases** —
  WP-8 and WP-5.
- **Cursor and lease mechanics have no cases** — **WP-9** owns them (spec §6.0). M-30b tests only
  that a job *records* positions.
- **Streaming / memory pressure**: no cases — WP-9. M-32 bounds a preview only.
- **Tenancy enforcement in routes**: no cases — Product-Platform (COORDINATION §10.1 A4). M-11c
  covers grant-level scoping only.
- **INV-10 is asserted but not enforceable today** — worktree agents run under the owner's git
  identity, so M-34 makes a violation *visible*, not impossible.
- **M-28a is an UNMET DESIGN CRITERION, not RED evidence** (C.2) — it gates ASK-WP2-1 and must not
  be marked pending or removed to make a suite green, but it has never been executed.
- **Rights/retention attachment has no cases that can pass today** — ASK-WP2-3 must resolve the
  WP-1 conflict first (spec §3.5.1). M-39a is specified against the *target* interface, and would
  fail against WP-1's current content-addressed `retention_class` for the correct reason.
- **Per-stream outcome rollup (M-05c/M-30a) depends on ASK-WP2-1** — the rollup rule for a run
  whose streams disagree is WP-0's to ratify.
