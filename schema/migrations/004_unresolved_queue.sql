-- 004_unresolved_queue.sql
-- Records that couldn't be matched with sufficient confidence.
-- Exposed in admin UI for manual review.

CREATE TABLE unresolved_entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    raw_value TEXT NOT NULL,
    record_type TEXT NOT NULL,
    source_type TEXT NOT NULL,
    context JSONB,
    suggested_match_id UUID,
    suggested_match_name TEXT,
    suggested_confidence FLOAT,
    resolved BOOLEAN DEFAULT FALSE,
    resolved_entity_id UUID,
    resolved_by TEXT,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_unresolved_pending ON unresolved_entities(resolved) WHERE resolved = FALSE;
CREATE INDEX idx_unresolved_source ON unresolved_entities(source_type);
CREATE INDEX idx_unresolved_type ON unresolved_entities(record_type);

COMMENT ON TABLE unresolved_entities IS 'Queue of entity names that could not be matched above the confidence threshold. Resolving an entry creates an entity_aliases row.';
