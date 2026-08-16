# WP-2 — Versioned source-contract control plane (Phase C.2 specification)

**Status:** Specification, **revision C.2**. **Spec-only** — no runtime wiring, no migration
reserved, no executable tests, no identity slice.
**Baseline:** `claude/handoff/h0-baseline` @ `da6887c`, read-only.
**Date:** 2026-08-15 (rev C.2: 2026-08-16)
**Covers:** G-01, G-07, G-10 (part — see §6.0), G-12, G-14 (SPEC-003 §6).
**Preceded by:** `WP-2_findings_reverification.md` (Phase A) · `WP-2_safe_fetch_threat_model.md`
(Phase B, rev C.2). Every "today" claim is a verified file:line, not a restatement of the review.

**Implementation gate (COORDINATION §13.3, unchanged):**

> H0 → H1 → H2 → WP-12 → WP-0 → WP-1 → H3/H4/H5 → **WP-2**.
> The threat model is the first *design* activity. Source identity and immutable contract
> foundations **may land with execution disabled**. Safe fetch and secret resolution are
> **mandatory before any probe, preview or scheduled outbound request can execute**.

### C.1 revision log — what C.1 changed and why

| # | Change | Cause |
|---|---|---|
| 1 | **Connector-type vocabulary corrected** and a scalar `record_type` replaced by typed **output streams** | Verified: `RUNTIME_CONNECTOR_TYPES = ("API_REST","CSV_FILE","RSS")`; ClinicalTrials emits 4 record types, Orange Book 3, SEC 3, PubMed 2 — a scalar cannot represent the fleet |
| 2 | **Lifecycle vs immutability reconciled** — mutable `ContractDraft`, immutable version from admission, append-only event log + current-state projections | C phase said "only SourceInstance is mutable" while requiring transitions everywhere |
| 3 | **`credential_ref` replaced by a server-issued `FetchGrant`** | A locator is not an authorization capability |
| 4 | **Preview de-cycled and re-authorized** | Preview required `execution_enabled`, which required certification, which required preview evidence |
| 5 | **Cursors/leases handed to WP-9**; WP-2 keeps only run-identity | Verified: SPEC-003 §6 assigns "durable cursors, streaming batches, leases, cost controls" to **WP-9** |
| 6 | **Keys, cardinalities, job and audit objects specified** | They were promised and absent |
| 7 | **TIV2 seam marked provisional and pinned by content digest** | Verified: TIV2 is **untracked** (`??`) and labelled *"DRAFT … Implementation authority: none until the owner records ratification"* |

### C.2 revision log — ten specification defects

| # | Change | Cause |
|---|---|---|
| 1 | Threat-model **C-10 rewritten**, **C-10a added** (query credentials excluded, not hashed) | C-10 still mandated `credential_ref`; value-hashing contradicted "secrets never enter URLs" |
| 2 | **Output streams become a relational table** `source_contract_streams`; per-stream run outcomes representable | Streams were JSONB while certifications, grants, jobs and provenance referenced them relationally — a FK cannot point into JSONB |
| 3 | **Composite FK given its required parent UNIQUE**; certification keys made NOT NULL with a sentinel | The C.1 composite FK was invalid SQL; nullable `stream_key` permitted duplicate certifications (NULLs are distinct in a UNIQUE) |
| 4 | **Event log is the sole authority; deployments/certifications relabelled as rebuildable projections** | They claimed append-only semantics while carrying mutable state columns |
| 5 | **ASK-WP2-3 opened** — WP-1 attaches `retention_class` to the content-addressed blob | Verified `WP-1 …:38` — `raw_artifacts` is content-addressed, so identical bytes under two licences cannot carry two retentions |
| 6 | **Tenancy specified at service / repository / worker boundaries**, not routes alone | Route-only enforcement leaves schedulers and background jobs unscoped |
| 7 | **Legacy backfill single-state-machine** — secret-bearing rows are quarantined and **not** admitted | The text said rows were both admitted and quarantined |
| 8 | **COORDINATION §13.1/§13.3 corrected** | The board still assigned cursors/leases and "no-write preview" to WP-2 after C.1 withdrew them |
| 9 | **M-28a relabelled an unmet design criterion**, not RED evidence | No executable test exists; "RED" implies an observed failing run |
| 10 | **Residual "recorded and committed" fixture claim removed** | C.1 corrected the header but left the same claim in the fixture section |

---

## 1. What WP-2 is

Today an outbound request originates from reviewed code with a hardcoded endpoint. WP-2 makes the
endpoint **user-authored data** — a versioned, validated, immutable contract that a deterministic
control plane admits, deploys, certifies, authorizes and audits. The work is mostly **threading and
versioning what already exists**: migration 099 persists a contract body, `list_runnable_sources()`
queries it, `build_connector_from_spec()` instantiates the generic connectors, and none of them has
a non-test caller (Phase A §1.1).

## 2. Dependency authority — read this before trusting any name below

**Upstream, binding** — SPEC-003 §8 and COORDINATION §13.4: *AI may propose declarative contracts;
deterministic validators control network access, persistence and production promotion.* No
arbitrary SQL or Python in a user-editable contract; no model judgement authorises network access,
secret resolution, or promotion.

**Downstream, PROVISIONAL — corrected in C.1.** The Phase C draft said this spec adopted TIV2-020's
names "verbatim" and treated them as a stable downstream contract. **That was overreach.** Verified
at the time of writing:

- `specs/trusted_intelligence_v2/` is **untracked** in the worktree (`git status` → `??`);
- `SPEC_TIV2_000_program.md:3` reads **"Status: DRAFT for … ratification"**;
- `:12` reads **"Implementation authority: none until the owner records ratification and sequence in
  `docs/COORDINATION.md`."**

COORDINATION §12 explicitly warns that *a board must not cite an untracked doc as ratified truth*.
Citing one as a binding interface is the same error. The seam is therefore recorded as
**provisional and pinned by content digest**, so the alignment is reproducible even though the
dependency is unratified:

| Aligned-to artefact | SHA-256 of the authoring copy |
|---|---|
| `SPEC_TIV2_000_program.md` | `594a03f8c3f05a690d57f807bc453467f145c277ff2782c96edab65faf9b90b5` |
| `SPEC_TIV2_020_source_evidence_belief_ledger.md` | `ba9f59baba815164ffc49befc815d97dabf25994d48eb49a2cfb935f2a3b9d22` |

**Status of the shared names** (`source_instance_id`, `source_contract_version_id`,
`rights_policy_version_id`, `retention_class`, `redistribution_class`, `source_certifications`):
*aligned with a draft*, not adopted from a ratified contract. They are defensible on WP-2's own
grounds — Phase A §1.2 independently established that a bare `source_id` is unusable because
`integration/cross_linker.py` means something else by it. **If TIV2 is ratified with different
names, WP-2 renames; if TIV2 is never ratified, these names still stand on the Phase A finding.**
Neither outcome blocks WP-2.

## 3. Object model

### 3.0 Connector types and output streams — corrected in C.1

**Vocabulary.** The live constant is
`RUNTIME_CONNECTOR_TYPES = ("API_REST", "CSV_FILE", "RSS")`
(`services/connector_taxonomy.py:34`), and migration 096's taxonomy also carries `WEB_SCRAPE`,
`WAREHOUSE` and `MANUAL`, which persist and draft but do not auto-run. The Phase C draft invented
`rest|csv|rss`. **C.1 uses the live vocabulary**, and states the rule: the runtime set is a subset
of the taxonomy set, and a contract of a non-runtime type is valid, storable, and permanently
`execution_enabled = FALSE`.

**Output streams.** The Phase C draft gave a contract one scalar `record_type`. Verified counts at
the baseline:

| Connector | Record types emitted |
|---|---|
| `clinical_trials.py` | `TRIAL`, `TRIAL_OUTCOME`, `TRIAL_LOCATION`, `INVESTIGATOR` |
| `orange_book.py` | `DRUG`, `PATENT`, `REGULATORY_MILESTONE` |
| `sec_edgar.py` | `COMPANY`, `DOCUMENT_CHUNK`, `EVENT` |
| `pubmed.py` | `LITERATURE`, `INVESTIGATOR` |

A scalar cannot backfill or instantiate those. **The fetch contract is separated from its typed
outputs — and in C.2 the streams are a relational table, not JSONB.**

C.1 declared `output_streams JSONB` while certifications, grants, jobs and `Provenance` all
referenced `stream_key` as if it were a key. **A foreign key cannot reference a value inside a
JSONB document**, so nothing enforced that a certification's `stream_key` named a stream that
existed, and a run could claim a stream the contract never declared.

```sql
source_contract_streams
  stream_id                  UUID PRIMARY KEY
  source_contract_version_id UUID NOT NULL REFERENCES source_contract_versions
  stream_key                 TEXT NOT NULL      -- stable within the contract
  record_type                TEXT NOT NULL      -- one RecordType
  records_path               TEXT NOT NULL
  external_id_field          TEXT NOT NULL
  field_map                  JSONB NOT NULL     -- leaf mapping data: JSONB is correct here
  identifiers_map            JSONB NOT NULL
  must_capture               TEXT[] NOT NULL DEFAULT '{}'
  UNIQUE (source_contract_version_id, stream_key)
  UNIQUE (stream_id, source_contract_version_id)   -- parent key for composite FKs (§9.2)
```

Streams are immutable with their contract version: a stream change is a new contract version, so
the table is append-only alongside its parent. `field_map` stays JSONB because it is *leaf* data
nothing references; `stream_key` leaves JSONB because four other objects reference it.

**Per-stream run outcomes (C.2).** C.1 could not represent a run where one stream landed and
another failed — the outcome was scalar per run. Corrected in §3.6: `source_jobs` carries an
overall terminal outcome **and** `source_job_streams` carries one row per stream with its own
outcome and counts. The run-level outcome is a deterministic **rollup**, and the rollup rule is
part of ASK-WP2-1 because WP-0 owns the vocabulary: a run whose streams mixed `LANDED` and
`ZERO_ROWS` must not silently report `LANDED`.

One fetch, many typed streams. This also makes certification honest: a SEC contract may be
`decision`-grade for `COMPANY` and only `discovery`-grade for `DOCUMENT_CHUNK`. **Migration 099's
scalar `record_type` becomes stream #1** in the backfill, and the generic connectors — which today
genuinely emit one type — get exactly one stream, so nothing regresses.

### 3.1 `SourceInstance` — stable identity, mutable metadata

```text
source_instance_id   UUID PK
legacy_source_key    TEXT UNIQUE NULL   -- FK -> sources.source_id (TEXT PK, migration 055)
display_name         TEXT
owner_principal      TEXT
tenant_id            TEXT NULL          -- §12
created_at, updated_at
```

`lifecycle` is **removed** — it conflated instance state with contract state (C.1 finding 2).
Current state is a projection of the event log (§3.6).

**`legacy_source_key` is `UNIQUE`** (C.1 finding 7): the alias must resolve exactly once, or the
backfill can silently fan one historical run history onto two instances.

### 3.2 `ContractDraft` (mutable) → `SourceContractVersion` (immutable from admission)

The Phase C draft allowed "mutation until something references it," which is not immutability.
C.1 splits the object:

```text
ContractDraft                     -- freely mutable, never executable, never referenced by a run
  draft_id UUID PK
  source_instance_id UUID FK
  body JSONB
  last_validated_at, last_diagnostics JSONB

SourceContractVersion             -- IMMUTABLE from the moment of admission
  source_contract_version_id UUID PK
  source_instance_id  UUID FK NOT NULL
  version             INTEGER NOT NULL
  connector_type      TEXT NOT NULL          -- §3.0 vocabulary
  transport           JSONB NOT NULL
  credential_slots    JSONB NOT NULL         -- named slots + placement, NOT values (§7)
  egress_allowlist    TEXT[] NOT NULL        -- normalized origins
  rights_policy_version_id UUID FK NOT NULL  -- §3.5
  cadence             JSONB NULL             -- NULL ⇒ manual/event-driven
  sla_days            INTEGER NULL
  trust_tier          INTEGER
  canonical_hash      TEXT NOT NULL          -- sha256 over the canonical serialization
                                             -- (covers the stream rows too, §3.2)
  validator_version   TEXT NOT NULL
  admitted_by, admitted_at
  UNIQUE (source_instance_id, version)
  UNIQUE (source_instance_id, canonical_hash)
  -- C.2: the parent key the deployment/certification composite FKs require (§9.2)
  UNIQUE (source_instance_id, source_contract_version_id)
```

Output streams live in `source_contract_streams` (§3.0), inserted in the same transaction as the
version row. The `canonical_hash` covers the version body **and** its ordered stream rows — a
contract whose streams changed is a different contract.

- **Admission is the immutability boundary.** A draft is validated; on success a version row is
  inserted; the draft is never promoted in place. There is no `UPDATE` path, and an append-only
  trigger rejects one.
- **`canonical_hash` is checked at approval and again at execution** (C.1 finding 2). A version
  whose stored body no longer hashes to its recorded `canonical_hash` fails closed — this is what
  makes immutability *verified* rather than *asserted*.
- Canonical serialization must be deterministic (sorted keys, normalized numbers/unicode, explicit
  null handling); a hash that is not reproducible is not a control (test case in the suite).

### 3.3 `SourceDeployment` — a rebuildable **projection**, not a record of authority

**C.2 correction.** C.1 said current state "is a projection of the event log" while this table
carried mutable `execution_enabled` and `superseded_by` columns and §3.6 called the design
append-only. Both cannot be true. The resolution names each object honestly:

| Layer | Mutability | Authority |
|---|---|---|
| `control_plane_events` | **append-only, immutable** | **the sole authority** |
| `source_deployments`, `source_certifications` | **mutable projections** | derived; rebuildable by replay |

Mutable columns on a projection are correct — a projection's whole job is to hold current state.
What C.1 got wrong was calling the projections append-only. A projection may be **dropped and
rebuilt** from the event log at any time, and a Lane-1 test asserts replay reproduces it exactly
(M-35a). No writer may update a projection without emitting the corresponding event in the same
transaction.

```sql
source_deployments                    -- PROJECTION of control_plane_events
  deployment_id              UUID PRIMARY KEY
  source_instance_id         UUID NOT NULL
  source_contract_version_id UUID NOT NULL
  environment                TEXT NOT NULL   -- draft | staging | prod
  execution_enabled          BOOLEAN NOT NULL DEFAULT FALSE
  superseded_by              UUID NULL REFERENCES source_deployments
  last_event_id              UUID NOT NULL   -- the event this row was derived from

  -- C.2: a composite FK REQUIRES a matching UNIQUE on the parent. C.1 omitted it,
  -- so the constraint below was invalid SQL. The parent key is added in §3.2.
  FOREIGN KEY (source_instance_id, source_contract_version_id)
      REFERENCES source_contract_versions (source_instance_id, source_contract_version_id)

  -- at most one effective deployment per scope
  UNIQUE (source_instance_id, environment) WHERE superseded_by IS NULL
```

The composite FK is the fix for "a deployment could pair a contract version belonging to a
different source instance." `source_instance_id` is *derived and constrained*, not independently
supplied — and it is now enforceable, because the parent carries
`UNIQUE (source_instance_id, source_contract_version_id)`.

Separating deployment from contract is what makes the §13.3 sequencing rule mechanical: a contract
can be authored, admitted, versioned and deployed with `execution_enabled = FALSE` before safe
fetch exists.

### 3.4 `SourceCertification` — projection over an append-only decision log

```sql
source_certifications                 -- PROJECTION (see §3.3); events are the authority
  certification_id           UUID PRIMARY KEY
  source_instance_id         UUID NOT NULL
  source_contract_version_id UUID NOT NULL
  -- C.2: was `stream_key TEXT NULL` meaning "whole contract". In Postgres NULLs are
  -- DISTINCT in a UNIQUE constraint, so two contract-wide certifications for the same
  -- purpose and effective_from were both admissible. A NOT NULL sentinel closes it.
  stream_key                 TEXT NOT NULL DEFAULT '*'   -- '*' = whole contract
  purpose                    TEXT NOT NULL   -- discovery | evidence | decision | restricted_internal
  allowed_record_types       TEXT[] NOT NULL DEFAULT '{}'
  allowed_predicates         TEXT[] NOT NULL DEFAULT '{}'
  allowed_jurisdictions      TEXT[] NOT NULL DEFAULT '{}'
  rights_policy_version_id   UUID NOT NULL REFERENCES rights_policy_versions
  certifier_principal        TEXT NOT NULL
  certification_evidence     JSONB NOT NULL
  effective_from             TIMESTAMPTZ NOT NULL
  effective_to               TIMESTAMPTZ NULL
  review_due_at              TIMESTAMPTZ NOT NULL
  revoked_at                 TIMESTAMPTZ NULL
  revoked_by                 TEXT NULL
  revocation_reason          TEXT NULL
  last_event_id              UUID NOT NULL

  FOREIGN KEY (source_instance_id, source_contract_version_id)
      REFERENCES source_contract_versions (source_instance_id, source_contract_version_id)
  -- a stream_key other than '*' must name a declared stream of THIS contract version
  FOREIGN KEY (source_contract_version_id, stream_key)
      REFERENCES source_contract_streams (source_contract_version_id, stream_key)
      -- enforced for non-'*' rows via a trigger or a '*' sentinel row per version
  UNIQUE (source_contract_version_id, stream_key, purpose, effective_from)
  -- at most one live certification per scope
  UNIQUE (source_contract_version_id, stream_key, purpose)
      WHERE revoked_at IS NULL AND effective_to IS NULL
```

**The decision history is append-only in `control_plane_events`;** this table is its current-state
projection (§3.3). A certification is superseded or revoked, never semantically edited, and the
`revoked_*` columns are projection state written alongside a `revoked` event in one transaction.
Revocation must be observable *during* execution (§7.4).

The stream FK is what the C.1 JSONB model could not express: a certification can no longer name a
stream the contract never declared.

**Not a quality number** — deliberately, and it corrects a live defect class: QUAL-001 found
`source_registry.recompute_quality` filling missing dimensions with `0.5`, producing a composite
that reads as judgement while measuring nothing.

> `services/source_registry.py` remains contested (open **PR #324**) and is untouched.

### 3.5 `RightsPolicyVersion` — a real table, and it attaches to acquisition

```text
rights_policy_version_id UUID PK
licence_id, licence_text, attribution_required
retention_class, redistribution_class, data_classification
permitted_purposes TEXT[]
effective_from, effective_to
```

Phase C had rights appearing three ways at once (contract JSON, an "envelope", an undefined table).
C.1 makes it **one versioned table**, referenced by FK from the contract version.

**Attachment point (C.1 finding 7):** rights belong to the **acquisition** — the
contract-version-scoped fetch that produced the bytes — **not to the content-addressed blob**. The
same bytes acquired under two contracts, licences, or tenants carry two rights envelopes.

### 3.5.1 Direct conflict with WP-1 — BLOCKING (new in C.2)

This is not a preference; it conflicts with the WP-1 design as written. Verified in
`specs/data_platform/WP-1_raw_capture_and_replay.md`:

- **line 38** — `raw_artifacts` (append-only, keyed by `sha256 PK`) carries
  **`retention_class`** and `legal_hold` **on the content-addressed row**;
- **line 23** — the store interface exposes `apply_retention(source_type, before) -> int`, keyed by
  `source_type`, not by acquisition;
- **line 19** — "retention/legal-hold governs eventual expiry per source".

Because the table is content-addressed with `ON CONFLICT (sha256) DO NOTHING`, **identical bytes
fetched under two different licences, retention classes, or tenants collapse to one row and one
retention class — silently, and in favour of whichever acquisition arrived first.** That is a
conservation failure of exactly the class this program exists to stop: a governance attribute is
lost without a record.

**The required interface** (ASK-WP2-3, COORDINATION §13.5):

1. `raw_artifacts` stays content-addressed and **loses `retention_class`** — bytes are bytes.
2. A per-acquisition row (WP-1's `artifact_usage`, or the TIV2 artefact-version object if that
   epic ratifies) carries `source_instance_id`, `source_contract_version_id`,
   `rights_policy_version_id`, `retention_class`, `redistribution_class`, `data_classification`.
3. **Retention and legal hold resolve over all acquisitions of a blob**, most-restrictive wins: a
   blob is deletable only when *every* acquisition referencing it is expired and unheld.
4. `apply_retention` is keyed by acquisition, not `source_type`.

**Neither WP-1 nor WP-2 may land its side of this unilaterally.** WP-2 does not have the authority
to alter WP-1's schema, and WP-1's current design cannot carry WP-2's rights model. This is
recorded as a blocking cross-lane ASK rather than resolved here.

### 3.6 Event log and current-state projections

Promised and absent in Phase C. Two append-only tables plus derived views:

```text
control_plane_events                -- ONE append-only log
  event_id UUID PK
  event_type   TEXT   -- draft_submitted | validated | rejected | admitted | deployed
                      -- | approved | enabled | disabled | superseded | rolled_back
                      -- | certified | revoked | grant_issued | grant_revoked
  subject_kind TEXT, subject_id UUID
  source_instance_id UUID
  actor_principal TEXT, actor_kind TEXT   -- human | service | agent (§12)
  payload JSONB       -- diagnostics, codes, prior/next state — redacted (§7.5)
  code_git_sha TEXT
  occurred_at TIMESTAMPTZ

source_jobs                         -- one row per execution attempt
  job_id UUID PK
  deployment_id, source_contract_version_id  (composite FK)
  trigger        TEXT   -- scheduled | manual | replay
  grant_id       UUID   -- §7
  etl_run_id     UUID
  rollup_outcome TEXT   -- DETERMINISTIC rollup of the stream rows below (§3.0, ASK-WP2-1)
  started_at, finished_at

source_job_streams                  -- NEW in C.2: per-stream outcome (§3.0)
  job_id     UUID NOT NULL REFERENCES source_jobs
  stream_id  UUID NOT NULL REFERENCES source_contract_streams
  cursor_before / cursor_after  JSONB   -- OWNED BY WP-9, recorded here (§6.0)
  records_in / records_mapped / records_dropped  INTEGER NOT NULL
  drop_reasons     JSONB NOT NULL
  terminal_outcome TEXT NOT NULL   -- WP-0 vocabulary (§5.3)
  truncated        BOOLEAN NOT NULL
  PRIMARY KEY (job_id, stream_id)
```

**Why the split (C.2).** A single scalar outcome on `source_jobs` could not represent a run where
one stream landed and another returned zero rows or was refused — the honest case for every
multi-output connector (ClinicalTrials has four streams). Cursors are also per-stream, so recording
them on the job row was wrong. `rollup_outcome` is derived, never independently written, and **the
rollup rule belongs to ASK-WP2-1** because WP-0 owns the vocabulary: a run mixing `LANDED` and
`ZERO_ROWS` must not report `LANDED`.

Current state (`deployment.state`, `contract.state`, `certification.status`) is a **projection**
over `control_plane_events`, not an independently writable column. Storing state twice is how the
two silently diverge.

## 4. Identity and provenance threading

| Layer | Today | After WP-2 |
|---|---|---|
| `ConnectorSpec.to_config()` | sets `config.source_id`, logs only (`connectors/spec.py:172`) | carries `source_instance_id` + `source_contract_version_id` |
| `Provenance` (`connectors/base.py:143-162`) | 6 fields, no source identity | **+ `source_instance_id`, `source_contract_version_id`, `stream_key`** |
| `_create_etl_run` (`integration/pipeline.py:491-504`) | `source_type.value`, `""`, `"{}"` | **+ instance id, contract version id, `job_id`, `code_git_sha`, and a *redacted* resolved endpoint** |
| `_finalize_etl_run` (`:549-580`) | counts + `outcome` | **+ per-stream counts, truncation, per-stage outcomes** |
| Catalog | static `DATASET_DEFINITIONS` | integrity gate (§9.4) |

**Redaction of run rows (C.1 finding 3; tightened in C.2).** The Phase C draft said to persist
"real query params," which would persist resolved credentials for any `api_key_param` contract.
C.1 corrected that to "parameter names plus a hash of the values" — but **a hash of a credential is
still a credential artefact**: low-entropy or structured tokens are recoverable offline, so that
still contradicted "secrets never enter persisted artefacts". Final rule (threat model C-10a):

| Parameter kind | Persisted in `etl_runs` / `source_jobs` / events / logs |
|---|---|
| Non-credential | name **and** a hash of the value (supports reconciliation and replay) |
| **Credential-bound** (any slot binding) | name **and the literal marker `REDACTED:credential`** — no hash, no length, no prefix, no value-derived material |

Plus the normalized origin and path. Query-placed credentials are forbidden by default and require
an owner-approved exception (C-10a).

**Naming rule:** never `source_id` inside `integration/` — `cross_linker.py` uses it for graph-edge
endpoints at 25 sites (Phase A §1.2).

## 5. State machines

### 5.1 Contract

```text
ContractDraft ──validate──▶ (diagnostics)
      │
      └──admit──▶ SourceContractVersion  [IMMUTABLE]
                        ├──deploy──▶ (deployment states, §5.2)
                        └──supersede/revoke──▶ terminal, still readable
```

Nothing is deleted. Rejection produces typed codes (§10), never a score.

### 5.2 Deployment and the execution gate

```text
registered ──approve──▶ approved ──enable──▶ live ──disable──▶ paused
     │                                          │
     └──────────────────────────────────────────┴──rollback──▶ rolled_back
```

`execution_enabled` may become `TRUE` only when all hold:

1. deployment is `approved` or `live`, and is the effective deployment for its scope (§3.3);
2. the contract version revalidates under a **current** `validator_version`;
3. `canonical_hash` still matches the stored body;
4. an active, unrevoked `SourceCertification` exists for the requested purpose **and stream**;
5. the safe-fetch boundary is present and enabled (Phase B, rev C.1);
6. every `credential_slot` resolves to a live credential version.

Failing any is a **fail-closed refusal**. Critically, this is checked when issuing a **FetchGrant**
(§7), not by trusting a boolean passed to a caller.

### 5.3 Run outcome — WP-0 owns the vocabulary

`classify_run_outcome` (`integration/pipeline.py:125-168`) is a good pure Lane-1 gate, and
migration 098 already persists `records_skipped`/`records_failed`. WP-2 proposes these **inputs**:

| Input | Meaning |
|---|---|
| `truncated` | page cap or bounded stop reached; completeness not asserted |
| `cursor_advanced` | recorded for reconciliation (WP-9 owns the semantics) |
| `contract_validation_failed` | a deployed contract stopped validating |
| `credential_unresolved` | secret missing — **not** a source outage |
| `egress_refused` | safe-fetch rejection — **not** a source outage |

**These are proposals, not decisions.** Phase C asserted agreement that does not exist; C.1 records
it as an open cross-lane ASK (§14, COORDINATION §13.5). *Rejecting unknown strings does not prove
semantic mapping* — the ASK must produce a **shared normative table** mapping each input to a
terminal outcome and to a health consequence, ratified before WP-0 or WP-2 lands.

## 6. Scheduling, cursors, leases — ownership corrected

### 6.0 WP-9 owns this; WP-2 consumes it

**Verified:** SPEC-003 §6 assigns *"durable cursors, streaming batches, leases, cost controls"* to
**WP-9** (row 10). Phase C specified a cursor table, a lease and a job model as WP-2 deliverables.
That was an ownership overreach and is withdrawn.

**Corrected split:**

| Concern | Owner |
|---|---|
| Cursor storage, typing, advance semantics, rollback policy | **WP-9** |
| Distributed lease mechanism | **WP-9** |
| Streaming/bounded iteration | **WP-9** |
| **Per-instance run identity** (`source_jobs`, §3.6) and the requirement that a job records `cursor_before`/`cursor_after` | **WP-2** |
| **Requirement** that a non-completeness-asserting outcome must not be treated as a completed window | **WP-2 states it; WP-9 implements it** |

WP-2 needs *an* addressable cursor per `(source_instance_id, stream_key)`; it does not get to
design it.

### 6.1 Design constraints WP-2 hands to WP-9 (not a design)

The Phase C draft got several of these wrong; recording the corrections so WP-9 inherits them
rather than rediscovering them:

- **Cardinality:** one cursor per source is insufficient — it must key on
  `(source_instance_id, stream_key)` and support partitioning. A contract with 4 output streams has
  up to 4 independent positions.
- **Typing:** `cursor_value TEXT` is untyped. A cursor needs a declared kind (opaque token,
  timestamp, monotonic id) so comparison and rollback are defined operations.
- **"Empty + advanced" is not always failure.** Phase C asserted it was. Several sync APIs
  legitimately return an empty page with a fresh token. The honest invariant is narrower:
  *an outcome that does not assert completeness must not advance a **completeness-derived**
  watermark* — which is not the same as forbidding token advancement.
- **Advisory locks and TTL/heartbeat/fencing leases are alternatives, not a stack.** Phase C listed
  both as if complementary. WP-9 picks one and states the failure mode it accepts.
- **Automatic rollback is unsafe by default.** Restoring `last_good_value` can duplicate or lose
  data depending on cursor kind and sink idempotency. Rollback must be an explicit, audited
  operation with a stated at-least-once/at-most-once guarantee — not an automatic side effect of
  redeploying.

## 7. Authority boundary — `FetchGrant` replaces `credential_ref`

C.1 finding 3, adopted. `credential_ref` was an arbitrary locator: unbound to tenant, source,
origin, principal, version or revocation. And returning `execution_enabled` to a caller is advice,
not authority — a caller can ignore or forge it.

### 7.1 The grant

A **server-issued, DB-derived, short-lived** capability. Not forgeable by a caller, because the
caller never constructs it.

```text
FetchGrant
  grant_id UUID
  principal_id, actor_kind            -- who
  tenant_id                           -- isolation scope
  source_instance_id
  source_contract_version_id          -- pinned; a redeploy invalidates
  contract_canonical_hash             -- pinned; a body change invalidates
  allowed_origins  TEXT[]             -- normalized (scheme, host, port), exact
  credential_slot_bindings            -- slot -> credential VERSION + permitted placement
  purpose                             -- must match an active certification
  max_requests, max_bytes, expires_at
  revocation_epoch                    -- see §7.4
```

### 7.2 Rules

1. **No grant, no request.** The fetch primitive takes a grant, not a URL and a config. Absence
   fails closed.
2. **Rechecked on every page, retry and redirect** — not once per run. A grant that expires or is
   revoked mid-run stops the run at the next request boundary.
3. **Origin match is exact and normalized** (scheme, host, port), evaluated after DNS validation
   and IP pinning (Phase B C-02).
4. **Credential placement is bound by the grant**, not chosen by the caller: a slot bound as
   `header:Authorization` cannot be emitted as a query parameter.
5. **Resolved secrets never enter** URLs, persisted query parameters, `etl_runs`, `source_jobs`,
   logs, `ConnectorError` messages, API responses, or event payloads (§4, §7.5).

### 7.3 Credential slots vs values

The contract declares **slots** — `{"slot": "primary_token", "placement": "header:Authorization"}`.
Values live in the resolver and are versioned. The contract grammar has no field that can hold a
secret, which is what makes Phase A's four bypasses (nested header, nested query param, URL
userinfo, unrecognised key) unrepresentable rather than stripped.

**Placement is header-only by default (C.2, threat model C-10a).** `placement: query:<name>` is
rejected with `CREDENTIAL_PLACEMENT_FORBIDDEN` unless the contract carries an owner-approved
`query_credential_exception`. Under that exception the value exists only in the in-flight request
and is **excluded — never hashed** — from every persisted artefact (§4). This closes the C.1
contradiction between "secrets never enter URLs" and the existence of `RestConfig.api_key_param`.

**This spec's single credential model is: slot (in the contract) + grant binding (at runtime).**
There is no `credential_ref` locator anywhere in WP-2; references to it in this document and in the
threat model are historical, describing what C.1 replaced.

### 7.4 Revocation during execution

A `revocation_epoch` on the source instance is bumped on credential rotation, certification
revocation, or deployment disable. Every grant check compares epochs; a stale epoch fails closed.
This is what makes "revoke" mean *now* rather than *next run*.

### 7.5 One redaction boundary

A single helper applied to every sink: logs, errors, API responses, catalog payloads,
`control_plane_events.payload`, and any git-tracked spec export. **It must cover source *values*,
not only contract configuration** — see §8.

## 8. Discovery and preview — de-cycled and re-authorized

### 8.0 The cycle, and the fix

Phase C required `execution_enabled` for preview; enabling required an active certification; and
certification realistically requires preview evidence. That is circular, and it pushes authors
toward certifying a source to production grade merely to look at it.

**Fix:** preview is authorized by its **own grant type**, not by production execution state.

| | Production fetch | Preview fetch |
|---|---|---|
| Authority | `FetchGrant`, purpose from certification | **`PreviewGrant`** — purpose `discovery` only |
| Requires certification | yes | **no** |
| Requires `execution_enabled` | yes | **no** |
| Safe-fetch primitive | same | **same** (Phase B C-06) |
| Writes | full pipeline | **security/audit + rate accounting only** (§8.1) |
| Limits | contract-declared | hard caps: 1 page, N records, byte cap, wall clock |
| Response | — | classified + redacted (§8.2) |

A preview **never** implies certification or evidence. An explicit rule: no certification decision
may cite a preview as its sole `certification_evidence`.

### 8.1 "No writes" was too broad — corrected

Phase C said preview writes nothing "of any kind." But preview *is outbound egress*, and egress
without a durable audit record is exactly the untracked-action problem. Corrected:

**MUST write:** a `control_plane_events` row (`grant_issued`, principal, tenant, origin, byte
count, outcome) and rate-limit accounting. These are security records and must survive.

**MUST NOT write:** any domain fact, entity, `etl_runs` row, cursor advance, DLQ record, embedding,
or downstream pipeline output. Enforced by running the transform stages against an in-memory sink,
asserted by table-count deltas.

### 8.2 Response classification — the second disclosure risk

Phase C returned sampled source values with a redactor that covered *contract configuration*.
A preview response containing real upstream rows can disclose licensed or sensitive **source data**
to a principal who is not entitled to it. Corrected:

- every returned value carries the contract's `data_classification`;
- values are redacted by classification, and sample size is bounded;
- object-level authorization is checked — the principal must be entitled to the *source instance*
  and the tenant, not merely authenticated;
- the response is not cacheable and not exportable.

### 8.3 Preview response contract

```jsonc
{
  "preview_id": "uuid",
  "grant_id": "uuid",
  "source_instance_id": "uuid",
  "source_contract_version_id": "uuid",
  "data_classification": "licensed",
  "executed_at": "2026-08-15T10:00:00Z",
  "fetch": { "origin": "https://api.example.org", "status_code": 200,
             "byte_size": 18422, "truncated": false, "page_count": 1 },
  "streams": [
    { "stream_key": "labels", "record_type": "drug_label",
      "schema_inference": [
        {"field": "brand_name", "inferred_type": "string", "null_rate": 0.02,
         "sample": "REDACTED:licensed"}
      ],
      "records": [ {"external_id": "…", "mapped": {"generic_name": "REDACTED:licensed"},
                    "unmapped_fields": ["ndc11"]} ],
      "conservation": { "records_in_page": 50, "records_mapped": 48,
                        "records_dropped": 2, "drop_reasons": {"missing_external_id": 2} } }
  ],
  "diagnostics": [ {"code": "MAPPING_TARGET_UNKNOWN", "severity": "error", "field": "foo"} ],
  "would_persist": false,
  "is_certification_evidence": false
}
```

`conservation` is mandatory **per stream** — a preview that silently drops rows teaches the author
that the mapping is complete.

## 9. Database design

**No migration number reserved.** SPEC-003 §9 requires reservation at implementation time via
COORDINATION §7.4; the highest existing is `099`. Reserving now would collide with H1/H2 work.

### 9.1 Tables

**Immutable / append-only (authority):** `source_contract_versions` · `source_contract_streams` ·
`control_plane_events` · `source_jobs` · `source_job_streams` · `fetch_grants` ·
`rights_policy_versions`

**Mutable projections (rebuildable by replay, §3.3):** `source_deployments` ·
`source_certifications`

**Mutable working state:** `source_instances` (metadata) · `contract_drafts`

*(cursors and leases are **WP-9**, §6.0)*

### 9.2 Keys and cardinalities

| Relationship | Cardinality | Constraint |
|---|---|---|
| instance → contract versions | 1..n | `UNIQUE (source_instance_id, version)` |
| instance → contract hash | 1..n | `UNIQUE (source_instance_id, canonical_hash)` |
| **parent key for composite FKs** | — | **`UNIQUE (source_instance_id, source_contract_version_id)`** on `source_contract_versions` — *C.2: without this the composite FKs below are invalid SQL* |
| contract version → streams | 1..n | `UNIQUE (source_contract_version_id, stream_key)`; plus `UNIQUE (stream_id, source_contract_version_id)` as a parent key |
| deployment → (instance, version) | n..1 | composite FK, now satisfiable (§3.3) |
| instance+environment → effective deployment | 1 | partial `UNIQUE … WHERE superseded_by IS NULL` |
| certification → (version, stream) | n..1 | composite FK; `stream_key NOT NULL DEFAULT '*'` — *C.2: a nullable key made duplicates admissible, since NULLs are distinct in a UNIQUE* |
| certification liveness | ≤1 per scope | partial `UNIQUE (version, stream_key, purpose) WHERE revoked_at IS NULL AND effective_to IS NULL` |
| contract version → rights policy | n..1 | FK `NOT NULL` |
| job → deployment | n..1 | composite FK |
| job → stream outcomes | 1..n | `PRIMARY KEY (job_id, stream_id)` |
| projection → event | n..1 | `last_event_id` FK; replay must reproduce the projection exactly |
| legacy alias | 1..1 | `legacy_source_key UNIQUE` |

**Composite-FK rule (C.2).** PostgreSQL requires a referenced column list to be backed by a
`UNIQUE` or `PRIMARY KEY` constraint on the parent. C.1 declared composite FKs against
`(source_instance_id, source_contract_version_id)` while the parent had only a single-column PK —
the constraint would have failed at migration time. Every composite FK in this spec now names its
parent key explicitly.

### 9.3 Migration and backfill — corrected

Migration 099's columns are **not dropped**; they are marked deprecated and cleanup is a separate
later PR (SPEC-003 §9: shadow → dual-read → reversible flag → cutover → separate cleanup).

**Legacy configs are quarantined, not trusted (C.1 finding 7).** The Phase C draft would have
turned existing onboarding rows into trusted v1 contracts. Corrected backfill:

**One state machine, three terminal states (corrected in C.2).** C.1 said rows are "admitted as
`legacy_unverified`" *and* that secret-bearing rows are "quarantined" — leaving it undefined
whether a secret-bearing row became a contract. It does not:

```text
                    ┌─ clean ──────────▶ ADMITTED as legacy_unverified
profile for         │                     (a real contract version: disabled,
embedded secrets ───┤                      uncertified, NO grant issuable)
                    │
                    ├─ credential-shaped ▶ QUARANTINED
                    │                     (NOT admitted; NO contract version created;
                    │                      original row preserved verbatim, flagged,
                    │                      reported for manual remediation)
                    │
                    └─ unparseable ──────▶ SKIPPED (reported with reason)
```

1. every `sources` row → one `source_instances` row, `legacy_source_key` set and UNIQUE;
2. every existing `source_onboarding` contract is **profiled for embedded secrets first** — the
   Phase A probe proved the current strip covers only three top-level keys, so nested headers,
   query params, URL userinfo and unrecognised keys may be sitting in production config today;
3. **clean rows only** are admitted as `legacy_unverified` contract versions: disabled,
   uncertified, no grant issuable;
4. **secret-bearing rows are quarantined and never admitted.** No contract version is created for
   them. The original row is preserved verbatim (evidence for remediation), flagged, and reported
   — never silently cleaned, and never turned into a contract carrying a live credential;
5. the migration emits a conservation report: rows in, instances created, contracts admitted,
   **quarantined**, skipped, **and why**. A silent partial backfill is the designed-against failure;
6. **Single authority:** after backfill, `source_onboarding`'s contract columns become read-only
   (trigger or revoked grants) so they cannot remain a second mutable authority.

Quarantine is a **halt with evidence**, not a downgrade: remediating a quarantined row means
rotating the exposed credential and re-authoring the contract with a slot, which is a human action.

### 9.4 `list_runnable_sources()` and catalog integrity

- The live query omits `field_mappings`, `must_capture` and `license` (Phase A). It is re-pointed at
  `source_deployments ⋈ source_contract_versions` and returns the full contract **plus** the
  deployment's effective state — but a caller still cannot execute on it without a grant (§7).
- **Catalog integrity gate (Lane 1, seeded):** every effective deployment resolves to a registry
  entry, an SLA, and an active certification; every catalog entry resolves to an effective
  deployment; no orphans either direction. **Schedules are required only for `cadence IS NOT NULL`
  contracts** — manual and event-driven sources legitimately have none (C.1 correction to the Phase
  C rule, which would have failed them).

## 10. Validation — deterministic, typed, versioned

| Class | Codes |
|---|---|
| Transport | `URL_SCHEME_FORBIDDEN`, `URL_USERINFO_PRESENT`, `ORIGIN_NOT_ALLOWLISTED`, `LOCAL_PATH_FORBIDDEN` |
| Secret | `INLINE_CREDENTIAL_PRESENT`, `CREDENTIAL_SLOT_UNKNOWN`, `CREDENTIAL_PLACEMENT_FORBIDDEN`, `QUERY_CREDENTIAL_EXCEPTION_UNAPPROVED` |
| Streams | `STREAM_KEY_DUPLICATE`, `RECORDS_PATH_INVALID`, `EXTERNAL_ID_FIELD_MISSING`, `MAPPING_TARGET_UNKNOWN` |
| Schema | `MUST_CAPTURE_UNMAPPED`, `IDENTIFIER_NAMESPACE_UNKNOWN` |
| Rights | `RIGHTS_POLICY_MISSING`, `RETENTION_CLASS_UNKNOWN`, `PURPOSE_NOT_CERTIFIED` |
| Structural | `NO_CALLABLE_IN_CONTRACT`, `UNKNOWN_FIELD`, `CONNECTOR_TYPE_UNKNOWN`, `CANONICAL_HASH_MISMATCH` |

**Where the LLM is permitted:** proposing a draft contract from a URL or sample payload, and
suggesting stream mappings. Its output enters as a `ContractDraft` and passes the **same** validator
with no elevated trust, no confidence threshold that skips a check, and no path to a grant.

## 11. API / OpenAPI delta

Additive on `api/routes/hub.py` (this lane's owned surface). **`api/routes/sources.py` is contested
(#320, #56) and untouched.** All mutating calls take an **idempotency key**.

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/hub/sources` | create a `SourceInstance` |
| `POST` | `/hub/sources/{id}/drafts` · `PATCH` `/drafts/{did}` | mutable draft authoring |
| `POST` | `/hub/sources/{id}/drafts/{did}/validate` | typed diagnostics, no storage |
| `POST` | `/hub/sources/{id}/contracts` | admit a draft → immutable version N+1 |
| `GET` | `/hub/sources/{id}/contracts` · `/{ver}` · `/{ver}/diff` | immutable history |
| `POST` | `/hub/sources/{id}/preview-grants` | issue a `PreviewGrant` (§8) |
| `POST` | `/hub/sources/{id}/discover` · `/preview` | no-domain-write, grant-authorized |
| `POST` | `/hub/sources/{id}/deployments` | deploy, `execution_enabled=false` |
| `POST` | `/hub/deployments/{id}/approve` · `/enable` · `/disable` · `/rollback` | gated transitions |
| `POST` | `/hub/sources/{id}/certifications` · `/{cid}/revoke` | append-only certification |
| `GET` | `/hub/sources/{id}/events` | the append-only log (redacted) |

**OpenAPI discipline (H3):** `schema/openapi.json` is protected from this lane; the delta is stated
here and the regen is coordinated with the H3 owner — the 381↔518 drift is why an unreviewed regen
from this lane would be harmful.

## 12. Principals, tenancy, approval

- **Actor kinds are typed** — `human | service | agent`. C.1 finding: the Phase C approval rule
  (`authored_by ≠ approved_by`) treats two unequal strings as independent principals, which an
  agent can satisfy trivially.
- **Approval requires a `human` actor kind and a distinct principal identity**, resolved from an
  identity source rather than a self-declared string.
- **Honest limit, restated:** worktree agents currently run under the owner's git identity
  (`conservation-gates.md`, "Reviewer identity"). Until a non-owner agent identity exists, this is
  **discipline, not structure**. WP-2 records `actor_kind` and principal separately so the
  violation is *visible*, and the acceptance suite asserts the intent — it cannot enforce it.
- **Tenancy is enforced at four boundaries, not one (corrected in C.2).** C.1 delegated enforcement
  to "routes", which leaves every non-route path unscoped — and the scheduler, the backfill and the
  health gate all reach this data without passing through a route. The seam
  (COORDINATION §10.1 A4) stays "Data adds the column, Product-Platform enforces", but the
  enforcement surface is specified here so it cannot be read as route-only:

  | Boundary | Requirement |
  |---|---|
  | **Route / API** | Principal's tenant resolved from the authenticated session, never from a request body or query parameter |
  | **Service** | Every control-plane operation takes an explicit tenant-scoped caller context; no ambient/default tenant, no `None` meaning "all" |
  | **Repository / query** | Every read and write of a WP-2 table is tenant-filtered at the query layer. RLS is **defence in depth, not the only filter** |
  | **Worker / scheduler / migration** | A background job runs under an explicit tenant context per source instance. A job with no resolvable tenant **fails closed** rather than running unscoped |

  A `FetchGrant` is tenant-bound (§7.1), so the fetch primitive is scoped even when reached from a
  worker. WP-2 carries the column, grant-scopes on it, and states these four requirements; the
  route-layer implementation remains Product-Platform's.

## 13. Explicitly out of scope

- **Cursors, leases, streaming, cost controls** → **WP-9** (§6.0).
- **Secret-resolver selection** → owner deployment decision (§14).
- **`DomainPack` activation** → **WP-3** (dormant in the whole ingestion path, Phase A G-07).
- **Untrusted fetched content reaching synthesis** → **WP-5** (Phase B T-20).
- **Source poisoning / quality as promotion gate** → **WP-8** (Phase B T-19).
- **Net-new connector breadth** — paused by SPEC-003 §3.
- **`services/source_registry.py`, `api/routes/sources.py`, `connectors/`** — contested or protected
  until #324/#320/#56/#66 land and WP-1 releases `BaseConnector`.

## 14. Open questions and cross-lane ASKs

**Blocking ASKs** (recorded in COORDINATION §13.5 — must resolve before any of the three lands):

1. **WP-0 ⇄ WP-2 outcome vocabulary.** A shared normative table mapping each §5.3 input to a
   terminal outcome and health consequence. Agreement is currently *asserted, not held*.
2. **WP-2 ⇄ WP-9 boundary.** Ratify §6.0's split and publish one normative cursor/lease interface
   before either specs its side.
3. **WP-1 ⇄ WP-2 rights/retention attachment (ASK-WP2-3, new in C.2).** WP-1 puts
   `retention_class` on the content-addressed `raw_artifacts` row, so identical bytes acquired
   under two licences or tenants collapse to one retention class, silently. Publish one
   acquisition-scoped rights/retention interface (§3.5.1) before either lane lands. **Neither may
   resolve this unilaterally** — WP-2 cannot alter WP-1's schema, and WP-1's current design cannot
   carry WP-2's rights model.

**Owner decisions:**

3. **Secret resolver** — env, cloud secret manager, or restricted-grant table? Changes §7.3 only.
4. **Preview authorization** — which principals may trigger outbound egress, at what rate? A
   security decision, not a UX one.
5. **Certification authority** — who may issue `decision`-grade, and does it require the same
   independence as approval (§12)?
6. **Egress default** — deny-by-default with per-contract opt-in (recommended) vs
   allow-public-deny-private.
7. **Legacy backfill scope** — all 15 bespoke connectors get instances (recommended, uniform
   lineage) or only the generic ones?

## 15. Acceptance

No commitment to PR #327's artifact design (COORDINATION §13.4). Acceptance criteria must be
**owner-ratified before implementation**; the builder must not self-author its merge bar. The
`V2_REVIEW_REQUEST` successor protocol is noted and **not adopted** — it is untracked and
unratified, the same status that produced C.1 finding 7.

Test specifications: `WP-2_test_specifications.md` (rev C.1). Executable tests are introduced
inside the implementation PR that turns them GREEN.
