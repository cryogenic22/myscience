-- Migration 045: war rooms (SPEC-021 Phase A)
--
-- Three tables for the decision-flywheel simulation layer:
--   war_rooms             — durable simulation session
--   war_room_rounds       — one player move per round (1..N per room)
--   war_room_reactions    — N competitor reactions per round
--
-- All additive. Idempotent via IF NOT EXISTS.

CREATE TABLE IF NOT EXISTS war_rooms (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    owner_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    scenario_question TEXT,
    primary_entity_type TEXT,
    primary_entity_id TEXT,
    primary_entity_name TEXT,
    source_signal_id UUID REFERENCES signals(id) ON DELETE SET NULL,
    game_phase TEXT NOT NULL DEFAULT 'launch'
        CHECK (game_phase IN ('prelaunch', 'launch', 'postlaunch')),
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('draft', 'active', 'closed')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS war_room_rounds (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    war_room_id UUID NOT NULL REFERENCES war_rooms(id) ON DELETE CASCADE,
    round_number INT NOT NULL,
    player_company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
    player_company_name TEXT,
    move_type TEXT NOT NULL,
    move_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    notes TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (war_room_id, round_number)
);

CREATE TABLE IF NOT EXISTS war_room_reactions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    round_id UUID NOT NULL REFERENCES war_room_rounds(id) ON DELETE CASCADE,
    competitor_company_id UUID REFERENCES companies(id) ON DELETE SET NULL,
    competitor_company_name TEXT NOT NULL,
    reaction_type TEXT NOT NULL,
    headline TEXT,
    specific_action TEXT,
    asset_leveraged JSONB,
    rationale TEXT,
    evidence_basis TEXT[] NOT NULL DEFAULT '{}',
    scores JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence TEXT
        CHECK (confidence IS NULL OR confidence IN ('high', 'medium', 'low')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_war_rooms_owner
    ON war_rooms (owner_user_id) WHERE owner_user_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_war_rooms_signal
    ON war_rooms (source_signal_id) WHERE source_signal_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_war_room_rounds_room
    ON war_room_rounds (war_room_id, round_number);

CREATE INDEX IF NOT EXISTS idx_war_room_reactions_round
    ON war_room_reactions (round_id);
