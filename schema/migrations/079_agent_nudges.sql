-- Migration 079: agent_nudges (PB-203)
-- A nudge is a reviewer instruction to a named agent (Sentinel/Strategist/
-- Curator). Agents run as background loops, so nudges are queued append-only
-- for the agent to consume on its next pass — not executed synchronously.

CREATE TABLE IF NOT EXISTS agent_nudges (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent       TEXT NOT NULL,              -- sentinel | strategist | curator
    intent      TEXT NOT NULL,              -- registry key (services/agent/nudge_intents.py)
    target      JSONB,                      -- {entity_id|signal_id|source_id|scenario_id|outcome_id: ...}
    note        TEXT,
    status      TEXT NOT NULL DEFAULT 'queued',  -- queued|acknowledged|done|dismissed
    created_by  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_nudges_agent
    ON agent_nudges(agent, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_nudges_status
    ON agent_nudges(status, created_at DESC);
