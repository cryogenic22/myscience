-- BE-2 · Add the missing materiality_score column on signals.
--
-- SPEC-031 (migration 058) added materiality_factors JSONB but never the
-- score column itself. As a result every call to
-- services.materiality.persist_score_to_signal() failed silently with
-- "column \"materiality_score\" of relation \"signals\" does not exist",
-- the frontend rendered NULL → 1%, and the materiality drawer (PB-103)
-- could not ship.
--
-- See specs/BE_002_materiality_diagnostic.md for the full root-cause
-- write-up.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'signals') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'signals'
               AND column_name = 'materiality_score'
        ) THEN
            ALTER TABLE signals
                ADD COLUMN materiality_score INTEGER
                CHECK (materiality_score IS NULL
                       OR (materiality_score BETWEEN 0 AND 100));
        END IF;
    END IF;
END $$;

-- Threshold queries (framing triggers) want a fast index over recent
-- high-score signals.
CREATE INDEX IF NOT EXISTS idx_signals_materiality_score
    ON signals (materiality_score DESC, created_at DESC)
    WHERE materiality_score IS NOT NULL;
