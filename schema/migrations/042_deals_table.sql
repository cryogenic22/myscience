-- Migration 042: deals table (skeleton)
--
-- SPEC-016 §7 swimlane A1, task A1.6.
--
-- Per CI design + comp_intel_2.md §2 KBQ 10 deep-dive: deal_types is
-- composite (a deal can be license-in + co-development + option), so it's
-- TEXT[], not a single enum. Acquirer/target side-of-deal direction matters
-- — separate FK columns (not just parties[]). Termination is a high-impact
-- event of its own, captured by status='terminated' with an end_date.
--
-- Populated by A2.2 (8-K Item 1.01 parser). Read by Deal Tracker (I7) and
-- the I3 quarterly briefing composer.

BEGIN;

CREATE TABLE IF NOT EXISTS deals (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Type — composite (multiple types per deal allowed)
    deal_types              TEXT[] NOT NULL,

    -- Parties — direction matters. acquirer_id+target_id for M&A;
    -- licensor_id+licensee_id for licenses. Both pairs may be set on
    -- composite deals (e.g. acquisition + license-back).
    acquirer_id             UUID REFERENCES companies(id),
    target_id               UUID REFERENCES companies(id),
    licensor_id             UUID REFERENCES companies(id),
    licensee_id             UUID REFERENCES companies(id),

    -- Subject
    subject_drug_ids        UUID[] NOT NULL DEFAULT '{}',
    subject_indications     JSONB NOT NULL DEFAULT '[]'::jsonb,
                            -- array of { mesh_id?, name, snomed_id? }
    geography               TEXT,
                            -- ISO country code or "WW" / "ROW" / "EU5"

    -- Financial terms
    currency                TEXT NOT NULL DEFAULT 'USD',
    upfront_value_usd       NUMERIC(18, 2),
    upfront_disclosed       BOOLEAN NOT NULL DEFAULT TRUE,
    milestones_total_usd    NUMERIC(18, 2),
    milestones_breakdown    JSONB,
                            -- [ { type: regulatory|commercial|development,
                            --     max_value: number } ]
    royalty_terms           JSONB,
                            -- { tier_count, range_low_pct, range_high_pct }
                            -- or null/undisclosed
    total_potential_usd     NUMERIC(18, 2),
    equity_component        BOOLEAN NOT NULL DEFAULT FALSE,

    -- Lifecycle
    announced_date          DATE,
    closing_date            DATE,
    end_date                DATE,
                            -- non-null when status='terminated'
    status                  TEXT NOT NULL DEFAULT 'announced',

    -- Provenance
    source_document_id      UUID,    -- references source_records (no FK to keep loose)
    press_release_url       TEXT,
    filing_url              TEXT,    -- 8-K Item 1.01 SEC URL when applicable

    -- Free-text notes (from extraction)
    notes                   TEXT,

    -- Audit
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- ============================================================
    -- Constraints
    -- ============================================================

    -- Status enum
    CONSTRAINT deals_status_check
        CHECK (status IN ('announced', 'closed', 'terminated')),

    -- deal_types members must come from the agreed set
    CONSTRAINT deals_deal_types_check
        CHECK (deal_types <@ ARRAY[
            'acquisition',
            'asset_purchase',
            'license_in',
            'license_out',
            'collaboration',
            'option',
            'co_promotion',
            'co_development',
            'royalty_monetisation'
        ]::TEXT[]
        AND cardinality(deal_types) >= 1),

    -- Sanity: upfront + max_milestones <= total_potential when total disclosed.
    -- (NULLs short-circuit as TRUE per SQL three-valued logic — we only
    -- enforce when all three are present.)
    CONSTRAINT deals_terms_sanity_check
        CHECK (
            upfront_value_usd IS NULL
            OR milestones_total_usd IS NULL
            OR total_potential_usd IS NULL
            OR upfront_value_usd + milestones_total_usd
               <= total_potential_usd * 1.05  -- 5% slack for rounding
        ),

    -- Termination paired with end_date
    CONSTRAINT deals_termination_paired_check
        CHECK (
            status != 'terminated' OR end_date IS NOT NULL
        )
);

COMMENT ON TABLE deals IS
    'M&A, asset purchases, licenses, collaborations, options, co-promotion, '
    'co-development, royalty monetisations. Populated by A2.2 (8-K Item 1.01 '
    'parser); read by Deal Tracker (I7). deal_types is composite — one deal '
    'can carry multiple types.';

COMMENT ON COLUMN deals.deal_types IS
    'Composite array. Members: acquisition | asset_purchase | license_in | '
    'license_out | collaboration | option | co_promotion | co_development | '
    'royalty_monetisation. Cardinality >= 1.';

COMMENT ON COLUMN deals.upfront_disclosed IS
    'False when the press release says "undisclosed terms". UI must show '
    '"terms undisclosed" prominently — never imply small deal by absent '
    'number per CI design soft-rule.';

COMMENT ON COLUMN deals.subject_indications IS
    'Array of indication descriptors: { mesh_id?, name, snomed_id? }. '
    'mesh_id resolves via existing therapeutic_areas table when possible.';

-- ============================================================
-- Indexes
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_deals_acquirer
    ON deals (acquirer_id) WHERE acquirer_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_deals_target
    ON deals (target_id) WHERE target_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_deals_licensor
    ON deals (licensor_id) WHERE licensor_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_deals_licensee
    ON deals (licensee_id) WHERE licensee_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_deals_announced
    ON deals (announced_date DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_deals_status
    ON deals (status);

CREATE INDEX IF NOT EXISTS idx_deals_deal_types
    ON deals USING GIN (deal_types);

CREATE INDEX IF NOT EXISTS idx_deals_subject_drugs
    ON deals USING GIN (subject_drug_ids);

COMMIT;
