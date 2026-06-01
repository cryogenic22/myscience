-- 075_gap_remediations.sql
--
-- UX05b / PB-UX05b — persist gap remediation choices.
--
-- The gaps stage (UX05) let users set a remediation per gap (primary_research /
-- accept_uncertainty / descope) but it was client-side only. This table makes
-- it durable + auditable, keyed by engagement + gap domain (gaps are one-per-
-- domain). Upsert on (engagement_id, gap_domain): the latest choice wins, with
-- provenance (who/when/note). Additive + idempotent.

CREATE TABLE IF NOT EXISTS gap_remediations (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    gap_domain    TEXT NOT NULL,
    remediation   TEXT NOT NULL CHECK (remediation IN
                      ('primary_research', 'accept_uncertainty', 'descope', 'pending')),
    note          TEXT,
    created_by    TEXT NOT NULL DEFAULT 'system',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT gap_remediations_unique UNIQUE (engagement_id, gap_domain)
);

CREATE INDEX IF NOT EXISTS idx_gap_remediations_engagement
    ON gap_remediations(engagement_id);
