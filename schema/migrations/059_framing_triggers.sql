-- SPEC_029 — Framing Triggers: auto-create draft Decision Briefs from
-- threshold/cluster/calendar signals.

-- ─── framing_triggers ────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS framing_triggers (
    trigger_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
    kind                TEXT NOT NULL CHECK (kind IN ('threshold','cluster','calendar')),
    config_jsonb        JSONB NOT NULL DEFAULT '{}'::jsonb,
    assignee_user_id    UUID,
    is_active           BOOLEAN NOT NULL DEFAULT TRUE,
    last_evaluated_at   TIMESTAMPTZ,
    next_fire_at        TIMESTAMPTZ,
    created_by_user_id  UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_framing_triggers_active
    ON framing_triggers (kind, is_active)
    WHERE is_active = TRUE;

CREATE INDEX IF NOT EXISTS idx_framing_triggers_next_fire
    ON framing_triggers (next_fire_at)
    WHERE is_active = TRUE AND next_fire_at IS NOT NULL;

-- ─── framing_trigger_fires ───────────────────────────────────────────
-- Append-only event log of every evaluation that produced (or skipped) a brief.
CREATE TABLE IF NOT EXISTS framing_trigger_fires (
    fire_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trigger_id       UUID NOT NULL REFERENCES framing_triggers(trigger_id) ON DELETE CASCADE,
    fired_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    signal_ids       UUID[] NOT NULL DEFAULT '{}',
    brief_id         UUID,  -- loose pointer; FK conditional
    status           TEXT NOT NULL CHECK (status IN ('success','skipped_no_match','skipped_dedup','failed')),
    failure_reason   TEXT
);

CREATE INDEX IF NOT EXISTS idx_fires_trigger_fired
    ON framing_trigger_fires (trigger_id, fired_at DESC);

CREATE INDEX IF NOT EXISTS idx_fires_brief
    ON framing_trigger_fires (brief_id)
    WHERE brief_id IS NOT NULL;

-- Conditional FK to decision_briefs (created in SPEC-023; may not exist
-- in all deploy orders)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'decision_briefs') THEN
        BEGIN
            ALTER TABLE framing_trigger_fires
              ADD CONSTRAINT fk_fires_brief
              FOREIGN KEY (brief_id) REFERENCES decision_briefs(brief_id) ON DELETE SET NULL;
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END;
    END IF;
END $$;

-- updated_at trigger
CREATE OR REPLACE FUNCTION framing_triggers_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_framing_triggers_updated_at ON framing_triggers;
CREATE TRIGGER trg_framing_triggers_updated_at
    BEFORE UPDATE ON framing_triggers
    FOR EACH ROW EXECUTE FUNCTION framing_triggers_set_updated_at();
