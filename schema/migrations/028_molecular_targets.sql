-- Migration 028: Molecular targets and bioactivities
-- Enables molecular intelligence layer: drug-target binding, genetic evidence, selectivity

CREATE TABLE IF NOT EXISTS molecular_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    gene_symbol TEXT,
    ensembl_id TEXT,
    chembl_id TEXT,
    uniprot_id TEXT,
    target_type TEXT NOT NULL DEFAULT 'SINGLE PROTEIN',
    organism TEXT DEFAULT 'Homo sapiens',
    biotype TEXT,
    tractability JSONB,
    disease_associations JSONB,
    target_embedding VECTOR(1536),
    source_api TEXT NOT NULL,
    source_url TEXT,
    retrieved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    record_status TEXT DEFAULT 'active',
    quality_score FLOAT
);

CREATE UNIQUE INDEX IF NOT EXISTS uix_target_ensembl ON molecular_targets(ensembl_id) WHERE ensembl_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uix_target_chembl ON molecular_targets(chembl_id) WHERE chembl_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uix_target_gene ON molecular_targets(gene_symbol) WHERE gene_symbol IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_target_name ON molecular_targets(name);

CREATE TABLE IF NOT EXISTS bioactivities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_id UUID REFERENCES drugs(id),
    target_id UUID REFERENCES molecular_targets(id),
    chembl_activity_id TEXT,
    activity_type TEXT NOT NULL,
    activity_value DOUBLE PRECISION,
    activity_units TEXT,
    activity_relation TEXT DEFAULT '=',
    pchembl_value DOUBLE PRECISION,
    assay_type TEXT,
    assay_description TEXT,
    source_api TEXT NOT NULL DEFAULT 'chembl',
    source_url TEXT,
    retrieved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_bioactivity_drug ON bioactivities(drug_id);
CREATE INDEX IF NOT EXISTS ix_bioactivity_target ON bioactivities(target_id);
CREATE INDEX IF NOT EXISTS ix_bioactivity_pchembl ON bioactivities(pchembl_value DESC NULLS LAST);
CREATE UNIQUE INDEX IF NOT EXISTS uix_bioactivity_chembl ON bioactivities(chembl_activity_id) WHERE chembl_activity_id IS NOT NULL;

-- Extend drugs table for molecular identity from PubChem
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS pubchem_cid TEXT;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS canonical_smiles TEXT;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS inchi TEXT;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS inchi_key TEXT;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS molecular_formula TEXT;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS molecular_weight DOUBLE PRECISION;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS xlogp DOUBLE PRECISION;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS tpsa DOUBLE PRECISION;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS hbd INTEGER;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS hba INTEGER;

CREATE UNIQUE INDEX IF NOT EXISTS uix_drug_pubchem ON drugs(pubchem_cid) WHERE pubchem_cid IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uix_drug_inchi_key ON drugs(inchi_key) WHERE inchi_key IS NOT NULL;

-- Update v_entity_labels to include molecular_target and bioactivity
CREATE OR REPLACE VIEW v_entity_labels AS
SELECT id::text AS entity_id, 'drug' AS entity_type,
       COALESCE(brand_name || ' (' || generic_name || ')', generic_name) AS label
FROM drugs
UNION ALL
SELECT id::text, 'company', name FROM companies
UNION ALL
SELECT id::text, 'trial',
       COALESCE(official_title, 'Trial ' || id) FROM clinical_trials
UNION ALL
SELECT id::text, 'literature', title FROM pubmed_articles
UNION ALL
SELECT id::text, 'event', LEFT(description, 120) FROM market_events
UNION ALL
SELECT id::text, 'therapeutic_area', name FROM therapeutic_areas
UNION ALL
SELECT id::text, 'mechanism', name FROM mechanisms_of_action
UNION ALL
SELECT id::text, 'trial_location',
       COALESCE(facility_name, '') || CASE WHEN city IS NOT NULL THEN ', ' || city ELSE '' END
       || CASE WHEN country IS NOT NULL THEN ', ' || country ELSE '' END
FROM trial_locations
UNION ALL
SELECT id::text, 'investigator',
       COALESCE(name, '') || CASE WHEN affiliation IS NOT NULL THEN ' (' || LEFT(affiliation, 50) || ')' ELSE '' END
FROM investigators
UNION ALL
SELECT id::text, 'trial_outcome',
       COALESCE(outcome_type || ': ', '') || COALESCE(measure, '')
       || CASE WHEN time_frame IS NOT NULL THEN ' [' || LEFT(time_frame, 40) || ']' ELSE '' END
FROM trial_outcomes
UNION ALL
SELECT id::text, 'adverse_event',
       COALESCE(drug_name, '') || ' - ' || COALESCE(reaction, '') || ' (' || COALESCE(outcome, '') || ')'
FROM adverse_events
UNION ALL
SELECT id::text, 'patent',
       COALESCE(patent_number, '') || CASE WHEN patent_expiry_date IS NOT NULL THEN ' (exp ' || patent_expiry_date::text || ')' ELSE '' END
FROM patents
UNION ALL
SELECT id::text, 'molecular_target',
       COALESCE(gene_symbol || ' - ', '') || name
FROM molecular_targets
UNION ALL
SELECT id::text, 'bioactivity',
       COALESCE(activity_type, '') || ' = ' || COALESCE(activity_value::text, '?') || ' ' || COALESCE(activity_units, '')
FROM bioactivities;
