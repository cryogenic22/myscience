# WP-2 — Test specifications, invariants and fixture designs (rev C.4)

**Status:** Specifications only, **revision C.4**. **No executable tests and no fixture files exist
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

**Companions:** `WP-2_source_contract_control_plane.md` (rev C.4) ·
`WP-2_safe_fetch_threat_model.md` (rev C.4, §7 owns the 11 safe-fetch cases — **not duplicated or
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
| **C.3** | **M-05h rewritten** — C.2 *claimed* cross-contract rejection that the schema could not enforce | `source_job_streams` referenced job and stream independently |
| **C.3** | **M-05i rewritten, M-05j/k added** — one `etl_runs` row per stream; no rollup to over-report | Execution grain was contradictory (one run id, many streams, INV-01) |
| **C.3** | **M-35d rewritten; M-35e–j added** — typed certification scope, interval exclusion, event ordering/versioning/idempotency, finalize-once, deployment `state` | C.2 sentinel was invalid DDL; replay and state were unrepresentable |
| **C.3** | **M-11e–h added** — grant concurrency, all nine invalidation triggers, stream authorization, handle forgery | Grant authority was under-specified |
| **C.3** | **M-33c–g added** — PreviewGrant single-use/purpose/tenancy, and the WP-5/WP-8 interim containment boundary | PreviewGrant was a name; T-19/T-20 could be reached before their WPs land |
| **C.3** | **M-39f–h added** — quarantine store secrecy, rotation/retention, staged cutover | Quarantine had no physical home; immediate read-only would break the live writer |
| **C.3** | **M-40 strengthened to a protected case manifest** | Proving one test per invariant leaves the rest deletable |

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
| **INV-10** *(corrected C.4)* | An approval is recorded by an authenticated `human` principal distinct from the author — **structurally enforced at runtime** | Spec §12: runtime approval IS enforceable server-side; only *git-reviewer* separation is not |
| **INV-11** | Every effective deployment resolves to a registry entry, an active certification, and — **only if `cadence IS NOT NULL`** — a schedule | G-12 |
| **INV-12** | No code path derives a certification from a numeric score | Corrects the QUAL-001 `0.5`-filler class |
| **INV-13** | WP-2 emits no outcome outside the ratified WP-0 vocabulary, and every proposed input has a ratified mapping | Rejecting unknown strings ≠ semantic agreement |
| **INV-14** | The contract grammar is closed — no field accepts a callable, SQL, or arbitrary expression | SPEC-003 §8 |
| **INV-15** | A contract with 1..n output streams round-trips: admitted, deployed, executed and certified per stream | Multi-output connectors (spec §3.0) |
| **INV-16** | Rights attach to the acquisition, not the content blob: identical bytes under two contracts carry two envelopes | Spec §3.5 |
| **INV-17** | Revocation takes effect at the next request boundary, not the next run | `revocation_epoch`, spec §7.4 |
| **INV-18** | A grant is scoped to a tenant; no grant authorizes a cross-tenant fetch or read | Spec §12 |
| **INV-19** *(rewritten C.4)* | Every stream has its **own `etl_runs` row** and terminal outcome; **no run-level rollup outcome is stored at all** | C.3 removed the rollup but this invariant still described one |
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
| **M-05g** *(C.2)* | Certify a stream the contract never declared | RED — the stream FK rejects it. Impossible to enforce under C.1's JSONB streams |
| **M-05h** *(rewritten C.3)* | A stream execution for an acquisition of contract A referencing a stream of contract B | RED. **C.2 claimed this but could not enforce it** — `source_job_streams` referenced job and stream *independently*. Now both FKs pin the same `source_contract_version_id` (spec §3.6.1) |
| **M-05i** *(rewritten C.3)* | Run a 4-stream contract where stream 1 lands and stream 3 returns zero rows | Four `etl_runs` rows, one per stream, each with its own outcome. **No rollup exists to over-report** — C.2's `rollup_outcome` is removed. INV-15, INV-19 |
| **M-05j** *(C.3)* | An `etl_runs` row reachable from more than one stream execution, or a stream execution with no `etl_runs` row | RED — `etl_run_id UNIQUE` makes INV-01 hold by construction rather than by convention |
| **M-05k** *(C.3)* | Insert an acquisition whose `deployment_id` belongs to a different contract version | RED — composite FK against the new `source_deployments (deployment_id, source_contract_version_id)` candidate key |
| **M-05l** *(C.4)* | A stream execution whose `etl_run_id` references no `etl_runs` row; and an `etl_runs` row (post-cutover, contract-driven) with **no** stream execution | RED both ways. C.3's `UNIQUE` gave neither direction — it forbade sharing only |
| **M-05m** *(C.4)* | Apply the full DDL to an **empty database** | Accepted. This is M-35c re-emphasised: it has never been executed, and both C.1's unbacked composite FK and C.3's inline partial UNIQUE would have failed here |

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
| **M-11e — concurrency** *(C.3)* | Two workers spend the last unit of a grant's budget simultaneously | Exactly one succeeds. C.2's limits were unenforceable under concurrency; the conditional atomic update (spec §7.1) is the fix |
| **M-11f — the nine invalidation triggers** *(C.3)* | For **each** of: revocation · expiry · credential rotation · certification revocation · **natural certification expiry** · deployment disable · **redeployment/supersession** · rights-policy supersession · principal disablement — hold a live grant and fire the trigger mid-run | RED at the next request boundary in all nine, each with a *distinct* diagnostic so "authority withdrawn" is never reported as "source down". C.2 claimed redeployment invalidates but omitted it from the trigger set, and `revocation_epoch` was never declared on `SourceInstance` |
| **M-11g** *(C.3)* | Fetch a stream absent from the grant's `authorized_streams`, or one whose paired certification has lapsed | RED — a grant authorized only a *purpose* in C.2 |
| **M-11h** *(C.3)* | Present a forged/guessed grant handle | RED — verification is a DB lookup on a stored hash of a 256-bit random handle; there is nothing offline to forge |
| **M-11i** *(C.4)* | A grant row whose authorized stream belongs to another contract version; a `fetch` grant with a NULL `certification_id`; a `preview` grant with a non-NULL one; a grant with **zero** child rows | RED in all four. C.3's parallel `UUID[]` columns could express every one of these |
| **M-11j** *(C.4)* | Fetch under a grant whose `query_credential_exception` has expired or been revoked mid-run | RED — validity condition 10. C.3 created the exception object and never checked it |
| **M-11k — byte cap** *(C.4)* | A response with no `Content-Length`, then one declaring a false small `Content-Length` but streaming far more | The read **aborts mid-stream** at the reserved cap and fails `egress_refused`. C.3's `bytes_used + $n <= max_bytes` presumed a size known before the request |
| **M-11l** *(C.4)* | Crash between reserve and settle | Reservation is released or expires; a grant cannot be permanently starved by a dead worker |
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
| **M-20a — secret canary, every sink** | Inject a unique canary token as a resolved credential, run a full fetch + failure + preview, then grep for the canary across: `etl_runs`, `source_acquisitions`, `source_stream_executions`, `fetch_grants`, `legacy_quarantine`, `control_plane_events.payload`, application logs, `ConnectorError` messages, every API response body, catalog payloads, and any exported spec file. **Zero occurrences.** |
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
| **M-30b** *(updated C.3)* | Run a production acquisition | Each `source_stream_executions` row records `cursor_before`/`cursor_after` and its own terminal outcome; the acquisition records the grant id. Cursor *semantics* remain WP-9's |
| M-31 | Preview a private-IP URL | Refused by the **same** primitive as production (threat model C-06) |
| M-32 | Preview a response exceeding the byte cap | Bounded, refused, reported — not silently truncated |
| **M-33** *(rewritten)* | Preview on a source with **no certification and `execution_enabled = FALSE`** | **GREEN** — a `PreviewGrant` authorizes it. The Phase C rule was circular. Separately: preview with **no grant** → RED; preview attempting a `decision`-purpose fetch → RED |
| **M-33a** | Preview response for a `licensed` contract | Values redacted by classification; principal without source-object entitlement → RED |
| **M-33b** | Cite a preview as the sole `certification_evidence` | RED — a preview is never certification evidence |
| **M-33c** *(C.3)* | Reuse a spent `PreviewGrant` for a second page or a second preview | RED — single-use, non-replayable (spec §8.0.1) |
| **M-33d** *(C.3)* | Issue a `PreviewGrant` with `purpose` other than `discovery` | RED — a preview grant bypasses certification, so it may never carry an evidence/decision purpose |
| **M-33e** *(C.3)* | Preview across tenants, to a non-allowlisted origin, or after revocation | RED — a preview skips *certification and enablement only*; tenancy, origin, credential binding, revocation, limits and audit all still apply |
| **M-33f — interim containment** *(C.3)* | Drive a contract-driven record toward `facts`, entity resolution, the graph, an embedding index, or LLM context while the WP-5/WP-8 interim flag is set | RED, **fail-closed with a counted and reasoned rejection** — not silently filtered. Plus a Lane-2 check that no `contract_driven` record has reached those sinks (spec §8.0.2). This is the mechanical boundary that makes WP-2 safely landable ahead of WP-5/WP-8 |
| **M-33g** *(C.3)* | Clear the interim containment flag as a builder | RED — protected-surface change, owner-recorded only |
| **M-33h — containment at ingress** *(C.4)* | With the flag set, drive a contract-driven record and assert **at each stage separately**: no entity created by `resolve` (`pipeline.py:343`), no vector by `embed` (`:364`), no row in the **shared** DLQ (`:274`), no canonical store | RED at all four. C.3 asserted only the store, so the first three could have run — resolve can auto-create entities and the DLQ is replayed into the canonical path |
| **M-33i** *(C.4)* | A failed contract-driven record | Lands in the **separate** contract-driven quarantine queue, never the shared DLQ; the diversion is counted and reasoned |

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
| **M-35d** *(rewritten C.3)* | Insert two live contract-scoped certifications for one version and purpose | RED — the `scope_kind = 'contract'` partial unique index. **C.2's `'*'` sentinel is gone**: it carried an unconditional FK into real stream rows, so it either failed to insert or required a fake stream row that would enter the stream table and the canonical hash |
| **M-35e** *(C.3)* | Two certifications for one scope+purpose with **overlapping finite** validity intervals | RED — the `EXCLUDE USING gist` constraint. C.2's partial uniqueness caught only open-ended rows |
| **M-35f** *(C.3)* | A stream with both a stream-scoped and a contract-scoped certification | The stream-scoped decision wins (spec §3.4 resolution rule); assert the broader one does not silently widen the narrower |
| **M-35g** *(C.3)* | Replay the event log with events deliberately out of `occurred_at` order but correct `aggregate_seq` | Projections rebuild correctly — ordering is by `aggregate_seq`, not wall clock |
| **M-35h** *(C.3)* | Replay a log missing `event_schema_version`, or emit two events with one `idempotency_key` | RED — replay determinism requires typed, versioned, idempotent events (INV-20) |
| **M-35i** *(C.3)* | Write to an acquisition or stream-execution row after finalization | RED — write-once-then-finalize-once, enforced by trigger. These rows are **not** immutable and are no longer described as such |
| **M-35j** *(C.3)* | Set `execution_enabled = TRUE` on a deployment whose `state` is `paused` or `rolled_back` | RED — CHECK constraint. C.2's projection had no `state` column at all, so §5.2 condition 1 was unevaluable |
| **M-35k** *(C.4)* | Enable execution for a `legacy_unverified` contract version — via the API, **and** by writing the projection row directly | RED both ways: the trigger is the floor, the enable path and grant-issue re-read are defence in depth. C.3 specified a cross-table CHECK, which PostgreSQL cannot express |
| **M-35l** *(C.4)* | Emit `aggregate_seq` with a gap; an unknown `event_type` or `aggregate_kind`; an event after a terminal one; a projection `last_event_id` pointing at another aggregate's event | RED in all four — replay must fail loudly on a gap rather than skip it |
| **M-35m** *(C.4)* | Drop a historical `event_schema_version`'s typed schema, then replay | RED — old events become unreplayable, which is silent history loss |
| **M-35n** *(C.4)* | An acquisition whose `rights_policy_version_id` differs from its issuing grant's | RED — lineage must answer "under which policy" without inference |
| **M-35o** *(C.4)* | Insert a certification with `scope_kind = 'archived'` (an unknown kind) and a NULL `stream_id` | RED — C.3's CHECK constrained the pairing but not the vocabulary |
| M-36 | Delete a certification instead of revoking | RED — supersede, don't delete |
| **M-36a** | Assert certification history is queryable after revocation, with prior decisions intact | GREEN |
| **M-37** *(rewritten)* | Effective deployment with **`cadence IS NOT NULL`** and no schedule → RED. Effective deployment with **`cadence IS NULL`** (manual/event-driven) and no schedule → **GREEN**. The Phase C rule failed legitimate manual sources | INV-11 |
| M-38 | Catalog entry pointing at a superseded deployment | RED — INV-11, both directions |
| M-39 | Derive a certification from a numeric quality score | RED — INV-12 |
| **M-39a — rights propagation** | Fetch identical bytes under two contracts with different licences/tenants; assert two distinct rights envelopes attached to the two acquisitions, and that the content-addressed blob carries none | RED against a blob-attached model — INV-16 |
| **M-39b — legacy quarantine** *(rewritten C.2)* | Backfill an onboarding row containing a nested `headers.Authorization` value | **QUARANTINED — no contract version is created at all.** The original row is preserved verbatim and reported. C.1 said the row was *both* quarantined *and* admitted as `legacy_unverified`; only clean rows are admitted |
| **M-39c** *(C.2)* | Backfill a clean legacy row | Admitted with `provenance = 'legacy_unverified'`: disabled, uncertified, **no grant issuable** (CHECK-enforced, spec §9.3.1) |
| **M-39f** *(C.3)* | Read a `legacy_quarantine.captured_row` via any API, catalog, log or event payload | RED — only `detector_findings` (paths, not values) may surface. The quarantine store is itself a secret store |
| **M-39g** *(C.3)* | Re-onboard a source whose quarantine row has `credential_rotation_status != 'rotated'`, or let `retention_expires_at` pass without purging the captured row | RED — preserving a secret verbatim moves the exposure; it must expire and the credential must rotate |
| **M-39h** *(C.3)* | Apply the migration, then call the existing `set_onboarding_contract` writer | **GREEN at stage 1–3.** C.2 would have made the 099 columns read-only immediately, breaking the live writer. The staged dual-write/dual-read cutover (spec §9.3) is asserted stage by stage, with a divergence check |
| **M-39d — tenancy at four boundaries** *(C.2)* | For each of route, service, repository and **worker/scheduler**: reach a WP-2 table with an unresolved or foreign tenant | RED at every one. Specifically: a scheduled job whose source instance has no resolvable tenant **fails closed** rather than running unscoped — the path that never passes through a route — INV-18, INV-22 |
| **M-39e** *(C.2)* | Call a control-plane service with an ambient/default/`None` tenant | RED — no implicit "all tenants" |

### 2.8 Anti-vacuous guards

Following `test_lane1_suite_is_not_vacuous()` in `tests/test_conservation_gates.py`:

| # | Case |
|---|---|
| **M-40** *(strengthened again C.4)* | C.3's manifest enumerated *case IDs*, but the threat model's §7 items 8–15 are **numbered variants inside one control** (mixed DNS answers, IPv4-mapped IPv6, SNI mismatch, peer verification, env proxy, allowlist substitution, expiry, alternate HTTP stacks). A manifest keyed on controls would let 7 of 8 variants vanish while staying green. **Every safe-fetch variant gets its own stable ID** (`SF-02a`…`SF-06d`), and the manifest enumerates variants, not controls. The suite asserts the collected variant set is *exactly* the manifest; the manifest is protected surface, so a builder cannot delete a variant by editing it |
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

- **Safe-fetch cases live in the threat model** (§7, rev C.4) — not restated, not counted here.
- **No DDL in this package has been executed.** M-35c ("apply the DDL to an empty database") was
  specified in C.2 and has never run, which is why C.3 shipped an invalid inline partial-UNIQUE and
  an unbacked composite FK. Every DDL claim here is **unverified by execution**, and the ledger
  records it as such rather than as correct.
- **T-19** (source poisoning) and **T-20** (fetched content as instructions) have **no cases** —
  WP-8 and WP-5.
- **Cursor and lease mechanics have no cases** — **WP-9** owns them (spec §6.0). M-30b tests only
  that a job *records* positions.
- **Streaming / memory pressure**: no cases — WP-9. M-32 bounds a preview only.
- **Tenancy enforcement in routes**: no cases — Product-Platform (COORDINATION §10.1 A4). M-11c
  covers grant-level scoping only.
- **INV-10 is enforceable at runtime and is specified as hard** (spec §12). What remains
  unenforceable is *git-reviewer* separation — a different problem, and WP-12's, not a reason to
  weaken the runtime check. C.3 corrected the spec; C.4 corrects this line, which still carried the
  old conflation.
- **M-28a is an UNMET DESIGN CRITERION, not RED evidence** (C.2) — it gates ASK-WP2-1 and must not
  be marked pending or removed to make a suite green, but it has never been executed.
- **Rights/retention attachment has no cases that can pass today** — ASK-WP2-3 must resolve the
  WP-1 conflict first (spec §3.5.1). M-39a is specified against the *target* interface, and would
  fail against WP-1's current content-addressed `retention_class` for the correct reason.
- **Per-stream outcome *vocabulary* (M-05c/M-30a) depends on ASK-WP2-1** — the mapping of each
  proposed input to a terminal outcome is WP-0's to ratify. There is no rollup rule to agree,
  because C.3 removed the rollup.
