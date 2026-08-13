# Market Zero connector and data-transformation architecture review

**Independent red-team review**  
**Date:** 2026-08-07  
**Audience:** Market Zero owner, Data/Substrate team, Product/Platform team  
**Scope:** connector control plane, ingestion runtime, normalization, entity resolution, storage, graph derivation, facts/evidence, unstructured documents, quality, scheduling, replay, lineage, and operational validation

## Executive decision

**Decision: Market Zero should not yet describe this pipeline as a gold-standard unstructured-data transformation platform.** It is a credible, well-tested pharmaceutical ingestion application with several strong platform seams. It is not yet a lossless, replayable, source-configured, domain-pluggable transformation platform.

The previous one-line diagnosis was directionally correct: the highest-value semantic improvement is a deterministic identity spine, not another general-purpose connector. The diagnosis was incomplete, however. Identity is the largest *data-quality* constraint, while immutable raw capture, truthful run semantics, and versioned source-instance configuration are the largest *platform-integrity* constraints. All four are prerequisites for a gold-standard claim.

My concise assessment is:

- For the current, bounded pharma use case, the connector and ingestion implementation is approximately **B/B+**.
- For deterministic identity and cross-source integration, it is approximately **C-**.
- For provenance as source labelling, it is approximately **B-**; for reproducible lineage and replay, it is approximately **D+/C-**.
- For configuration-driven addition of a new source into an existing entity model, it is approximately **C** in code and **D** operationally because the generic adapters are not wired to a persisted runtime control plane.
- For a genuinely new domain or entity model, it is not config-only: `RecordType`, normalization, storage handlers, schemas, quality rules, and link behavior still require code and migrations.
- For unstructured transformation, it is an early **C-**: common office formats can be parsed and embedded, but raw artifacts, stable locators, OCR, span-correct entity linking, structured stage status, and replay are missing or incomplete.

The good news is architectural: this does not require a rewrite. The existing connector boundary, facts/evidence ledgers, resolution audit, DLQ, quality rules, and conservation culture are useful foundations. The work should be an additive hardening program with shadow reads and compatibility adapters.

**Decision: Pause net-new connector breadth except connectors that directly improve raw capture or deterministic identifiers until the P0 work in this report is complete.** More sources feeding a name-resolved graph will increase ambiguity faster than value.

**Decision: Keep Postgres as the curated entity/fact store and add an immutable object-backed bronze layer. Do not introduce Kafka, Spark, or a lakehouse engine until measured volume, latency, or recovery requirements justify them.** A bounded iterator, durable source cursor, object storage, Postgres metadata, and distributed leases are sufficient for the next architecture stage.

## Questions answered directly

### Is the deep design and approach sound?

The approach is sound for a vertical intelligence product: acquire authoritative records, normalize them, resolve entities, store canonical state, create relationships, and emit evidence-bearing facts. The append-only facts/evidence direction is especially strong.

The current execution model does not yet fully implement that design. Several comments and abstractions overstate the runtime guarantees:

- `DomainPack` is not active in the normal scheduler/API pipeline construction path.
- Generic REST/RSS/CSV connector classes exist but are neither registered nor scheduled per onboarded source instance.
- Critical hooks fail open, post-store quality cannot prevent the write, and the scheduler can call a partially failed pipeline run “OK”.
- Provenance identifies a source and payload hash but normally cannot reproduce the source artifact or the exact transformation.
- Core entity rows preserve only the most recent row-level source label, not source observations or field-level derivation.

### Can this become a gold standard for unstructured transformations?

Yes, but only after the architecture treats an uploaded or fetched artifact as an immutable first-class entity and every extraction as a versioned derivation with stable locators. Today, documents are flattened into strings, character-sliced, embedded, and optionally sent through best-effort extraction. That is useful retrieval plumbing, not yet an auditable unstructured transformation substrate.

### Is it modular/configurable enough for different data types?

It has two promising seams:

1. Generic transport adapters (`RestConnector`, `RssConnector`, `CsvConnector`) can map source payloads into existing `RecordType` values.
2. `DomainPack` centralizes much of the intended semantic configuration.

Neither seam currently provides end-to-end runtime modularity. The honest extensibility contract should be:

- **New source instance, existing semantic type:** configuration-only after the source-contract control plane is implemented.
- **New source protocol:** one reviewed connector adapter, reusable by many source instances.
- **New entity type or domain semantics:** a reviewed domain plugin plus schema migration; not arbitrary runtime configuration.

This boundary is safer and more maintainable than trying to make new relational semantics or arbitrary SQL config-only.

## Review method and evidence status

This review used four evidence classes:

1. Direct source inspection of the live construction path and its dependencies.
2. Targeted executable probes against imported repository code.
3. Targeted tests, run without changing production code.
4. The earlier `docs/data-pipeline-groundup-analysis-20260805.html` as secondary evidence for its 2026-08-05 production read-only probes.

No production writes were performed. The earlier report's production row counts were not re-probed on 2026-08-07 and must not be presented as current counts without a new read-only production query.

Validation executed for this review:

```text
224 passed, 14 warnings in 50.23s
```

The targeted set covered user documents, NER, generic REST/RSS/CSV connectors, crosswalk loaders, resolver cascade, cross-linker, ETL outcomes, source contracts/taxonomy, auto-create hook wiring, and DLQ behavior.

Two executable architecture probes also established:

```text
DomainRegistry.active() after importing integration.pipeline -> None

SourceType values: 20
registered connector classes: 15
scheduled connector classes: 14
pharma DomainPack sources: 12
static dataset catalog definitions: 12
generic REST/RSS/CSV registered: false / false / false
generic REST/RSS/CSV scheduled: false / false / false
drug exact identifier keys in DomainPack: nda_number only
DomainPack owner of chembl_id: molecular_target, not drug
```

Passing tests show that the implemented unit contracts are stable. They do not disprove the architectural gaps; several gaps are precisely contracts that do not yet have tests.

## Standards used as target references

These are reference models, not demands to import a large vendor stack:

- [OpenLineage core specification](https://github.com/OpenLineage/OpenLineage/blob/main/spec/OpenLineage.md): run/job/dataset separation, START and terminal events, source-code/version facets, input/output statistics, data-quality facets, and dataset versions.
- [W3C PROV Data Model](https://www.w3.org/TR/prov-dm/): explicit entities, activities, agents, derivations, responsibility, and versioned/specialized entities.
- [Open Data Contract Standard 3.1](https://bitol-io.github.io/open-data-contract-standard/latest/): versioned schema, data quality, owners/roles, support, infrastructure, and SLA declarations.
- [MLCommons Croissant 1.1](https://docs.mlcommons.org/croissant/docs/croissant-spec-1.1.html): versioned JSON-LD, resources, record sets, typed fields, references, hashes, licenses, and machine validation.

Market Zero need not mirror these schemas internally. It should be able to emit or map to them without inventing missing lineage after the fact.

## What actually runs today

### Main connector path

```text
APScheduler / manual API
        |
        v
connector.fetch(since=last_success_completed_at) -> list[RawRecord]
        |
        v
Normalizer -> EntityResolver -> Embedder
        |                         ^
        |                         | embedding currently happens before change detection
        v
PRE_STORE hooks: validation + change detection (hook exceptions fail open)
        |
        v
KnowledgeStore handler (autocommit)
        |
        v
CrossLinker (separate autocommit writes)
        |
        v
POST_STORE quality assessment + HITL (cannot undo the stored row)
        |
        v
ETL run finalized
        |
        +--> ON_RUN_COMPLETE hooks (after finalization)
        +--> static catalog refresh (best effort)
```

Evidence: `integration/pipeline.py:180-222`, `integration/pipeline.py:224-317`, `integration/pipeline.py:331-455`, `integration/pipeline_hooks.py:71-124`, and `db.py:10,73,146-190`.

### Derived-data path

There are two materially different orchestration paths:

- The live scheduler registers connectors plus sensing promotion and ledger convergence (`scheduler/runner.py:630-683`).
- `run_now()` additionally invokes a long sequence of linkage, quality-fix, pricing, TA, deduplication, auto-curation, steward, calibration, learning, and regrounding tasks (`scheduler/runner.py:101-338`). Most of those are not dependency-tracked live jobs.

This supports the earlier report's finding: important company/drug/therapeutic-area/competition topology was produced by backfill or curation jobs rather than wholly by the per-record live cross-linker. The live cross-linker can create direct links when the incoming record already contains a resolver-recognized identifier; it does not replace the offline derivations.

### Control plane

There are currently three partial and non-unified control planes:

- `connector_config`: enable/manual/approval flags for registered code connectors.
- `sources` plus `source_onboarding`: source metadata, connector taxonomy, and lifecycle.
- Python connector configuration, scheduler constants, normalizer maps, `DomainPack`, and static dataset definitions.

The scheduler does not read `connector_config` when registering or running cron jobs. `source_onboarding` does not persist the generic connector's endpoint, mappings, authentication reference, quality contract, must-capture fields, or license contract. No runtime factory loads a production onboarding row into `RestConfig`, `RssConfig`, or `CsvConfig`.

## What is already strong

The red-team findings should not hide the good engineering already present:

- A small `BaseConnector` interface and consistent `RawRecord` envelope make bespoke sources understandable.
- Source endpoint, retrieval time, query parameters, and response hashes are captured at record construction for many connectors.
- Core store handlers are generally idempotent and use deterministic external keys or conflict constraints.
- Failed record processing has a DLQ with payload, error, traceback, and basic provenance.
- Entity resolution has an explicit strategy cascade, audit table, unresolved queue, confidence, and HITL concepts.
- Facts and evidence have append-only intent, content hashes, validity fields, confidence, epistemic class, and supersession.
- Generic CSV/RSS/REST adapters have useful mapping and pagination capabilities with focused tests.
- Source quality, dataset catalog, freshness SLAs, and richer ETL outcome vocabulary show good operational instincts.
- The repository's conservation gates and anti-vacuous-green tests are the correct engineering culture for this work.

These are foundations to retain, not reasons to preserve the current orchestration semantics unchanged.

## Red-team corrections to the earlier analysis

### Correction 1: “A-grade provenance substrate” is too generous

`Provenance` records source type, endpoint, query parameters, retrieval time, a hash, and optional run ID (`connectors/base.py:142-167`). For most core rows, the store saves only `source_api`, `source_url`, and `retrieved_at`; only selected tables carry `etl_run_id`. A hash without retained bytes or an immutable snapshot reference cannot be replayed or independently verified.

The evidence ledger is stronger than entity ingestion, but it is downstream and does not reconstruct a discarded API page or uploaded binary.

### Correction 2: “skips are counted” is only locally true

Generic connectors count malformed/no-ID records in local variables and write warnings. Those counts are not returned in a structured fetch report, persisted in `etl_runs`, or included in a conservation equation. REST truncation at `max_pages` or a stuck cursor is also only a warning and returns a partial list (`connectors/rest_connector.py:373-443`). A partial response can therefore finalize as a landed success.

### Correction 3: `fact_class` belongs to fact emission, not the quality engine

The source-to-class policy is in `services/fact_emitters/base.py:40-71,247-249`. The earlier footer correction is accurate.

### Correction 4: the global chunk configuration does not drive the embedder

`config.pipeline.chunk_size_tokens` and `chunk_overlap_tokens` are declared at `config.py:103-105`. `Embedder` hard-truncates text to 32,000 characters (`integration/embedder.py:72-107`) and does not use those settings. `UserDocumentConnector` performs its own character-based chunking with separate defaults; the upload route does not inject global chunk settings. NER has a third, 12,000-character chunk policy.

### Correction 5: `DomainPack` is an intended seam, not the current live control plane

The pipeline uses `domain_pack or DomainRegistry.active()` (`integration/pipeline.py:180-185`), but no normal composition root registers the pharma pack. The executable probe returned `None`. Storage remains a hardcoded `RecordType` router (`integration/knowledge_store.py:142-178`), and `EntitySchema.store_columns`, `upsert_conflict_column`, and `coalesce_on_update` are declared but unused.

### Correction 6: uploaded entity mentions do not currently produce the claimed links

`UserDocumentConnector` puts parallel `entity_mentions` and `mention_types` arrays into identifiers (`connectors/user_document.py:110-138`). The resolver recognizes keys such as `generic_name`, `company_name`, and exact IDs, not `entity_mentions`. `CrossLinker._link_chunk` likewise checks only `company_name`, `cik`, and `generic_name` (`integration/cross_linker.py:387-411`). Unit tests assert mention arrays are emitted but do not assert a mention resolves and creates an entity link.

## Gold-standard capability scorecard

| Capability | Current state | Verdict |
|---|---|---|
| Stable source-instance identity | Generic instances collapse to `SourceType.REST/RSS/CSV_FILE`; ETL watermarks and run names use type | Fail |
| Versioned source contract | Transport configs exist in Python; onboarding does not persist/deploy them | Fail |
| Lossless raw landing | Hashes exist; source bytes/pages normally do not | Fail |
| Deterministic replay | No raw artifact plus config/code version input bundle | Fail |
| Stage conservation | Strong culture and some counters; connector skips/truncation and post stages do not fully reconcile | Partial |
| Truthful success/failure | Rich outcome vocabulary exists; fail-open hooks and scheduler “OK” weaken it | Partial |
| Deterministic entity identity | Some exact keys and a governed crosswalk table exist; molecule crosswalk is sparse and not in resolver | Partial/Fail |
| Modular source onboarding | Generic adapters exist; no runtime source factory/scheduler wiring | Partial/Fail |
| Modular domain semantics | `DomainPack` design exists; inactive by default and storage remains hardcoded | Partial/Fail |
| Unstructured structure preservation | PDF/PPTX/DOCX/HTML/text extraction exists; layout/locators/OCR/span correctness incomplete | Partial |
| Versioned transforms and derived jobs | Fact emitters are registered; many graph derivations remain script-shaped and path-dependent | Partial |
| Field-level provenance and survivorship | Row-level current source only | Fail |
| Quality contracts and quarantine | Configurable rules/HITL/DLQ exist; unknown rules pass and strict post-store quality cannot gate | Partial |
| Standard lineage export | No end-to-end OpenLineage/PROV activity graph | Fail |
| Machine-valid dataset metadata | Croissant-like static JSON-LD exists; definitions are static and no 1.1 validation gate is evident | Partial |
| Fault-tolerant scaling | In-memory lists, process-local batch counters, no source lease/checkpoint | Partial/Fail |

## Findings register

### G-01 — Source type is being used as source-instance identity

**Priority:** P0  
**Confidence:** High

`BaseConnector.source_type()` and `CONNECTOR_REGISTRY` are keyed by a closed enum. `_create_etl_run` writes `source_type.value`, a blank endpoint, and `{}` query parameters. The scheduler retrieves the last successful completion using that same value. This works for one bespoke connector per enum but cannot safely host ten REST sources: they would share run history and watermark.

The `source_id` on generic config never enters `RawRecord.Provenance`, `etl_runs`, storage provenance, scheduler identity, or catalog identity.

**Impact:** Config-driven multi-source onboarding is structurally unsafe even if the generic classes are registered tomorrow.

### G-02 — Fail-open control semantics can create false green

**Priority:** P0  
**Confidence:** High

- Every hook exception becomes `HookResult(action="continue")` (`integration/pipeline_hooks.py:94-119`), including validation and change detection.
- Strict validation is counted as a skip, not a quarantine/failure, and `records_skipped` is not persisted in ETL finalization.
- `NewEntityReviewHook` return values are ignored by the pipeline (`integration/pipeline.py:345-361`), so manual blocking is ineffective there.
- `QualityGateHook` runs after store and its block result is not acted on (`integration/pipeline.py:412-429`).
- ON_RUN_COMPLETE hooks run after the ETL row is finalized; their failure cannot change the terminal outcome.
- `_run_connector` does not raise when `PipelineResult` contains record errors, so the scheduler caller can report “OK”.
- Enrichment queue failure is a literal `except Exception: pass` (`integration/pipeline.py:431-455`).

**Impact:** “SUCCESS” does not consistently mean all mandatory controls ran and all conservation-critical stages completed.

### G-03 — Raw inputs are not replayable

**Priority:** P0  
**Confidence:** High

API item hashes are often computed after JSON parsing or mapping, and uploaded bytes are hashed but discarded after the request. There is no immutable artifact reference in `Provenance`; `evidence_records.archived_snapshot_ref` is optional and downstream. DLQ stores the mapped `record.data`, not the original response bytes, headers, page, or artifact.

**Impact:** A parser change, mapping dispute, upstream deletion, or audit cannot be reproduced from retained inputs.

### G-04 — A record is not an atomic transaction

**Priority:** P0  
**Confidence:** High

Database operations autocommit unless explicitly wrapped. Resolver auto-create, change-log insertion, entity store, graph links, quality results, and HITL writes occur as separate commits. Change detection logs a mutation before the store succeeds. A cross-link failure can leave the entity stored while the record goes to the DLQ.

**Impact:** Partial state is recoverable only by idempotent retry and luck; audit rows can describe writes that did not complete.

### G-05 — The deterministic identity spine is designed but not operational

**Priority:** P0  
**Confidence:** High

The drug `DomainPack` exact lookup includes only `nda_number`. Existing unique columns such as `unii` and `chembl_id`, plus `rxcui`, `pubchem_cid`, `inchi_key`, NDCs, and crosswalk records, are not a unified exact resolver path. Examples:

- openFDA label RxCUI is stored in data but not emitted as a resolver identifier.
- PubChem emits CID and InChIKey in data, but the resolver does not exact-match them.
- ChEMBL emits `chembl_id`, while the global pack lookup for that key currently points at `molecular_targets`, illustrating the danger of identifier keys without entity context.
- `crosswalk_records` is populated by offline loaders and is not queried by `EntityResolver`.
- Crosswalk bootstrap first selects an internal drug by name, then attaches an external ID.
- The crosswalk uniqueness key allows the same external identity to attach to multiple internal entities; that is legitimate for class mappings such as ATC but unsafe for active exact substance identity without a relation-aware uniqueness rule.

`KnowledgeStore._store_drug` falls back from NDA to case-insensitive generic name. That can collapse salts, formulations, combinations, brands, and substances that should be related rather than identical.

**Impact:** Cross-source joins depend on names even when authoritative identifiers are available.

### G-06 — The unstructured path loses structure and has an entity-span defect

**Priority:** P0 for the stated gold-standard goal  
**Confidence:** High

- Original binaries are not archived.
- PDF/PPTX tables are flattened into text; chunks do not retain page/slide, bounding box, table/cell, section, or source character locator.
- Scanned PDFs have no OCR branch or OCR confidence.
- Character slicing can split headings, sentences, tables, and page boundaries.
- NER chunks long text but does not add each chunk's global start offset to model-returned offsets. It also deduplicates by `(text, type)`, losing repeated occurrences and their locators.
- The later chunk assignment assumes global offsets, so mentions after the first NER chunk can be assigned to the wrong document chunk.
- Mention arrays are not resolver-recognized, so the advertised mention-to-link path is incomplete.
- Upload validation fetches/extracts/NERs once for preview and the pipeline repeats it; fact extraction extracts the document a third time.
- Pipeline failures are returned inside `PipelineResult`, so the upload route's `try/except` does not convert them to HTTP 500 as its comment implies.
- Fact extraction is best effort and can return zero with only a server log; no stage outcome explains “not applicable”, “LLM unavailable”, “extraction failed”, or “subject unresolved”.

**Impact:** Retrieval may work, but exact evidence reconstruction and trustworthy structured extraction do not.

### G-07 — `DomainPack` and generic adapters are not an operational plugin system

**Priority:** P1  
**Confidence:** High

`DomainPack` centralizes intended lookup, validation, mapping, and link declarations, but it is dormant by default and incomplete for current sources. The pharma pack omits several newer sources from mappings/config/staleness. `KnowledgeStore` still requires a hardcoded handler for every `RecordType`. Generic adapters are unit-tested but absent from the runtime registry and schedule.

**Impact:** The system is modular in source layout, not yet modular in deployment or semantics.

### G-08 — Derived graph topology is path-dependent and not a first-class live data product

**Priority:** P1  
**Confidence:** High

Direct record links are created in `CrossLinker`. Broader OWNS, TA, mechanism, sponsor, cross-source, deduplication, and competition derivations are materially dependent on scripts such as `backfill_data_linkage.py`, `scripts/backfill_ta_links.py`, `scripts/dedup_companies.py`, and auto-curation. Most run only in `run_now()`, not as live dependency-aware jobs.

`entity_links` uses `ON CONFLICT DO NOTHING`, so a later stronger confidence/provenance cannot update an existing edge, and a no-longer-derivable edge is not automatically superseded.

**Impact:** The graph differs depending on which operational path was invoked and when a one-off script last ran.

### G-09 — Canonical rows overwrite source observations and field provenance

**Priority:** P1  
**Confidence:** High

Core handlers merge new data directly into canonical rows and overwrite `source_api/source_url/retrieved_at`. There is no retained per-source observation or field assertion explaining which source supplied each current value. Incoming non-null values can replace current values without a centrally enforced authority/freshness policy.

**Impact:** Multi-source corroboration, conflict explanation, rollback, survivorship changes, and historical reconstruction are weak. A single `source_api` is not provenance for a composite entity.

### G-10 — Incremental ingestion and scaling are not checkpoint-safe

**Priority:** P1  
**Confidence:** High

- `fetch()` returns an in-memory list; REST/CSV/RSS parsers and most bespoke connectors accumulate whole batches.
- The scheduler watermark is the previous run's `completed_at`, not a source-native cursor or maximum accepted source timestamp.
- Several connectors ignore or only partially honor `since`.
- A truncation warning does not block cursor advancement.
- Chunked connector batch counters are process-local and reset on restart.
- There is no distributed per-source lease; each application process can start its own scheduler.
- Retry ignores `Retry-After`, lacks a shared rate limiter/circuit breaker, and returns the last retryable response after exhaustion.

**Impact:** Large inputs risk memory pressure; delayed or mid-run source updates can be skipped; multi-instance deployments can duplicate work; crashes lose page progress.

### G-11 — Quality is useful but cannot yet be a promotion gate

**Priority:** P1  
**Confidence:** High

- It runs after the canonical write.
- Unknown rule types return a passing 1.0 result.
- An empty completeness field list passes 1.0.
- An unparseable timestamp returns a “pass” helper with a 0.5 score.
- Per-record quality results are deleted and replaced, losing assessment history.
- Cross-source quality counts link provenance, not independent field-level observations.
- A composite average can hide a failed critical dimension.

**Impact:** The score is a monitoring annotation, not a safe contract or silver-to-gold promotion decision.

### G-12 — Run lineage and catalog metadata are incomplete and static

**Priority:** P1  
**Confidence:** High

`etl_runs.api_endpoint` and `query_params` are written blank by the main pipeline. Run rows lack source-contract version, transform version, code SHA, raw input artifacts, output dataset versions, cursor before/after, connector skip counts, truncation, and stage outcomes. Catalog definitions are static Python entries and therefore drift from the registry, scheduler, `DomainPack`, and onboarding database.

**Impact:** There is no exact query from a fact or graph edge back through every activity to a retained input and deployed contract.

### G-13 — Important many-to-many relationships are flattened

**Priority:** P1  
**Confidence:** High

ClinicalTrials.gov takes the first DRUG intervention as `generic_name`; `clinical_trials.drug_id` is scalar. Combination regimens, comparator arms, biologics, devices, multiple sponsors/collaborators, and intervention roles cannot be represented faithfully by one FK. Similar flattening exists when article/document mentions are converted into one primary entity.

**Impact:** The graph can be internally consistent but semantically incomplete or wrong for multi-asset trials.

### G-14 — Runtime-configured and unstructured sources need a security boundary

**Priority:** P1 before enabling generic production onboarding  
**Confidence:** High

Generic REST auth values are direct config fields rather than secret references. Arbitrary URLs create SSRF and redirect risks. Document uploads need archive encryption/retention, malware/archive-bomb controls, PII classification, license/use restrictions, and prompt-injection-safe treatment as untrusted data.

**Impact:** Wiring the existing generic connectors directly to a UI would expand the attack and compliance surface before governance is enforceable.

### G-15 — Fact/evidence derivation can collapse corroborating sources

**Priority:** P1  
**Confidence:** Medium/High

Document trial-readout idempotency is based on drug, trial identifier, and date, not artifact hash. A second independent document can be treated as the same existing fact without attaching a second evidence record. `facts` has one `source_doc_id`, while the separate claims ledger supports many evidence links. The document readout fact also leaves `valid_from` unset even though the extraction schema supplies a readout date.

**Impact:** Re-upload deduplication is useful, but independent corroboration and temporal fidelity can be lost.

### G-16 — Tests prove components, not the end-to-end guarantees

**Priority:** P1  
**Confidence:** High

The targeted 224 tests are healthy. Missing architectural assertions include:

- every connector item is emitted, filtered with an explicit reason, quarantined, or failed;
- truncation prevents success and cursor advance;
- critical hook failure is terminal;
- strict quality prevents current-state promotion;
- scheduler propagates a partial/failed `PipelineResult`;
- a generic onboarded source is instantiated, scheduled, run, and catalogued by `source_id`;
- an uploaded mention resolves to the correct entity and exact source span;
- a killed job restarts from a durable checkpoint;
- two scheduler instances execute a source only once;
- raw replay with pinned versions yields identical canonical output.

## Target architecture

### Architectural layers

```text
                         CONTROL PLANE
 Git-reviewed SourceContract vN + secret refs + DomainPlugin version
             | validate | approve | deploy | pause | rollback
             v

                          DATA PLANE
 source -> fetch page/file -> immutable RawArtifact (bronze)
                              |
                              v
                    SourceRecord envelopes
                     /          |          \
              contract      parse/IR     quarantine
              validation        |             |
                     \          v             |
                      -> normalized observations (silver)
                                  |
                                  v
                       deterministic identity spine
                                  |
                  +---------------+----------------+
                  |                                |
          canonical projections             versioned transforms
          (entities/current state)       (facts, edges, signals, marts)
                  |                                |
                  +---------------+----------------+
                                  v
                    published dataset snapshot (gold)

 Every arrow emits a stage result and lineage edge. Every output can resolve
 to input artifact, source contract, code/config version, and run.
```

### Canonical ingestion envelope

Replace the implicit combination of `SourceType`, `RawRecord`, and logging counters with a versioned envelope. Names are illustrative; the contract is what matters.

```json
{
  "envelope_version": "1.0",
  "source_id": "openfda-labels-prod",
  "connector_kind": "api_rest",
  "source_record_id": "set-id-or-source-key",
  "record_kind": "drug_label",
  "artifact_id": "uuid-of-raw-page-or-file",
  "artifact_sha256": "...",
  "source_event_time": "2026-08-01T00:00:00Z",
  "observed_at": "2026-08-07T02:00:00Z",
  "source_cursor": "opaque-upstream-cursor",
  "contract_version": "3.2.0",
  "parser_version": "git-sha:module:version",
  "schema_version": "drug_label/2",
  "license_policy_id": "fda-public-domain/v1",
  "payload_or_pointer": {},
  "identifiers": [
    {"entity_type": "substance", "namespace": "rxnorm", "value": "...", "scope": "IN"}
  ]
}
```

Do not put secrets into the envelope or raw request metadata. Store only a secret reference and redact credential-bearing query/header values before hashing metadata.

### Honest modularity boundary

**Decision: Make source instances config-driven, but keep new semantic types code-reviewed.**

Split the current broad `DomainPack` idea into two responsibilities:

- `SourceContract`: declarative, versioned, validated, deployable configuration for transport, mapping, schema, data quality, SLA, licensing, ownership, and secrets references.
- `DomainPlugin`: reviewed code that owns record/entity schemas, typed identifier namespaces, projection/store strategy, link rules, and migrations.

A new REST feed mapping into an existing `drug_label` or `event` contract should need no Python change. A new concept such as genomic sample, payer formulary, image assay, or package-level medicinal product should require a plugin and migration because it changes semantics and storage, not merely configuration.

### Identity model

Do not treat every drug-like row as the same entity grain. Ratify an ADR covering at minimum:

- substance/ingredient;
- precise ingredient or salt where necessary;
- medicinal/clinical product and strength/form;
- branded product;
- regulatory application;
- package/presentation;
- trial intervention/arm.

Identifiers must be typed by entity grain and vocabulary. Examples:

- UNII and correctly scoped RxNorm IN/PIN for substance identity;
- full InChIKey or an explicitly declared connectivity-only match with stereochemistry/salt caveats;
- ChEMBL molecule ID and PubChem CID as external molecular records, governed by relation/scope;
- RxNorm SCD/SBD for clinical/branded product, not molecule identity;
- NDA/BLA/ANDA as regulatory-application relations, not universal molecule identity;
- NDC as product/package identity;
- ATC as classification, never exact identity.

Prefer unresolved or quarantined over a false merge. Name, fuzzy, embedding, and LLM decisions are candidate generation or fallback linkage, not identity proof.

## Implementation program

Each work package below maps to one or more findings. Reserve the next migration number at implementation time; do not copy a number from this report into a concurrent branch.

### WP-0 — Make run outcomes and controls truthful

**Covers:** G-02, part of G-04, G-16  
**Priority:** P0; land first

#### Implementation

1. Add typed stage severity/policy to hooks: `advisory`, `required`, and `promotion_gate`.
2. Change `HookRegistry.fire` so exceptions from required or promotion-gate hooks return a terminal failure; only explicitly advisory hooks may fail open.
3. Replace string actions with an enum and validate illegal actions.
4. Make validation failures create a quarantine/record-attempt row with a reason. Keep the raw record; do not call this “unchanged” or silently skip it.
5. Move quality evaluation before canonical promotion, or initially evaluate a candidate record and prevent promotion in strict mode. Do not claim that a post-store block blocked anything.
6. Act on the result of `NewEntityReviewHook`; in manual mode, persist a pending candidate rather than creating a live canonical entity first.
7. Remove the enrichment `except: pass`; return an advisory stage failure counter and log with run/record IDs.
8. Persist `records_fetched`, `records_emitted`, `records_filtered`, `records_skipped`, `records_quarantined`, `records_failed`, `connector_malformed`, and `truncated` in the run schema.
9. Run ON_RUN_COMPLETE required hooks before setting the terminal ETL state. Advisory catalog refresh may remain after terminal state, but must have its own job/run outcome.
10. Change `_run_connector` and API callers to raise or return a non-OK status when `result.success` is false, when the result is partial, or when a required stage failed.
11. Make `FAILURE_ZERO_ROWS`, `PARTIAL`, and `FAILURE` consistent between `status`, `outcome`, API responses, health scoring, and scheduler results.

#### Required tests

Create focused RED tests first, then implement:

- `test_required_hook_exception_fails_run`
- `test_advisory_hook_exception_is_visible_but_nonterminal`
- `test_strict_validation_quarantines_and_does_not_store`
- `test_strict_quality_does_not_promote_candidate`
- `test_manual_auto_create_does_not_create_live_entity`
- `test_scheduler_does_not_report_ok_for_partial_pipeline_result`
- `test_skipped_and_quarantined_counts_persist`
- `test_on_run_required_failure_changes_terminal_outcome`

#### Validation and exit gate

For every stage, assert a conservation equation using stage-specific units. At connector item level:

```text
items_seen = emitted + filtered_by_contract + rejected_malformed + quarantined
```

At pipeline record level:

```text
records_emitted = inserted + updated + unchanged + quarantined + failed
```

No successful non-truncated run may violate either equation. A deliberately failing hook must produce a red terminal result in unit, integration, and deployed canary probes.

### WP-1 — Add immutable raw artifacts and deterministic replay

**Covers:** G-03, G-04, G-12  
**Priority:** P0

#### Implementation

1. Define a `RawArtifactStore` interface: `put(bytes, metadata) -> artifact_ref`, `get(ref)`, `exists(hash)`, and retention/legal-hold operations.
2. Implement a local filesystem adapter for tests and the deployment's object-store adapter for production. Use content-addressed paths and server-side encryption.
3. Add append-only metadata tables for raw artifacts and artifact-to-run usage. Record source ID, content hash, byte size, MIME type, sanitized HTTP metadata, observed time, upstream version/ETag if available, license policy, and immutable URI.
4. Capture each fetched API page/file/feed/upload before parsing it. The artifact is the hash of exact bytes, not reconstructed JSON.
5. Link every `SourceRecord` to an artifact and, where applicable, a JSON pointer, XML locator, row number, page, or byte range inside it.
6. Add parser/normalizer/config/code versions to each transformation attempt.
7. Implement `scripts/replay_artifact.py --artifact-id ... --contract-version ... --dry-run` using the same parser/normalizer interfaces without refetching the source.
8. Compare replay output hashes after excluding declared nondeterministic fields. Store the comparison result.
9. Put artifact and stage metadata inside a per-record transaction; never write a change-log entry before the corresponding projection commits.
10. Define retention by source contract. Do not silently delete artifacts referenced by active facts, signed decisions, legal holds, or unresolved reviews.

#### Required tests

- Exact source bytes can be retrieved and hash-verified.
- Replay with identical code/config produces identical normalized observation hashes.
- Parser-version change produces a new derivation without overwriting the old result.
- A corrupt/missing artifact fails closed.
- Secrets in headers/query strings never appear in artifact metadata or logs.
- Re-uploading identical bytes deduplicates storage but records a new observation/run relationship when required.

#### Validation and exit gate

Select one API page, one RSS/Atom feed, one CSV, one PDF, and one PPTX. Demonstrate, from only database metadata plus object storage, exact-byte recovery and deterministic replay into the expected source-record set. This is the minimum bar for calling provenance replayable.

### WP-2 — Create a versioned source-contract control plane

**Covers:** G-01, G-07, G-10, G-12, G-14  
**Priority:** P0/P1

#### Implementation

1. Define a strict Pydantic/JSON Schema `SourceContract`; set unknown fields to forbidden so the F5-style silent-loss defect cannot recur.
2. Include: `source_id`, display/owner/support, connector kind/adapter, endpoint or file locator, record kind, schema version, field/identifier mappings, must-capture fields, incremental cursor policy, pagination, expected volume, freshness SLA, quality rules, license/use/retention, secret references, network policy, schedule, and status.
3. Align export/import fields with ODCS 3.1 where practical; keep Market Zero extensions in a namespaced custom section.
4. Store immutable contract versions. A lifecycle row points to the deployed version; edits create a new version rather than mutating production history.
5. Choose a single desired-state authority. Recommended: Git-reviewed contracts under `contracts/sources/`, with the database storing deployments and runtime state.
6. Replace direct secret values with provider/key references resolved only inside the connector factory.
7. Build `ConnectorFactory.create(contract_version)` for bespoke and generic adapters. The connector must expose `source_id` separately from connector kind.
8. Make the scheduler load all deployed `prod` contracts, apply `enabled/paused/manual_only`, and register jobs by `source_id`.
9. Remove scheduler dependence on one enum value per source. Preserve `SourceType` temporarily as connector kind/legacy compatibility, not identity.
10. Make health, run history, watermark, catalog, DLQ, lineage, and source quality use `source_id`.
11. Add staged onboarding gates: contract lint -> network/credential check -> sample fetch -> schema/mapping validation -> dry-run conservation -> steward approval -> staged shadow run -> production.
12. Implement rollback by repointing deployment to the previous immutable contract version.

#### Security requirements

- Allow only `https` by default.
- Resolve DNS and block loopback, link-local, metadata-service, and private networks unless an explicit enterprise network policy allows them.
- Revalidate redirects and cap redirect count/response bytes/decompression ratio.
- Enforce host allowlists, timeouts, MIME type, content length, rate limit, and TLS policy.
- Redact secrets from logs, run metadata, DLQ, and artifact metadata.

#### Required tests

- Two REST sources have independent run IDs, cursors, schedules, health, and catalog entries.
- Unknown contract fields are rejected.
- A prod transition without mappings/license/must-capture/owner is rejected.
- Paused/disabled/manual-only sources do not run on cron.
- Contract rollback restores the prior behavior without deleting history.
- SSRF and redirect tests cover loopback, RFC1918, link-local, DNS rebinding simulation, and oversized responses.

#### Validation and exit gate

Onboard two safe public fixtures through only source contracts—no Python edits—into an existing record kind. Run them concurrently and prove that their artifacts, counts, cursors, failures, provenance, and catalog entries never collide.

### WP-3 — Turn domain configuration into an explicit, testable plugin

**Covers:** G-07, G-12  
**Priority:** P1

#### Implementation

1. Add an application composition root that explicitly injects `get_pharma_pack()` into every scheduler and API pipeline construction.
2. Add a startup assertion: production cannot silently run with no domain plugin unless an explicit legacy mode is enabled.
3. Create parity tests comparing pack-derived mappings/validation/links with legacy registries for every registered `RecordType` and source.
4. Complete the pharma plugin for currently registered sources before deleting fallback maps.
5. Replace global identifier-key maps with `(entity_type, namespace)` identity specs so `chembl_id` cannot ambiguously mean a drug or target.
6. Introduce a `RecordHandler`/`EntityAdapter` interface for validation, identity extraction, projection, and direct links.
7. Refactor `KnowledgeStore` routing to a handler registry. Move one low-risk record type first, then migrate types incrementally.
8. Remove or implement unused `EntitySchema` fields; declarations that do nothing should fail a plugin compile check.
9. Validate the entire plugin at startup: unique record ownership, valid tables/columns, valid link types, recognized identifier namespaces, and quality rule types.
10. Version plugins and stamp the version on transformation runs.

#### Required tests

- Pipeline construction has an active pharma plugin in scheduler and upload API paths.
- Every registered record kind has exactly one store handler.
- Every source mapping targets a declared field.
- Every link rule has a valid link type and compatible source/target entity grain.
- Legacy and plugin output hashes match on a fixture corpus before legacy removal.
- A synthetic second plugin can process a small fixture without editing pipeline core.

#### Validation and exit gate

Remove the legacy fallback only after 100% fixture parity and a shadow production comparison. “New domain” is accepted only when a plugin, migration, contract, and end-to-end test land together.

### WP-4 — Build and wire the deterministic identity spine

**Covers:** G-05, G-09, G-13, part of G-15  
**Priority:** P0/P1; highest semantic leverage

#### Implementation

1. Write and approve an ADR defining entity grains and allowed identity relations. Include combination products, salts, stereochemistry, strength/form, brands, applications, and packages.
2. Add a normalized `entity_identifiers` table or evolve `crosswalk_records` behind a compatibility view. Required fields: entity type/grain, entity ID, namespace, raw and normalized value, relation, scope/TTY, confidence, method, source observation, validity, review state, and status.
3. Add relation-aware constraints. Active exact identity identifiers must not map to multiple canonical entities; class/related mappings may be many-to-many.
4. Preserve every conflicting assertion and quarantine the resolution. Never silently reassign an exact ID.
5. Backfill identifier observations from current columns: NDA, UNII, ChEMBL, PubChem, InChIKey, RxCUI, NDC, CIK, LEI, ticker, PMID/DOI, NCT, Ensembl, ORCID, patent IDs, and source-specific IDs.
6. Update connectors to emit typed identifiers with intended entity grain and scope. Do not leave authoritative IDs only in `data`.
7. Specifically map RxNorm TTY; do not treat an SBD/SCD RxCUI as molecule identity. Keep ATC as classification.
8. Add a resolver stage before aliases/fuzzy matching that queries active approved exact identifiers and governed crosswalks.
9. Make exact-ID conflicts terminal to automatic resolution and route them to a dedicated review queue.
10. Use names to generate candidates only after exact identifiers fail. Disable auto-alias creation from unreviewed LLM/fuzzy matches until precision is demonstrated.
11. Backfill in shadow mode: write proposed mappings and compare with current links without changing canonical FKs.
12. Review high-value/collision clusters, then promote approved mappings in bounded batches with before/after manifests.
13. Dual-read old and new resolver paths, record disagreements, and switch behind a feature flag.
14. Update store handlers to locate canonical entities through the identity service rather than NDA/name-specific SQL.

#### Required tests and gold set

Create a reviewed identity gold set containing:

- same molecule across UNII/RxNorm IN/ChEMBL/PubChem/InChIKey;
- salt/base and stereoisomer distinctions;
- brand vs ingredient;
- SCD/SBD vs IN/PIN;
- combination therapies and reordered components;
- same name in different entity types;
- ambiguous abbreviations and placebo/dosage-arm junk;
- mergers/aliases for companies;
- conflicting exact identifiers.

Test that exact IDs are deterministic, scope rules are enforced, conflicts quarantine, and name methods never override an exact conflict.

#### Validation and exit gate

Recommended launch floor, subject to owner approval:

- 100% of gold-set exact identifiers resolve through the exact/crosswalk path.
- Zero active exact-identity namespace collisions.
- At least 99.5% precision on reviewed automatic identity decisions; prefer lower recall to false merges.
- 100% of the top 500 product-priority assets have a reviewed substance/product identity status, even if that status is unresolved.
- No regression in downstream trial/fact counts after canonical remapping; all moved relationships reconcile by manifest.

### WP-5 — Replace flat document text with a versioned Document IR

**Covers:** G-06, G-14, G-15, G-16  
**Priority:** P0/P1 for unstructured goal

#### Implementation

1. Make the raw artifact from WP-1 the document root and assign a stable `document_id` based on artifact hash plus source observation.
2. Define a `DocumentIR` with ordered blocks. Each block carries document/page/slide, section hierarchy, block type, text, global character range, optional bounding box, table/cell coordinates, language, parser method, and confidence.
3. Preserve PDF/PPTX/DOCX/HTML structure. Flattened text may remain a derived view, never the only representation.
4. Add an OCR branch for image-only pages, with per-page method and confidence. Store images only according to license/retention policy.
5. Replace character-count chunking with a pluggable segmenter using model tokenization and semantic boundaries. Do not cross a page/slide/section/table boundary without an explicit policy.
6. Stamp each segment with `segmenter_version`, token model, overlap policy, parent block IDs, exact source spans, and a segment content hash.
7. Fix NER offsets by carrying `(chunk_text, global_start)` and translating all returned offsets. Keep every occurrence as an `entity_mention`; do not deduplicate away span locations.
8. Replace parallel mention/type arrays with rows or typed objects: mention ID, entity type, text, normalized text, start/end, block/segment, extraction method/model/prompt version, confidence, and status.
9. Resolve each mention with entity-type context through WP-4 and create a provenance-bearing mention-to-entity link.
10. Run parsing, segmentation, NER, fact extraction, and embedding once per versioned stage. The preview endpoint should read the dry-run stage result rather than re-extracting.
11. Give document fact extraction an explicit outcome enum: `not_applicable`, `unavailable`, `succeeded`, `partial`, `failed`, `subject_unresolved`.
12. Attach every extracted fact to one or more precise evidence locators and the raw artifact. Preserve multiple independent evidence records for corroboration.
13. Populate fact valid time from the extracted readout/period date and asserted time from ingestion.
14. Treat all document content as untrusted data in model prompts. Use structured outputs, bounded content, prompt separation, content-policy scans, and never execute embedded instructions/URLs/macros.

#### Gold corpus and required tests

Create a versioned, licensed fixture corpus with:

- native and scanned PDF;
- multi-column paper;
- PDF and PPTX tables;
- deck speaker notes;
- DOCX headings/tables;
- HTML with scripts/styles and hostile prompt text;
- UTF-8 and non-UTF-8 text;
- long documents with repeated entity mentions beyond the first NER chunk;
- corrupted, oversized, encrypted, and archive-bomb-like inputs.

Required assertions:

- Every segment's text can be reconstructed from its source blocks.
- Every mention locator round-trips to the exact displayed source text.
- Mentions after the first NER chunk land in the correct segment.
- Repeated mentions remain distinct occurrences.
- One uploaded mention creates the expected resolver decision and graph link.
- Reprocessing with a new parser/segmenter creates a new version without deleting the old one.
- Two documents corroborating one fact retain two evidence links.

#### Validation and exit gate

Do not choose an extraction-accuracy threshold from convenience. Establish a double-reviewed gold corpus, measure precision/recall by fact type and entity type, and have the owner approve release floors. Structural floors are non-negotiable: 100% valid locators, 100% artifact lineage, and zero silent extraction failures.

### WP-6 — Make derived graph and fact transforms first-class jobs

**Covers:** G-08, G-12, G-15  
**Priority:** P1

#### Implementation

1. Define a `TransformJob` contract: name, semantic version, code SHA, input datasets/versions, output dataset, dependencies, cursor/partition, quality checks, owner, and reconciliation mode.
2. Add `derived_job_runs` plus input/output manifests and lineage edges.
3. Refactor each backfill/curation script into a pure transformation core accepting an explicit DB/run context; keep CLI wrappers thin.
4. Inventory and classify every post task: continuous derivation, scheduled maintenance, one-time migration, or report. Do not run one-time recovery scripts forever.
5. Convert OWNS, sponsor, therapeutic-area, mechanism, competition, event regrounding, and evidence backfill into versioned jobs in dependency order.
6. Register continuous jobs in the live scheduler or trigger them from completed input snapshots. `run_now()` must invoke the same registry, not a separate code path.
7. Add a distributed job lease and heartbeat.
8. Replace `ON CONFLICT DO NOTHING` for derived edges with governed reconciliation: update stronger evidence/confidence, retain derivation history, and supersede edges no longer produced by the current input snapshot.
9. Separate asserted source relationships from inferred relationships and preserve epistemic class/method.
10. Publish an output snapshot only after required quality and conservation checks pass.

#### Required tests

- Same input snapshot + transform version produces the same output manifest.
- Re-run is idempotent.
- Removed input causes an inferred edge to be superseded, not silently retained.
- Stronger evidence updates current projection while preserving history.
- Live cron and `run_now()` execute the identical job registry.
- A failed upstream snapshot blocks dependent publication without deleting prior good output.

#### Validation and exit gate

Choose a bounded drug/company/trial fixture and independently compute expected direct and derived edges. Reconcile input/output counts and edge hashes. In production shadow mode, compare old script output to new job output before switching consumers.

### WP-7 — Preserve source observations and field-level survivorship

**Covers:** G-09, G-11, G-12  
**Priority:** P1

#### Implementation

1. Add an append-only normalized observation layer keyed by source ID, source record ID, artifact, observation hash, and schema/transform version.
2. Store field assertions or a structured observation payload without overwriting prior source observations.
3. Define versioned survivorship policies per entity field: source authority, recency, specificity, null policy, conflict tolerance, and manual override.
4. Build canonical entity rows as projections from approved observations; retain the winning assertion ID per field or an equivalent field-lineage map.
5. Separate `observed_at`, source event/effective time, valid time, and system assertion time.
6. Record conflicts instead of resolving them through write order.
7. Rebuild `data_change_log` from actual committed projection changes and include before/after observation references.
8. Make manual corrections first-class assertions with actor, reason, validity, and override policy—not direct untraceable row edits.

#### Required tests

- Changing source arrival order does not change the canonical result under the same policy.
- Higher-authority values win according to an explicit policy.
- A null or lower-authority update cannot erase a protected value.
- Every current field traces to one or more source observations or a manual assertion.
- Policy-version change can rebuild a projection and show an explainable diff.

#### Validation and exit gate

For a reviewed sample of composite drugs, companies, and trials, generate a field-lineage report showing every current field, alternatives, winning policy rule, source artifact, and observation time. Unexplained current fields must be zero.

### WP-8 — Convert quality from annotation into contract and promotion policy

**Covers:** G-02, G-11, G-16  
**Priority:** P1

#### Implementation

1. Define an enum/schema for supported rule types and validate every rule/config at deploy time.
2. Treat unknown rule types, missing required rule configuration, and empty required field lists as contract errors, never passing scores.
3. Split quality into dimensions: schema validity, completeness, validity/range, uniqueness, referential integrity, identity confidence, freshness, source coverage, and drift.
4. Evaluate source records before silver promotion and canonical candidates before current-state publication.
5. Persist append-only quality results with run, contract, rule version, input observation, and evaluated value. Do not delete prior assessments.
6. Make critical rule failure override composite average; report dimension scores alongside any aggregate.
7. Make quality policy source- and record-kind-specific. “Unknown/not measured” must be distinct from pass.
8. Use field-level independent observations for corroboration instead of counting any graph link source.
9. Define quarantine release/retry workflows and record reviewer decisions.
10. Version thresholds and gold sets; any threshold change requires RED evidence, rationale, reviewer, and before/after distribution.

#### Required tests

- Unknown rule/config cannot deploy.
- Critical failure cannot be averaged into a passing release.
- `unknown`, `not_applicable`, `not_measured`, `pass`, and `fail` remain distinct.
- Quality history remains queryable across reassessment.
- A quarantined observation can be fixed/replayed/promoted with full lineage.

#### Validation and exit gate

Run contract checks against a known-good and deliberately corrupted source artifact. Demonstrate correct quarantine, no current-state mutation, exact reason codes, successful replay after correction, and retained history.

### WP-9 — Add durable cursors, streaming batches, leases, and cost controls

**Covers:** G-01, G-10, part of G-04  
**Priority:** P1 after truthful outcomes/source IDs

#### Implementation

1. Replace `list[RawRecord]` with a backward-compatible iterator/batch result carrying records, page artifact, source cursor, counters, truncation, and warnings.
2. Persist cursor-before, candidate cursor-after, page checkpoints, and heartbeat by `source_id`.
3. Advance the durable cursor only after all required stages for the batch succeed and the fetch is not truncated.
4. Prefer opaque upstream cursor/version. If using event time, persist max accepted source time and apply an overlap/lookback window with idempotent deduplication.
5. Replace process-local batch counters with durable partitions/checkpoints.
6. Acquire a Postgres advisory or lease-table lock keyed by source ID before fetch; heartbeat and expire it safely after process death.
7. Set APScheduler `max_instances`, coalescing, misfire policy, and explicit execution timeout, while retaining the database lease as the cross-process authority.
8. Use a pooled HTTP client, shared per-host rate limiter, `Retry-After`, bounded exponential backoff, circuit breaker, response-size cap, and request telemetry.
9. Move content-hash/change detection before embedding. Cache embedding by `(content_hash, model, dimensions, preprocessing_version)`.
10. Use batch embedding on changed segments/records; persist embedding stage outcome and cost.
11. Bound unresolved/HITL/post-job work by durable cursor, not an unscoped top-100 global sweep after every source run.

#### Required tests

- Kill after page N; restart at the correct durable checkpoint with no missing/duplicate canonical records.
- Truncation/stuck cursor prevents cursor advancement and terminal success.
- Late-arriving event inside the overlap window is captured once.
- Two scheduler processes compete; exactly one owns a source lease.
- A million-row synthetic CSV/REST stream stays within the approved memory budget.
- Unchanged records make zero embedding calls.
- 429 honors `Retry-After`; circuit breaker opens and recovers predictably.

#### Validation and exit gate

Set performance budgets from measured production-like volumes. Required structural results are: bounded memory, no data loss under kill/restart, no concurrent duplicate source execution, and zero cursor advance on partial failure.

### WP-10 — Emit end-to-end lineage and validate the catalog

**Covers:** G-03, G-12, G-16  
**Priority:** P1/P2

#### Implementation

1. Map Market Zero concepts to OpenLineage: source contract/transform as Job, execution as Run, raw/observation/projection/facts/edges as Datasets.
2. Emit START plus COMPLETE/FAIL/ABORT events with input/output datasets and counts.
3. Include source code location/SHA, contract/plugin/parser/transform versions, cursor partition, input/output statistics, schema, and quality assertion facets.
4. Internally model W3C PROV-equivalent relationships: artifact/observation/output as Entity; fetch/parse/resolve/project/derive as Activity; source/operator/software/config responsibility as Agent/Plan.
5. Add a lineage query/service from any fact, edge, signal, or canonical field back to raw artifact and deployed contract.
6. Generate the dataset catalog from deployed contracts, domain handlers, and published snapshots rather than a static Python list.
7. Emit Croissant 1.1 with `dct:conformsTo`, resources/FileObjects, hashes, RecordSets, typed Fields, references, license, owner, and source/transform description.
8. Run the official `mlcroissant` validator in CI on every generated catalog artifact.
9. Distinguish dataset version/snapshot from mutable table name.
10. Keep lineage emission failure policy explicit: buffer/retry operational export, while the internal lineage transaction remains required.

#### Required tests

- Every terminal run has exactly one start and one terminal lineage state.
- Every published dataset version references complete input versions.
- A fact-to-artifact trace crosses all expected activities and includes code/config versions.
- Generated Croissant passes 1.1 validation.
- Registry, scheduler, contracts, published datasets, and catalog have no orphan/drift entries.

#### Validation and exit gate

Select one document-derived fact, one registry-derived fact, one competition edge, and one canonical drug field. Produce a machine-readable and human-readable lineage trace to exact input bytes and transformation versions. Any missing hop is a release blocker for the gold-standard claim.

### WP-11 — Normalize multi-valued domain relationships

**Covers:** G-05, G-13  
**Priority:** P1, can proceed alongside WP-5 after identity ADR

#### Implementation

1. Replace the semantic use of `clinical_trials.drug_id` as the complete intervention model with bridge tables for trial interventions, arms, roles, comparator/placebo, dose/strength, and canonical entity link.
2. Ingest every intervention, not just the first `DRUG` item. Preserve raw labels and source IDs.
3. Link sponsors and collaborators with explicit role and source provenance.
4. Represent document/article mentions as many occurrence links; derive a primary entity only as a separate scored projection.
5. Keep legacy scalar FKs as compatibility projections during migration.
6. Update graph/fact emitters and dossier queries to consume the bridge model.

#### Required tests

- Combination and multi-arm trials retain every intervention and role.
- Placebo/device/biologic/comparator are not coerced into drug identity.
- Legacy `drug_id` projection is deterministic and clearly incomplete/deprecated.
- Trial/fact counts reconcile before and after migration.

#### Validation and exit gate

Review a gold set of complex trials against the source UI/API. Require exact intervention/arm conservation and no false canonical identity links.

### WP-12 — Build the assurance harness and safe rollout

**Covers:** all findings, especially G-16  
**Priority:** Continuous; required for every package

#### Test layers

1. Pure parser/mapping tests with frozen source fixtures.
2. Contract tests for every source schema and pagination/cursor mode.
3. Property-based conservation tests for malformed, missing, duplicate, reordered, and late data.
4. Identity gold-set and adversarial ambiguity tests.
5. Unstructured gold-corpus span and extraction tests.
6. Transaction/fault-injection tests at every commit boundary.
7. Replay determinism and version-diff tests.
8. Multi-process lease and kill/restart tests.
9. Shadow production comparison and reconciliation reports.
10. Read-only production probes for volume, flow, quality, collision, unresolved, lineage, and latency.

#### Rollout protocol

For every package:

1. Write RED tests and a migration/backfill conservation manifest.
2. Land additive schema and compatibility readers first.
3. Dual-write or shadow-compute without changing consumers.
4. Compare old/new outputs by entity, field, link, fact, and count—not only aggregate row totals.
5. Independently review ambiguity and silent-loss risks.
6. Enable a small source/partition canary.
7. Observe at least one full source SLA window.
8. Expand gradually behind a reversible flag.
9. Retain the prior projection and contract version until reconciliation is signed off.
10. Remove legacy paths only after a separate cleanup PR and a final no-consumer search.

#### Global conservation gates

- No fetched item disappears without a terminal reason.
- No schema field disappears without an explicit mapping/rejection record.
- No source cursor advances after truncation or required-stage failure.
- No exact identifier conflict is resolved by fuzzy/LLM fallback.
- No canonical field exists without source/manual lineage.
- No fact or derived edge exists without derivation provenance.
- No quality rule or unmeasured dimension creates a vacuous green.
- No threshold, SLA, or gold set changes without versioned rationale and before/after evidence.

## Recommended delivery sequence

| Order | Package | Why this order | Parallel-safe work |
|---:|---|---|---|
| 1 | WP-0 truthful outcomes | Prevents new work from hiding failure | RED tests and run-schema design |
| 2 | WP-1 raw artifacts | Makes every later parser/identity change replayable | Object-store adapter and metadata schema |
| 3 | WP-2 source contracts/source ID | Establishes safe config-driven runtime | Contract schema, UI can remain preview |
| 4 | WP-4 identity ADR + shadow spine | Highest semantic leverage | Identifier emission by connectors after ADR |
| 5 | WP-3 explicit domain plugin | Removes dual control planes safely | Parity harness while identity schema lands |
| 6 | WP-5 Document IR | Enables auditable unstructured work | Fixture corpus/OCR evaluation |
| 7 | WP-6 derived job registry | Makes graph topology live and reproducible | Job inventory/refactoring without scheduling |
| 8 | WP-7 field observations | Enables real multi-source survivorship | Observation schema and projection prototype |
| 9 | WP-8 quality promotion | Depends on candidate/observation layers | Rule compiler and history schema |
| 10 | WP-9 scale/recovery | Refactor after source/run contracts stabilize | Load/fault harness early |
| 11 | WP-10 lineage/catalog | Instrument stable stage contracts | OpenLineage/Croissant mapping prototype |
| 12 | WP-11 relationship normalization | Uses identity grains and observation lineage | Trial gold-set curation |

WP-12 applies throughout.

## First two implementation sprints

### Sprint A — integrity floor

Deliver only:

- required/advisory hook policy;
- truthful scheduler/API propagation;
- persisted skip/quarantine/truncation counts;
- no cursor advance on partial/truncated run;
- remove silent enrichment loss;
- raw artifact metadata schema and local test adapter;
- source-instance ID in run/envelope compatibility layer;
- RED tests for the current document mention-to-link gap and long-document offset gap.

Exit only when deliberately induced failures are red and conservation counters reconcile.

### Sprint B — replay and identity shadow

Deliver:

- raw page/file/upload capture for one REST source, one bespoke API source, and upload;
- deterministic replay command;
- identity-grain ADR;
- `entity_identifiers` compatibility schema/view;
- connector emission for RxNorm/UNII/ChEMBL/PubChem/InChIKey with scope;
- exact/crosswalk shadow resolver and disagreement report;
- strict `SourceContract` schema plus two fixture-based generic sources;
- explicit pharma plugin injection with a startup assertion.

Do not switch canonical identity consumers until the reviewed gold set and collision report pass.

## Definition of “gold standard” for Market Zero

The platform may make that claim only when all of the following are demonstrable, not merely documented:

1. Every production source runs from a versioned, approved contract with an independent source ID.
2. Exact input bytes and sanitized acquisition metadata are retained according to policy.
3. The same artifact plus pinned versions deterministically replays to the same outputs.
4. Every stage has reconciling counters and explicit terminal reasons.
5. Required controls fail closed and terminal statuses are truthful.
6. Deterministic identifiers and governed crosswalks precede names, embeddings, and LLMs.
7. Exact identity conflicts quarantine rather than merge.
8. Unstructured outputs retain exact artifact/page/block/span/table locators and parser/model versions.
9. Canonical fields preserve source observations and survivorship rationale.
10. Derived edges/facts are versioned jobs with input/output manifests and supersession.
11. Source/event/valid/asserted times are distinct where semantics require them.
12. Quality is versioned, non-vacuous, historical, and capable of blocking promotion.
13. A fact/edge/field can trace to artifact, source contract, run, and code/config version.
14. Generated catalog metadata validates against Croissant 1.1 and reflects deployed reality.
15. Kill/restart, truncation, late arrival, and multi-instance tests prove no loss or duplicate publication.
16. Security, license, retention, PII, and untrusted-content policies are enforced in the runtime path.

## What not to do

- Do not add the generic connector classes to `CONNECTOR_REGISTRY` under one shared enum and call onboarding complete.
- Do not populate `canonical_molecule_id` by fuzzy name alone.
- Do not equate ATC class membership with molecule identity.
- Do not make LLM confidence an identity proof.
- Do not treat a payload hash as replayable provenance when the bytes are gone.
- Do not add another best-effort post task without a run record, dependency, lease, and output manifest.
- Do not put arbitrary SQL or Python callables into user-editable runtime contracts.
- Do not solve bounded current volumes with an unnecessary distributed-data stack before fault/recovery requirements demand it.
- Do not delete legacy data or old derivations during migration; supersede and reconcile.

## File-level evidence index

The most consequential evidence locations are:

- `connectors/base.py:58-105` — closed source/record enums.
- `connectors/base.py:142-209` — provenance and raw-record envelopes.
- `connectors/base.py:217-304` — list-returning connector contract and retry behavior.
- `connectors/__init__.py:28-58` — code-only registered connector classes.
- `connectors/rest_connector.py:66-137` — runtime-capable but direct-secret config.
- `connectors/rest_connector.py:210-291` — connector-local skips and reconstructed item hashes.
- `connectors/rest_connector.py:373-443` — in-memory pagination and warning-only truncation.
- `connectors/user_document.py:82-160` — extract/NER/chunk/mention arrays.
- `services/document_ner.py:182-253` — chunk-relative offsets and occurrence deduplication.
- `services/document_extractor.py:91-162,167-331` — format detection and structure flattening.
- `api/routes/upload.py:61-121` — repeated extraction and best-effort fact stage.
- `integration/pipeline.py:180-222` — inactive-by-default plugin lookup and component construction.
- `integration/pipeline.py:224-317` — finalization before run hooks and returned failures.
- `integration/pipeline.py:331-455` — embed-before-change, store/link/quality order, ignored block, silent catch.
- `integration/pipeline_hooks.py:71-124` — universal fail-open hook behavior.
- `integration/pipeline_hooks.py:237-280` — post-store quality block.
- `integration/pipeline_hooks.py:464-582` — validation behavior.
- `integration/normalizer.py:298-358` — pack/fallback/pass-through normalization.
- `integration/entity_resolver.py:115-150` — narrow exact-key map.
- `integration/entity_resolver.py:190-312` — name/embedding/LLM/auto-create cascade.
- `integration/knowledge_store.py:142-178` — hardcoded store router.
- `integration/knowledge_store.py:260-396` — NDA/name drug upsert and row-level source overwrite.
- `integration/cross_linker.py:27-139` — declarative plus custom direct links.
- `integration/cross_linker.py:565-626` — edge conflict-do-nothing behavior.
- `integration/data_quality.py:236-275` — composite score and unknown-rule vacuous pass.
- `integration/data_quality.py:471-489` — replacement rather than historical results.
- `domain/schema.py:24-87,200-249` — intended plugin declarations.
- `domain/pharma/pack.py:38-57,523-592` — drug identity limits and incomplete source/staleness config.
- `schema/migrations/035_canonical_molecule_id.sql:1-28` — self-link with deferred backfill.
- `schema/migrations/038_drugs_modality_external_ids.sql:55-124` — existing identifiers not wired into resolver.
- `schema/migrations/091_crosswalk_records.sql:14-45` — governed but currently separate crosswalk store.
- `schema/migrations/096_connector_taxonomy_onboarding.sql:51-64` — lifecycle-only onboarding persistence.
- `scheduler/config.py:27-115` — static schedules and run order.
- `scheduler/runner.py:101-338` — manual-only broad post-task path.
- `scheduler/runner.py:630-779` — live registration, process-local batches, and completed-at watermark.
- `services/fact_emitters/base.py:40-71` — actual `fact_class` policy.
- `services/fact_emitters/document_facts.py:99-150,249-328` — document fact identity and best-effort extraction.
- `services/crosswalk_loader.py:81-155` — name-bootstrap crosswalk persistence.

## Final architectural position

The pipeline should be evolved, not discarded. Its strongest pieces—the connector boundary, audited resolution cascade, facts/evidence ledgers, DLQ, quality concepts, and conservation culture—are exactly what a trustworthy data platform needs.

The next plateau is not “more adapters.” It is an architecture where source instances are versioned contracts, bytes are retained, stage outcomes reconcile, identifiers are typed and deterministic, document spans are reconstructable, canonical state is a projection over preserved observations, and every derived edge or fact is a versioned job output.

Once that is true, Market Zero can credibly be a reference implementation for regulated, evidence-heavy unstructured transformation. Until then, it is a promising vertical pipeline with platform ambitions—and the report above is the shortest safe path from one to the other.
