-- SPEC_026 — LLM Gateway: prompt registry + llm_call_log augmentation.

-- ─── prompt_registry ─────────────────────────────────────────────────
-- Versioned, addressable prompts. Idempotent register: same (name, content_hash)
-- returns existing row.
CREATE TABLE IF NOT EXISTS prompt_registry (
    prompt_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                 TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
    version              INTEGER NOT NULL CHECK (version >= 1),
    content              TEXT NOT NULL CHECK (char_length(content) BETWEEN 1 AND 32768),
    content_hash         BYTEA NOT NULL,
    purpose              TEXT,
    model_pref           TEXT,
    max_tokens           INTEGER CHECK (max_tokens IS NULL OR (max_tokens > 0 AND max_tokens <= 100000)),
    created_by_user_id   UUID,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (name, version),
    UNIQUE (name, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_prompts_name
    ON prompt_registry (name, version DESC);

CREATE INDEX IF NOT EXISTS idx_prompts_content_hash
    ON prompt_registry (content_hash);

-- ─── augment llm_call_log (additive, back-compat) ────────────────────
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
         WHERE table_name = 'llm_call_log'
           AND column_name = 'prompt_id'
    ) THEN
        ALTER TABLE llm_call_log
            ADD COLUMN prompt_id UUID;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_llm_call_log_prompt_id
    ON llm_call_log (prompt_id)
    WHERE prompt_id IS NOT NULL;

-- created_at::date is STABLE (TZ-dependent); cast at UTC for IMMUTABLE.
CREATE INDEX IF NOT EXISTS idx_llm_call_log_caller_day
    ON llm_call_log (caller, ((created_at AT TIME ZONE 'UTC')::date));

CREATE INDEX IF NOT EXISTS idx_llm_call_log_user_day
    ON llm_call_log (user_id, ((created_at AT TIME ZONE 'UTC')::date))
    WHERE user_id IS NOT NULL;
