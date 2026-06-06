-- 087_eval_runs.sql
--
-- Track I — the EVAL HARNESS storage. The harness scores the SYSTEM's own
-- answer for each Forge gold item (forge_eval_items, migration 083) and persists
-- the result so accuracy / precision / recall / coverage can be reported over
-- time, per round-type and per playbook.
--
--   eval_runs     one harness execution: when it ran, how big the gold set was,
--                 and the aggregate metrics summary (per round-type / playbook).
--   eval_results  one scored gold item within a run: gold answer vs system
--                 answer + verdict (correct / partial / miss) + precision/recall
--                 for set-valued answers (routing route-sets). Each row traces a
--                 metric back to a real scored item — no fabricated numbers.
--
-- Additive + idempotent (CREATE ... IF NOT EXISTS) + reversible (drop to revert).

-- ── runs ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS eval_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- a stable, human-readable run id (eval-YYYYMMDD-HHMMSS) for cross-referencing
    run_key         TEXT NOT NULL,
    gold_count      INTEGER NOT NULL DEFAULT 0,   -- gold items the run scored
    scored_count    INTEGER NOT NULL DEFAULT 0,   -- items that produced a verdict
    -- aggregate metrics: overall + per-round-type + per-playbook accuracy /
    -- precision / recall / coverage (the scorecard reads this).
    metrics         JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes           TEXT,
    created_by      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eval_runs_created ON eval_runs(created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_eval_runs_run_key ON eval_runs(run_key);

-- ── per-item results ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS eval_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id          UUID NOT NULL REFERENCES eval_runs(id) ON DELETE CASCADE,
    -- the gold item scored (forge_eval_items.id). FK-free (the gold set may be
    -- pruned independently); stored as the round-type + playbook for rollups.
    eval_item_id    TEXT NOT NULL,
    round_type      TEXT NOT NULL,                -- what_matters | routing | signal_or_noise | critique
    playbook_id     TEXT NOT NULL,
    verdict         TEXT NOT NULL,                -- correct | partial | miss | skipped
    -- set-valued answers (routing) carry precision / recall; point answers leave
    -- them NULL and rely on verdict.
    precision       DOUBLE PRECISION,
    recall          DOUBLE PRECISION,
    -- the gold answer + the system's answer + a short why, for audit / the scorecard.
    detail          JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_eval_results_run ON eval_results(run_id);
CREATE INDEX IF NOT EXISTS idx_eval_results_round_type ON eval_results(round_type);
CREATE INDEX IF NOT EXISTS idx_eval_results_playbook ON eval_results(playbook_id);
