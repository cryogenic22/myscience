# WP-2 — Versioned source-contract control plane (Phase C specification)

**Status:** Specification. **Spec-only** — no runtime wiring, no migration reserved, no executable
tests in this branch.
**Baseline:** `claude/handoff/h0-baseline` @ `da6887c`, read-only.
**Date:** 2026-08-15
**Covers:** G-01, G-07, G-10, G-12, G-14 (SPEC-003 §6).
**Preceded by:** `WP-2_findings_reverification.md` (Phase A — what is actually true at the
baseline) and `WP-2_safe_fetch_threat_model.md` (Phase B — the security boundary). Every
"today" claim below is a verified file:line from Phase A, not a restatement of the review.

**Implementation gate (COORDINATION §13.3, unchanged by this document):**

> H0 → H1 → H2 → WP-12 → WP-0 → WP-1 → H3/H4/H5 → **WP-2**.
> The safe-fetch threat model is the first *design* activity. Source identity and immutable
> contract foundations **may land with execution disabled**. Safe fetch and secret resolution are
> **mandatory before any probe, preview or scheduled outbound request can execute**.

---

## 1. What WP-2 is, in one paragraph

Today an outbound request originates from reviewed code: a connector class with a hardcoded
endpoint, merged through CODEOWNERS. WP-2 makes the endpoint **user-authored data** — a versioned,
validated, immutable contract that a deterministic control plane deploys, certifies, schedules and
audits. The work is mostly **threading and versioning what already exists**, not new adapters:
migration 099 already persists a contract body, `list_runnable_sources()` already queries it, and
`build_connector_from_spec()` already instantiates the generic connectors. None of them has a
consumer (Phase A §1.1). WP-2 makes that path immutable, identified, certified and safe — then
connects it.

## 2. Two consumers pin this design

**Upstream constraint — SPEC-003 §8 and COORDINATION §13.4:** *AI may propose declarative
contracts; deterministic validators control network access, persistence and production promotion.*
No arbitrary SQL or Python callables in a user-editable runtime contract; no model judgement may
authorise network access, secret resolution, or promotion.

**Downstream constraint — TIV2-020** (`specs/trusted_intelligence_v2/SPEC_TIV2_020_…`, an
architecture overlay whose §2 explicitly reuses *"WP-2's source-instance/contract version,
certification, rights, and safe-fetch boundary"*). Its `source_artifact_versions` object requires
these fields to already exist and be stable:

| Field TIV2 requires | Owner |
|---|---|
| `source_instance_id` | **WP-2** |
| `source_contract_version_id` | **WP-2** |
| `rights_policy_version_id`, `retention_class`, `redistribution_class` | **WP-2** |
| `data_classification` | **WP-2** |
| `created_by_run_id`, `code_git_sha` | **WP-2** (run identity) / WP-1 (artefact) |
| `raw_artifact_sha256` | WP-1 |
| `source_native_id`, `source_native_version`, `publisher_independence_key` | WP-2 declares in contract; WP-1/TIV2 populate |

TIV2 also specifies `source_certifications` keyed on `source_instance_id + contract_version`.
**This spec adopts those names verbatim.** Independently choosing different names here would force
a rename migration in a downstream epic — and it happens to confirm the Phase A §1.2 finding that
a bare `source_id` cannot be reused, since `integration/cross_linker.py` already means something
else by it.

## 3. Object model

Five objects. Only the first is mutable.

### 3.1 `SourceInstance` — the stable identity of a feed

The thing that persists across every contract edit. **Mutable metadata only**; it never carries
transport, mapping or credentials.

```text
source_instance_id   UUID PK          -- new, first-class, never reused
legacy_source_key    TEXT NULL        -- FK -> sources.source_id (migration 055, TEXT PK)
display_name         TEXT
owner_principal      TEXT             -- who is accountable
tenant_id            TEXT NULL        -- H1/SEC-002 seam; see §12
lifecycle            TEXT             -- see §5.1
created_at, updated_at
```

**The legacy bridge is the load-bearing detail.** `sources.source_id` is a `TEXT` primary key
(`schema/migrations/055_source_registry.sql:6`), and 15 bespoke connectors are keyed by the
`SourceType` enum. WP-2 does **not** rename or retire either. Every bespoke connector gets a
`SourceInstance` row whose `legacy_source_key` equals its existing `SourceType.value`, so
`etl_runs.source_name` continues to resolve and no historical run loses its lineage. This is the
conservation requirement for WP-2: **no run history is orphaned by the introduction of a new
identity.**

### 3.2 `SourceContractVersion` — immutable, versioned, validated

```text
source_contract_version_id  UUID PK
source_instance_id          UUID FK
version                     INTEGER          -- monotonic per instance
connector_type              TEXT             -- rest | csv | rss (RUNTIME_CONNECTOR_TYPES)
record_type                 TEXT             -- a RecordType
transport                   JSONB            -- url, pagination, page_size, max_pages, timeout
mapping                     JSONB            -- field_map, identifiers_map, external_id_field, records_path
schema_contract             JSONB            -- must_capture[], types, required identifiers
credential_refs             JSONB            -- REFERENCES ONLY (§7)
egress_allowlist            TEXT[]           -- pinned hosts (Phase B C-07)
rights                      JSONB            -- §3.4
cadence                     JSONB            -- CronTrigger kwargs
sla_days                    INTEGER          -- feeds scheduler/config.py FRESHNESS_SLA_DAYS
trust_tier                  INTEGER          -- 1..3, as migration 099
contract_hash               TEXT             -- sha256 of the canonical body
authored_by, authored_at
validator_version           TEXT             -- which validator admitted it
UNIQUE (source_instance_id, version)
```

**Immutability is enforced structurally, not by convention:** no `UPDATE` path exists in the
service; an edit inserts version N+1. A DB trigger or an append-only guard rejects mutation of a
row that any deployment or run references. Rationale — Phase A found the *current* contract row
(migration 099) is mutable in place, so a run cannot be tied to the configuration that produced it.

### 3.3 `SourceDeployment` — which version is live, where

```text
deployment_id               UUID PK
source_instance_id          UUID FK
source_contract_version_id  UUID FK
environment                 TEXT     -- draft | staging | prod
state                       TEXT     -- see §5.2
execution_enabled           BOOLEAN  -- THE GATE (§5.2)
approved_by, approved_at
superseded_by               UUID NULL
```

Separating deployment from contract is what lets the §13.3 sequencing rule be *mechanically true*
rather than a promise: a contract can be authored, validated, versioned and deployed with
`execution_enabled = FALSE` before safe fetch exists. There is no code path that fetches from a
deployment with the flag false — the flag is checked in the fetch primitive, not only in the UI.

### 3.4 `SourceCertification` — a purpose-scoped policy decision, not a score

Names and semantics adopted from TIV2-020 §3.1.

```text
source_instance_id + source_contract_version_id
purpose              TEXT   -- discovery | evidence | decision | restricted_internal
allowed_record_types TEXT[]
allowed_predicates   TEXT[]
allowed_jurisdictions TEXT[]
rights_policy_version_id UUID
redistribution_class TEXT
certifier, certification_evidence
effective_from, effective_to, review_due_at
status               TEXT   -- active | expired | revoked
```

**Not a quality number.** This is deliberate and it corrects a known live defect: QUAL-001 found
`source_registry.recompute_quality` silently filling missing dimensions with `0.5`, producing a
composite score that reads as a judgement while measuring nothing. A certification is a typed,
expiring, purpose-scoped decision with a named certifier — it cannot be produced by averaging.
One source may be `discovery`-grade and never `decision`-grade.

> **Ownership note:** `services/source_registry.py` is contested — open **PR #324** (QUAL-001) owns
> it. WP-2 does not touch it until #324 lands (COORDINATION §13.1).

### 3.5 `Rights` envelope

```text
rights_policy_version_id  UUID
licence_id / licence_text
retention_class           TEXT  -- how long raw bytes may be kept (WP-1 consumes)
redistribution_class      TEXT  -- may this leave the tenant / appear in an export
data_classification       TEXT  -- public | licensed | internal | restricted
permitted_purposes        TEXT[]
attribution_required      BOOLEAN
```

Rights are **contract-versioned**, so a licence change is a new contract version and every
artefact fetched under the old one keeps its original envelope. TIV2 principle 10 requires the
envelope to propagate into prompts, indexes, API, exports and MCP; WP-2's job is only to make it
*exist and be immutable at the point of capture*.

## 4. Identity and provenance threading

The Phase A finding was that `source_id` is authored at the connector edge and dropped at the
pipeline boundary — a stranded identifier structurally identical to WP-4's stranded molecule IDs.
WP-2 threads it, using the §1.3 glossary names:

| Layer | Today | After WP-2 |
|---|---|---|
| `ConnectorSpec.to_config()` | sets `config.source_id`, used for logs (`connectors/spec.py:172`) | carries `source_instance_id` + `source_contract_version_id` |
| `Provenance` (`connectors/base.py:143-162`) | `source_type, api_endpoint, query_params, retrieved_at, raw_response_hash, etl_run_id` | **+ `source_instance_id`, `source_contract_version_id`** |
| `_create_etl_run` (`integration/pipeline.py:491-504`) | `source_type.value`, `""`, `"{}"` | **+ instance id, contract version id, resolved endpoint, real query params, `code_git_sha`, cursor-before** |
| `_finalize_etl_run` (`:549-580`) | counts + `outcome` | **+ cursor-after, truncation, per-stage outcomes** |
| Scheduler (`scheduler/runner.py:748,814-827`) | watermark keyed on `source_name` | keyed on `source_instance_id` with a durable cursor (§6) |
| Catalog | `DATASET_DEFINITIONS` static list | integrity gate over registry + deployments + schedules (§9.4) |

**Naming rule (Phase A §1.2–1.3):** never `source_id` inside `integration/` —
`integration/cross_linker.py` already uses that name at 25 sites for a graph-edge endpoint.
`source_instance_id` at the pipeline/provenance boundary; `sources.source_id` remains the legacy
TEXT registry key, mapped explicitly via `legacy_source_key`.

## 5. State machines

### 5.1 Contract lifecycle

```text
draft ──validate──▶ valid ──deploy──▶ deployed ──supersede──▶ superseded
  │                   │                   │
  └──reject───────────┘                   └──revoke──▶ revoked
```

- `validate` is deterministic (§10). A rejection carries a typed diagnostic code, never a score.
- Nothing is deleted. `superseded` and `revoked` are terminal but readable — the conservation rule.

### 5.2 Deployment state — where the execution gate lives

```text
registered ──approve──▶ approved ──enable──▶ live ──disable──▶ paused
     │                                          │
     └──────────────────────────────────────────┴──rollback──▶ rolled_back
```

`execution_enabled` may only become `TRUE` when **all** hold, checked deterministically at the
fetch primitive:

1. deployment state is `approved` or `live`;
2. the contract version passed validation under a validator version that is still current;
3. an active `SourceCertification` exists for the requested purpose;
4. **the safe-fetch boundary is present and enabled** (Phase B C-01…C-15);
5. every `credential_ref` resolves.

Failing any of these is a **fail-closed refusal**, not a downgrade. This is the mechanism that
makes "contracts may land with execution disabled" enforceable rather than aspirational.

### 5.3 Run outcome — extend, do not replace

`classify_run_outcome` (`integration/pipeline.py:125-168`) is already a good pure Lane-1 gate
(`LANDED` / `NO_CHANGE` / `ZERO_ROWS` / `PARTIAL`), and migration 098 already persists
`records_skipped` / `records_failed` (Phase A drift finding). WP-2 **feeds it new inputs**; it does
not introduce a second outcome vocabulary:

| New input | Why |
|---|---|
| `truncated` | Phase A: `truncated` is a local variable in `rest_connector.py:383-441` that never escapes `fetch()`, so a truncated run finalizes clean and the watermark advances past unfetched data |
| `cursor_advanced` | a run that fetched nothing but moved the cursor is a distinct failure |
| `contract_validation_failed` | a deployed contract that stopped validating |
| `credential_unresolved` | distinguishes "secret missing" from "source down" |
| `egress_refused` | a safe-fetch rejection is not a source outage |

**Coordination requirement:** WP-0 owns this function. WP-2 must not fork it — the two specs share
one outcome vocabulary, agreed in COORDINATION before either lands.

### 5.4 Health state

Lane 2 only (`scripts/connector_health.py`, protected surface). A contract declares `sla_days`;
the health gate reads it per **instance**, not per enum member — which is what makes ten REST
sources individually observable instead of sharing one enum's history.

## 6. Durable cursors, leases, jobs

Phase A confirmed: the watermark is the previous run's `completed_at`
(`scheduler/runner.py:814-827`), there is **no lease anywhere** in `scheduler/`, and `fetch()`
returns a fully materialised list.

### 6.1 Cursor

```text
source_instance_id PK
cursor_kind      TEXT   -- source_native | max_accepted_timestamp | page_token
cursor_value     TEXT
advanced_at, advanced_by_run_id
last_good_value  TEXT   -- rollback target
```

Rules:
1. The cursor advances **only** on a terminal outcome that asserts completeness. `truncated`,
   `PARTIAL`, `egress_refused` and `credential_unresolved` all **hold** the cursor.
2. Advancing is part of the same transaction as run finalisation, or it does not happen.
3. `last_good_value` makes rollback a data operation, not a manual SQL fix.

### 6.2 Lease

A Postgres advisory lock (or a `source_leases` row with a fencing token) keyed on
`source_instance_id`, with a TTL and heartbeat. Multi-instance deployments currently each start
their own scheduler with no coordination — two processes can run the same source concurrently and
double-count. The lease is the minimum fix; full streaming/batching is **WP-9**, not WP-2.

### 6.3 Job record

Every scheduled or manual execution produces a job row referencing
`deployment_id + contract_version_id + cursor_before`, so a run is reproducible from stored state
rather than from whatever the config happened to be at the time.

## 7. Secret boundary

Per Phase B (C-10…C-14), and correcting the partial mitigation Phase A found
(`_SECRET_CONFIG_KEYS` covers exactly three top-level keys; nested headers, query params, URL
userinfo and unrecognised keys all survive — reproduced by probe):

1. **`credential_ref`, not credentials.** The contract stores
   `{"credential_ref": "src/<source_instance_id>/token"}`. The config dataclasses lose their
   plaintext `auth_token` / `auth_password` / `api_key` fields entirely.
2. **Allowlist-shaped projection, not denylist stripping.** The persisted contract is built by
   projecting *declared, non-secret* fields, so an unknown key is dropped by construction.
3. **Reject, don't strip.** A contract submitted with inline credentials is rejected with a
   diagnostic. Silent stripping is precisely how the nested-secret bypass hid behind a passing test.
4. **URL userinfo is a validation error**, detected by parsing rather than substring search.
5. **One redaction helper** applied at every egress of the contract itself: logs, `ConnectorError`
   messages, API responses, catalog UI, and any git-tracked spec file.

The resolver is deliberately unspecified here (env, cloud secret manager, or a `secrets` table with
restricted grants) — it is an owner deployment decision (§13). What is specified is that **no code
path may read a credential from the contract body**, because none exists there.

## 8. No-write discovery and preview

The wizard/chat flow needs to show a user what a source will produce *before* anything is stored.
This is the highest-risk surface in the whole lane — it is a user-triggered outbound fetch — so it
is specified as strictly as production execution.

**Discovery** (`POST /hub/sources/{id}/discover`) fetches one bounded page and returns inferred
field names, types and cardinality. **Preview** (`POST /hub/sources/{id}/preview`) applies a
candidate mapping to that same fetched payload and returns transformed records.

Invariants:

1. **No write of any kind** — no `etl_runs` row, no entity, no cursor advance, no DLQ. Enforced by
   running the pipeline's transform stages against an in-memory sink, not by discipline.
2. **Runs through the same safe-fetch primitive** as production (Phase B C-06). A preview is not
   a lower-security path; historically that is exactly where SSRF hides.
3. **Requires `execution_enabled`** on a deployment, so preview cannot be used to bypass §5.2.
4. **Bounded**: one page, a hard byte cap, a hard wall-clock, and a rate limit per principal.
5. **Redacted**: the response passes the §7 redaction helper.

### 8.1 Preview response contract

```jsonc
{
  "preview_id": "uuid",
  "source_instance_id": "uuid",
  "source_contract_version_id": "uuid",
  "executed_at": "2026-08-15T10:00:00Z",
  "fetch": {
    "resolved_host": "api.example.org",     // post-validation, pre-pin
    "status_code": 200,
    "byte_size": 18422,
    "truncated": false,
    "page_count": 1
  },
  "schema_inference": [
    {"field": "brand_name", "inferred_type": "string", "null_rate": 0.02, "sample": "Ozempic"}
  ],
  "records": [
    {"external_id": "…", "mapped": {"generic_name": "semaglutide"}, "unmapped_fields": ["ndc11"]}
  ],
  "diagnostics": [
    {"code": "MAPPING_TARGET_UNKNOWN", "severity": "error", "field": "foo", "message": "…"}
  ],
  "conservation": {
    "records_in_page": 50, "records_mapped": 48,
    "records_dropped": 2, "drop_reasons": {"missing_external_id": 2}
  },
  "would_persist": false
}
```

`conservation` is mandatory and is the reason the block exists: a preview that silently drops rows
teaches the author that the mapping is complete. **Dropped rows are counted and reasoned in the
response**, matching the conservation-before-correctness principle.

## 9. Database design

**No migration number is reserved.** SPEC-003 §9 requires the number to be reserved at
implementation time via COORDINATION §7.4; the highest existing is `099`. Reserving now would
collide with whatever lands during H1/H2.

### 9.1 New tables

`source_instances` · `source_contract_versions` · `source_deployments` ·
`source_certifications` · `source_rights_policies` · `source_cursors` · `source_leases`

### 9.2 Evolution of migration 099 — not replacement

Migration 099 added `config`, `field_mappings`, `record_type`, `trust_tier`, `must_capture`,
`license`, `cadence` to `source_onboarding`. WP-2 does **not** drop those columns. The migration:

1. creates the new tables;
2. **backfills** one `source_instances` row per existing `sources` row and one
   `source_contract_versions` row (version 1) per non-empty `source_onboarding` contract;
3. leaves the 099 columns readable, marked deprecated in `SCHEMA.md`;
4. cleanup is a **separate later PR** with its own evidence (SPEC-003 §9 shadow → dual-read →
   reversible flag → cutover → separate cleanup).

Backfill is a conservation event: the migration reports rows in, rows created, rows skipped and
why. A silent partial backfill is the failure mode to design against.

### 9.3 `list_runnable_sources()` — fix the field omission

Phase A: it selects `source_id, display_name, connector_type, record_type, config, cadence,
trust_tier` and **omits `field_mappings`, `must_capture`, `license`** — exactly the
contract-enforcement and governance fields. WP-2 re-points it at
`source_deployments ⋈ source_contract_versions` and returns the full contract, including
`execution_enabled` so the caller cannot forget to check it.

### 9.4 Catalog integrity gate

Phase A correction: a best-effort join already exists (`services/connector_registry.py:135`
iterates `CONNECTOR_REGISTRY` and joins schedules + dataset metadata), but it ignores dynamic
sources and enforces nothing. WP-2 adds a **Lane-1 integrity assertion**: every live deployment has
a registry entry, a schedule, an SLA and a certification; every catalog entry resolves to a live
deployment; no orphans in either direction. A mismatch fails the gate.

## 10. Validation — deterministic, typed, versioned

One validator, versioned (`validator_version` on the contract). Every rejection is a typed code,
never a score, never model output:

| Class | Examples |
|---|---|
| Transport | `URL_SCHEME_FORBIDDEN`, `URL_USERINFO_PRESENT`, `HOST_NOT_ALLOWLISTED`, `LOCAL_PATH_FORBIDDEN` |
| Secret | `INLINE_CREDENTIAL_PRESENT`, `CREDENTIAL_REF_UNRESOLVABLE` |
| Mapping | `MAPPING_TARGET_UNKNOWN`, `EXTERNAL_ID_FIELD_MISSING`, `RECORDS_PATH_INVALID` |
| Schema | `MUST_CAPTURE_UNMAPPED`, `IDENTIFIER_NAMESPACE_UNKNOWN` |
| Rights | `LICENCE_MISSING`, `RETENTION_CLASS_UNKNOWN`, `PURPOSE_NOT_CERTIFIED` |
| Structural | `NO_CALLABLE_IN_CONTRACT` (SPEC-003 §8), `UNKNOWN_FIELD` |

`NO_CALLABLE_IN_CONTRACT` is the structural expression of the standing invariant: the contract
grammar is closed, so there is no field into which arbitrary SQL or Python could be written.

**Where the LLM is permitted:** proposing a draft contract from a URL or a sample payload, and
suggesting field mappings. Its output enters the pipeline **exactly like a hand-typed draft** —
through the same validator, with no elevated trust, no confidence threshold that skips a check, and
no path to `execution_enabled`.

## 11. API / OpenAPI delta

Additive, on the existing `api/routes/hub.py` router (owned by this lane, COORDINATION §13.1).
**`api/routes/sources.py` is contested (PR #320 / #56) and is not touched by WP-2.**

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/hub/sources` | create a `SourceInstance` |
| `GET` | `/hub/sources/{id}` | instance + current deployment + certification summary |
| `POST` | `/hub/sources/{id}/contracts` | submit a contract → validate → version N+1 |
| `GET` | `/hub/sources/{id}/contracts` | version history (immutable) |
| `GET` | `/hub/sources/{id}/contracts/{ver}/diff` | contract-version diff |
| `POST` | `/hub/sources/{id}/discover` | no-write schema discovery (§8) |
| `POST` | `/hub/sources/{id}/preview` | no-write transformation preview (§8) |
| `POST` | `/hub/sources/{id}/deployments` | deploy a version, `execution_enabled=false` |
| `POST` | `/hub/deployments/{id}/approve` | approval (independent principal, §12) |
| `POST` | `/hub/deployments/{id}/enable` · `/disable` | the execution gate |
| `POST` | `/hub/deployments/{id}/rollback` | supersede with a prior version + cursor rollback |
| `GET` | `/hub/deployments/{id}/audit` | append-only audit trail |
| `POST` | `/hub/sources/{id}/certifications` | issue/revoke a certification |

**OpenAPI discipline (H3):** `schema/openapi.json` is protected from this lane. WP-2 states the
delta here and the regen is coordinated with the H3 reconcile owner — the drift (381↔518 operations)
is exactly why an unreviewed regen from this lane would be harmful.

## 12. Promotion, approval, rollback, audit

- **Promotion** is a state transition on `SourceDeployment`, never an edit to a contract.
- **Approval requires a principal distinct from the author.** This is the honest weak point:
  worktree agents currently run under the owner's git identity, so authorship separation is
  discipline, not structure (`conservation-gates.md`, "Reviewer identity"). WP-2 records
  `authored_by` and `approved_by` separately and a Lane-1 test asserts they differ — which makes
  the violation *visible* even while identity separation is unenforced.
- **Rollback** re-deploys a prior contract version and restores `source_cursors.last_good_value`.
  Nothing is deleted; the superseded deployment stays queryable.
- **Audit** is append-only: contract submitted / validated / rejected (with codes) / deployed /
  approved / enabled / disabled / rolled back / certified / revoked, each with principal, timestamp
  and `code_git_sha`.
- **Tenancy** is the recorded cross-lane seam (COORDINATION §10.1 A4): Data adds `owner_id` /
  `tenant_id`, Product-Platform enforces it in routes. WP-2 carries the column and does **not**
  implement enforcement.

## 13. Explicitly out of scope

Named so they are not assumed covered:

- **Streaming/batched ingestion** — bounded iterators, memory pressure → **WP-9**.
- **Secret-store selection** — an owner deployment decision (§7).
- **`DomainPack` activation** — dormant in the whole ingestion path (Phase A G-07) → **WP-3**.
- **Untrusted fetched content reaching synthesis** as instructions → **WP-5** (Phase B T-20).
- **Source poisoning / quality as a promotion gate** → **WP-8** (Phase B T-19).
- **Net-new connector breadth** — paused by SPEC-003 §3 regardless.
- **`services/source_registry.py`, `api/routes/sources.py`, `connectors/`** — contested or
  protected until #324/#320/#66 land and WP-1 releases `BaseConnector` (COORDINATION §13.1).

## 14. Open questions for the owner

1. **Secret resolver** — env vars, a cloud secret manager, or a restricted-grant table? Changes
   §7's resolver and the deployment story, nothing else.
2. **Preview authorisation** — which principals may trigger an outbound fetch, at what rate? It is
   a user-triggered egress and therefore a security decision, not a UX one.
3. **Certification authority** — who may issue a `decision`-grade certification, and does it require
   the same independence as approval (§12)?
4. **Egress allowlist default** — deny-by-default with per-contract opt-in (recommended), or
   allow-public-deny-private? The former is stricter and slower to onboard.
5. **Legacy bespoke connectors** — do all 15 get a `SourceInstance` in the backfill (recommended,
   for uniform lineage), or only the generic ones?

## 15. Acceptance

Per COORDINATION §13.4, this lane makes **no commitment to PR #327's current artifact design**.
Acceptance criteria for WP-2 implementation must be **owner-ratified before implementation** under
whatever corrected WP-12 protocol lands; the builder must not self-author or modify its merge bar.
The candidate successor protocol (`specs/trusted_intelligence_v2/templates/V2_REVIEW_REQUEST.md`,
exact-SHA review requests with controller-resolved actor identity) is noted but **not adopted
here** — adopting an unratified protocol would repeat the mistake §13.4 exists to prevent.

Test specifications, golden fixtures, invariants and mutation cases: `WP-2_test_specifications.md`.
Executable tests are introduced inside the implementation PR that turns them GREEN.
