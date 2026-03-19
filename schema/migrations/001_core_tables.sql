-- 001_core_tables.sql
-- Core tables for Market-Zero knowledge layer.
-- Every table includes provenance columns (source_api, source_url, retrieved_at).

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- for fuzzy text matching

-- ============================================================
-- ONTOLOGY TABLES (populated from MeSH, not hand-typed)
-- ============================================================

CREATE TABLE therapeutic_areas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    mesh_id TEXT UNIQUE,
    tree_numbers TEXT[],
    parent_mesh_id TEXT,
    scope_note TEXT,
    scope_note_embedding VECTOR(1536),
    source_api TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE mechanisms_of_action (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    mesh_id TEXT UNIQUE,
    tree_numbers TEXT[],
    parent_mesh_id TEXT,
    scope_note TEXT,
    source_api TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- ENTITY TABLES
-- ============================================================

CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,
    ticker TEXT,
    cik TEXT,
    region TEXT,
    market_cap_tier TEXT,
    strategy_embedding VECTOR(1536),
    source_api TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE drugs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id),
    brand_name TEXT,
    generic_name TEXT NOT NULL,
    nda_number TEXT,
    therapeutic_area_id UUID REFERENCES therapeutic_areas(id),
    mechanism_id UUID REFERENCES mechanisms_of_action(id),
    approval_date DATE,
    patent_expiry_date DATE,
    patent_number TEXT,
    supply_status TEXT DEFAULT 'NORMAL',
    molecule_embedding VECTOR(1536),
    source_api TEXT NOT NULL,
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE clinical_trials (
    id TEXT PRIMARY KEY,
    drug_id UUID REFERENCES drugs(id),
    sponsor_name TEXT,
    status TEXT NOT NULL,
    phase TEXT,
    conditions TEXT[],
    interventions TEXT[],
    start_date DATE,
    completion_date DATE,
    enrollment_target INTEGER,
    actual_enrollment INTEGER,
    failure_reason TEXT,
    detailed_description TEXT,
    protocol_embedding VECTOR(1536),
    source_api TEXT NOT NULL DEFAULT 'clinicaltrials_gov_v2',
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE market_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_id UUID REFERENCES drugs(id),
    event_type TEXT NOT NULL,
    event_date DATE NOT NULL,
    description TEXT,
    impact_score FLOAT,
    source_api TEXT NOT NULL,
    source_url TEXT NOT NULL,
    etl_run_id UUID,  -- FK added after etl_runs table exists
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE pubmed_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pmid TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    abstract TEXT,
    authors TEXT[],
    journal TEXT,
    publication_date DATE,
    mesh_terms TEXT[],
    mesh_descriptor_ids TEXT[],
    drug_id UUID REFERENCES drugs(id),
    abstract_embedding VECTOR(1536),
    source_api TEXT NOT NULL DEFAULT 'pubmed_efetch',
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL,
    entity_id UUID NOT NULL,
    source_type TEXT NOT NULL,
    source_reference TEXT NOT NULL,
    source_url TEXT NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding VECTOR(1536),
    etl_run_id UUID,
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ============================================================
-- ETL TRACKING
-- ============================================================

CREATE TABLE etl_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name TEXT NOT NULL,
    api_endpoint TEXT NOT NULL,
    query_params JSONB,
    status TEXT NOT NULL DEFAULT 'RUNNING',
    records_processed INTEGER DEFAULT 0,
    records_inserted INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMP
);

-- Add FK from market_events and knowledge_chunks to etl_runs
ALTER TABLE market_events
    ADD CONSTRAINT fk_market_events_etl_run
    FOREIGN KEY (etl_run_id) REFERENCES etl_runs(id);

ALTER TABLE knowledge_chunks
    ADD CONSTRAINT fk_knowledge_chunks_etl_run
    FOREIGN KEY (etl_run_id) REFERENCES etl_runs(id);

-- ============================================================
-- INDEXES
-- ============================================================

-- Ontology
CREATE INDEX idx_ta_mesh ON therapeutic_areas(mesh_id);
CREATE INDEX idx_moa_mesh ON mechanisms_of_action(mesh_id);

-- Entities
CREATE INDEX idx_companies_ticker ON companies(ticker);
CREATE INDEX idx_companies_cik ON companies(cik);
CREATE INDEX idx_companies_name_trgm ON companies USING gin(name gin_trgm_ops);

CREATE INDEX idx_drugs_generic ON drugs(generic_name);
CREATE INDEX idx_drugs_nda ON drugs(nda_number);
CREATE INDEX idx_drugs_ta ON drugs(therapeutic_area_id);
CREATE INDEX idx_drugs_mechanism ON drugs(mechanism_id);
CREATE INDEX idx_drugs_company ON drugs(company_id);

CREATE INDEX idx_trials_status ON clinical_trials(status);
CREATE INDEX idx_trials_phase ON clinical_trials(phase);
CREATE INDEX idx_trials_sponsor_trgm ON clinical_trials USING gin(sponsor_name gin_trgm_ops);

CREATE INDEX idx_events_type ON market_events(event_type);
CREATE INDEX idx_events_date ON market_events(event_date DESC);
CREATE INDEX idx_events_drug ON market_events(drug_id);
CREATE INDEX idx_events_etl ON market_events(etl_run_id);

CREATE INDEX idx_pubmed_pmid ON pubmed_articles(pmid);
CREATE INDEX idx_pubmed_drug ON pubmed_articles(drug_id);
CREATE INDEX idx_pubmed_date ON pubmed_articles(publication_date DESC);

CREATE INDEX idx_chunks_entity ON knowledge_chunks(entity_type, entity_id);
CREATE INDEX idx_chunks_source ON knowledge_chunks(source_type);
CREATE INDEX idx_chunks_etl ON knowledge_chunks(etl_run_id);

CREATE INDEX idx_etl_source ON etl_runs(source_name, started_at DESC);
CREATE INDEX idx_etl_status ON etl_runs(status);

-- Vector indexes (HNSW for approximate nearest neighbor)
CREATE INDEX idx_chunks_embedding ON knowledge_chunks
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_drugs_embedding ON drugs
    USING hnsw (molecule_embedding vector_cosine_ops);
CREATE INDEX idx_pubmed_embedding ON pubmed_articles
    USING hnsw (abstract_embedding vector_cosine_ops);
CREATE INDEX idx_trials_embedding ON clinical_trials
    USING hnsw (protocol_embedding vector_cosine_ops);
