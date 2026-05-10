-- BE-25 · Licence fields on the source registry.
--
-- Existing source registry already carries license_status +
-- license_renewal_at (SPEC-027). PB-807's Licence Health Panel needs
-- two more: annual_cost_usd and licence_type so it can render the
-- per-source row, the total-today number, and the projected total
-- after Phase 2 connectors enable.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'sources') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'sources' AND column_name = 'annual_cost_usd'
        ) THEN
            ALTER TABLE sources
                ADD COLUMN annual_cost_usd NUMERIC(12, 2)
                CHECK (annual_cost_usd IS NULL OR annual_cost_usd >= 0);
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'sources' AND column_name = 'licence_type'
        ) THEN
            ALTER TABLE sources
                ADD COLUMN licence_type TEXT
                CHECK (licence_type IS NULL OR licence_type IN
                       ('public_domain','open','commercial','enterprise','byod'));
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'sources' AND column_name = 'phase'
        ) THEN
            ALTER TABLE sources
                ADD COLUMN phase TEXT DEFAULT 'now'
                CHECK (phase IN ('now','phase1','phase2','phase3','phase4'));
        END IF;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_sources_phase
    ON sources (phase) WHERE phase IS NOT NULL;
