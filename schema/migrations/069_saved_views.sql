-- BE-21 · saved_views — first-class persisted graph state.
--
-- PB-703 lets a user save a configured graph view (centre entity,
-- hops, edge filters, multi-select state) and share it via a slug.
-- The saved view is versioned so a steward can roll back if a tweak
-- breaks something downstream.

CREATE TABLE IF NOT EXISTS saved_views (
    view_id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_user_id   UUID NOT NULL,
    name            TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
    version         INTEGER NOT NULL DEFAULT 1 CHECK (version >= 1),
    state           JSONB NOT NULL DEFAULT '{}'::jsonb,
    shareable_slug  TEXT UNIQUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_saved_views_owner
    ON saved_views (owner_user_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_saved_views_slug
    ON saved_views (shareable_slug)
    WHERE shareable_slug IS NOT NULL;

-- updated_at + version bump trigger (PATCH overwrites bump version too)
CREATE OR REPLACE FUNCTION saved_views_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_saved_views_updated_at ON saved_views;
CREATE TRIGGER trg_saved_views_updated_at
    BEFORE UPDATE ON saved_views
    FOR EACH ROW EXECUTE FUNCTION saved_views_set_updated_at();
