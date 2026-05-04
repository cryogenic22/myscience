-- Migration 048: war room collaboration (SPEC-021 Phase B)
--
-- Adds:
--   - war_rooms.archived_at (timestamp; NULL = not archived)
--     Distinct from status='closed' (soft delete). A room can be active
--     OR closed AND independently archived. Archive = "out of my list,
--     keep it readable." Close = "soft delete, hide from default list."
--   - war_room_comments table for threaded discussion on a room or
--     specific round. Authors can edit/delete their own; room owners
--     can delete any. Anonymous read so share-by-URL keeps working.
--
-- Migration is additive + idempotent. Safe to re-run.

ALTER TABLE war_rooms
    ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_war_rooms_archived
    ON war_rooms (owner_user_id, archived_at)
    WHERE archived_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS war_room_comments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    war_room_id UUID NOT NULL REFERENCES war_rooms(id) ON DELETE CASCADE,
    round_id UUID REFERENCES war_room_rounds(id) ON DELETE SET NULL,
    author_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    author_display_name TEXT NOT NULL,
    body TEXT NOT NULL CHECK (length(body) BETWEEN 1 AND 4000),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    edited_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_war_room_comments_room
    ON war_room_comments (war_room_id, created_at);

CREATE INDEX IF NOT EXISTS idx_war_room_comments_round
    ON war_room_comments (round_id)
    WHERE round_id IS NOT NULL;

COMMENT ON TABLE war_room_comments IS
    'SPEC-021 B threaded discussion on a war room or a specific round. '
    'Anon read enables share-by-URL flows. Mutations are author-only '
    '(or room-owner for delete). Body is plain-text + safe markdown only; '
    'sanitized server-side at write time.';

COMMENT ON COLUMN war_rooms.archived_at IS
    'NULL = visible in default list. Non-NULL = archived (hidden from '
    'default list, still readable). Independent of status (active|closed).';
