-- BE-9 · Adversary digital twins.
--
-- PB-502 renders a "posterior side panel" with 6 adversary twins
-- (Pfizer / Lilly / AZN / FDA / Payer / KOL) per the diabetes/obesity
-- TA's seed roster. Each twin carries a behavioural posterior
-- (aggressive / defensive / cash_constrained mixture) plus a log of
-- the 5 most recent evidence updates that shifted the posterior.

CREATE TABLE IF NOT EXISTS adversary_twins (
    twin_id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 200),
    kind             TEXT NOT NULL
                     CHECK (kind IN ('competitor','regulator','payer','kol')),
    posterior        JSONB NOT NULL
                     DEFAULT '{"aggressive":0.5,"defensive":0.3,"cash_constrained":0.2}'::jsonb,
    last_updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    evidence_log     JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (kind, name)
);

CREATE INDEX IF NOT EXISTS idx_adversary_twins_kind
    ON adversary_twins (kind);

-- Seed the diabetes/obesity TA roster.
INSERT INTO adversary_twins (name, kind, posterior)
VALUES
    ('Pfizer',  'competitor', '{"aggressive":0.55,"defensive":0.25,"cash_constrained":0.20}'::jsonb),
    ('Lilly',   'competitor', '{"aggressive":0.70,"defensive":0.20,"cash_constrained":0.10}'::jsonb),
    ('AstraZeneca', 'competitor', '{"aggressive":0.40,"defensive":0.40,"cash_constrained":0.20}'::jsonb),
    ('FDA',     'regulator',  '{"aggressive":0.30,"defensive":0.55,"cash_constrained":0.15}'::jsonb),
    ('Payer',   'payer',      '{"aggressive":0.20,"defensive":0.50,"cash_constrained":0.30}'::jsonb),
    ('KOL Panel', 'kol',      '{"aggressive":0.50,"defensive":0.35,"cash_constrained":0.15}'::jsonb)
ON CONFLICT (kind, name) DO NOTHING;
