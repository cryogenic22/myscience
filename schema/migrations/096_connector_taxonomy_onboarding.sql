-- 096_connector_taxonomy_onboarding.sql
--
-- DataHub L2 (docs/SPEC_DATA_HUB.md §5.1) — make source onboarding a first-class,
-- typed lifecycle instead of a closed enum + a binary active flag.
--
-- Three additive pieces, all reuse the existing `sources` table (055):
--   1. connector_types — the taxonomy a source's connector belongs to
--      (API_REST / RSS / CSV_FILE / WEB_SCRAPE / WAREHOUSE / MANUAL). Lets a
--      new source declare HOW it is fetched without a code-side enum edit.
--   2. sources.connector_type — a nullable FK onto that taxonomy. Nullable so
--      every existing source row stays valid (backfilled later, not here); the
--      FK fails closed on an unknown type.
--   3. source_onboarding — the onboarding lifecycle for a source:
--      draft → test → staged → prod → paused → retired (transitions enforced in
--      services/connector_taxonomy.py; the column only constrains the SET).
--
-- All additive; no existing column/table is altered destructively.

-- ─── connector_types (the taxonomy) ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS connector_types (
    name             TEXT PRIMARY KEY CHECK (char_length(name) BETWEEN 1 AND 50),
    payload_formats  TEXT[] NOT NULL DEFAULT '{}',
    auth_kinds       TEXT[] NOT NULL DEFAULT '{}',
    description      TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed the six canonical connector types. Idempotent: ON CONFLICT DO NOTHING so
-- re-applying the migration (or a manual re-seed) never errors or duplicates.
-- This SQL is the source of truth for the table; services/connector_taxonomy.py
-- mirrors the names for offline validation (a test asserts they stay in sync).
INSERT INTO connector_types (name, payload_formats, auth_kinds, description) VALUES
    ('API_REST',   ARRAY['json'],              ARRAY['none','api_key','oauth2','basic'], 'REST/JSON HTTP API with pagination + JSONPath extraction'),
    ('RSS',        ARRAY['xml','rss','atom'],  ARRAY['none'],                            'RSS/Atom feed polled for new items'),
    ('CSV_FILE',   ARRAY['csv','tsv'],         ARRAY['none','api_key'],                  'CSV/TSV file or download URL (streamed)'),
    ('WEB_SCRAPE', ARRAY['html','pdf'],        ARRAY['none'],                            'HTML/PDF page fetch + selector/extraction (robots-aware)'),
    ('WAREHOUSE',  ARRAY['sql'],               ARRAY['dsn','oauth2'],                    'Snowflake/Databricks/BigQuery via a DSN + query'),
    ('MANUAL',     ARRAY['json','csv','pdf'],  ARRAY['none'],                            'Human-uploaded document or hand-entered record')
ON CONFLICT (name) DO NOTHING;

-- ─── sources.connector_type (the linkage) ─────────────────────────────────
ALTER TABLE sources
    ADD COLUMN IF NOT EXISTS connector_type TEXT
    REFERENCES connector_types(name) ON UPDATE CASCADE ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_sources_connector_type
    ON sources(connector_type)
    WHERE connector_type IS NOT NULL;

-- ─── source_onboarding (the lifecycle) ────────────────────────────────────
CREATE TABLE IF NOT EXISTS source_onboarding (
    source_id     TEXT PRIMARY KEY REFERENCES sources(source_id) ON DELETE CASCADE,
    status        TEXT NOT NULL DEFAULT 'draft'
                  CHECK (status IN ('draft','test','staged','prod','paused','retired')),
    owner         TEXT,
    contact       TEXT,
    go_live_date  DATE,
    escalation    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_source_onboarding_status
    ON source_onboarding(status);

-- updated_at trigger (reuse the sources_set_updated_at() function from 055)
DROP TRIGGER IF EXISTS trg_source_onboarding_updated_at ON source_onboarding;
CREATE TRIGGER trg_source_onboarding_updated_at
    BEFORE UPDATE ON source_onboarding
    FOR EACH ROW EXECUTE FUNCTION sources_set_updated_at();
