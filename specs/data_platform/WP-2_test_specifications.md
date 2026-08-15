# WP-2 — Test specifications, invariants and golden fixtures (Phase C)

**Status:** Specifications only. **No executable tests in this branch** — a spec-only branch that
merged intentionally-red tests would be a standing *vacuous red*, the mirror of a vacuous green
(COORDINATION §13.3). Each case below becomes an executable RED test **inside the implementation
PR that turns it GREEN**, in the slice named in the Slice column.

**Companion documents:** `WP-2_source_contract_control_plane.md` (the spec),
`WP-2_safe_fetch_threat_model.md` (§7 already specifies the 11 safe-fetch mutation cases —
**not duplicated here**), `WP-2_findings_reverification.md` (verified baseline state).

**Lane assignment** (`conservation-gates.md`): every case below is **Lane 1** — deterministic,
DB-free or seeded, PR-blocking — unless marked **Lane 2**. No live-source dependency may enter a
PR gate.

---

## 1. Invariants (the properties, stated so they can be falsified)

| ID | Invariant | Why it exists |
|---|---|---|
| **INV-01** | Every `etl_runs` row written after cutover resolves to exactly one `source_instance_id` **and** one `source_contract_version_id` | G-01: today the run identity is `source_type.value` with a blank endpoint |
| **INV-02** | No historical `etl_runs` row is orphaned by the identity migration | Conservation: the backfill must not break lineage for 15 bespoke connectors |
| **INV-03** | A contract version row is never updated after any deployment or run references it | Immutability is the point of versioning |
| **INV-04** | No outbound request occurs for a deployment with `execution_enabled = FALSE` | Makes the §13.3 sequencing rule mechanical |
| **INV-05** | The persisted contract contains no credential-shaped value, at any nesting depth | Phase A probe: the 3-key denylist leaks 4 ways |
| **INV-06** | The cursor advances only on a terminal outcome asserting completeness | G-10: a truncated run currently advances the watermark |
| **INV-07** | Two schedulers cannot execute one source instance concurrently | G-10: no lease exists anywhere in `scheduler/` |
| **INV-08** | Discovery and preview write nothing — no run, entity, cursor, or DLQ row | Preview is user-triggered egress |
| **INV-09** | Every dropped row in a preview is counted and reasoned in the response | Conservation before correctness |
| **INV-10** | `authored_by ≠ approved_by` on every approved deployment | Separation of authorship |
| **INV-11** | Every live deployment has a registry entry, schedule, SLA and active certification; and every catalog entry resolves to a live deployment | G-12: the existing join enforces nothing |
| **INV-12** | A certification is typed and expiring; no code path derives one from a numeric score | Corrects the QUAL-001 `0.5`-filler defect class |
| **INV-13** | WP-2 emits no run outcome outside WP-0's vocabulary | One outcome vocabulary, not two |
| **INV-14** | The contract grammar is closed — no field accepts a callable, SQL, or arbitrary expression | SPEC-003 §8 |

## 2. Mutation cases

Each must be **RED before** the control lands and **GREEN after**. A case that cannot be made RED
is not a test — it is decoration, and should be reported as such rather than counted.

### 2.1 Identity threading

| # | Mutation | Expected | Slice |
|---|---|---|---|
| M-01 | Remove `source_instance_id` from `Provenance` | RED — provenance completeness assertion | identity |
| M-02 | Write an `etl_runs` row with a null contract version | RED — INV-01 | identity |
| M-03 | Point two contract versions at one `(instance, version)` pair | RED — unique constraint | identity |
| M-04 | Run the backfill against a fixture where one `sources` row has no onboarding contract | GREEN, and the migration **reports** the skip with a reason — a silent partial backfill is the failure being designed against | identity |
| M-05 | Rename `source_instance_id` → `source_id` anywhere under `integration/` | RED — a naming guard, because `cross_linker.py` uses that name for graph-edge endpoints at 25 sites | identity |

### 2.2 Contract immutability and validation

| # | Mutation | Expected | Slice |
|---|---|---|---|
| M-06 | `UPDATE source_contract_versions` on a referenced row | RED — INV-03 | contracts |
| M-07 | Submit a contract with an unknown top-level field | RED — `UNKNOWN_FIELD` | contracts |
| M-08 | Submit a contract embedding a Python/SQL expression in any field | RED — `NO_CALLABLE_IN_CONTRACT`, INV-14 | contracts |
| M-09 | Submit a contract whose `must_capture` names an unmapped field | RED — `MUST_CAPTURE_UNMAPPED` | contracts |
| M-10 | Bump `validator_version` and re-validate every stored contract | Every previously-valid contract either revalidates or is flagged — **never silently downgraded** | contracts |

### 2.3 The execution gate

| # | Mutation | Expected | Slice |
|---|---|---|---|
| M-11 | Call the fetch primitive for a deployment with `execution_enabled = FALSE` | RED — refused, INV-04. Asserted at the **primitive**, not the route, so a new caller cannot bypass it | safe-fetch |
| M-12 | Enable execution with no active certification for the requested purpose | RED — `PURPOSE_NOT_CERTIFIED` | certification |
| M-13 | Enable execution with the safe-fetch boundary absent/disabled | RED — fail-closed | safe-fetch |
| M-14 | Enable execution with an unresolvable `credential_ref` | RED — `CREDENTIAL_REF_UNRESOLVABLE`, distinct from "source down" | secrets |

### 2.4 Secrets — the Phase A probe, inverted into a gate

The exact config that survived stripping at `da6887c` must now be **rejected**:

```python
{
  "url": "https://user:pass@example.com/data",   # M-15 URL_USERINFO_PRESENT
  "auth_token": "TOPLEVEL",                       # M-16 INLINE_CREDENTIAL_PRESENT
  "headers": {"Authorization": "Bearer NESTED"},  # M-17 nested — currently survives
  "query_params": {"api_key": "QUERY"},           # M-18 nested — currently survives
  "auth_secret": "UNRECOGNISED-KEY",              # M-19 unknown key — currently survives
}
```

| # | Expected | Slice |
|---|---|---|
| M-15…M-19 | Each rejected with its typed code. **Rejected, not stripped** — silent stripping is how this bypass hid behind a passing test | secrets |
| M-20 | Assert the persisted projection contains no value from the above at any depth (INV-05) | secrets |
| M-21 | Trigger a `ConnectorError` on a userinfo URL; assert no credential appears in the message, logs, API response, or catalog payload | secrets |
| M-22 | Add a **new** credential-shaped field to a config dataclass | RED — the projection is allowlist-shaped, so an undeclared field cannot reach storage | secrets |

M-22 is the important one: it proves the fix is structural rather than a longer denylist.

### 2.5 Cursors, leases, outcomes

| # | Mutation | Expected | Slice |
|---|---|---|---|
| M-23 | Finish a run with `truncated = True` | Cursor does **not** advance (INV-06); the run's terminal outcome reflects truncation — not a log line | cursors |
| M-24 | Kill the process between store and finalise | Cursor unchanged on restart — advance and finalise share one transaction | cursors |
| M-25 | Start two schedulers against one instance | Exactly one acquires the lease; the other declines cleanly (INV-07) | cursors |
| M-26 | Expire a lease mid-run, then let the original holder finalise | Fencing token rejects the stale writer | cursors |
| M-27 | Roll back a deployment | Cursor restored to `last_good_value`; superseded rows remain queryable, nothing deleted | promotion |
| M-28 | Emit an outcome string not in WP-0's vocabulary | RED — INV-13 | outcomes |

### 2.6 Discovery and preview

| # | Mutation | Expected | Slice |
|---|---|---|---|
| M-29 | Run preview; assert zero rows written to `etl_runs`, entities, `source_cursors`, DLQ | INV-08, asserted by row counts before/after | preview |
| M-30 | Preview a payload where 2 of 50 records lack an external id | Response reports `records_dropped: 2` with reasons; INV-09 | preview |
| M-31 | Preview against a private-IP URL | Refused by the **same** safe-fetch primitive as production (threat-model C-06) | preview |
| M-32 | Preview a response exceeding the byte cap | Bounded, refused, reported — not truncated silently | preview |
| M-33 | Preview on a deployment with `execution_enabled = FALSE` | RED — preview cannot bypass the gate | preview |

### 2.7 Promotion, audit, catalog

| # | Mutation | Expected | Slice |
|---|---|---|---|
| M-34 | Approve a deployment as its own author | RED — INV-10 | promotion |
| M-35 | Delete or update an audit row | RED — append-only | promotion |
| M-36 | Delete a certification instead of revoking it | RED — supersede, don't delete | certification |
| M-37 | Create a live deployment with no schedule / SLA / certification | RED — INV-11 | catalog |
| M-38 | Leave a catalog entry pointing at a superseded deployment | RED — INV-11, both directions | catalog |
| M-39 | Derive a certification from a numeric quality score | RED — INV-12 | certification |

### 2.8 Anti-vacuous guards (the gate that guards the gate)

Following the `test_lane1_suite_is_not_vacuous()` pattern already in
`tests/test_conservation_gates.py`:

| # | Case |
|---|---|
| M-40 | The WP-2 suite asserts it is non-empty and that each named invariant has at least one executing test — deleting a test turns the gate **red**, not green |
| M-41 | The validator self-test proves it can still reject (a known-bad fixture must fail) on every run, so a broken validator cannot read as "all contracts valid" |
| M-42 | The catalog integrity gate asserts it examined >0 deployments |

## 3. Golden fixtures

Under `tests/connector_platform/fixtures/` (new tree, this lane's owned surface).

**Valid:**
- `rest_minimal.json` — REST contract, `credential_ref`, single-host allowlist, no pagination
- `rest_paginated.json` — cursor pagination, `max_pages`, declared SLA and rights
- `csv_upload.json` — CSV via upload identifier, **no `path` field** (§8/C-08)
- `rss_feed.json` — RSS, public source, `discovery` certification only

**Rejected** — one per validation code, each paired with its expected diagnostic:
`URL_SCHEME_FORBIDDEN` · `URL_USERINFO_PRESENT` · `HOST_NOT_ALLOWLISTED` · `LOCAL_PATH_FORBIDDEN` ·
`INLINE_CREDENTIAL_PRESENT` · `CREDENTIAL_REF_UNRESOLVABLE` · `MAPPING_TARGET_UNKNOWN` ·
`EXTERNAL_ID_FIELD_MISSING` · `RECORDS_PATH_INVALID` · `MUST_CAPTURE_UNMAPPED` ·
`IDENTIFIER_NAMESPACE_UNKNOWN` · `LICENCE_MISSING` · `RETENTION_CLASS_UNKNOWN` ·
`PURPOSE_NOT_CERTIFIED` · `NO_CALLABLE_IN_CONTRACT` · `UNKNOWN_FIELD`

**Payloads:** a recorded upstream response per connector type, plus one hostile payload
(cursor pointing at an absolute private-host URL — threat-model T-07) and one oversized payload.
All recorded and committed — **no live network in any Lane-1 test.**

**Migration:** a seeded `sources` + `source_onboarding` state for the backfill, including one row
with no contract (M-04) and one bespoke connector with existing `etl_runs` history (INV-02).

## 4. API examples

```http
POST /hub/sources/{id}/contracts
```
```jsonc
{
  "connector_type": "rest",
  "record_type": "drug_label",
  "transport": {"url": "https://api.example.org/v1/labels", "pagination": "cursor",
                "cursor_path": "meta.next", "page_size": 100, "max_pages": 50},
  "mapping": {"records_path": "results", "external_id_field": "id",
              "field_map": {"brand_name": "brand_name", "generic_name": "generic_name"}},
  "schema_contract": {"must_capture": ["external_id", "generic_name"]},
  "credential_refs": {"auth_token": "src/1f3c…/token"},
  "egress_allowlist": ["api.example.org"],
  "rights": {"licence_id": "CC-BY-4.0", "retention_class": "indefinite",
             "redistribution_class": "attribution_required", "data_classification": "public"},
  "cadence": {"hour": "*/12"},
  "sla_days": 2
}
```

**201** → `{"source_contract_version_id": "…", "version": 3, "contract_hash": "sha256:…", "state": "valid"}`

**422** → typed diagnostics, never prose:
```jsonc
{"state": "rejected", "diagnostics": [
  {"code": "INLINE_CREDENTIAL_PRESENT", "pointer": "/transport/headers/Authorization",
   "message": "Credentials must be supplied as a credential_ref, not inline."},
  {"code": "HOST_NOT_ALLOWLISTED", "pointer": "/transport/url", "message": "…"}
]}
```

A rejection returns **every** diagnostic, not the first — an author fixing one error at a time
across five round-trips is how inline-credential habits form.

## 5. Lane 2 (scheduled, never PR-blocking)

| ID | Check |
|---|---|
| L2-01 | Every live deployment has fetched within its declared `sla_days`, **per instance** — not per `SourceType` enum member |
| L2-02 | No certification is past `review_due_at` without being expired |
| L2-03 | No cursor has been stationary beyond its cadence while runs report success |
| L2-04 | No lease is held beyond TTL by a dead process |
| L2-05 | Catalog integrity holds against the live DB (the Lane-1 version runs against seeded state) |

`scripts/connector_health.py` and `scheduler/config.py` are **protected surface**. Adding an SLA
entry for a new source is a permitted strengthening; loosening a threshold to pass is not, and
routes through the owner (`conservation-gates.md`).

## 6. Coverage honesty

Stated explicitly so this document cannot read as more coverage than it provides:

- **Safe-fetch cases live in the threat model** (§7, 11 cases). This document does not restate them
  and does not count them.
- **T-19** (source poisoning) and **T-20** (fetched content reaching synthesis as instructions) have
  **no cases here** — they are WP-8 and WP-5.
- **Streaming/memory-pressure** cases are **WP-9**; M-32 bounds a preview only.
- **Tenancy enforcement** has no cases here — WP-2 carries the column, Product-Platform enforces it
  (COORDINATION §10.1 A4).
- **INV-10 is asserted but not enforceable today** — worktree agents run under the owner's git
  identity, so the test makes a violation visible rather than impossible.
