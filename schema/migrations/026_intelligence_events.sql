-- Migration 026: Intelligence events — extend market_events for proactive
-- intelligence (SPEC-003 Stream 1) and create impact_assessments table.

-- ============================================================
-- EXTEND market_events WITH intelligence columns
-- ============================================================

ALTER TABLE market_events ADD COLUMN IF NOT EXISTS source_tier TEXT DEFAULT 'tier_3';
ALTER TABLE market_events ADD COLUMN IF NOT EXISTS trust_score FLOAT DEFAULT 0.5;
ALTER TABLE market_events ADD COLUMN IF NOT EXISTS primary_entity_type TEXT;
ALTER TABLE market_events ADD COLUMN IF NOT EXISTS primary_entity_name TEXT;
ALTER TABLE market_events ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'new';
ALTER TABLE market_events ADD COLUMN IF NOT EXISTS event_hash TEXT;
ALTER TABLE market_events ADD COLUMN IF NOT EXISTS corroborating_sources JSONB DEFAULT '[]'::jsonb;
ALTER TABLE market_events ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ;

-- ============================================================
-- NEW TABLE: impact_assessments
-- ============================================================

CREATE TABLE IF NOT EXISTS impact_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id UUID NOT NULL REFERENCES market_events(id),
    affected_entity_id TEXT,
    affected_entity_type TEXT,
    affected_entity_name TEXT,
    impact_magnitude FLOAT,
    impact_direction TEXT,
    assessment_type TEXT NOT NULL,
    scenario_result JSONB,
    narrative TEXT,
    graph_path JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================

-- market_events indexes
CREATE INDEX IF NOT EXISTS idx_events_status ON market_events(status);
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_hash ON market_events(event_hash) WHERE event_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_events_trust ON market_events(trust_score DESC);
CREATE INDEX IF NOT EXISTS idx_events_primary ON market_events(primary_entity_type, primary_entity_name);

-- impact_assessments indexes
CREATE INDEX IF NOT EXISTS idx_impact_event ON impact_assessments(event_id);
CREATE INDEX IF NOT EXISTS idx_impact_entity ON impact_assessments(affected_entity_id, affected_entity_type);
CREATE INDEX IF NOT EXISTS idx_impact_magnitude ON impact_assessments(impact_magnitude DESC);
