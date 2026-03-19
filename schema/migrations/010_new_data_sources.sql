-- Migration 010: New data source tables
-- Adds tables for adverse events (FDA FAERS), drug labels (openFDA/DailyMed),
-- and PubMed Central full-text articles.

-- ============================================================
-- Adverse events from FDA FAERS
-- ============================================================
CREATE TABLE IF NOT EXISTS adverse_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    report_id TEXT UNIQUE NOT NULL,  -- FAERS safety_report_id
    drug_id UUID REFERENCES drugs(id),
    drug_name TEXT,
    reaction TEXT NOT NULL,
    reaction_meddra_pt TEXT,  -- MedDRA preferred term
    outcome TEXT,  -- hospitalization, death, disability, etc
    severity TEXT,  -- serious, not_serious
    report_date DATE,
    patient_age NUMERIC,
    patient_sex TEXT,
    reporter_type TEXT,  -- physician, pharmacist, consumer
    source_api TEXT DEFAULT 'openfda_faers',
    source_url TEXT,
    retrieved_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    content_hash TEXT,
    last_verified_at TIMESTAMPTZ,
    record_status TEXT DEFAULT 'active',
    quality_score NUMERIC
);
CREATE INDEX IF NOT EXISTS idx_ae_drug ON adverse_events(drug_id);
CREATE INDEX IF NOT EXISTS idx_ae_reaction ON adverse_events(reaction);
CREATE INDEX IF NOT EXISTS idx_ae_report_date ON adverse_events(report_date);

-- ============================================================
-- FDA Drug Labels from DailyMed/openFDA
-- ============================================================
CREATE TABLE IF NOT EXISTS drug_labels (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_id UUID REFERENCES drugs(id),
    drug_name TEXT,
    set_id TEXT UNIQUE,  -- DailyMed SPL set_id
    spl_version INTEGER,
    indications TEXT,
    contraindications TEXT,
    warnings_and_precautions TEXT,
    boxed_warning TEXT,
    dosage_and_administration TEXT,
    adverse_reactions_text TEXT,
    drug_interactions_text TEXT,
    clinical_pharmacology TEXT,
    effective_date DATE,
    manufacturer TEXT,
    label_embedding vector(1536),
    source_api TEXT DEFAULT 'openfda_labels',
    source_url TEXT,
    retrieved_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    content_hash TEXT,
    last_verified_at TIMESTAMPTZ,
    record_status TEXT DEFAULT 'active',
    quality_score NUMERIC
);
CREATE INDEX IF NOT EXISTS idx_label_drug ON drug_labels(drug_id);
CREATE INDEX IF NOT EXISTS idx_label_set_id ON drug_labels(set_id);

-- ============================================================
-- PubMed Central full-text articles
-- ============================================================
CREATE TABLE IF NOT EXISTS pmc_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pmc_id TEXT UNIQUE NOT NULL,  -- PMC ID (e.g., PMC1234567)
    pmid TEXT,  -- linked PubMed PMID
    pubmed_article_id UUID REFERENCES pubmed_articles(id),
    drug_id UUID REFERENCES drugs(id),
    title TEXT,
    full_text TEXT,
    article_type TEXT,  -- research-article, review, clinical-trial, protocol
    is_protocol BOOLEAN DEFAULT FALSE,
    is_systematic_review BOOLEAN DEFAULT FALSE,
    license TEXT,
    full_text_embedding vector(1536),
    source_api TEXT DEFAULT 'pmc',
    source_url TEXT,
    retrieved_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    content_hash TEXT,
    last_verified_at TIMESTAMPTZ,
    record_status TEXT DEFAULT 'active',
    quality_score NUMERIC
);
CREATE INDEX IF NOT EXISTS idx_pmc_pmid ON pmc_articles(pmid);
CREATE INDEX IF NOT EXISTS idx_pmc_drug ON pmc_articles(drug_id);
CREATE INDEX IF NOT EXISTS idx_pmc_protocol ON pmc_articles(is_protocol) WHERE is_protocol = TRUE;
CREATE INDEX IF NOT EXISTS idx_pmc_review ON pmc_articles(is_systematic_review) WHERE is_systematic_review = TRUE;
