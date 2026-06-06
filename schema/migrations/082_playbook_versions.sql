-- 082_playbook_versions.sql
--
-- DI-5 — version history + audit trail for SME-authored playbooks.
--
-- The `playbooks` table (migration 080) holds the CURRENT version of each
-- DB-backed playbook. Every SME edit (create / update / rollback) appends an
-- immutable snapshot here: who, when, what changed (a diff against the prior
-- version), and the full playbook state at that version. This is the governance
-- requirement for a regulated domain — every edit is versioned, audited, and
-- rollback-able (a rollback is itself a new forward version pointing back).
--
-- Append-only by design: rows are INSERTed, never UPDATEd, so the audit trail
-- is tamper-evident. Additive + idempotent + reversible (drop to revert).

CREATE TABLE IF NOT EXISTS playbook_versions (
    id           BIGSERIAL PRIMARY KEY,
    playbook_id  TEXT NOT NULL,                       -- FK-free (playbooks.id may be deleted)
    version      INTEGER NOT NULL,                    -- monotonically increasing per playbook_id
    action       TEXT NOT NULL DEFAULT 'update',      -- create | update | rollback | delete
    snapshot     JSONB NOT NULL DEFAULT '{}'::jsonb,  -- full {id,pack,trigger,dimensions,synthesis}
    diff         JSONB NOT NULL DEFAULT '{}'::jsonb,  -- {field: {from, to}} vs the prior version
    author       TEXT,                                -- audit: who made the edit
    note         TEXT,                                -- optional human note / rollback reason
    rolled_back_from INTEGER,                         -- when action='rollback', the version restored
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_playbook_versions_pb_ver
    ON playbook_versions(playbook_id, version);
CREATE INDEX IF NOT EXISTS idx_playbook_versions_pb
    ON playbook_versions(playbook_id, created_at DESC);
