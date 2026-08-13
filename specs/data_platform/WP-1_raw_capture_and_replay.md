# WP-1 — Immutable Raw Artifacts, Deterministic Replay & Per-Record Atomicity

## Summary

Market Zero's ingestion keeps only a SHA-256 of each source response (`Provenance.raw_response_hash`, `connectors/base.py:153,161`) and discards the bytes, and it commits each record's writes under an autocommit connection (`db.py:73,103`), so a record's resolve → store → cross-link → quality → HITL steps are *separate* commits. The consequence: we cannot deterministically replay or audit what a source actually returned, and a mid-record failure leaves a half-written record with no rollback (a silent conservation break). This WP adds an immutable, content-addressed raw-artifact store for the top ~5 highest-value sources (bronze layer), links every source record to the exact bytes + locator it came from, stamps transform versions for deterministic replay, and wraps each record in the *existing* `db.transaction()` for per-record atomicity. It is P0 because without stored bytes there is no ground truth to replay against, and non-atomic records are undetectable partial-loss (G-03/G-04, part of G-12).

## Current state (verified)

- **Bytes are hashed then dropped.** `Provenance` (`connectors/base.py:142-162`) carries `raw_response_hash` and `hash_response(raw_bytes)` (`:164-167`) but stores no bytes or artifact reference. Handlers persist only `source_api`/`source_url`/`retrieved_at` (`integration/knowledge_store.py:230-232, 253-255`) — a hash and a URL, never the payload.
- **No per-record atomicity.** Default single conn is `autocommit = True` (`db.py:73`); pooled conns are handed out `autocommit = True` (`db.py:103`). `_process_record` (`integration/pipeline.py:331-455`) runs `store.store` (`:395`), `linker.cross_link` (`:409`), `hooks.fire` POST_STORE (`:422`), and an enrichment `self.db.execute` (`:437`) as independent autocommitted statements. A failure after `:395` leaves an orphaned stored row.
- **A transaction primitive exists but is unused per-record.** `Database.transaction()` (`db.py:145-190`) sets `autocommit=False` and yields `self` (single-conn) or a `_TxnView` over one pooled conn — never invoked by `_process_record`.
- **ETL-run provenance is blank.** `_create_etl_run` hardcodes `api_endpoint=""` and `query_params="{}"` (`integration/pipeline.py:498-504`) and never backfills them.
- **DLQ loses the original bytes.** `_dlq_insert` stores the *mapped* `record.data` (`integration/pipeline.py:484`), not the response bytes/headers/page, so a parse failure cannot be reproduced.

## Target behavior

Every fetched API page, file, feed chunk, or upload for a bronze source is written to an immutable, content-addressed, encrypted artifact store **before** parsing. Each resulting source record carries an `artifact_usage` row: `(artifact_sha256, locator, parser_version, normalizer_version, config_hash, code_git_sha)`. `scripts/replay_artifact.py` re-derives records from stored bytes with **no network fetch** and hash-compares against what production stored. `etl_runs.api_endpoint`/`query_params` reflect the real request. Each record's writes commit or roll back as one unit. Nothing is deleted; retention/legal-hold governs eventual expiry per source.

## Design & approach

**`RawArtifactStore` interface** (`integration/artifact_store.py`): `put(content: bytes, content_type: str, source_type, meta: dict) -> ArtifactRef`, `get(sha256) -> bytes`, `exists(sha256) -> bool`, `set_legal_hold(sha256, bool)`, `apply_retention(source_type, before: datetime) -> int`. `ArtifactRef = {sha256, size, storage_uri, content_type}`. Content-addressing (SHA-256) gives free dedup and tamper-evidence.

- **`LocalFSArtifactStore`** (tests/dev): writes `root/<aa>/<bb>/<sha256>` (fan-out by hash prefix), fsync + rename for atomicity.
- **`ObjectStoreArtifactStore`** (prod): S3-compatible, key = `sha256`, server-side encryption (SSE), object-lock (WORM) for immutability. No Kafka/Spark — filesystem/object-store + Postgres metadata only.

**Capture point:** connectors already hold `raw_bytes` (they call `hash_response`). Add a `BaseConnector` hook so the fetch path calls `artifact_store.put(raw_bytes, ...)` and threads the returned `ArtifactRef` onto `Provenance` (new optional field `artifact_sha256`) and a per-record `locator`. Gated by a `BRONZE_SOURCES` set (top ~5: ClinicalTrials.gov, PubMed, openFDA, SEC 8-K, ChEMBL) so non-bronze connectors are untouched.

**Locator** is a discriminated union serialized to text: `jsonptr:/results/3` (JSON page), `row:42` (CSV), `page:7` (PDF), `bytes:1024-2048` (arbitrary).

**Per-record atomicity:** `_process_record` opens `with self.db.transaction() as tx:` and threads `tx` as the db handle into `store.store(..., db=tx)`, `linker.cross_link(..., db=tx)`, and the POST_STORE/enrichment writes. In single-conn mode `transaction()` yields `self` with autocommit off, so existing `self.db.execute` sites enroll automatically; pooled mode requires the threaded `tx`. A raised exception rolls the whole record back; the DLQ insert (now carrying the `artifact_sha256`) runs on a *fresh* autocommit statement outside the aborted txn.

## Schema / migrations

Migration NNN (reserve number at impl time), additive + reversible:

- `raw_artifacts` (append-only): `sha256 PK, size_bytes, content_type, source_type, storage_uri, legal_hold bool default false, retention_class, first_seen_at, etl_run_id`. Insert is `ON CONFLICT (sha256) DO NOTHING` (dedup).
- `artifact_usage`: `id PK, artifact_sha256 FK→raw_artifacts, entity_table, entity_id, external_id, locator text, parser_version, normalizer_version, config_hash, code_git_sha, etl_run_id, created_at`. Indexed on `(entity_table, entity_id)` and `etl_run_id`.
- `Provenance` gains optional `artifact_sha256: str|None` and `locator: str|None` (dataclass only). `etl_runs.api_endpoint/query_params` columns already exist — code fix, no migration.

Down migration drops the two new tables only; no legacy column or row is dropped.

## Tests (RED→GREEN)

`tests/test_artifact_store.py`:
- `test_artifact_put_is_content_addressed_and_dedups` — same bytes twice → one row, identical `sha256`.
- `test_artifact_get_roundtrip_bytes_identical`.
- `test_legal_hold_blocks_retention_delete`.

`tests/test_pipeline_atomicity.py`:
- `test_process_record_rolls_back_on_link_failure` — inject a `cross_link` that raises; assert the stored row is **absent** afterward (fails today: autocommit leaves an orphan).
- `test_process_record_commits_all_or_nothing` — success path leaves store + links + usage all present.

`tests/test_artifact_provenance.py`:
- `test_bronze_record_has_artifact_usage_row` — every record from a bronze fixture run has an `artifact_usage` locator.
- `test_etl_run_records_real_endpoint_and_params` — no longer `""`/`{}` (fails today).
- `test_dlq_insert_references_raw_artifact` — DLQ row carries `artifact_sha256`.

`tests/test_replay_artifact.py`:
- `test_replay_rederives_without_refetch` — replay from stored bytes with a network guard asserting **zero** fetch calls; re-derived record hash == stored.

## Exit gate / conservation equation

For every bronze-source run: `count(source_records) == count(records with an artifact_usage row)` (no record without traceable bytes), and replay reproduces record hashes 100%. Paste-able:

```
python -m pytest tests/test_artifact_store.py tests/test_pipeline_atomicity.py tests/test_artifact_provenance.py tests/test_replay_artifact.py -v
python scripts/replay_artifact.py --run <run_id> --verify   # prints matched/total, exits nonzero on any mismatch
python scripts/probe_substrate.py --sql "SELECT s.n, u.n FROM (…records…) s, (…artifact_usage…) u"   # s.n == u.n for bronze
```

Lane-1 (deterministic): atomicity + content-addressing + usage-row tests, DB-free via `MockDB`/`LocalFSArtifactStore`. Lane-2 (operational, behind `DATABASE_URL`): a scheduled artifact-coverage probe + a sampled replay-verify over the last N bronze runs.

## Rollout

1. **Shadow** — deploy artifact capture + `artifact_usage` writes for bronze sources; atomicity and replay-verify disabled. Pure add: no behavior change, artifacts accrue.
2. **Dual-read** — nightly `replay_artifact.py --verify` on the prior day's bronze runs, comparing stored-bytes re-derivation to live rows; alert on mismatch. No cutover yet.
3. **Flag** — enable `MZ_RECORD_ATOMICITY=true` (wraps `_process_record` in `db.transaction()`) after the shadow comparison shows no coverage gaps; reversible by unsetting.
4. **Cutover** — turn atomicity + capture on for all 5 bronze sources; monitor DLQ (now artifact-backed) and Lane-2 coverage probe.
5. **Cleanup** — nothing deleted. Once coverage holds ~100%, tighten the Lane-2 artifact-coverage ceiling toward 0 as an owner-reviewed protected-surface change; extend bronze set source-by-source in later WPs.

## Risks & out-of-scope

- **Pooled-mode atomicity** requires threading the `tx` handle into `store`/`linker`/hooks; a missed call site silently escapes the txn — covered by `test_process_record_rolls_back_on_link_failure` running in pooled mode too. Decision: thread an explicit `db=tx` handle rather than rely on ambient autocommit state, because the pooled `_TxnView` does not intercept `self.db.execute`.
- **Storage growth / PII in raw bytes** — governed by per-source `retention_class` + legal-hold + SSE encryption; retention deletes are recorded, never silent.
- **Out of scope:** the other 23 sources' bronze coverage, a silver/gold lakehouse, streaming infra (Kafka/Spark), and re-modeling name-less ontology associations (separate follow-up noted at `knowledge_store.py:188-194`).

Grounding files: `connectors/base.py:142-167`, `db.py:55-190`, `integration/pipeline.py:331-504`, `integration/knowledge_store.py:142-258`.
