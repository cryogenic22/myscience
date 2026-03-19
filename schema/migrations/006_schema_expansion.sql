-- 006_schema_expansion.sql
-- Schema expansion: 6 new tables + column additions to 4 existing tables.
-- Supports Orange Book, ClinicalTrials.gov, PubMed, SEC EDGAR connectors.

-- ============================================================
-- NEW TABLES
-- ============================================================

-- Patents: one drug can have many patents (formulation, composition, method of use)
CREATE TABLE patents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_id UUID REFERENCES drugs(id),
    patent_number TEXT NOT NULL,
    patent_expiry_date DATE,
    patent_type TEXT,  -- "Drug Substance", "Drug Product", "Method of Use"
    applicant_holder TEXT,
    source_api TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_patents_unique ON patents(drug_id, patent_number);
CREATE INDEX idx_patents_drug ON patents(drug_id);
CREATE INDEX idx_patents_expiry ON patents(patent_expiry_date);
CREATE INDEX idx_patents_number ON patents(patent_number);

-- Regulatory milestones: FDA approval timeline events
CREATE TABLE regulatory_milestones (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_id UUID REFERENCES drugs(id),
    submission_type TEXT,       -- ORIG, SUPPL, EFFICACY_SUPPL
    submission_number TEXT,
    submission_status TEXT,     -- AP (approved), TA (tentative approval)
    submission_status_date DATE,
    review_priority TEXT,       -- STANDARD, PRIORITY
    document_url TEXT,
    source_api TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE UNIQUE INDEX idx_milestones_unique ON regulatory_milestones(drug_id, submission_type, submission_number);
CREATE INDEX idx_milestones_drug ON regulatory_milestones(drug_id);
CREATE INDEX idx_milestones_date ON regulatory_milestones(submission_status_date DESC);

-- Trial outcomes: primary/secondary endpoints measured in clinical trials
CREATE TABLE trial_outcomes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id TEXT REFERENCES clinical_trials(id),
    outcome_type TEXT NOT NULL,  -- PRIMARY, SECONDARY, OTHER
    measure TEXT NOT NULL,
    time_frame TEXT,
    description TEXT,
    source_api TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_outcomes_trial ON trial_outcomes(trial_id);
CREATE INDEX idx_outcomes_type ON trial_outcomes(outcome_type);

-- Trial locations: geographic footprint of clinical trials
CREATE TABLE trial_locations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    trial_id TEXT REFERENCES clinical_trials(id),
    facility_name TEXT,
    city TEXT,
    state TEXT,
    country TEXT NOT NULL,
    status TEXT,  -- Recruiting, Active, Completed
    source_api TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_locations_trial ON trial_locations(trial_id);
CREATE INDEX idx_locations_country ON trial_locations(country);

-- Investigators: Key Opinion Leaders from trials and publications
CREATE TABLE investigators (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    affiliation TEXT,
    affiliation_country TEXT,
    orcid TEXT,
    source_api TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_investigators_name_trgm ON investigators USING gin(name gin_trgm_ops);
CREATE INDEX idx_investigators_orcid ON investigators(orcid) WHERE orcid IS NOT NULL;
CREATE INDEX idx_investigators_country ON investigators(affiliation_country);

-- Entity tags: user annotations on any entity
CREATE TABLE entity_tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    tag_name TEXT NOT NULL,
    tag_value TEXT,
    created_by TEXT DEFAULT 'system',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_tags_entity ON entity_tags(entity_type, entity_id);
CREATE INDEX idx_tags_name ON entity_tags(tag_name);
CREATE UNIQUE INDEX idx_tags_unique ON entity_tags(entity_type, entity_id, tag_name);

-- ============================================================
-- ALTER EXISTING TABLES
-- ============================================================

-- drugs: add FDA-specific columns
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS dosage_form TEXT;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS route TEXT;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS marketing_status TEXT;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS rxcui TEXT;

-- clinical_trials: add detail columns
ALTER TABLE clinical_trials ADD COLUMN IF NOT EXISTS study_type TEXT;
ALTER TABLE clinical_trials ADD COLUMN IF NOT EXISTS official_title TEXT;
ALTER TABLE clinical_trials ADD COLUMN IF NOT EXISTS eligibility_criteria TEXT;
ALTER TABLE clinical_trials ADD COLUMN IF NOT EXISTS primary_completion_date DATE;
ALTER TABLE clinical_trials ADD COLUMN IF NOT EXISTS collaborator_names TEXT[];

-- pubmed_articles: add enrichment columns
ALTER TABLE pubmed_articles ADD COLUMN IF NOT EXISTS doi TEXT;
ALTER TABLE pubmed_articles ADD COLUMN IF NOT EXISTS publication_type TEXT;
ALTER TABLE pubmed_articles ADD COLUMN IF NOT EXISTS grant_agencies TEXT[];
ALTER TABLE pubmed_articles ADD COLUMN IF NOT EXISTS keywords TEXT[];

-- companies: add EDGAR-specific columns
ALTER TABLE companies ADD COLUMN IF NOT EXISTS sic_code TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS country TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS fiscal_year_end TEXT;

-- ============================================================
-- ADDITIONAL INDEXES
-- ============================================================

CREATE INDEX IF NOT EXISTS idx_drugs_rxcui ON drugs(rxcui) WHERE rxcui IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_pubmed_doi ON pubmed_articles(doi) WHERE doi IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_companies_sic ON companies(sic_code) WHERE sic_code IS NOT NULL;
