-- 088_etl_run_outcome.sql
--
-- Connector status emission — replace the binary SUCCESS/FAILURE that let feeds
-- go 105 days stale while logging SUCCESS (and let Open Targets/EMA return 0
-- records under a SUCCESS run) with a richer, run-level OUTCOME.
--
-- ADDITIVE by design: the coarse `status` column is UNCHANGED (RUNNING / SUCCESS
-- / PARTIAL / FAILURE / FAILED) so every existing consumer that queries
-- `status = 'SUCCESS'` (scheduler/runner.py, connector_health.py, dashboards)
-- keeps working. The new `outcome` column carries the sharper signal:
--
--   SUCCESS_LANDED      fresh data landed (inserted + updated > 0)
--   SUCCESS_NO_CHANGE   checked, nothing new (processed > 0, 0 changed) — OK
--   FAILURE_ZERO_ROWS   the silent-zero: ran "successfully" but fetched 0 rows
--                       (the Open Targets / EMA / 105-day-stale signature)
--   PARTIAL             some records failed mid-run
--   FAILURE             the run raised
--
-- Staleness (FAILURE_STALE) stays a connector_health verdict — it compares the
-- table's newest-row age to the SLA, which a single run cannot know.
--
-- Existing rows keep outcome = NULL (connector_health treats NULL as "no detail",
-- falling back to `status`). New runs populate it. Idempotent + reversible.

ALTER TABLE etl_runs ADD COLUMN IF NOT EXISTS outcome TEXT;

-- Index for the operational-health gate's "latest run per source" lookups.
CREATE INDEX IF NOT EXISTS idx_etl_runs_source_outcome
    ON etl_runs (source_name, started_at DESC);

COMMENT ON COLUMN etl_runs.outcome IS
    'Run-level outcome (additive to status): SUCCESS_LANDED / SUCCESS_NO_CHANGE / '
    'FAILURE_ZERO_ROWS / PARTIAL / FAILURE. NULL on pre-088 rows. See migration 088.';
