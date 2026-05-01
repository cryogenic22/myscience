-- Migration 044: watchlist_entries table (SPEC-020)
--
-- Per-user CI watchlist. An entry pins a (entity_type, entity_id) so the
-- analyst's signal feed and brief subscriptions can filter to their tracked
-- companies / drugs / mechanisms.
--
-- No team-shared lists in MVP — defer per comp_intel_2.md §3.2.
--
-- Migration is additive. Idempotent via IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS watchlist_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    label TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (user_id, entity_type, entity_id)
);

CREATE INDEX IF NOT EXISTS idx_watchlist_user
    ON watchlist_entries (user_id);
