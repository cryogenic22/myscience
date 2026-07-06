-- BE-12 · Agent authority spectrum.
--
-- PB-504 surfaces a 5-level authority spectrum
-- (L1 watch / L2 suggest / L3 recommend / L4 act-with-notice /
-- L5 auto-audit) per (agent, scenario_type). Promotion is earned by
-- calibration ≥ 0.70 over 14 scenarios.

CREATE TABLE IF NOT EXISTS agent_authority (
    agent              TEXT NOT NULL,
    scenario_type      TEXT NOT NULL,
    current_level      INTEGER NOT NULL DEFAULT 1
                       CHECK (current_level BETWEEN 1 AND 5),
    calibration_score  REAL NOT NULL DEFAULT 0.5
                       CHECK (calibration_score BETWEEN 0 AND 1),
    scenario_count     INTEGER NOT NULL DEFAULT 0
                       CHECK (scenario_count >= 0),
    last_promoted_at   TIMESTAMPTZ,
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (agent, scenario_type)
);

CREATE INDEX IF NOT EXISTS idx_agent_authority_level
    ON agent_authority (current_level DESC, agent);

-- Append-only promotion audit so a steward can replay any change.
CREATE TABLE IF NOT EXISTS agent_authority_promotions (
    id                  BIGSERIAL PRIMARY KEY,
    agent               TEXT NOT NULL,
    scenario_type       TEXT NOT NULL,
    from_level          INTEGER NOT NULL CHECK (from_level BETWEEN 1 AND 5),
    to_level            INTEGER NOT NULL CHECK (to_level BETWEEN 1 AND 5),
    calibration_score   REAL NOT NULL,
    scenario_count      INTEGER NOT NULL,
    actor               TEXT,    -- 'auto' for promotion-engine | user_id for manual
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agent_authority_promotions_agent
    ON agent_authority_promotions (agent, created_at DESC);
