-- BE-35 · Curator-driven weight learning audit log.
--
-- Append-only record of every change to sources.predictive_accuracy
-- so a steward can replay the curator's reasoning.

CREATE TABLE IF NOT EXISTS source_weight_audit_log (
    id                       BIGSERIAL PRIMARY KEY,
    source_id                TEXT NOT NULL,
    old_weight               REAL NOT NULL,
    new_weight               REAL NOT NULL,
    delta                    REAL NOT NULL,
    contributing_decisions   INTEGER NOT NULL CHECK (contributing_decisions >= 0),
    actor                    TEXT NOT NULL,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_weight_audit_source
    ON source_weight_audit_log (source_id, created_at DESC);
