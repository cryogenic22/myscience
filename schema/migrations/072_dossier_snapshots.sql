-- Migration 072: dossier_snapshots (Dossier Knowledge Base — KB1)
--
-- Today's dossier (services/dossier.py) is a read-only view assembled on
-- every page load — never persisted, never versioned, never fed to the
-- war-game. That makes it impossible to (a) reuse a dossier across
-- engagements, (b) compare how the picture changed over time, or (c) hand a
-- frozen, evidence-grounded read to the simulation. This table is the
-- substrate for the Dossier Knowledge Base: a persisted, VERSIONED,
-- 8-domain dossier assembled FROM the facts ledger / signals / evidence.
--
-- The payload (`domains`) is the list[DomainView] the EngagementDossierPage
-- (F7) renders directly — 8 ZS domains, each with typed facts (fact_class
-- ◇/◆/◈/✦), a coverage state (complete/in_progress/gap), and optional
-- visuals. Storing the rendered shape keeps assembly server-side and the
-- UI dumb.
--
-- Versioning is append-only: each assemble writes version = prev+1 and
-- points the prior latest at the new row via superseded_by. get_latest =
-- the row with superseded_by IS NULL (equivalently MAX(version)). This
-- gives the "knowledge base of dossiers" — history + drift, not a single
-- mutable blob.

BEGIN;

CREATE TABLE IF NOT EXISTS dossier_snapshots (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id   UUID NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    focal_asset     TEXT NOT NULL,                  -- e.g. 'drug:wegovy'
    version         INTEGER NOT NULL,               -- 1-based, per engagement
    domains         JSONB NOT NULL DEFAULT '[]'::jsonb,  -- list[DomainView]
    coverage_score  REAL NOT NULL DEFAULT 0
                    CHECK (coverage_score >= 0 AND coverage_score <= 1),
    fact_count      INTEGER NOT NULL DEFAULT 0,
    assembled_by    TEXT NOT NULL,
    assembled_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Supersession chain (append-only versioning). NULL = current head.
    superseded_by   UUID REFERENCES dossier_snapshots(id),
    tenant_scope    TEXT,                           -- null = global
    CONSTRAINT dossier_snapshots_version_positive CHECK (version >= 1),
    CONSTRAINT dossier_snapshots_engagement_version_uniq
        UNIQUE (engagement_id, version)
);

-- Latest-version lookups + version listing (both order by version DESC).
CREATE INDEX IF NOT EXISTS idx_dossier_snapshots_engagement
    ON dossier_snapshots (engagement_id, version DESC);
-- Fast "current head" filter.
CREATE INDEX IF NOT EXISTS idx_dossier_snapshots_head
    ON dossier_snapshots (engagement_id)
    WHERE superseded_by IS NULL;

COMMENT ON TABLE dossier_snapshots IS
    'Persisted, versioned 8-domain dossier assembled from the facts ledger / '
    'signals / evidence. The Dossier Knowledge Base (KB1). domains JSONB is '
    'the list[DomainView] the EngagementDossierPage renders. Append-only '
    'versioning via superseded_by.';

COMMIT;
