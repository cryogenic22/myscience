-- 023: FAIR data quality snapshots
-- Stores periodic quality score snapshots for trending and API exposure.

CREATE TABLE IF NOT EXISTS data_quality_snapshots (
    id SERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    overall_score REAL,
    entity_completeness JSONB,   -- {"drug": 0.56, "company": 0.33, ...}
    link_density REAL,           -- avg links per entity (normalized 0-1)
    source_diversity REAL,       -- % entities with 2+ sources (0-1)
    freshness REAL,              -- % records updated in last 30 days (0-1)
    resolution_rate REAL,        -- % of unresolved cleared (0-1)
    total_records INTEGER,
    total_links INTEGER,
    details JSONB                -- full breakdown for deep inspection
);

-- Index for fast latest/trend lookups
CREATE INDEX IF NOT EXISTS idx_dqs_created_at
    ON data_quality_snapshots (created_at DESC);
