-- Migration 030: Concept Registry table
-- Moves the 15 hardcoded pharma analytical concepts to database-backed storage.
-- The in-memory ConceptRegistry loads from this table on init (with cache).

CREATE TABLE IF NOT EXISTS concepts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    computation_path TEXT NOT NULL DEFAULT '',
    intents TEXT[] NOT NULL DEFAULT '{}',
    entity_types TEXT[] NOT NULL DEFAULT '{}',
    staleness_days INTEGER NOT NULL DEFAULT 7,
    weight REAL NOT NULL DEFAULT 1.0,
    active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_concepts_active ON concepts (active) WHERE active = true;
CREATE INDEX idx_concepts_name ON concepts (name);

-- Seed the 15 pharma domain concepts (same as hardcoded in concept_registry.py)

INSERT INTO concepts (name, description, computation_path, intents, entity_types, staleness_days, weight) VALUES
(
    'pipeline_strength',
    'Weighted count of active clinical trials by phase, with later phases scored higher (P3=4, P2=2, P1=1).',
    'services.metrics.PharmaMetrics.drug_pipeline_strength',
    ARRAY['landscape', 'pipeline', 'dossier'],
    ARRAY['drug', 'therapeutic_area'],
    7,
    0.95
),
(
    'competitive_landscape',
    'Market structure analysis: competitor count, concentration, and positioning within a therapeutic area.',
    'services.metrics.PharmaMetrics.competitive_landscape',
    ARRAY['landscape', 'compare'],
    ARRAY['drug', 'company', 'therapeutic_area'],
    14,
    0.90
),
(
    'trial_success_rate',
    'Historical phase transition success rate for a drug or therapeutic area, based on trial status progression.',
    'services.metrics.PharmaMetrics.trial_success_rate',
    ARRAY['pipeline', 'dossier'],
    ARRAY['drug', 'trial', 'therapeutic_area'],
    30,
    0.85
),
(
    'evidence_density',
    'Publication volume and recency across PubMed, PMC, and clinical trial results for an entity.',
    'services.metrics.PharmaMetrics.evidence_density',
    ARRAY['dossier', 'general', 'compare'],
    ARRAY['drug', 'mechanism', 'therapeutic_area'],
    14,
    0.80
),
(
    'safety_signals',
    'Adverse event reports from FAERS, FDA shortages, and label warnings aggregated per drug.',
    'services.metrics.PharmaMetrics.evidence_density',
    ARRAY['dossier', 'pipeline', 'compare'],
    ARRAY['drug'],
    7,
    0.88
),
(
    'company_portfolio',
    'Breadth and depth of a company''s drug portfolio across therapeutic areas and development phases.',
    'services.metrics.PharmaMetrics.company_portfolio',
    ARRAY['portfolio', 'landscape', 'dossier'],
    ARRAY['company'],
    14,
    0.85
),
(
    'mechanism_coverage',
    'How many drugs target a given mechanism of action, and their distribution across development phases.',
    'services.graph.GraphTraversal.drugs_by_mechanism_class',
    ARRAY['landscape', 'dossier', 'general'],
    ARRAY['mechanism', 'drug'],
    14,
    0.75
),
(
    'patent_landscape',
    'Patent expiry timeline, exclusivity windows, and generic entry risk for a drug or company.',
    'services.graph.GraphTraversal.neighborhood',
    ARRAY['dossier', 'landscape'],
    ARRAY['drug', 'patent', 'company'],
    30,
    0.70
),
(
    'regulatory_status',
    'Current regulatory milestones: NDA filing, approval dates, supplemental indications, REMS.',
    'services.graph.GraphTraversal.entity_summary',
    ARRAY['dossier', 'pipeline'],
    ARRAY['drug'],
    7,
    0.82
),
(
    'therapeutic_area_depth',
    'Knowledge density for a therapeutic area: entity count, link density, trial count, publication volume.',
    'services.graph.GraphTraversal.entity_summary',
    ARRAY['landscape', 'general'],
    ARRAY['therapeutic_area'],
    14,
    0.70
),
(
    'clinical_endpoint_data',
    'Primary and secondary endpoint results from completed trials, including effect sizes and confidence intervals.',
    'services.search.HybridSearch.search',
    ARRAY['dossier', 'compare', 'pipeline'],
    ARRAY['drug', 'trial'],
    30,
    0.78
),
(
    'market_concentration',
    'Herfindahl-Hirschman Index (HHI) approximation for therapeutic area competitive intensity.',
    'services.metrics.PharmaMetrics.competitive_landscape',
    ARRAY['landscape'],
    ARRAY['therapeutic_area', 'company'],
    14,
    0.65
),
(
    'evidence_recency',
    'Median age of publications and trial updates, indicating how actively an entity is being studied.',
    'services.metrics.PharmaMetrics.evidence_density',
    ARRAY['dossier', 'general'],
    ARRAY['drug', 'mechanism', 'therapeutic_area'],
    14,
    0.60
),
(
    'entity_completeness',
    'Data quality score: percentage of recommended fields populated, link density, and source diversity.',
    'services.metrics.PharmaMetrics.evidence_density',
    ARRAY['general', 'dossier'],
    ARRAY['drug', 'company', 'trial', 'mechanism', 'therapeutic_area'],
    7,
    0.55
),
(
    'competitive_position',
    'A drug''s relative standing among competitors in the same therapeutic area, based on trial phase, evidence, and portfolio.',
    'services.metrics.PharmaMetrics.competitive_landscape',
    ARRAY['landscape', 'compare', 'dossier'],
    ARRAY['drug', 'company'],
    14,
    0.85
)
ON CONFLICT (name) DO NOTHING;
