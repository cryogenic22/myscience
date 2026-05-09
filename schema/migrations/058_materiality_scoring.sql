-- SPEC_031 — Factor-attributed materiality scoring.
-- Adds materiality_factors JSONB to signals (additive, back-compat) and
-- creates a singleton config for tunable weights + factor reference values.

-- ─── Augment signals (if it exists) ──────────────────────────────────
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'signals') THEN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
             WHERE table_name = 'signals'
               AND column_name = 'materiality_factors'
        ) THEN
            ALTER TABLE signals ADD COLUMN materiality_factors JSONB;
        END IF;
    END IF;
END $$;

-- ─── materiality_weight_config ───────────────────────────────────────
CREATE TABLE IF NOT EXISTS materiality_weight_config (
    config_id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    is_active                  BOOLEAN NOT NULL DEFAULT FALSE,
    weights_jsonb              JSONB NOT NULL,
    tier_values_jsonb          JSONB NOT NULL,
    claim_type_values_jsonb    JSONB NOT NULL,
    criticality_values_jsonb   JSONB NOT NULL,
    recency_half_life_days     REAL NOT NULL DEFAULT 30
                               CHECK (recency_half_life_days > 0 AND recency_half_life_days <= 3650),
    created_by_user_id         UUID,
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at                 TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- At most one active config row at a time
CREATE UNIQUE INDEX IF NOT EXISTS uq_materiality_active
    ON materiality_weight_config (is_active)
    WHERE is_active = TRUE;

-- updated_at trigger
CREATE OR REPLACE FUNCTION materiality_config_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_materiality_config_updated_at ON materiality_weight_config;
CREATE TRIGGER trg_materiality_config_updated_at
    BEFORE UPDATE ON materiality_weight_config
    FOR EACH ROW EXECUTE FUNCTION materiality_config_set_updated_at();

-- ─── Seed initial active config with documented defaults ─────────────
INSERT INTO materiality_weight_config (
    is_active, weights_jsonb, tier_values_jsonb,
    claim_type_values_jsonb, criticality_values_jsonb,
    recency_half_life_days
)
SELECT
    TRUE,
    '{"source_tier":0.30,"entity_criticality":0.30,"claim_type":0.25,"recency":0.15}'::jsonb,
    '{"1":1.0,"2":0.7,"3":0.4,"4":0.6}'::jsonb,
    '{"clinical_readout":1.0,"regulatory_action":0.95,"safety_signal":0.85,"pricing_change":0.8,"formulary_change":0.75,"pipeline_update":0.6,"earnings_commentary":0.4,"other":0.3}'::jsonb,
    '{"focal":1.0,"top_competitor":0.7,"watched":0.5,"other":0.2}'::jsonb,
    30
WHERE NOT EXISTS (
    SELECT 1 FROM materiality_weight_config WHERE is_active = TRUE
);
