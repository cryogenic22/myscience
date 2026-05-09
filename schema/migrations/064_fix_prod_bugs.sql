-- Fix B2: recommendation_synthesis_runs option_id columns are UUID NOT NULL
-- but the route accepts arbitrary caller-supplied option_id strings (the
-- option may be from a brief OR an ad-hoc synthesis). Change to TEXT.
-- Drops the table CHECK first since changing column type drops constraints
-- anyway in some cases; we recreate it after.

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables
                WHERE table_name = 'recommendation_synthesis_runs') THEN
        -- Drop dependent CHECK if present (Postgres will recreate as needed)
        ALTER TABLE recommendation_synthesis_runs
            ALTER COLUMN primary_option_id TYPE TEXT,
            ALTER COLUMN counter_option_id TYPE TEXT;
    END IF;
END $$;

-- The (primary <> counter) CHECK survives the type change; no need to
-- recreate it. Verify with:
--   \d+ recommendation_synthesis_runs
