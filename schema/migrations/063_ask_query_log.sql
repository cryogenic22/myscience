-- SPEC_035 — Ask Query Log: append-only telemetry for the /ask endpoint.

CREATE TABLE IF NOT EXISTS ask_query_log (
    ask_query_id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question            TEXT NOT NULL CHECK (char_length(question) BETWEEN 1 AND 1000),
    matched_pattern     TEXT,
    intent_jsonb        JSONB NOT NULL DEFAULT '{}'::jsonb,
    result_node_count   INTEGER NOT NULL DEFAULT 0 CHECK (result_node_count >= 0),
    result_edge_count   INTEGER NOT NULL DEFAULT 0 CHECK (result_edge_count >= 0),
    latency_ms          INTEGER NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
    succeeded           BOOLEAN NOT NULL,
    error_message       TEXT,
    user_id             UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aql_user_time
    ON ask_query_log (user_id, created_at DESC)
    WHERE user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_aql_pattern
    ON ask_query_log (matched_pattern, created_at DESC)
    WHERE matched_pattern IS NOT NULL;
