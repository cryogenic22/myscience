-- 098_etl_runs_skip_visibility.sql
--
-- Make the DLQ / fail-closed-skip signal VISIBLE to Lane-2 (conservation floor).
--
-- The pipeline already COUNTS records_skipped (the #300 fail-closed skip for
-- name-less ontology terms — counted, logged, never stored) and records_failed
-- (a DLQ insert into failed_records) on PipelineResult. But _finalize_etl_run
-- dropped BOTH on the floor: etl_runs had no column for them. So a run that
-- fail-closed-skipped 3,121 open_targets records still logged a clean SUCCESS
-- with the skip count invisible — which is *why* that backlog bled 18 days
-- unseen (every run green, the failed_records pile growing silently under it).
--
-- ADDITIVE + reversible: two nullable integer counters, default 0. Every existing
-- consumer (scheduler/runner.py, connector_health.py, dashboards) is untouched.
-- Pre-098 rows read 0 — correct, they predate the counters (no skip/fail
-- attribution to claim). connector_health's new DLQ verdict reads failed_records
-- directly for the live backlog; these columns add per-run skip attribution + the
-- trailing-window skip sum (the #300 skip never reaches the DLQ, so failed_records
-- alone cannot see it).
--
-- Reverse: ALTER TABLE etl_runs DROP COLUMN records_skipped, DROP COLUMN records_failed;

ALTER TABLE etl_runs ADD COLUMN IF NOT EXISTS records_skipped INTEGER DEFAULT 0;
ALTER TABLE etl_runs ADD COLUMN IF NOT EXISTS records_failed  INTEGER DEFAULT 0;

COMMENT ON COLUMN etl_runs.records_skipped IS
    'Records fail-closed-skipped this run (e.g. name-less ontology terms, #300): '
    'counted + logged, NOT stored, NOT a DLQ insert. 0 on pre-098 rows. Migration 098.';
COMMENT ON COLUMN etl_runs.records_failed IS
    'Records routed to the DLQ (failed_records) this run. 0 on pre-098 rows. Migration 098.';
