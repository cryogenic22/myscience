-- Migration 020: User feedback entries
-- Captures bug reports, feature requests, and data quality issues from users.
-- Data feedback (data_quality, data_request) feeds the Data Steward signal collector.

CREATE TABLE IF NOT EXISTS feedback_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(255),
    session_id VARCHAR(255),
    page_url TEXT,
    category VARCHAR(30) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    priority VARCHAR(20) DEFAULT 'medium',
    status VARCHAR(20) DEFAULT 'new',
    resolution TEXT,
    resolved_by VARCHAR(20),
    entity_context JSONB,
    diagnostic_context JSONB,
    attachments JSONB DEFAULT '[]',
    steward_action_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_fb_category ON feedback_entries(category);
CREATE INDEX IF NOT EXISTS idx_fb_status ON feedback_entries(status);
CREATE INDEX IF NOT EXISTS idx_fb_created ON feedback_entries(created_at);
CREATE INDEX IF NOT EXISTS idx_fb_data ON feedback_entries(category, status)
    WHERE category IN ('data_quality', 'data_request');
