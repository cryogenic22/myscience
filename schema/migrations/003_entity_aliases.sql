-- 003_entity_aliases.sql
-- Stores confirmed name variants across sources.
-- Once a fuzzy match is confirmed, it becomes an instant exact lookup.

CREATE TABLE entity_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    alias_text TEXT NOT NULL,
    source_type TEXT NOT NULL,
    confidence FLOAT NOT NULL,
    verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_alias_unique ON entity_aliases(entity_type, alias_text, source_type);
CREATE INDEX idx_alias_entity ON entity_aliases(entity_type, entity_id);
CREATE INDEX idx_alias_text_trgm ON entity_aliases USING gin(alias_text gin_trgm_ops);

COMMENT ON TABLE entity_aliases IS 'Name variants learned from entity resolution. "Novo Nordisk A/S" → "Novo Nordisk" eliminates repeated fuzzy matching.';
