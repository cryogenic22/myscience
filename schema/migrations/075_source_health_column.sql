-- BE-36 · health column on the source registry.
--
-- ``check_health`` writes here so the /sources detail surface can
-- render the current health pill without joining connector_runs.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'sources') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'sources' AND column_name = 'health'
        ) THEN
            ALTER TABLE sources
                ADD COLUMN health TEXT
                CHECK (health IS NULL OR health IN ('healthy','degraded','down','unknown'));
        END IF;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_sources_health
    ON sources (health) WHERE health IS NOT NULL;
