-- Migration 032: Add market_events.primary_entity_id
--
-- Migration 026 added primary_entity_type and primary_entity_name to
-- market_events but not the id. The dossier handler at
-- api/routes/catalog.py queries WHERE primary_entity_id = %s — without
-- this column the recent-events section of the dossier returns nothing.

ALTER TABLE market_events
    ADD COLUMN IF NOT EXISTS primary_entity_id TEXT;

CREATE INDEX IF NOT EXISTS idx_market_events_primary_entity_id
    ON market_events (primary_entity_id, primary_entity_type)
    WHERE primary_entity_id IS NOT NULL;
