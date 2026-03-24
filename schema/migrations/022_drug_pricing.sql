-- Migration 022: Drug pricing table for NADAC, AWP, WAC, GPRM price data.
-- Supports multi-country, multi-source pricing linked to drugs.

CREATE TABLE IF NOT EXISTS drug_pricing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_id UUID REFERENCES drugs(id),
    drug_name TEXT NOT NULL,
    ndc_code TEXT,
    price_type TEXT NOT NULL,        -- 'nadac', 'awp', 'wac', 'gprm'
    unit_price NUMERIC(12,4),
    unit TEXT,                        -- 'per unit', 'per tablet', 'per ml'
    currency TEXT DEFAULT 'USD',
    country TEXT DEFAULT 'US',
    source_api TEXT NOT NULL,
    source_url TEXT,
    effective_date DATE,
    retrieved_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pricing_drug ON drug_pricing(drug_id);
CREATE INDEX IF NOT EXISTS idx_pricing_ndc ON drug_pricing(ndc_code);
CREATE INDEX IF NOT EXISTS idx_pricing_date ON drug_pricing(effective_date DESC);
CREATE INDEX IF NOT EXISTS idx_pricing_country ON drug_pricing(country);
