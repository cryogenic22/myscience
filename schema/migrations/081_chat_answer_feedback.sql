-- Migration 080: chat_answer_feedback (C2 — learning loops).
-- The missing training signal: a user thumbs up/down per chat answer.
-- Diagnosis: "No response-quality signal — no thumbs up/down on chat
-- answers, so no training signal from users." This table captures it so
-- the learning loops (and future model/prompt evaluation) have ground truth.
--
-- A feedback row is keyed loosely to a query: by session_id + question_hash
-- (always available) and optionally to a query_telemetry row when one exists.
-- Append-only, additive; one latest rating per (session, question) is what we
-- read, but we keep history (a user may flip their vote).

CREATE TABLE IF NOT EXISTS chat_answer_feedback (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      TEXT,
    question_hash   TEXT NOT NULL,             -- sha256(question)[:16], matches query_telemetry
    question_text   TEXT,
    rating          SMALLINT NOT NULL CHECK (rating IN (-1, 1)),  -- -1 = down, +1 = up
    comment         TEXT,
    intent          TEXT,
    answer_excerpt  TEXT,                       -- first chars of the answer, for context
    query_telemetry_id UUID,                    -- soft FK to query_telemetry.id (nullable)
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chat_feedback_question
    ON chat_answer_feedback (question_hash, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_feedback_session
    ON chat_answer_feedback (session_id, created_at DESC)
    WHERE session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_chat_feedback_rating
    ON chat_answer_feedback (rating, created_at DESC);
