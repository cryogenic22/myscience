# WP-0 — Make Run Outcomes and Controls Truthful

## Summary
The ETL pipeline's control hooks fail open and its run accounting is not conservative, so a run can swallow a validation/change-detection/quality gate and still finalize as `SUCCESS`/report `OK`. This WP makes hook severity explicit (advisory may fail open; `required`/`promotion_gate` cannot), converts silent skips into recorded QUARANTINE rows that preserve the raw record, persists a full disposition ledger per run, and closes a row-conservation equation at finalize. P0 because it is the G-02 "fail-open false green" class: the harness floor's #1 and #3 principles (no silent loss, no vacuous green) are structurally violated in the hottest path in the system.

## Current state (verified)
- `integration/pipeline_hooks.py:116-118` — the sole exception path in `HookRegistry.fire` swallows **any** hook exception into `HookResult(action="continue")`. Validation (`ValidationGateHook`), change-detection (`ChangeDetectionHook`), and quality all fail open identically.
- `integration/pipeline.py:422-429` — POST_STORE results are consumed only for `quality_score`/`failures` counting; `self.hooks.has_block(post_results)` is **never** called (contrast PRE_STORE at `:383`), and the gate runs at `:422` *after* the store at `:395`.
- `integration/pipeline.py:345-361` — the ON_NEW_ENTITY dispatch is dead: its guard is `hasattr(link_info, 'method') and link_info.method == 'auto_create'` (`:348`), but `ResolvedLink` (`integration/entity_resolver.py:90-99`) has **no** `method` field — the attribute is `matched_via`. `hasattr(...,'method')` is `False`, so the hook never fires; the `fire()` return at `:361` is also discarded.
- `integration/pipeline.py:454-455` — bare `except Exception: pass` on the enrichment-HITL insert.
- `classify_run_outcome` (`integration/pipeline.py:125-168`) is a clean pure Lane-1 gate but consumes only `success/processed/inserted/updated`. `PipelineResult.success` (`:86-87`) ignores `records_skipped`; a required control swallowed at `:116` leaves `records_failed==0`, so `success` is `True`. `_finalize_etl_run` (`:528-574`) persists processed/inserted/updated/unchanged only — **`records_skipped` and `records_failed` are never persisted**, and there is no balance check. A strict-mode validation block increments `records_skipped` and `return`s (`:383-385`) — the raw record vanishes.
- `scheduler/runner.py:685-759` — `_run_connector` calls `pipeline.run()`, logs counts, and never inspects `result.success`/`result.outcome`; `run_now` (`:114-121`) sets `results[name]="OK"` unless `_run_connector` raises. Because `run()` catches internally and never re-raises, PARTIAL/FAILURE runs report `OK`.
- `etl_runs` columns today: base (`schema/migrations/001_core_tables.sql:152-164`) + `quality_score_avg`,`hitl_items_created`,`records_unchanged` (`008:173-175`) + `outcome` (`088:25`). No skipped/failed/fetched/emitted/filtered/quarantined/truncated columns; no quarantine table.

## Target behavior
The run's accounting equals its reality. Every fetched record lands in exactly one terminal disposition; a swallowed required control is impossible.
1. Hooks carry a typed `severity`: `advisory | required | promotion_gate`. Only `advisory` exceptions fail open; a `required`/`promotion_gate` exception propagates to a terminal disposition (record → quarantine/failed; run-scoped hook → terminal run state).
2. `block` from POST_STORE is honored: the stored row is superseded to `record_status='quarantined'` (reversible) and counted, never left as a clean insert.
3. A validation/gate failure produces a **QUARANTINE row that keeps the raw record**, not a silent skip.
4. `_finalize_etl_run` persists `records_fetched/emitted/filtered/skipped/quarantined/failed/truncated`; required ON_RUN_COMPLETE hooks run **before** the terminal state is written.
5. `classify_run_outcome` enforces the conservation equation and downgrades to `PARTIAL`/`FAILURE_ZERO_ROWS` when a required control fired or the balance breaks.
6. `_run_connector`/scheduler propagate PARTIAL/FAILURE instead of `OK`.
7. The dead `auto_create` guard uses `matched_via`.

## Design & approach
- **`HookSeverity` enum** in `pipeline_hooks.py`; `PipelineHook.severity: HookSeverity = ADVISORY`. Assign: `ValidationGateHook`,`QualityGateHook` → `promotion_gate`; `ChangeDetectionHook`,`NewEntityReviewHook` → `required`; `Staleness/Unresolved/QualityMonitor` → `advisory`.
- **`HookRegistry.fire`** (`:116`): on exception, if `hook.severity is ADVISORY` keep the `continue` fallback; else append `HookResult(action="fail", message=…)` and set a flag. Add `has_fail(results)`. Never blanket-swallow.
- **`_process_record`**: after PRE_STORE, `has_block`/`has_fail` → `_quarantine(record, reason, etl_run_id)` (append-only insert of the full `RawRecord` payload + provenance) and `result.records_quarantined += 1` instead of the silent `records_skipped` at `:384`. After POST_STORE (`:422`), add `if self.hooks.has_block(post_results) or self.hooks.has_fail(post_results):` → supersede stored row to `record_status='quarantined'`, decrement the insert/update tally, `records_quarantined += 1`.
- **Counter model** on `PipelineResult`: add `records_fetched` (set in `_fetch`), `records_emitted`, `records_filtered`, `records_quarantined`, `records_truncated` (connector-reported page-cap flag). `_fetch` sets `records_fetched=len(records)`.
- **`classify_run_outcome`** gains `quarantined`,`failed` params and asserts `emitted == inserted+updated+unchanged+quarantined+failed`; on mismatch or `quarantined>0`/`failed>0` returns `PARTIAL`. `PipelineResult.success` also `and records_quarantined == 0`.
- **`:454`** `except Exception: pass` → `except Exception as e: logger.warning(...); result.errors.append(...)` (counted, not silent).
- **`:348`** guard → `getattr(link_info,'matched_via',None) == 'auto_create'`; pass `confidence=link_info.confidence`, `entity_id=link_info.entity_id`.
- **Scheduler**: `_run_connector` returns `result`; `run_now`/`run_one` map `result.outcome` → `OK`/`PARTIAL`/`FAILURE`, never bare `OK` when `not result.success`.

## Schema / migrations
Migration NNN (reserve number at impl time), additive + reversible:
- `ALTER TABLE etl_runs ADD COLUMN IF NOT EXISTS records_fetched|records_emitted|records_filtered|records_skipped|records_quarantined|records_failed INTEGER DEFAULT 0`, `records_truncated INTEGER DEFAULT 0`. (Existing rows keep `0`; no backfill required.)
- New append-only table `quarantined_records (id, etl_run_id, source_type, external_id, record_type, reason, raw_payload JSONB, provenance JSONB, quarantined_at)` — the raw record is **kept**, never dropped. Down-migration `DROP TABLE`/`DROP COLUMN IF EXISTS` only.

## Tests (RED→GREEN)
Paste `python -m pytest` output for each. New file `tests/test_wp0_run_truthfulness.py`:
- `test_required_hook_exception_does_not_fail_open` — required hook raising → run `PARTIAL`, record quarantined (RED: today `continue`).
- `test_advisory_hook_exception_fails_open` — advisory raise → `continue` (guards the escape hatch).
- `test_post_store_block_quarantines_stored_row` — POST_STORE `block` supersedes row, `records_quarantined==1` (RED: `has_block` never called at `:422`).
- `test_validation_block_writes_quarantine_row_keeps_raw` — strict validation block → `quarantined_records` holds the raw payload; not counted as `records_skipped` (RED).
- `test_on_new_entity_fires_on_auto_create` — a `matched_via='auto_create'` link fires the hook (RED: dead `.method` guard).
- `test_enrichment_insert_failure_is_logged_not_swallowed` (RED: `:454`).
- `test_classify_run_outcome_conservation_equation` — `emitted != inserted+updated+unchanged+quarantined+failed` ⇒ `PARTIAL` (RED: signature lacks the terms).
- `test_finalize_persists_all_dispositions` — MockDB asserts all seven counters written (RED).
- `test_scheduler_reports_partial_not_ok` — `run_now` maps a PARTIAL run to non-`OK` (RED).

## Exit gate / conservation equation
Per finished run: `records_emitted == records_inserted + records_updated + records_unchanged + records_quarantined + records_failed` **and** `records_fetched == records_emitted + records_filtered + records_skipped`. Lane-1 (deterministic, DB-free): `python -m pytest tests/test_wp0_run_truthfulness.py tests/test_conservation_gates.py -q` green. Lane-2 (post-deploy, behind `DATABASE_URL`): `SELECT count(*) FROM etl_runs WHERE completed_at > now()-interval '2 days' AND records_emitted <> records_inserted+records_updated+records_unchanged+records_quarantined+records_failed;` must return `0` — paste it. No protected-surface file edited to pass.

## Rollout
1. **Shadow** — land migration + counters; compute `outcome_v2` and the balance in parallel, log a WARN on any imbalance, but keep writing the legacy `status`/`outcome`. No behavior change.
2. **Dual-read** — Lane-2 query above runs daily; compare `outcome_v2` vs `outcome` over a week; confirm imbalance count trends to 0 (fix connectors that under-report `fetched`).
3. **Flag** — gate the fail-closed severity + POST_STORE block enforcement behind `MZ_HOOK_SEVERITY_ENFORCED` (default `false`); shadow-compare quarantine counts.
4. **Cutover** — flip the flag to `true` after a clean shadow window; scheduler begins propagating PARTIAL/FAILURE.
5. **Cleanup** — once the balance holds ≥2 weeks, make the flag default `true`, then remove the legacy silent-skip branch at `:384` and the dual-write shim. Legacy rows (`records_*=0`, `outcome NULL`) are left in place, never rewritten.

## Risks & out-of-scope
- **Risk: connectors under-reporting `records_fetched`** break the balance and would red Lane-2. Mitigated by the shadow week (step 2) before enforcement.
- **Risk: newly-visible PARTIAL runs** may look like a regression in dashboards — it is the truth surfacing; communicate the outcome-vocabulary shift, do not re-hide it.
- **Risk: quarantine growth** — `quarantined_records` is append-only; add a Lane-2 volume alert (not a PR gate) in a follow-up.
- **Out of scope:** the connector status-emission split (`SUCCESS_LANDED`/`FAILURE_STALE` at source, per conservation-gates.md's "known next loops"); reprocessing/replay of quarantined rows (a separate DLQ-adjacent WP); tightening `facts.source_doc_id` ceiling; any change to `protected-surface.txt` thresholds.

Decision: hook severity is a three-value enum (`advisory|required|promotion_gate`) rather than a boolean, because POST_STORE gates must both fail-closed *and* act on `block` (supersede the stored row), which a binary required/advisory flag cannot express.

Decision: a validation/gate rejection becomes an append-only `quarantined_records` row preserving the raw payload, not a `records_skipped` increment, because conservation principle #2 forbids silent row loss — quarantine is the soft-delete/record-the-drop form.

Decision: the row-conservation equation is enforced inside the pure `classify_run_outcome` (Lane-1) so it is DB-free and PR-hard, with the live balance query as the Lane-2 backstop — keeping the two lanes separate per the harness floor.

The "make `_run_connector` re-raise on PARTIAL" approach didn't work because `run()` deliberately catches internally to finalize the etl_runs row; re-raising would skip finalize and leave a RUNNING orphan — so the scheduler must inspect the returned `result.outcome` instead of relying on exception propagation.
