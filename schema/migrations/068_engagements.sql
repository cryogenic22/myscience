-- Migration 068: engagements + engagement_audit_log (Z3)
--
-- The Engagement is the v7 design canon's unit of work. Every meaningful
-- piece of work in the platform belongs to an Engagement, and the
-- surfaces of /ci are the stages of its lifecycle.
--
-- Lifecycle (7 stages, from helix-v7-gap-analysis §1.2):
--   brief → sources → dossier → synthesis → gaps → scenarios → workshop
--
-- Status (orthogonal):
--   draft → active → completed → archived
--
-- The FSM is enforced in Python (services/engagement.py) AND mirrored as
-- CHECK constraints here (defence in depth). engagement_audit_log captures
-- every stage/status mutation with rationale — procurement-grade artifact.

BEGIN;

CREATE TABLE IF NOT EXISTS engagements (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name            TEXT NOT NULL,
    asset           TEXT NOT NULL,                   -- e.g. 'drug:cagrisema'
    sponsor         TEXT,                            -- e.g. 'novo_nordisk'
    situation       TEXT NOT NULL
                    CHECK (situation IN ('launch','defense','lcm')),
    workshop_date   TIMESTAMPTZ,
    stage           TEXT NOT NULL DEFAULT 'brief'
                    CHECK (stage IN ('brief','sources','dossier','synthesis','gaps','scenarios','workshop')),
    status          TEXT NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft','active','completed','archived')),
    scope           JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_by      TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    tenant_scope    TEXT,                            -- nullable = global
    CONSTRAINT engagements_name_nonempty
        CHECK (length(btrim(name)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_engagements_status
    ON engagements (status, workshop_date DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_engagements_situation
    ON engagements (situation);
CREATE INDEX IF NOT EXISTS idx_engagements_workshop_date
    ON engagements (workshop_date)
    WHERE workshop_date IS NOT NULL;

CREATE TABLE IF NOT EXISTS engagement_audit_log (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id   UUID NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    actor           TEXT NOT NULL,
    event_type      TEXT NOT NULL
                    CHECK (event_type IN ('created','stage_change','status_change','scope_change')),
    from_value      TEXT,
    to_value        TEXT NOT NULL,
    rationale       TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT engagement_audit_rationale_nonempty
        CHECK (length(btrim(rationale)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_engagement_audit_engagement
    ON engagement_audit_log (engagement_id, created_at DESC);

COMMENT ON TABLE engagements IS
    'Engagement-as-spine (v7 canon). Unit of work. 7-stage lifecycle FSM '
    'in services/engagement.py + CHECK constraints here for defence in '
    'depth. Z3.';
COMMENT ON TABLE engagement_audit_log IS
    'Append-only audit of stage/status/scope changes. Procurement-grade. Z3.';

COMMIT;
