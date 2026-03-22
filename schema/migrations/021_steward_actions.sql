-- Migration 021: Data Steward action log
-- Records every action taken by the autonomous Data Steward loop.
-- Links back to feedback_entries for auto-resolution tracking.

CREATE TABLE IF NOT EXISTS steward_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    signal_source VARCHAR(30) NOT NULL,
    signal_id VARCHAR(255),
    entity_type VARCHAR(50),
    entity_id VARCHAR(255),
    entity_name VARCHAR(500),
    action_type VARCHAR(50) NOT NULL,
    action_details JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    fair_before REAL,
    fair_after REAL,
    fair_delta REAL,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_sa_status ON steward_actions(status);
CREATE INDEX IF NOT EXISTS idx_sa_entity ON steward_actions(entity_id);
CREATE INDEX IF NOT EXISTS idx_sa_signal ON steward_actions(signal_source, signal_id);

-- Add FK from feedback_entries to steward_actions
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
        WHERE constraint_name = 'fk_feedback_steward_action'
    ) THEN
        ALTER TABLE feedback_entries
            ADD CONSTRAINT fk_feedback_steward_action
            FOREIGN KEY (steward_action_id)
            REFERENCES steward_actions(id)
            ON DELETE SET NULL;
    END IF;
END $$;
