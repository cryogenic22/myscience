-- Agent session persistence: tracks agent runs with checkpoint support
-- for crash recovery and observability.

CREATE TABLE IF NOT EXISTS agent_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_type TEXT NOT NULL,
    goal TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    current_step INT DEFAULT 0,
    total_steps INT,
    checkpoint_data JSONB DEFAULT '{}',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    last_checkpoint TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    error_message TEXT,
    metadata JSONB DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_agent_sessions_status ON agent_sessions(status);
CREATE INDEX IF NOT EXISTS idx_agent_sessions_type ON agent_sessions(agent_type, started_at DESC);

CREATE TABLE IF NOT EXISTS agent_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id UUID REFERENCES agent_sessions(id),
    event_type TEXT NOT NULL,
    agent_type TEXT,
    tool_name TEXT,
    trust_tier TEXT,
    args_hash TEXT,
    result_status TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_events_session ON agent_events(session_id);
CREATE INDEX IF NOT EXISTS idx_agent_events_type ON agent_events(event_type, created_at DESC);
