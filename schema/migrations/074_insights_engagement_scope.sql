-- 074_insights_engagement_scope.sql
--
-- UX06 / PB-UX06 — scope synthesis insights to an engagement.
--
-- The insights + rejected_insights tables (migration 066) were global
-- (tenant_scope only). The engagement Synthesis stage derives insights from a
-- specific engagement's dossier snapshot, so we add an engagement_id (FK,
-- cascade) + dossier_snapshot_id provenance + an is_archived flag so re-deriving
-- archives the prior batch instead of deleting (append-only in spirit, matching
-- the scenarios table from migration 073).
--
-- All additive + idempotent: existing global rows keep engagement_id NULL.

ALTER TABLE insights
    ADD COLUMN IF NOT EXISTS engagement_id       UUID REFERENCES engagements(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS dossier_snapshot_id UUID,
    ADD COLUMN IF NOT EXISTS is_archived         BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE rejected_insights
    ADD COLUMN IF NOT EXISTS engagement_id UUID REFERENCES engagements(id) ON DELETE CASCADE,
    ADD COLUMN IF NOT EXISTS is_archived   BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_insights_engagement
    ON insights(engagement_id) WHERE engagement_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rejected_insights_engagement
    ON rejected_insights(engagement_id) WHERE engagement_id IS NOT NULL;
