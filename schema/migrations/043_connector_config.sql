-- Migration 043: Connector config table (SPEC-019)
--
-- One row per data connector to control runtime behavior:
--   enabled            — false hides from scheduler + blocks manual runs
--   auto_approve_runs  — true lets uploader role trigger runs (else enterprise)
--   manual_only        — true skips scheduler but allows manual runs
--   notes              — free-text rationale shown in UI
--
-- Absence of a row = defaults (enabled=true, auto_approve=false, manual_only=false).
-- We intentionally do NOT pre-seed rows; new connectors are usable immediately.
--
-- Migration is additive. Idempotent via IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS connector_config (
    source_key TEXT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    auto_approve_runs BOOLEAN NOT NULL DEFAULT FALSE,
    manual_only BOOLEAN NOT NULL DEFAULT FALSE,
    notes TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by UUID REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_connector_config_enabled
    ON connector_config (enabled) WHERE NOT enabled;
