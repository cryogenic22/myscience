-- BE-37 · Tenant model on core entity tables (SaaS-blocker fix)
--
-- Adds tenant_id to the four tables called out in
-- AGENT_BACKLOG.md#be-37 — drugs, companies, clinical_trials,
-- mechanisms_of_action. Default 'public' so existing data and any
-- public-connector ingestion stays in the shared tenant.
--
-- BE-38 (next migration / branch) introduces the
--   WHERE tenant_id = current_tenant
-- middleware that consumes these columns. BE-39 adds CI tests
-- that prove cross-tenant queries return zero rows.
--
-- Sequencing: PostgreSQL fills existing rows with DEFAULT 'public'
-- as part of the ALTER, so we land NOT NULL in the same statement.
-- A separate backfill is only needed once ingestion paths start
-- populating tenant_id from session context — the script
-- scripts/backfill_tenant_id.py exists for that next phase.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'drugs') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'drugs' AND column_name = 'tenant_id'
        ) THEN
            ALTER TABLE drugs
                ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'public';
        END IF;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'companies') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'companies' AND column_name = 'tenant_id'
        ) THEN
            ALTER TABLE companies
                ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'public';
        END IF;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'clinical_trials') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'clinical_trials' AND column_name = 'tenant_id'
        ) THEN
            ALTER TABLE clinical_trials
                ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'public';
        END IF;
    END IF;

    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'mechanisms_of_action') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'mechanisms_of_action' AND column_name = 'tenant_id'
        ) THEN
            ALTER TABLE mechanisms_of_action
                ADD COLUMN tenant_id TEXT NOT NULL DEFAULT 'public';
        END IF;
    END IF;
END $$;

-- Tenant filter indexes (BE-38 middleware will use these on every
-- read against core tables, so they pay back fast).
CREATE INDEX IF NOT EXISTS idx_drugs_tenant_id
    ON drugs (tenant_id);
CREATE INDEX IF NOT EXISTS idx_companies_tenant_id
    ON companies (tenant_id);
CREATE INDEX IF NOT EXISTS idx_clinical_trials_tenant_id
    ON clinical_trials (tenant_id);
CREATE INDEX IF NOT EXISTS idx_mechanisms_of_action_tenant_id
    ON mechanisms_of_action (tenant_id);

-- Audit log written by scripts/backfill_tenant_id.py and (later)
-- by tenant-management endpoints. Append-only — never DELETE.
CREATE TABLE IF NOT EXISTS tenant_id_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    table_name      TEXT NOT NULL,
    tenant_id       TEXT NOT NULL,
    matched_count   INTEGER NOT NULL,
    where_clause    TEXT NOT NULL,
    actor           TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tenant_id_audit_log_tenant
    ON tenant_id_audit_log (tenant_id, created_at DESC);

COMMENT ON COLUMN drugs.tenant_id IS
    'BE-37 multi-tenancy. ''public'' for shared / pre-tenancy data; '
    'per-customer slug for customer-private uploads. Filtered by '
    'BE-38 query middleware on every read.';
COMMENT ON COLUMN companies.tenant_id IS
    'BE-37 multi-tenancy — see drugs.tenant_id.';
COMMENT ON COLUMN clinical_trials.tenant_id IS
    'BE-37 multi-tenancy — see drugs.tenant_id.';
COMMENT ON COLUMN mechanisms_of_action.tenant_id IS
    'BE-37 multi-tenancy — see drugs.tenant_id.';
