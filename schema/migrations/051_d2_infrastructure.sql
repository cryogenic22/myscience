-- Migration 051: D2 infrastructure (SPEC-021 Phase D2)
--
-- Adds the storage layer for:
--   - Idempotent decision promotion (UNIQUE on war_room_round_id)
--   - LLM call telemetry (llm_call_log)
--   - Daily quota tracking per user (llm_quota_usage)
--   - Autonomous outcome detection bookkeeping
--     (decisions.outcome_auto_checked_at + outcome_proposals table)
--
-- Migration is additive + idempotent. Safe to re-run.

-- ── Idempotency for decision promotion ─────────────────────────
-- Reject duplicate POST /decisions/from-round/{round_id} via
-- a unique partial index. The route catches the conflict and returns
-- the existing row with HTTP 200 instead of 201.
CREATE UNIQUE INDEX IF NOT EXISTS uq_decisions_war_room_round
    ON decisions (war_room_round_id)
    WHERE war_room_round_id IS NOT NULL;

-- ── LLM call telemetry ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS llm_call_log (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- 'war_game' | 'suggester' | 'outcome_detector' | 'synthesize' | 'raw_chat'
    caller            TEXT NOT NULL,
    model             TEXT,
    prompt_version    TEXT,
    user_id           UUID REFERENCES users(id) ON DELETE SET NULL,
    latency_ms        INTEGER,
    prompt_tokens     INTEGER,
    completion_tokens INTEGER,
    cost_estimate_usd REAL,
    succeeded         BOOLEAN NOT NULL,
    error_message     TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_call_log_caller_time
    ON llm_call_log (caller, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_llm_call_log_user_day
    ON llm_call_log (user_id, created_at);

COMMENT ON TABLE llm_call_log IS
    'SPEC-021 D2 LLM telemetry. Every raw_chat call writes a row here '
    'so we can compute p95 latency, daily cost rollup per user, and '
    'retrospectively diagnose bad responses.';

-- ── Daily LLM quota tracking ───────────────────────────────────
CREATE TABLE IF NOT EXISTS llm_quota_usage (
    user_id     UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    day         DATE NOT NULL,
    call_count  INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, day)
);

COMMENT ON TABLE llm_quota_usage IS
    'SPEC-021 D2 daily LLM call quota per authenticated user. Default '
    'cap is MZ_LLM_DAILY_CAP env (default 200). Resets at midnight UTC.';

-- ── Autonomous outcome detection bookkeeping ───────────────────
ALTER TABLE decisions
    ADD COLUMN IF NOT EXISTS outcome_auto_checked_at TIMESTAMPTZ;

-- Partial index optimised for "which open decisions need auto-check?"
CREATE INDEX IF NOT EXISTS idx_decisions_auto_check
    ON decisions (outcome_auto_checked_at NULLS FIRST)
    WHERE status IN ('open', 'in_progress');

COMMENT ON COLUMN decisions.outcome_auto_checked_at IS
    'SPEC-021 D2 set by outcome_scheduler each tick. NULL = never '
    'checked yet; non-NULL + < NOW() - 6h means due for re-scan.';

-- ── Auto-detected outcome proposals ────────────────────────────
CREATE TABLE IF NOT EXISTS outcome_proposals (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    decision_id       UUID NOT NULL REFERENCES decisions(id) ON DELETE CASCADE,
    matched_signal_id UUID NOT NULL REFERENCES signals(id) ON DELETE CASCADE,
    match_score       REAL NOT NULL CHECK (match_score BETWEEN 0.0 AND 1.0),
    match_components  JSONB NOT NULL DEFAULT '{}'::jsonb,
    status            TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'confirmed', 'dismissed')),
    proposed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolved_at       TIMESTAMPTZ,
    resolved_by       UUID REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE (decision_id, matched_signal_id)
);

CREATE INDEX IF NOT EXISTS idx_outcome_proposals_status_decision
    ON outcome_proposals (status, decision_id);

COMMENT ON TABLE outcome_proposals IS
    'SPEC-021 D2 autonomous matches awaiting human confirm. '
    'Scheduler appends; UI lists pending; owner confirms (→ '
    'capture-outcome) or dismisses (→ never re-propose this signal).';
