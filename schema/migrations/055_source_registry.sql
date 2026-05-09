-- SPEC_027 — Source Registry + 5-dim quality scoring.
-- Per-source identity, license posture, and append-only quality history.

-- ─── sources ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sources (
    source_id            TEXT PRIMARY KEY CHECK (char_length(source_id) BETWEEN 1 AND 100),
    display_name         TEXT NOT NULL CHECK (char_length(display_name) BETWEEN 1 AND 200),
    tier                 INTEGER NOT NULL CHECK (tier BETWEEN 1 AND 4),
    kind                 TEXT NOT NULL DEFAULT 'free' CHECK (kind IN ('free','paid','internal')),
    base_url             TEXT,
    description          TEXT,
    active               BOOLEAN NOT NULL DEFAULT TRUE,
    license_status       TEXT NOT NULL DEFAULT 'not_applicable'
                         CHECK (license_status IN ('active','expired','rate_limited','not_applicable')),
    license_renewal_at   TIMESTAMPTZ,
    rate_limit_per_min   INTEGER CHECK (rate_limit_per_min IS NULL OR rate_limit_per_min > 0),
    usage_profile        JSONB NOT NULL DEFAULT '{}'::jsonb,
    latest_quality_id    UUID,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_sources_tier
    ON sources(tier)
    WHERE active = TRUE;

CREATE INDEX IF NOT EXISTS idx_sources_kind_active
    ON sources(kind, active);

-- ─── source_quality_history ───────────────────────────────────────────
-- Append-only time series of per-source quality scores. Latest row is
-- referenced by sources.latest_quality_id for fast lookup.
CREATE TABLE IF NOT EXISTS source_quality_history (
    quality_id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id             TEXT NOT NULL REFERENCES sources(source_id) ON DELETE CASCADE,
    computed_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    coverage              REAL CHECK (coverage IS NULL OR (coverage >= 0 AND coverage <= 1)),
    latency_p95_ms        INTEGER CHECK (latency_p95_ms IS NULL OR latency_p95_ms >= 0),
    latency_score         REAL CHECK (latency_score IS NULL OR (latency_score >= 0 AND latency_score <= 1)),
    predictive_accuracy   REAL CHECK (predictive_accuracy IS NULL OR (predictive_accuracy >= 0 AND predictive_accuracy <= 1)),
    stability_score       REAL CHECK (stability_score IS NULL OR (stability_score >= 0 AND stability_score <= 1)),
    license_health_score  REAL CHECK (license_health_score IS NULL OR (license_health_score >= 0 AND license_health_score <= 1)),
    overall_score         REAL CHECK (overall_score IS NULL OR (overall_score >= 0 AND overall_score <= 1)),
    inputs_jsonb          JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_sqh_source_time
    ON source_quality_history (source_id, computed_at DESC);

-- Append-only by convention: no DELETE/UPDATE triggers (lighter touch
-- than evidence_records). The service only ever inserts.

-- updated_at trigger for sources
CREATE OR REPLACE FUNCTION sources_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sources_updated_at ON sources;
CREATE TRIGGER trg_sources_updated_at
    BEFORE UPDATE ON sources
    FOR EACH ROW EXECUTE FUNCTION sources_set_updated_at();
