-- 076_entity_comments.sql
--
-- UX02 / PB-UX02 — generic entity comments.
--
-- A reusable comment thread for ANY entity (target_type + target_id) — the
-- collaboration primitive the war-room rounds had hardcoded. Lets a brief,
-- scenario, insight, gap, dossier domain, etc. carry a discussion thread
-- without a bespoke table each. Append-only in spirit (edited_at tracks edits).
-- Additive + idempotent.

CREATE TABLE IF NOT EXISTS entity_comments (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    target_type         TEXT NOT NULL,
    target_id           TEXT NOT NULL,
    author_user_id      TEXT,
    author_display_name TEXT NOT NULL DEFAULT 'Anonymous',
    body                TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    edited_at           TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_entity_comments_target
    ON entity_comments(target_type, target_id, created_at);
