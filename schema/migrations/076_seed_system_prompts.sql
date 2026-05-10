-- BE-40 · Seed prompt_registry with the system prompts that today
-- live as a hardcoded dict in services/llm.py:179.
--
-- Per-intent prompts get a stable name = "system.<intent>". Version
-- 1 is the seed; subsequent edits via UI / scripts mint new
-- versions and the active row is the highest version.

-- Add a `name = active flag` column so the registry can express
-- "current production prompt for this name" without recomputing.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'prompt_registry') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'prompt_registry' AND column_name = 'is_active'
        ) THEN
            ALTER TABLE prompt_registry
                ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT FALSE;
        END IF;
    END IF;
END $$;

-- The actual seed is performed by scripts/migrate_system_prompts.py
-- so the migration stays small and the seeding logic can be
-- re-run idempotently as the source dict evolves.
