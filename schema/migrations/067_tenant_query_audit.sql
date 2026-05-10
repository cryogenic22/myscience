-- BE-39 · Per-tenant query audit log.
--
-- Append-only record of reads against tenant-scoped tables, used by
-- stewards to confirm cross-customer isolation. 90-day TTL is
-- enforced by services.tenant_audit.cleanup_older_than which a cron
-- / steward invokes; we don't use a DB-side TRIGGER to keep the
-- migration narrow.
--
-- See specs/BE_039_tenant_audit_tests.md.

CREATE TABLE IF NOT EXISTS tenant_query_audit_log (
    id          BIGSERIAL PRIMARY KEY,
    tenant_id   TEXT NOT NULL,
    query_kind  TEXT NOT NULL,
    table_name  TEXT NOT NULL,
    row_count   INTEGER NOT NULL CHECK (row_count >= 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenant_query_audit_tenant
    ON tenant_query_audit_log (tenant_id, created_at DESC);

COMMENT ON TABLE tenant_query_audit_log IS
    'BE-39 multi-tenancy audit. One row per read against a '
    'tenant-scoped table (drugs / companies / clinical_trials / '
    'mechanisms_of_action). Append-only; 90-day retention enforced '
    'by services.tenant_audit.cleanup_older_than.';
