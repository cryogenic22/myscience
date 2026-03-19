-- 008_quality_lifecycle.sql
-- Data quality, CRUD lifecycle, HITL review, dataset catalog, change log.
-- Aligns with ODI AI-Readiness Framework (2025).

-- ============================================================
-- 1. Lifecycle columns on core tables
-- ============================================================

-- content_hash: SHA-256 of canonical payload for change detection
-- last_verified_at: last time record confirmed present at source
-- record_status: active | stale | withdrawn | superseded
-- quality_score: composite quality score 0.0-1.0

DO $$ BEGIN
    -- drugs
    ALTER TABLE drugs ADD COLUMN IF NOT EXISTS content_hash TEXT;
    ALTER TABLE drugs ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMP;
    ALTER TABLE drugs ADD COLUMN IF NOT EXISTS record_status TEXT DEFAULT 'active';
    ALTER TABLE drugs ADD COLUMN IF NOT EXISTS quality_score FLOAT;

    -- companies
    ALTER TABLE companies ADD COLUMN IF NOT EXISTS content_hash TEXT;
    ALTER TABLE companies ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMP;
    ALTER TABLE companies ADD COLUMN IF NOT EXISTS record_status TEXT DEFAULT 'active';
    ALTER TABLE companies ADD COLUMN IF NOT EXISTS quality_score FLOAT;

    -- clinical_trials
    ALTER TABLE clinical_trials ADD COLUMN IF NOT EXISTS content_hash TEXT;
    ALTER TABLE clinical_trials ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMP;
    ALTER TABLE clinical_trials ADD COLUMN IF NOT EXISTS record_status TEXT DEFAULT 'active';
    ALTER TABLE clinical_trials ADD COLUMN IF NOT EXISTS quality_score FLOAT;

    -- pubmed_articles
    ALTER TABLE pubmed_articles ADD COLUMN IF NOT EXISTS content_hash TEXT;
    ALTER TABLE pubmed_articles ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMP;
    ALTER TABLE pubmed_articles ADD COLUMN IF NOT EXISTS record_status TEXT DEFAULT 'active';
    ALTER TABLE pubmed_articles ADD COLUMN IF NOT EXISTS quality_score FLOAT;

    -- market_events
    ALTER TABLE market_events ADD COLUMN IF NOT EXISTS content_hash TEXT;
    ALTER TABLE market_events ADD COLUMN IF NOT EXISTS last_verified_at TIMESTAMP;
    ALTER TABLE market_events ADD COLUMN IF NOT EXISTS record_status TEXT DEFAULT 'active';
    ALTER TABLE market_events ADD COLUMN IF NOT EXISTS quality_score FLOAT;
END $$;

-- Indexes for lifecycle queries
CREATE INDEX IF NOT EXISTS idx_drugs_status ON drugs(record_status);
CREATE INDEX IF NOT EXISTS idx_trials_status ON clinical_trials(record_status);
CREATE INDEX IF NOT EXISTS idx_articles_status ON pubmed_articles(record_status);
CREATE INDEX IF NOT EXISTS idx_events_status ON market_events(record_status);
CREATE INDEX IF NOT EXISTS idx_drugs_verified ON drugs(last_verified_at);
CREATE INDEX IF NOT EXISTS idx_trials_verified ON clinical_trials(last_verified_at);

-- ============================================================
-- 2. Data quality rules (configurable per entity type)
-- ============================================================

CREATE TABLE IF NOT EXISTS data_quality_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    rule_type TEXT NOT NULL,
    rule_config JSONB NOT NULL,
    severity TEXT NOT NULL DEFAULT 'warning',
    enabled BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(entity_type, rule_name)
);

COMMENT ON TABLE data_quality_rules IS
    'Configurable quality rules per entity type. rule_type: completeness, freshness, consistency, cross_source, embedding_coverage. severity: info, warning, error, critical.';

-- ============================================================
-- 3. Quality assessment results (per-record)
-- ============================================================

CREATE TABLE IF NOT EXISTS data_quality_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    rule_id UUID REFERENCES data_quality_rules(id),
    passed BOOLEAN NOT NULL,
    score FLOAT,
    details JSONB,
    assessed_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dqr_entity ON data_quality_results(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_dqr_rule ON data_quality_results(rule_id);
CREATE INDEX IF NOT EXISTS idx_dqr_failed ON data_quality_results(passed) WHERE passed = FALSE;

-- ============================================================
-- 4. HITL review queue
-- ============================================================

CREATE TABLE IF NOT EXISTS hitl_review_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    priority INTEGER DEFAULT 50,
    status TEXT DEFAULT 'pending',
    payload JSONB NOT NULL,
    source_etl_run_id UUID,
    assigned_to TEXT,
    resolution JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    resolved_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_hitl_pending ON hitl_review_queue(status, priority) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_hitl_type ON hitl_review_queue(review_type);
CREATE INDEX IF NOT EXISTS idx_hitl_entity ON hitl_review_queue(entity_type, entity_id);

COMMENT ON TABLE hitl_review_queue IS
    'Human-in-the-loop review queue. review_type: entity_resolution, quality_failure, conflict, new_entity, withdrawal. status: pending, assigned, approved, rejected, deferred.';

-- ============================================================
-- 5. Dataset catalog (ODI AI-readiness metadata layer)
-- ============================================================

CREATE TABLE IF NOT EXISTS dataset_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dataset_name TEXT UNIQUE NOT NULL,
    source_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    description TEXT,
    table_name TEXT NOT NULL,
    row_count INTEGER,
    last_refreshed_at TIMESTAMP,
    refresh_frequency TEXT,
    license_name TEXT,
    license_url TEXT,
    api_base_url TEXT,
    quality_score_avg FLOAT,
    completeness_pct FLOAT,
    freshness_days FLOAT,
    source_imbalance JSONB,
    croissant_metadata JSONB,
    updated_at TIMESTAMP DEFAULT NOW()
);

COMMENT ON TABLE dataset_catalog IS
    'ODI AI-readiness: machine-readable catalog of all datasets with Croissant JSON-LD metadata, quality metrics, and provenance.';

-- ============================================================
-- 6. Data change log (version tracking)
-- ============================================================

CREATE TABLE IF NOT EXISTS data_change_log (
    id BIGSERIAL PRIMARY KEY,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    change_type TEXT NOT NULL,
    changed_fields TEXT[],
    old_content_hash TEXT,
    new_content_hash TEXT,
    etl_run_id UUID,
    changed_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dcl_entity ON data_change_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_dcl_time ON data_change_log(changed_at);
CREATE INDEX IF NOT EXISTS idx_dcl_type ON data_change_log(change_type);

COMMENT ON TABLE data_change_log IS
    'Tracks every data mutation: created, updated, withdrawn, restored. Enables version-control-style auditing per ODI framework criterion 3c.';

-- ============================================================
-- 7. Add quality-related columns to etl_runs
-- ============================================================

ALTER TABLE etl_runs ADD COLUMN IF NOT EXISTS quality_score_avg FLOAT;
ALTER TABLE etl_runs ADD COLUMN IF NOT EXISTS hitl_items_created INTEGER DEFAULT 0;
ALTER TABLE etl_runs ADD COLUMN IF NOT EXISTS records_unchanged INTEGER DEFAULT 0;
