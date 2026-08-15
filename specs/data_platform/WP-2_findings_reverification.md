# WP-2 — Findings re-verification (Phase A)

**Status:** Re-verification complete. Spec-only lane; no code changed.
**Verified against:** `claude/handoff/h0-baseline` @ `da6887c` (H0.3), read-only.
**Verification interval:** 2026-08-14 → 2026-08-15 (sweep started 08-14; commit and this
amendment dated 08-15 — the commit timestamp is the authoritative evidence date).
**Why this exists:** SPEC-003 §6 marks WP-2 **"pending re-verify"**, and SPEC-003 §3 ratifies
*"verify each finding against current code before speccing it."* The review
(`design-review-output/data_pipeline_deep_design_review_2026_08_07.md`) is dated 2026-08-07;
this record establishes which of its WP-2 claims still hold at the baseline, and records drift
rather than silently correcting it (COORDINATION §12 governance).

**Scope:** G-01, G-07, G-10, G-12, G-14 (the WP-2 coverage set, SPEC-003 §6).

## Verdict summary

| Finding | Verdict | Note |
|---|---|---|
| **G-01** source type used as source-instance identity | **CONFIRMED** | + a partial control plane already exists (§1.1) and a naming collision the review missed (§1.2) |
| **G-07** `DomainPack` / generic adapters not an operational plugin system | **CONFIRMED** | `DomainPack` dormant in the entire ingestion path; a connector factory *does* exist but has no caller |
| **G-10** incremental ingestion not checkpoint-safe | **CONFIRMED**, 1 sub-claim refined | truncation is now *detected*; it still cannot block cursor advancement |
| **G-12** run lineage + catalog metadata incomplete/static | **CONFIRMED w/ DRIFT** | skip/fail counts **are** now persisted (migration 098) — do not re-spec as absent; a best-effort catalog join already exists |
| **G-14** runtime-configured sources need a security boundary | **CONFIRMED**, widened | zero SSRF controls on the *shared* fetcher + arbitrary local-file read; secret stripping exists but is partial |

---

## G-01 — Source type is being used as source-instance identity → **CONFIRMED**

- `SourceType` is a closed enum — `connectors/base.py:58-82`. The generic kinds `CSV_FILE`,
  `RSS`, `REST` are enum members alongside the 15 bespoke sources.
- `CONNECTOR_REGISTRY: dict[SourceType, type[BaseConnector]]` — `connectors/__init__.py:28-45`.
  Keyed by the enum, so it structurally cannot host two REST sources.
- `_create_etl_run` — `integration/pipeline.py:491-504`:
  ```python
  INSERT INTO etl_runs (id, source_name, api_endpoint, query_params, status, started_at)
  VALUES (%s, %s, %s, %s, 'RUNNING', NOW())
  """, [run_id, source_type.value, "", "{}"],
  ```
  Confirms verbatim: `source_type.value` as the run's identity, **blank** endpoint, **`"{}"`**
  query params.
- Scheduler keys the watermark on that same value — `scheduler/runner.py:748`,
  `_get_last_success` at `:814-827`.
- `Provenance` — `connectors/base.py:143-162` — carries `source_type, api_endpoint,
  query_params, retrieved_at, raw_response_hash, etl_run_id`. **No `source_id`.**

**The precise shape of the gap:** `source_id` *does* exist, and is *required and validated*, on
every generic config — `CsvConfig.source_id` (`connectors/csv_connector.py:49,64-65`),
`RestConfig.source_id` (`connectors/rest_connector.py:68,112-113`), `RssConfig.source_id`
(`connectors/rss_connector.py:65,77`). It is validated, serialized by `ConnectorSpec`, and
injected into every generic config by `ConnectorSpec.to_config()`
(`connectors/spec.py:172` — `kwargs["source_id"] = self.source_id`).

Stated precisely: **`source_id` never escapes connector/spec construction into `RawRecord`,
provenance, ETL history, scheduling or catalog identity; its runtime semantic use inside the
adapters is limited to diagnostics.** Occurrence count by directory at `da6887c`: `connectors/`
26 · `scheduler/` **0** · `integration/knowledge_store.py` **0** · `api/routes/catalog.py` **0**.

So this is a **stranded identifier**, structurally identical to WP-4's stranded identity spine:
the value is authored at the connector edge and dropped at the pipeline boundary. WP-2 is a
*threading* problem, not an invention problem.

### 1.1 A partial control plane already exists (corrects the first draft of this record)

The first draft of this document described what WP-2 must introduce without recording what is
already built. That was a material omission — it would have licensed inventing parallel tables
and loaders. The corrected finding:

> **A partial mutable control plane and connector factory exist, but the scheduler never consumes
> them; the persisted contract is unversioned and the runnable query omits mappings,
> `must_capture` and licence fields.**

Verified at `da6887c`:

- **`schema/migrations/099_source_onboarding_contract.sql:19-35`** already persists the contract
  body: `config` JSONB, `field_mappings` JSONB, `record_type`, `trust_tier` (1-3, CHECKed),
  `must_capture TEXT[]`, `license`, `cadence` JSONB. Its own header states the intent — *"the
  scheduler rebuilds a ConnectorSpec from (display_name, connector_type, record_type, config) and
  runs it through the universal IntegrationPipeline."*
- **`services/connector_taxonomy.py:459-479`** — `list_runnable_sources()` already selects
  `prod`-status rows with a runtime connector type. But it selects only
  `source_id, display_name, connector_type, record_type, config, cadence, trust_tier` — it
  **omits `field_mappings`, `must_capture` and `license`**, i.e. exactly the contract-enforcement
  and governance fields 099 added.
- **`connectors/spec.py:175-190`** — `build_connector_from_spec()` already instantiates the
  existing generic adapters from a spec ("the dynamic loader that closes the register → it just
  runs gap").

**And the gap is wider than the review states:** `list_runnable_sources` and
`build_connector_from_spec` have **zero non-test callers** anywhere in the tree. The control
plane is built end-to-end — migration, query, factory — and simply has no consumer. `scheduler/`
contains no reference to `ConnectorSpec`, `build_connector_from_spec`, or `list_runnable_sources`.

**Load-bearing for WP-2 scope:** *evolve migration 099, `list_runnable_sources` and the spec
factory — do not invent a parallel contract table or a second loader.* The unversioned contract
row is what WP-2 makes immutable and versioned; the missing scheduler consumer is what WP-2
wires, behind the safe-fetch boundary.

### 1.2 Naming collision the review did not catch (new)

A raw `grep source_id integration/` returns 25 hits — **all false positives**. Every one is in
`integration/cross_linker.py` (`:100-620`), where `source_id` means *the source endpoint of a
graph edge* (`source_id` → `target_id` of an `entity_link`), an unrelated concept.

**Design constraint for WP-2:** do not introduce a source-instance `source_id` into
`integration/` under that bare name — it would silently collide with edge-endpoint semantics in
the one module most likely to be read by a future maintainer.

### 1.3 Identifier glossary (required by the spec — three distinct things share one name)

| Term | Meaning | Where it lives today |
|---|---|---|
| `source_instance_id` | **the ingestion source instance** — a deployed contract for one feed | proposed; today only `config.source_id` at the connector edge |
| `source_entity_id` | **knowledge-graph edge endpoint** — the source node of an `entity_link` | `integration/cross_linker.py` (25 sites, as `source_id`) |
| `source_id` (legacy) | existing API/DB column — `sources.source_id`, `source_onboarding.source_id` | migration 099, `connector_taxonomy.py`; **requires an explicit mapping**, not a rename |

The WP-2 spec carries this glossary. A bare `source_id` must not be threaded into `integration/`.

## G-07 — Not an operational plugin system → **CONFIRMED**

- **`DomainPack` is dormant in the entire ingestion path.** Non-test runtime references to
  `get_pharma_pack` / `DomainPack` exist in exactly three places —
  `services/agent/schema_introspector.py:13,27,29`, `services/domain_intelligence/validation.py:74-76`,
  `api/deps.py:327-328`. **Zero** references in `connectors/`, `integration/`, or `scheduler/`.
- **`KnowledgeStore` requires a hardcoded handler per `RecordType`** —
  `integration/knowledge_store.py:154-171`, an explicit 18-entry dict literal mapping each
  `RecordType` to a `_store_*` method. A new record kind is code, not config.
- **Generic adapters are absent from the runtime registry** — `CONNECTOR_REGISTRY`
  (`connectors/__init__.py:28-45`) contains the 15 bespoke connectors and *no* `CSV_FILE` / `RSS`
  / `REST` entry, despite those being enum members. **But** a second, parallel instantiation path
  *does* exist — `build_connector_from_spec()` (`connectors/spec.py:175-190`) — which has no
  non-test caller (§1.1). So the accurate statement is not "reachable only in tests" but *"two
  registration mechanisms exist; the enum-keyed one cannot express a source instance, and the
  spec-keyed one is never invoked."*

This is the strongest structural argument for WP-2 ordering: the generic connectors and their
loader are built and tested but unreachable in production, so WP-2 is mostly *wiring an existing
factory under a versioned contract*, not new adapter code.

## G-10 — Incremental ingestion not checkpoint-safe → **CONFIRMED** (one sub-claim refined)

| Sub-claim | Verdict | Evidence |
|---|---|---|
| `fetch()` returns an in-memory list | **CONFIRMED** | `connectors/base.py:230` — `def fetch(self, since=None) -> list[RawRecord]` |
| Watermark is the previous run's `completed_at` | **CONFIRMED** | `scheduler/runner.py:814-827` — `SELECT completed_at … ORDER BY completed_at DESC` |
| No distributed per-source lease | **CONFIRMED** | zero matches for `lease` / `advisory_lock` / `pg_try_advisory` under `scheduler/` |
| Retry ignores `Retry-After` | **CONFIRMED** | `connectors/base.py:261-305` — backoff is `(2 ** attempt) + random.uniform(0, 1)`; the header is never read, though 429 is in `retryable_codes` |
| Returns last retryable response after exhaustion | **CONFIRMED** | `connectors/base.py:305` — `return resp  # Return last response even if retryable` |
| No shared rate limiter / circuit breaker | **CONFIRMED** | per-call retry only; no cross-connector coordination |
| Truncation does not block cursor advancement | **CONFIRMED — but the review understates current state** | see below |

**Refinement (drift toward better).** Truncation *is* now detected: `rest_connector.py:408`
sets `truncated = True` on the `max_pages` cap, and `:428` adds a **stuck-cursor guard** (an
unchanged cursor stops the loop loudly) that the review predates. However `truncated` is a
**local variable that never escapes `fetch()`** — its only consumer is the log line at `:441`.
It is not a field on `PipelineResult` (`integration/pipeline.py:66-84`) and not a column on
`etl_runs`. A truncated run therefore still finalizes as a normal success and the
`completed_at` watermark still advances, silently skipping the untruncated remainder.

**Spec consequence:** the WP-2 contract must carry truncation as a *terminal-outcome input*, not
a log line. This is the same class as G-02's fail-open — a detected condition with no path to
the outcome.

## G-12 — Run lineage and catalog metadata → **CONFIRMED, with recorded DRIFT**

**Still true:**
- `etl_runs.api_endpoint` and `query_params` are written blank by the main pipeline —
  `integration/pipeline.py:503` (`"", "{}"`), as under G-01.
- `_finalize_etl_run` (`integration/pipeline.py:549-580`) writes no source-contract version, no
  transform version, no code SHA, no raw-input artifact reference, no output dataset version, no
  cursor before/after, and no truncation or per-stage outcome.
- Catalog definitions are static Python — `DATASET_DEFINITIONS` in
  `integration/dataset_catalog.py`, consumed by `services/connector_registry.py:8,23,47,52`.
  **Correction to the first draft of this record:** "nothing reconciles them" was too absolute.
  `services/connector_registry.py:135` (`list_connectors`) iterates `CONNECTOR_REGISTRY.keys()`
  and joins `CONNECTOR_SCHEDULES`, per-source config, last-run state and dataset metadata for
  display. The accurate gap is:

  > A best-effort static join exists for bespoke connectors, but it ignores dynamic onboarding
  > sources and has no integrity gate enforcing alignment across registry, schedules,
  > definitions, deployed contract versions and runtime state.

  That distinction matters: WP-2 adds an *integrity gate* over an existing display join, and
  extends it to the dynamic sources of §1.1 — it does not build a catalog from nothing.

**DRIFT — the review is stale here, matching the warning in COORDINATION §12:**
the claim "connector skip counts" are missing is **no longer true**. `_finalize_etl_run`
persists both, with an in-code note naming migration 098:

```python
records_skipped = %s,
records_failed  = %s,
```
`integration/pipeline.py:558-559`, values at `:573-575`. An `outcome` column is also written
(`:553`) from `classify_run_outcome`. **Do not re-spec `records_skipped` / `records_failed` as
absent** — WP-2 extends this surface, it does not introduce it.

## G-14 — Runtime-configured sources need a security boundary → **CONFIRMED**

**Corrected secret finding.** The first draft of this record claimed *"any contract persisted or
displayed carries live credentials."* That is **wrong** — a partial mitigation exists.
`services/connector_taxonomy.py:356-366` defines
`_SECRET_CONFIG_KEYS = ("auth_token", "auth_password", "api_key")` and `_strip_secret_config()`
removes them before persistence, and a focused test covers it. The accurate finding:

> **Runtime connector objects still accept plaintext credentials. Persistence strips three exact
> top-level keys, but nested headers, query parameters, URL userinfo and unrecognised credential
> fields survive. No `credential_ref` model or runtime secret resolver exists.**

Independently reproduced at `da6887c` (not taken from the review) —
`python -c "from services.connector_taxonomy import _strip_secret_config; ..."`:

```
stripped keys : ('auth_token', 'auth_password', 'api_key')
dropped       : ['auth_token']
PERSISTED     :
    url = https://user:pass@example.com/data          ← URL userinfo survives
    headers = {'Authorization': 'Bearer NESTED'}      ← nested header survives
    query_params = {'api_key': 'QUERY'}               ← nested query param survives
    auth_secret = UNRECOGNISED-KEY                    ← unlisted credential key survives
```

The runtime side is unmitigated: `RestConfig` (`connectors/rest_connector.py:88-95`) declares
`auth_token`, `auth_username`, `auth_password`, `api_key` as direct `Optional[str]` fields,
consumed verbatim in `_build_auth()` at `:333-342`
(`headers["Authorization"] = f"Bearer {c.auth_token or ''}"`).

**Two attack surfaces, not one.** The first draft searched only the REST/RSS connector files and
so under-scoped the finding. Both of these are in scope for the Phase B threat model:

- **Network SSRF — the *shared* fetcher, not just REST.** `connectors/base.py:284` performs
  `requests.get(url, params=params, timeout=timeout, headers=headers)` with no restriction, and
  it is inherited by **every** connector. A grep for
  `ssrf|ipaddress|is_private|allowlist|allowed_host|urlparse` across the REST and RSS connectors
  returns **no matches**: no host allowlist, no private/link-local/loopback rejection, no scheme
  restriction, no redirect-chain re-validation, no DNS-rebinding defense, no egress proxy.
  `config.url` is fetched as given (`RestConfig.url`, `:71` — there is **no** `base_url` field).
- **Local-file disclosure.** `connectors/csv_connector.py:197-204` — `_load_text()` accepts an
  arbitrary server-local `config.path`, checks only `os.path.exists`, then
  `open(self.config.path, "r", ...)`. A contract authored through the wizard can therefore read
  any file readable by the application user; no root-directory confinement or path canonicalization
  exists.

**This is the hard gate on the whole lane.** G-14 is why WP-2 stays spec-only: activating the
dormant control plane of §1.1 today would expose arbitrary-URL fetch *and* arbitrary local-file
read from the application's network position, with credentials that are only partially stripped
on the way to storage.

## What this changes in the WP-2 spec

1. **Evolve, don't invent** — migration 099, `list_runnable_sources()` and
   `build_connector_from_spec()` already exist (§1.1). WP-2 makes the persisted contract
   *immutable and versioned*, adds the missing `field_mappings` / `must_capture` / `license` to
   the runnable query, and wires the absent scheduler consumer. No parallel contract table, no
   second loader.
2. **Thread, don't invent (identity)** — `source_id` exists and is validated at the edge; WP-2
   carries it through `Provenance` → `etl_runs` → scheduler identity → catalog under a
   non-colliding name, per the §1.3 glossary.
3. **Truncation must reach the terminal outcome**, not just the log (G-10 refinement) — same
   defect class as the WP-0 fail-open work, so the two specs must agree on the outcome vocabulary.
4. **Do not re-spec `records_skipped` / `records_failed`** — already landed via migration 098.
5. **`DomainPack` activation is a WP-3 dependency, not WP-2 scope** — but WP-2's contract model
   must not assume a plugin system that is currently dormant in the ingestion path.
6. **Catalog work is an integrity gate over an existing join** (G-12), extended to dynamic
   sources — not a catalog built from nothing.
7. **Safe-fetch ordering — the precise rule** (reconciles this record with COORDINATION §13.3,
   which sequences *source identity + immutable contracts → safe fetch → preview/runtime*):

   > The safe-fetch threat model is the **first design activity**. Source identity and immutable
   > contract foundations **may land first with execution disabled**. Safe fetch and secret
   > resolution are **mandatory before any probe, preview or scheduled outbound request can
   > execute**.

   This preserves the provenance/identity foundation while making an unsafe activation path
   structurally unreachable. The earlier phrasing here ("safe-fetch precedes every other slice")
   contradicted the board and is withdrawn.
