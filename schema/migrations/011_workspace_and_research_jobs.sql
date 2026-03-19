-- 011_workspace_and_research_jobs.sql
-- Workspace persistence for saved chat sessions and async deep-research jobs.

CREATE TABLE IF NOT EXISTS chat_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope_key TEXT NOT NULL DEFAULT 'default',
    title TEXT NOT NULL,
    transcript JSONB NOT NULL,
    summary TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_sessions_scope_updated
    ON chat_sessions(scope_key, updated_at DESC);

CREATE TABLE IF NOT EXISTS deep_research_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope_key TEXT NOT NULL DEFAULT 'default',
    question TEXT NOT NULL,
    options JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'queued',
    result_payload JSONB,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_deep_research_jobs_scope_created
    ON deep_research_jobs(scope_key, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_deep_research_jobs_status
    ON deep_research_jobs(status, updated_at DESC);
