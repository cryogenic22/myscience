-- SPEC_028 — Multi-Agent War-Game Adversaries.
-- Per-brief war-game runs with grounded adversary panels.
-- Critical invariant: every action MUST cite an evidence_record (NOT NULL FK).

-- ─── war_game_runs ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS war_game_runs (
    run_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    brief_id            UUID NOT NULL,  -- FK to decision_briefs added below if exists
    status              TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending','running','complete','failed','cancelled')),
    num_rounds          INTEGER NOT NULL DEFAULT 3 CHECK (num_rounds BETWEEN 1 AND 10),
    started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at        TIMESTAMPTZ,
    failure_reason      TEXT,
    summary_jsonb       JSONB NOT NULL DEFAULT '{}'::jsonb,
    started_by_user_id  UUID
);

CREATE INDEX IF NOT EXISTS idx_war_game_runs_brief
    ON war_game_runs(brief_id, started_at DESC);

CREATE INDEX IF NOT EXISTS idx_war_game_runs_status
    ON war_game_runs(status, started_at DESC);

-- Conditional FK to decision_briefs (only if table exists from SPEC-023)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'decision_briefs') THEN
        BEGIN
            ALTER TABLE war_game_runs
              ADD CONSTRAINT fk_war_game_runs_brief
              FOREIGN KEY (brief_id) REFERENCES decision_briefs(brief_id) ON DELETE CASCADE;
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END;
    END IF;
END $$;

-- ─── war_game_adversaries ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS war_game_adversaries (
    adversary_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                  UUID NOT NULL REFERENCES war_game_runs(run_id) ON DELETE CASCADE,
    kind                    TEXT NOT NULL CHECK (kind IN ('competitor','payer','regulator','kol')),
    name                    TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
    entity_type             TEXT,
    entity_id               UUID,
    persona_jsonb           JSONB NOT NULL DEFAULT '{}'::jsonb,
    grounding_evidence_ids  UUID[] NOT NULL DEFAULT '{}',
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_adversaries_run
    ON war_game_adversaries (run_id, kind);

-- ─── war_game_actions ────────────────────────────────────────────────
-- The grounding rule is enforced at the DB level: grounding_evidence_id
-- is NOT NULL and FK-constrained against evidence_records.
CREATE TABLE IF NOT EXISTS war_game_actions (
    action_id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                 UUID NOT NULL REFERENCES war_game_runs(run_id) ON DELETE CASCADE,
    adversary_id           UUID NOT NULL REFERENCES war_game_adversaries(adversary_id) ON DELETE CASCADE,
    option_id              UUID NOT NULL,  -- FK to decision_brief_options when present
    round_num              INTEGER NOT NULL CHECK (round_num >= 1),
    action_kind            TEXT NOT NULL DEFAULT 'react'
                           CHECK (action_kind IN ('react','escalate','wait','concede','threat','counter','partner')),
    action_text            TEXT NOT NULL CHECK (char_length(action_text) BETWEEN 1 AND 8000),
    grounding_evidence_id  UUID NOT NULL,  -- FK to evidence_records added below if exists
    grounding_precedent    TEXT,
    confidence             REAL CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    llm_call_id            UUID,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (run_id, adversary_id, option_id, round_num)
);

CREATE INDEX IF NOT EXISTS idx_actions_run_round
    ON war_game_actions (run_id, round_num, adversary_id);

CREATE INDEX IF NOT EXISTS idx_actions_option
    ON war_game_actions (option_id);

-- Conditional FK to decision_brief_options
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'decision_brief_options') THEN
        BEGIN
            ALTER TABLE war_game_actions
              ADD CONSTRAINT fk_actions_option
              FOREIGN KEY (option_id) REFERENCES decision_brief_options(option_id) ON DELETE CASCADE;
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END;
    END IF;
END $$;

-- Conditional FK to evidence_records (the grounding rule)
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'evidence_records') THEN
        BEGIN
            ALTER TABLE war_game_actions
              ADD CONSTRAINT fk_actions_grounding_evidence
              FOREIGN KEY (grounding_evidence_id) REFERENCES evidence_records(evidence_id) ON DELETE RESTRICT;
        EXCEPTION
            WHEN duplicate_object THEN NULL;
        END;
    END IF;
END $$;
