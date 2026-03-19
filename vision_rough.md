# Market-Zero: Product Vision, PRD & Technical Specification

**Version:** 1.1 (Consolidated -- Real Data Mandate)
**Status:** Ready for Engineering Review
**Scope:** MVP -- Vertical Slice on Diabetes/Obesity (GLP-1)

---

## 0. Foundational Design Principle: No Fabricated Data

**Every data point displayed to the user must trace back to a real, verifiable external source.**

This is a non-negotiable constraint across the entire system:

- **No mock data in the product.** The database is populated exclusively by automated ETL pipelines pulling from real public APIs and filings. There are no hand-typed rows, no synthetic datasets, no placeholder values.
- **No hardcoded outputs.** The Risk Score, factor breakdown, citations, and LLM critique are all computed at query time from live database contents. Nothing is pre-scripted.
- **Full provenance chain.** Every row in the database records: which source it came from, the exact API call or URL that produced it, and the timestamp of retrieval. If a citation says "FDA Orange Book," a user (or auditor) can follow the `source_url` and `retrieved_at` fields back to the original document.
- **Ontology terms are sourced, not invented.** Drug classifications, mechanisms of action, and therapeutic area labels are derived from established taxonomies (MeSH, ATC, FDA Orange Book categories) -- not free-text invented by developers.
- **The UI is the only "demo" layer.** The frontend is a presentation layer over real data and real computation. It may be polished for demo purposes, but the data behind it is never faked.

**What this means for development:** The ETL pipelines are the *first* thing built and validated. The database must contain real, API-sourced data before any other component (scoring engine, agent, UI) is developed against it. If a pipeline cannot be completed in time, the scope of the demo narrows to what real data is available -- it never backfills with fabricated data.

---

## 1. Product Vision

**Market-Zero is a War-Gaming Engine for Pharmaceutical Strategy.**

Current AI tools (ChatGPT, Perplexity) act as passive librarians -- they retrieve text but lack judgment. Market-Zero acts as an active **Red Team**. It evaluates user strategies against real-world friction (regulatory barriers, competitor moves, supply chain disruptions) using a structured **Risk Scoring Engine** backed by live, source-verified market data, preventing costly strategic failures before they happen.

### What Market-Zero Is Not

- Not a chatbot or general-purpose search tool.
- Not a wrapper around an LLM. The scoring engine operates independently from the language model.
- Not a replacement for strategic judgment -- it is a stress-test for it.
- Not a prototype running on fake data. Every data point is real, sourced, and traceable.

---

## 2. Product Requirements Document (PRD)

### 2.1 Target User

**Primary:** Pharma Strategy Analyst / Associate Director -- the person who builds the slide deck, runs the competitive landscape analysis, and flags risks for the Brand Director.

**Secondary (aspirational):** Brand Director / Strategy Lead -- consumes the output, requests scenario variations.

The MVP interface is designed for the analyst workflow: structured input, detailed output, source traceability.

### 2.2 The Problem

Strategy teams spend weeks assembling disjointed data (PDFs, news, FDA logs, SEC filings) to evaluate launch viability. They routinely miss critical signals -- a competitor's silent supply chain move, an upcoming patent cliff, a resolved drug shortage that invalidates a compounding strategy -- until the strategy is already in motion.

They have plenty of **search** tools. They have zero **simulation** tools.

### 2.3 The Solution (MVP Scope)

A **Launch Simulator** for the GLP-1 (Diabetes/Obesity) market. The user defines a launch strategy through a structured form. The system returns:

1. A **Risk Score** (0.0 -- 10.0) representing aggregate strategic friction.
2. A **Risk Breakdown** identifying which specific factors drove the score.
3. **Source Citations** linking each risk factor to a specific document, filing, or data point.
4. A **Pivot Suggestion** when the score exceeds the critical threshold.

### 2.4 User Stories

| ID | User Story | Acceptance Criteria |
|----|-----------|---------------------|
| **US-1** | As an Analyst, I want to define my launch strategy (drug type, price point, target indication, launch market, compounding strategy) so the system can evaluate it. | Structured form with dropdowns and constrained inputs. Parsed into a `StrategyInput` JSON object. |
| **US-2** | As an Analyst, I want to see a Risk Score (0--10) with a visual severity indicator. | Dashboard displays a color-coded gauge (Green 0--4, Yellow 4--7, Red 7--10). |
| **US-3** | As an Analyst, I want to see exactly *which* risk factors contributed to my score and *how much* each one contributed. | Itemized risk breakdown table: factor name, weight triggered, source citation. |
| **US-4** | As an Analyst, I want to know the specific documents behind each risk flag (traceability). | Each risk factor links to a source (e.g., "Novo Nordisk 10-K 2024, Item 1A" or "FDA Shortage DB, retrieved 2025-02-14"). |
| **US-5** | As an Analyst, I want to modify one parameter and re-simulate to compare outcomes. | "Adjust & Re-run" action preserves prior results for side-by-side comparison. |
| **US-6** | As an Analyst, I want to see when the underlying data was last refreshed so I know if I'm working with stale information. | Data Freshness indicator on dashboard: per-source last-updated timestamps and overall staleness warning (amber if >48h, red if >7d). |
| **US-7** | As an Analyst, I want the system to pull daily updates from ClinicalTrials.gov and FDA Drug Shortages for the Diabetes/Obesity sector. | Automated ETL pipeline runs nightly. Health check endpoint confirms last successful run. Alert fires on two consecutive failures. |
| **US-8** | As an Admin, I want to manually trigger ingestion for a specific URL or filing. | `POST /admin/ingest` endpoint accepts a URL and source type, returns processing status. |
| **US-9** | As an Analyst, I want a natural-language explanation of why my strategy is risky when the score is high. | When Risk Score > 7.0, the system generates an LLM-authored critique grounded in the retrieved sources. No hallucinated citations. |
| **US-10** | As an Admin, I want to see pipeline health: what data is in the system, when it was last updated, and whether any jobs failed. | Admin dashboard shows: source counts, last ETL run per source, failure log. |

### 2.5 Out of Scope for MVP

- Multi-therapeutic-area support (Oncology, Vaccines, etc.).
- Real-time stock/financial data integration.
- Multi-user collaboration or access control.
- Learned/ML-based scoring model (deferred to Phase 2; see Section 5).

---

## 3. Technical Specification

### 3.1 Architecture Decision: PostgreSQL-Only for MVP

**Decision:** The MVP runs on **PostgreSQL 16 + pgvector** as the single data store. Neo4j is deferred to Phase 2.

**Rationale:**

| Concern | Postgres-Only (MVP) | Postgres + Neo4j (Phase 2) |
|---------|---------------------|---------------------------|
| Operational complexity | 1 container | 2+ services, sync logic |
| ACID consistency | Native | Requires distributed coordination |
| Join-based traversal (1--2 hops) | Standard SQL joins -- fast and simple | Overkill for this depth |
| Multi-hop traversal (3+ hops) | Expensive recursive CTEs | Native graph traversal -- justified here |
| Cost | Single managed instance | Additional Neo4j Aura instance |

**Phase 2 trigger:** Add Neo4j when a concrete user story requires 3+ hop relationship traversal (e.g., "Find competitors who share a manufacturer that failed an FDA audit in a different therapeutic area"). Until then, SQL joins cover all MVP queries.

### 3.2 Database Schema

Every table includes provenance columns (`source_api`, `source_url`, `retrieved_at`) so any row can be traced back to the exact API call or document that produced it. No row is inserted without these fields populated.

*file: `schema.sql`*

```sql
CREATE EXTENSION IF NOT EXISTS vector;

-- ONTOLOGY: Standardized terms from real taxonomies.
-- Populated by ETL from MeSH (NIH), ATC (WHO), and FDA Orange Book.
-- NOT free-text invented by developers.
CREATE TABLE therapeutic_areas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,          -- e.g., "Diabetes Mellitus, Type 2"
    mesh_id TEXT,                       -- MeSH descriptor ID (e.g., "D003924")
    source_api TEXT NOT NULL,           -- "mesh_api"
    source_url TEXT NOT NULL,           -- Full URL of the MeSH API call
    retrieved_at TIMESTAMP NOT NULL
);

CREATE TABLE mechanisms_of_action (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,          -- e.g., "Glucagon-Like Peptide-1 Receptor Agonists"
    mesh_id TEXT,                       -- MeSH pharmacological action ID
    atc_code TEXT,                      -- WHO ATC code (e.g., "A10BJ")
    source_api TEXT NOT NULL,           -- "mesh_api" or "who_atc"
    source_url TEXT NOT NULL,
    retrieved_at TIMESTAMP NOT NULL
);

-- COMPANIES
-- Seeded from SEC EDGAR XBRL company search, not hand-typed.
CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT UNIQUE NOT NULL,          -- e.g., "Novo Nordisk A/S"
    ticker TEXT,                        -- e.g., "NVO"
    cik TEXT,                           -- SEC Central Index Key for EDGAR lookups
    region TEXT,                        -- Derived from EDGAR registrant data
    market_cap_tier TEXT,               -- "Mega", "Large", "Mid"
    strategy_embedding VECTOR(1536),    -- Embedding of 10-K strategy section (from real filing)
    source_api TEXT NOT NULL,           -- "sec_edgar"
    source_url TEXT NOT NULL,           -- EDGAR company page URL
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- DRUGS
-- Seeded from FDA Orange Book API + Drugs@FDA.
-- Patent data comes from Orange Book patent listings, not manually entered.
CREATE TABLE drugs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id),
    brand_name TEXT,                    -- e.g., "Wegovy" (from Orange Book)
    generic_name TEXT NOT NULL,         -- e.g., "Semaglutide" (from Orange Book)
    nda_number TEXT,                    -- NDA/ANDA number from FDA (e.g., "215256")
    therapeutic_area_id UUID REFERENCES therapeutic_areas(id),
    mechanism_id UUID REFERENCES mechanisms_of_action(id),
    approval_date DATE,                -- From Drugs@FDA approval history
    patent_expiry_date DATE,            -- From Orange Book patent listings
    patent_number TEXT,                 -- e.g., "US10,806,797" (from Orange Book)
    supply_status TEXT DEFAULT 'NORMAL', -- Derived from FDA Shortage DB pipeline
    molecule_embedding VECTOR(1536),
    source_api TEXT NOT NULL,           -- "fda_orange_book" or "drugs_at_fda"
    source_url TEXT NOT NULL,           -- Exact API endpoint or page URL
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- CLINICAL TRIALS
-- Populated exclusively from ClinicalTrials.gov API v2.
CREATE TABLE clinical_trials (
    id TEXT PRIMARY KEY,                -- NCT Number (e.g., "NCT01234567") from API
    drug_id UUID REFERENCES drugs(id),
    sponsor_name TEXT,                  -- LeadSponsorName from API response
    status TEXT NOT NULL,               -- OverallStatus from API
    phase TEXT,                         -- Phase from API
    conditions TEXT[],                  -- Condition list from API
    start_date DATE,
    completion_date DATE,
    enrollment_target INTEGER,
    actual_enrollment INTEGER,
    failure_reason TEXT,                -- WhyStopped field from API (nullable)
    detailed_description TEXT,          -- Full description from API, used for embedding
    protocol_embedding VECTOR(1536),
    source_api TEXT NOT NULL DEFAULT 'clinicaltrials_gov_v2',
    source_url TEXT NOT NULL,           -- Full API request URL that returned this record
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- MARKET EVENTS (signals that affect risk scoring)
-- Each event is derived from a specific ETL pipeline run against a real source.
CREATE TABLE market_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_id UUID REFERENCES drugs(id),
    event_type TEXT NOT NULL,           -- "FDA_APPROVAL", "SHORTAGE_START",
                                        -- "SHORTAGE_RESOLVED", "PATENT_LAWSUIT",
                                        -- "PATENT_EXPIRY", "GUIDANCE_ISSUED"
    event_date DATE NOT NULL,
    description TEXT,
    impact_score FLOAT,                 -- -1.0 (negative) to 1.0 (positive)
    source_api TEXT NOT NULL,           -- Which pipeline produced this event
    source_url TEXT NOT NULL,           -- Direct link to the source document/page
    etl_run_id UUID REFERENCES etl_runs(id), -- Which ETL run created this row
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- KNOWLEDGE CHUNKS (RAG corpus)
-- Every chunk traces back to a real document with a retrievable URL.
CREATE TABLE knowledge_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entity_type TEXT NOT NULL,          -- "company", "drug", "trial"
    entity_id UUID NOT NULL,
    source_type TEXT NOT NULL,          -- "10-K", "10-Q", "FDA_LETTER", "PUBMED", "NEWS"
    source_reference TEXT NOT NULL,     -- e.g., "Item 1A, Risk Factors" or "PMID:38291034"
    source_url TEXT NOT NULL,           -- Direct URL to the source document
    chunk_text TEXT NOT NULL,
    embedding VECTOR(1536),
    etl_run_id UUID REFERENCES etl_runs(id),
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- PUBMED ARTICLES
-- Populated from PubMed E-Utilities API (efetch/esearch).
CREATE TABLE pubmed_articles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pmid TEXT UNIQUE NOT NULL,          -- PubMed ID (e.g., "38291034")
    title TEXT NOT NULL,
    abstract TEXT,
    authors TEXT[],
    journal TEXT,
    publication_date DATE,
    mesh_terms TEXT[],                  -- MeSH descriptors assigned by NLM
    drug_id UUID REFERENCES drugs(id),  -- Linked via MeSH term matching
    abstract_embedding VECTOR(1536),
    source_api TEXT NOT NULL DEFAULT 'pubmed_efetch',
    source_url TEXT NOT NULL,           -- e.g., "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id=38291034"
    retrieved_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ETL HEALTH TRACKING
-- Every pipeline run is recorded with full audit trail.
CREATE TABLE etl_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_name TEXT NOT NULL,          -- "clinical_trials_gov", "fda_shortages",
                                        -- "sec_edgar", "fda_orange_book",
                                        -- "pubmed", "mesh_ontology"
    api_endpoint TEXT NOT NULL,         -- The base URL/endpoint hit during this run
    query_params JSONB,                 -- The exact parameters sent to the API
    status TEXT NOT NULL,               -- "SUCCESS", "FAILURE", "RUNNING"
    records_processed INTEGER DEFAULT 0,
    records_inserted INTEGER DEFAULT 0,
    records_updated INTEGER DEFAULT 0,
    error_message TEXT,
    started_at TIMESTAMP NOT NULL,
    completed_at TIMESTAMP
);

-- INDEXES
CREATE INDEX idx_drugs_therapeutic ON drugs(therapeutic_area_id);
CREATE INDEX idx_events_type ON market_events(event_type);
CREATE INDEX idx_events_date ON market_events(event_date DESC);
CREATE INDEX idx_events_etl ON market_events(etl_run_id);
CREATE INDEX idx_chunks_entity ON knowledge_chunks(entity_type, entity_id);
CREATE INDEX idx_chunks_embedding ON knowledge_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX idx_drugs_embedding ON drugs USING hnsw (molecule_embedding vector_cosine_ops);
CREATE INDEX idx_pubmed_embedding ON pubmed_articles USING hnsw (abstract_embedding vector_cosine_ops);
CREATE INDEX idx_pubmed_drug ON pubmed_articles(drug_id);
CREATE INDEX idx_etl_source ON etl_runs(source_name, started_at DESC);
CREATE INDEX idx_trials_status ON clinical_trials(status);
CREATE INDEX idx_trials_phase ON clinical_trials(phase);
```

### 3.3 Risk Scoring Engine (Rule-Based, MVP)

For the MVP, the scoring engine is a **deterministic, weighted rule system** -- not a learned model. This is explainable, debuggable, and ships without training data dependencies.

#### Risk Factors

Each factor has a **weight** (0.0 -- 3.0) and a **trigger condition** evaluated against the current market state. The total Risk Score is the sum of triggered weights, capped at 10.0.

| # | Risk Factor | Weight | Trigger Condition | Data Source (real pipeline) | Provenance |
|---|------------|--------|-------------------|---------------------------|------------|
| R1 | Active Patent Block | 3.0 | `drugs.patent_expiry_date > strategy.launch_date` for target molecule | FDA Orange Book pipeline (Section 4.1) -> `drugs` table | `drugs.source_api`, `drugs.source_url` |
| R2 | Shortage Loophole Closed | 2.5 | `market_events.event_type = 'SHORTAGE_RESOLVED'` within last 90 days for target molecule | FDA Shortage scraper (Section 4.3) -> `market_events` table | `market_events.source_url`, `market_events.etl_run_id` |
| R3 | Competitor Phase 3 Active | 2.0 | Competitor has trial with `status = 'Recruiting'` AND `phase = 'Phase 3'` in same therapeutic area | ClinicalTrials.gov pipeline (Section 4.2) -> `clinical_trials` table | `clinical_trials.source_url` (API request URL) |
| R4 | Price Undercut Exposure | 1.5 | `strategy.price < competitor.price * 0.7` AND competitor has established market share | Cross-reference `drugs` (Orange Book) + `knowledge_chunks` (SEC filings for pricing data) | `knowledge_chunks.source_url` |
| R5 | Regulatory Headwind | 1.5 | `market_events.event_type = 'GUIDANCE_ISSUED'` within last 180 days for therapeutic area | FDA Shortage/Guidance scraper (Section 4.3) -> `market_events` table | `market_events.source_url` (FDA page URL) |
| R6 | Supply Chain Concentration | 1.0 | Manufacturer mentioned in 2+ companies' 10-K filings (extracted from `knowledge_chunks`) | SEC EDGAR pipeline (Section 4.4) -> `knowledge_chunks` table | `knowledge_chunks.source_url` (EDGAR filing URL) |
| R7 | Litigation Overhang | 1.0 | Active `PATENT_LAWSUIT` event in last 365 days involving target molecule | SEC EDGAR pipeline (Section 4.4) -> `market_events` table | `market_events.source_url` |
| R8 | Failed Precedent | 1.0 | Terminated trial for same mechanism of action in last 3 years, corroborated by PubMed adverse event literature | ClinicalTrials.gov (Section 4.2) + PubMed (Section 4.5) -> `clinical_trials` + `pubmed_articles` | `clinical_trials.source_url`, `pubmed_articles.source_url` |

#### Scoring Logic (Pseudocode)

```python
def calculate_risk_score(strategy: StrategyInput, market: MarketState) -> RiskResult:
    triggered = []

    for factor in RISK_FACTORS:
        if factor.evaluate(strategy, market):
            triggered.append({
                "factor": factor.name,
                "weight": factor.weight,
                "explanation": factor.explain(strategy, market),
                "sources": factor.get_sources(strategy, market)
            })

    raw_score = sum(t["weight"] for t in triggered)
    capped_score = min(raw_score, 10.0)

    return RiskResult(
        score=capped_score,
        triggered_factors=triggered,
        data_freshness=market.get_freshness_report()
    )
```

Each risk factor's `explain()` method returns a human-readable sentence with a specific citation **derived from the database row's provenance fields.** The patent number, expiry date, and retrieval timestamp are read from `drugs.patent_number`, `drugs.patent_expiry_date`, and `drugs.retrieved_at` -- never hardcoded. Example output:

> **R1 triggered (3.0):** "Semaglutide is protected by patent {drugs.patent_number} (expiry: {drugs.patent_expiry_date}). Launching before expiry exposes you to injunction risk. Source: FDA Orange Book ({drugs.source_url}), retrieved {drugs.retrieved_at}."

#### Phase 2: Learned Scoring Model

Once the MVP is live and generating user interaction data, the rule-based engine will be augmented (not replaced) by a learned **Energy-Based Model (EBM)**:

- **Architecture:** PyTorch MLP with bilinear interaction layer (not raw concatenation) between strategy and market state embeddings.
- **Training data:** Real user simulations + outcomes (requires 500+ labeled examples for meaningful generalization).
- **Deployment:** Runs alongside the rule engine. The UI shows both scores during a calibration period. The learned model only replaces the rule engine after demonstrating superior precision on a held-out eval set.
- **Attribution:** Integrated gradient or SHAP-based attribution so the EBM contributes to explanations, not just scores.

### 3.4 Data Schema: The MarketSnapshot Object

The `MarketSnapshot` is **assembled at query time by joining live database tables** -- it is never cached, pre-built, or hardcoded. Every field traces to a specific row in the database, which traces to a specific API call.

```json
{
  "snapshot_timestamp": "-- NOW() at query time --",
  "therapeutic_area": {
    "name": "-- FROM therapeutic_areas.name --",
    "mesh_id": "-- FROM therapeutic_areas.mesh_id --"
  },
  "competitors": [
    {
      "company": "-- FROM companies.name --",
      "drug": "-- FROM drugs.brand_name --",
      "generic_name": "-- FROM drugs.generic_name --",
      "mechanism": "-- FROM mechanisms_of_action.name via drugs.mechanism_id --",
      "supply_status": "-- FROM drugs.supply_status (updated by FDA Shortage pipeline) --",
      "patent_number": "-- FROM drugs.patent_number (sourced from Orange Book) --",
      "patent_expiry": "-- FROM drugs.patent_expiry_date (sourced from Orange Book) --",
      "active_phase3_trials": "-- COUNT(*) FROM clinical_trials WHERE phase='Phase 3' AND status='Recruiting' --",
      "recent_events": "-- FROM market_events WHERE event_date > NOW() - INTERVAL '180 days' --"
    }
  ],
  "regulatory_climate": {
    "shortage_declared": "-- derived from drugs.supply_status --",
    "shortage_resolved_date": "-- FROM market_events WHERE event_type='SHORTAGE_RESOLVED' ORDER BY event_date DESC LIMIT 1 --",
    "new_guidance_issued": "-- EXISTS in market_events WHERE event_type='GUIDANCE_ISSUED' within 180 days --"
  },
  "data_freshness": {
    "-- per source --": "-- FROM etl_runs WHERE status='SUCCESS' ORDER BY completed_at DESC LIMIT 1, per source_name --",
    "overall_staleness": "-- computed: FRESH if all daily sources < 48h, STALE if any > 48h, CRITICAL if any > 7d --"
  }
}
```

**Note:** The JSON above uses `-- comments --` to show the SQL derivation of each field. In the actual API response, these are replaced by the real values queried from the database at request time. No value is illustrative or hardcoded.

### 3.5 API Endpoints (FastAPI)

```
POST /simulate
  Input:  StrategyInput JSON (drug_type, price_point, target_indication,
          launch_market, compounding_strategy, launch_date)
  Output: {
            "risk_score": 8.5,
            "severity": "HIGH",
            "triggered_factors": [...],
            "critique": "...",           // LLM-generated when score > 7.0
            "sources": [...],
            "data_freshness": {...},
            "snapshot_id": "uuid"        // For comparison
          }

POST /simulate/compare
  Input:  { "baseline_snapshot_id": "uuid", "adjusted_strategy": {...} }
  Output: Side-by-side comparison of two simulation results.

GET /market/entity/{name}
  Input:  Entity name (e.g., "Semaglutide")
  Output: Entity details + relationships + recent events.

GET /market/snapshot
  Output: Current MarketSnapshot JSON.

GET /admin/health
  Output: ETL run history, per-source last-updated, failure alerts.

POST /admin/ingest
  Input:  { "url": "...", "source_type": "10-K" }
  Output: { "status": "PROCESSING", "job_id": "uuid" }

GET /admin/ingest/{job_id}
  Output: Ingestion job status and result.
```

### 3.6 Agent Orchestration (LangGraph)

The agent handles two query modes, routed automatically:

**Mode A: Research (Fact Lookup)**
1. **Router** classifies the query as factual.
2. **Retriever** runs vector search against `knowledge_chunks` + structured queries against relational tables.
3. **Synthesizer (LLM)** assembles a cited answer from retrieved context.

**Mode B: Simulation (Strategy Evaluation)**
1. **Router** classifies the query as a simulation request.
2. **Strategy Parser** extracts structured parameters from natural language (or accepts form input directly).
3. **Market Assembler** builds the `MarketSnapshot` from current DB state.
4. **Risk Engine** evaluates all risk factors and produces the score + breakdown.
5. **Critique Generator (LLM):** If score > 7.0, generates a natural-language explanation grounded in the triggered factors and their source documents. The LLM receives only the triggered factors and their citations as context -- it does not freestyle.
6. **Response Assembler** packages the final output.

---

## 4. Source Integration Pipeline (ETL)

Every pipeline follows the same contract: **create an `etl_runs` row before starting, record the exact API endpoint and query parameters, and tag every inserted/updated row with `source_api`, `source_url`, and `retrieved_at`.** If a pipeline cannot determine provenance for a data point, it skips that record and logs a warning -- it never inserts unattributed data.

### 4.0 Source 0: Ontology Bootstrapping (MeSH + ATC)

**This runs once at setup, then monthly to catch updates. It populates the `therapeutic_areas` and `mechanisms_of_action` tables that all other pipelines reference.**

- **MeSH (Medical Subject Headings):**
  - **API:** NIH MeSH RDF API (`id.nlm.nih.gov/mesh/`).
  - **Logic:** Fetch descriptors for the Diabetes and Obesity subtrees. Each descriptor becomes a row in `therapeutic_areas` with its `mesh_id` and the API URL as provenance.
  - **Example:** Descriptor `D003924` ("Diabetes Mellitus, Type 2") is fetched from `https://id.nlm.nih.gov/mesh/D003924.json`.
- **ATC (Anatomical Therapeutic Chemical):**
  - **API:** WHO ATC/DDD Index (or mirrored via KEGG Drug API).
  - **Logic:** Fetch ATC codes for antidiabetic agents (A10B*). Each code becomes a row in `mechanisms_of_action` with its `atc_code`.
- **Provenance:** Every ontology term row records the API URL it was fetched from and the retrieval timestamp. If a MeSH term is retired or renamed, the monthly refresh detects the change and updates accordingly.

### 4.1 Source A: FDA Orange Book (Patent & Exclusivity Data)

**This is the authoritative source for patent expiry dates and drug approval data. It replaces all hand-entered patent information.**

Two data paths are combined because the openFDA API and the Orange Book bulk files contain different data:

- **Drug Approval Data:** openFDA API (`api.fda.gov/drug/drugsfda.json`). Returns brand names, generic names, NDA numbers, approval dates, sponsor names. JSON format, optional free API key (240 req/min without, 120k req/day with).
- **Patent & Exclusivity Data:** Orange Book bulk data files (`fda.gov/drugs/drug-approvals-and-databases/orange-book-data-files`). Monthly ZIP download containing `patent.txt` (patent numbers, expiry dates, drug substance/product flags, patent use codes) and `exclusivity.txt` (exclusivity codes, expiry dates). Tilde-delimited text format.
- **Frequency:** Weekly (download bulk files + query API for new approvals).
- **Scope:** Products matching therapeutic areas in the `therapeutic_areas` table.
- **Logic:**
  1. Download the Orange Book ZIP. Parse `patent.txt` to extract patent numbers and expiry dates keyed by NDA number.
  2. Query the openFDA API for products by `active_ingredient` (e.g., "SEMAGLUTIDE"). Extract: `brand_name`, `generic_name`, `nda_number`, `approval_date`.
  3. Join the two datasets on `nda_number`. **Upsert** into `drugs` table. The `patent_expiry_date` and `patent_number` come from the bulk file; approval metadata from the API.
  4. Link each drug to its `mechanism_id` by matching the drug's `openfda.pharm_class_epc` against `mechanisms_of_action.name`.
  5. Record `source_api = 'fda_orange_book'`, `source_url` = both the bulk file download URL and the API request URL.
  6. **Caveat:** Orange Book patent expiry dates include patent term extensions but do not reflect early expiration due to missed USPTO maintenance fees. Phase 2 enhancement: cross-validate against USPTO PatentsView API.

### 4.2 Source B: ClinicalTrials.gov

- **API:** ClinicalTrials.gov API v2 (`clinicaltrials.gov/api/v2/studies`).
- **Frequency:** Daily (01:00 UTC).
- **Scope:** Studies where `Condition` matches any term in `therapeutic_areas` table.
- **Logic:**
  1. Fetch studies updated in last 24h using `filter.lastUpdatePostDate` parameter.
  2. Extract: `NCTId`, `BriefTitle`, `DetailedDescription`, `LeadSponsorName`, `OverallStatus`, `Phase`, `WhyStopped`, `EnrollmentInfo`.
  3. **Entity Resolution:** Fuzzy match `LeadSponsorName` to `companies.name` (threshold: 85% Jaro-Winkler similarity). Unmatched sponsors are logged to an `unresolved_entities` table for manual review -- they are never silently dropped or guessed.
  4. **Embedding:** Send `DetailedDescription` to OpenAI `text-embedding-3-small`.
  5. **Upsert:** `INSERT ... ON CONFLICT (id) DO UPDATE`. Store the full API response URL in `source_url`.
  6. **Event Detection:** If a trial's `status` changed to `Terminated` since last retrieval, insert a `market_events` row with `event_type = 'TRIAL_TERMINATED'`, linking back to the specific NCT record.

### 4.3 Source C: FDA Drug Shortages

- **API:** openFDA Drug Shortages endpoint (`api.fda.gov/drug/shortages.json`). Structured JSON API -- no HTML scraping required.
- **Frequency:** Daily (01:30 UTC).
- **Auth:** Optional free API key (1,000 req/hr without, 120,000 req/hr with).
- **Fields available:** `generic_name`, `proprietary_name`, `company_name`, `status` (current/resolved/discontinued), `shortage_reason`, `update_date`, `initial_posting_date`, `therapeutic_category`, `dosage_form`, `strength`.
- **Logic:**
  1. Query the API for shortages matching generic names in the `drugs` table.
  2. Compare against the most recent `market_events` of type `SHORTAGE_START` or `SHORTAGE_RESOLVED` for each drug.
  3. **State change detection:**
     - New shortage appears (status = "current"): Insert `SHORTAGE_START` event. Update `drugs.supply_status` to `'SHORTAGE'`.
     - Shortage resolved (status = "resolved"): Insert `SHORTAGE_RESOLVED` event. Update `drugs.supply_status` to `'NORMAL'`.
  4. Each event records `source_api = 'fda_shortages'`, `source_url` pointing to the exact API request URL, and `retrieved_at` timestamp.

### 4.4 Source D: SEC EDGAR

- **Method:** Python `sec-edgar-downloader` library + EDGAR full-text search API.
- **Frequency:** Quarterly (triggered by RSS feed detection of new filings, not a calendar timer).
- **Scope:** 10-K and 10-Q filings for CIK numbers in `companies.cik` column.
- **Logic:**
  1. Download filing from EDGAR. Store the EDGAR filing URL as provenance.
  2. **Section extraction:** Parse `Item 1A (Risk Factors)` and `Item 7 (MD&A)`. Section headers vary across filers -- use regex patterns with fallback heuristics. If extraction fails, log a warning and skip (never fabricate section boundaries).
  3. **Chunking:** Split into 500-token chunks with 50-token overlap.
  4. **Embedding:** Generate vectors for each chunk.
  5. **Store:** Insert into `knowledge_chunks` with:
     - `source_type = '10-K'` or `'10-Q'`
     - `source_reference` = specific section name (e.g., "Item 1A, Risk Factors")
     - `source_url` = EDGAR filing URL (e.g., `https://www.sec.gov/Archives/edgar/data/1000694/...`)
     - `retrieved_at` = download timestamp

### 4.5 Source E: PubMed (Clinical Evidence)

**PubMed provides peer-reviewed clinical evidence that grounds the system's risk assessments in published science, not just regulatory filings.**

- **API:** NCBI E-Utilities (`eutils.ncbi.nlm.nih.gov/entrez/eutils/`).
  - `esearch.fcgi` to find articles by MeSH term + drug name.
  - `efetch.fcgi` to retrieve full metadata (title, abstract, authors, MeSH terms).
- **Frequency:** Weekly.
- **Scope:** Articles matching MeSH terms in `therapeutic_areas` table AND drug names in `drugs` table. Limited to last 5 years for MVP.
- **Logic:**
  1. For each drug in `drugs`, run an esearch query: `"{generic_name}"[MeSH] AND "{therapeutic_area}"[MeSH] AND "last 5 years"[PDat]`.
  2. Fetch article metadata via efetch for new PMIDs not already in `pubmed_articles`.
  3. **Embedding:** Send `title + abstract` to OpenAI `text-embedding-3-small`.
  4. **Store:** Insert into `pubmed_articles` with full provenance (`source_url` = the exact efetch URL for that PMID).
  5. **Chunk for RAG:** Also insert the abstract as a `knowledge_chunks` row with `source_type = 'PUBMED'` and `source_reference = 'PMID:{pmid}'`.
- **Use case in scoring:** R8 (Failed Precedent) cross-references PubMed for published adverse event reports or trial failure analyses, giving the LLM critique real literature citations instead of just ClinicalTrials.gov status codes.

### 4.6 Pipeline Health & Monitoring

- **`etl_runs` table** records every pipeline execution with: source name, exact API endpoint, query parameters (as JSONB), status, record counts (processed/inserted/updated), and error details.
- **Health check endpoint** (`GET /admin/health`) exposes per-source freshness, last run status, and record counts.
- **Alerting:** If any source fails two consecutive runs, an alert is sent (webhook/email -- configurable).
- **Dead-man's switch:** If no ETL run is recorded for 48h for any daily source (or 8 days for weekly sources), alert fires regardless of status.
- **Provenance audit query:** At any time, an admin can run `SELECT source_api, source_url, retrieved_at FROM {any_table} WHERE id = $row_id` to trace any data point back to its origin. This is not optional -- it is the mechanism that enforces the "no fabricated data" principle.

---

## 5. Development Roadmap (6 Weeks)

### Week 1: Real Data Foundation (ETL-First)

**The database must contain real, API-sourced data before any other component is built.** No downstream work (scoring, agent, UI) proceeds until real data is flowing.

- Set up PostgreSQL with pgvector extension. Apply `schema.sql`.
- **Ontology bootstrap:** Run the MeSH and ATC pipelines to populate `therapeutic_areas` and `mechanisms_of_action` tables with real taxonomy terms.
- **FDA Orange Book pipeline:** Implement and run. Populate `drugs` table with real Semaglutide, Tirzepatide, Metformin, and other GLP-1/Diabetes drugs -- including real patent numbers and expiry dates sourced from the API.
- **ClinicalTrials.gov pipeline:** Implement and run initial historical backfill (all Diabetes/Obesity trials, not just last 24h). Populate `clinical_trials` with real NCT-numbered records.
- **FDA Drug Shortages scraper:** Implement and run. Populate initial `market_events` from current shortage list.
- **SEC EDGAR pipeline:** Implement for the 5 target companies (Novo Nordisk, Eli Lilly, Sanofi, AstraZeneca, Pfizer). Download real 10-K filings, extract sections, chunk, embed, and load into `knowledge_chunks`.
- **PubMed pipeline:** Implement and run initial backfill for target drugs. Populate `pubmed_articles`.
- **Validation:** Every table has real rows. Run `SELECT id, source_api, source_url, retrieved_at FROM drugs LIMIT 5` and confirm provenance fields are populated. No row exists without a traceable source.

**Milestone:** All 6 ETL pipelines have run at least once. `etl_runs` shows `SUCCESS` for each. `drugs` contains real patent data from Orange Book. `clinical_trials` contains real NCT records. `knowledge_chunks` contains real 10-K excerpts. `pubmed_articles` contains real literature. `SELECT COUNT(*) FROM {table}` confirms non-trivial record counts for each table.

### Week 2: Risk Scoring Engine + UI Skeleton

- Implement all 8 risk factors (R1--R8) as modular Python classes. Each factor queries the real data now in the DB.
- Build the `MarketSnapshot` assembler (queries live DB state).
- Build `POST /simulate` endpoint.
- **UI:** Scaffold the React dashboard with the strategy input form, Risk Score gauge, risk factor breakdown table, and Data Freshness indicator.
- Wire the form to the API. Submit a real strategy and confirm the score is computed from real DB data.

**Milestone:** Submitting the Semaglutide strategy via the form returns a scored breakdown where every citation traces to a real `source_url` in the database.

### Week 3: ETL Hardening + Scheduling

- Switch all pipelines to scheduled operation (cron): daily for ClinicalTrials.gov and FDA Shortages, weekly for PubMed and Orange Book, quarterly-trigger for EDGAR.
- Implement `etl_runs` audit logging: `api_endpoint`, `query_params`, record counts.
- Implement `GET /admin/health` endpoint.
- Implement alerting on consecutive failures and dead-man's switch.
- Implement `POST /admin/ingest` for manual filing ingestion.
- **Entity resolution audit:** Review fuzzy match logs from Week 1 backfill. Fix false matches. Populate the `unresolved_entities` review queue.

**Milestone:** Pipelines run unattended overnight. `GET /admin/health` returns accurate per-source freshness. At least one ClinicalTrials.gov delta update has run and upserted changed records.

### Week 4: Agent + LLM Integration

- Build the LangGraph orchestration: Router, Retriever, Risk Engine, Critique Generator, Response Assembler.
- Implement Mode A (Research) and Mode B (Simulation) flows.
- Implement `POST /simulate/compare` endpoint for side-by-side re-runs (US-5).
- Wire critique generation: when score > 7.0, LLM explains using only the triggered factors and their cited sources. The LLM prompt explicitly includes the `source_url` for each factor so it can cite real URLs.
- **Validation:** Run a simulation and confirm the LLM critique mentions only facts present in the DB. Grep the critique for any patent number, NCT ID, or date and verify each exists in the corresponding table.

**Milestone:** End-to-end flow works with real data: user submits strategy, gets score + breakdown + LLM critique. Every citation in the critique can be verified against the DB.

### Week 5: Testing + Hardening

- Run the **Ozempic Demo Scenario** (Section 6) end-to-end. Execute all validation criteria against live DB data.
- Run 10 additional test scenarios covering each risk factor in isolation and in combination.
- **Pipeline failure testing:** Temporarily break the FDA scraper (e.g., point at a wrong URL). Verify: alert fires, Data Freshness shows STALE, system continues operating on last-known data.
- **Provenance audit:** Select 20 random rows across all tables. For each, follow `source_url` to the external source and confirm the data matches.
- **Entity resolution accuracy audit:** Review all fuzzy matches, correct false matches.
- UI polish: error states, loading states, empty states.

**Milestone:** Demo scenario produces correct, fully-cited output. Provenance audit passes (20/20 rows traceable). Pipeline monitoring works.

### Week 6: Demo Prep + Documentation

- Record the demo walkthrough against live data (not screenshots of staged output).
- Write the API documentation (OpenAPI spec auto-generated from FastAPI).
- Write the operator runbook: deployment, monitoring, manual intervention, provenance audit procedure.
- Final bug fixes.

**Milestone:** Internal demo ready. System is stable, documented, and every displayed data point is verifiably real.

---

## 6. MVP Demo Scenario: "The Ozempic Compounding Play"

This is the scripted scenario used to validate the MVP. Every feature is exercised. **The expected outputs below are not hardcoded into the system.** They are the results we expect to see *because the ETL pipelines have ingested real data from real APIs* that contain these facts. If the real-world data changes (e.g., FDA declares a new shortage), the system output will change accordingly -- and that is correct behavior.

### Setup

A Strategy Analyst at a mid-size generics company is evaluating a launch strategy for a compounded Semaglutide product targeting the Obesity market, relying on the FDA's 503B compounding exception during the active drug shortage.

### Strategy Input

| Parameter | Value |
|-----------|-------|
| Drug Type | Compounded Semaglutide |
| Target Indication | Obesity (off-label) |
| Launch Market | US |
| Price Point | $200/month |
| Compounding Strategy | 503B Outsourcing Facility |
| Planned Launch Date | 2025-06-01 |

### Expected System Output (derived from live DB)

**The following outputs are what we expect the system to produce given the current state of public data.** Each value traces to a specific row in the database, which traces to a specific API call.

**Risk Score: HIGH (expect >= 8.0)**

| Factor | Weight | Expected Triggered Because | Provenance Chain |
|--------|--------|---------------------------|------------------|
| R1: Active Patent Block | 3.0 | `drugs.patent_expiry_date` for Semaglutide is post-launch-date. Patent number and expiry date were fetched from FDA Orange Book API. | `drugs` row -> `source_api = 'fda_orange_book'` -> `source_url` = Orange Book API call |
| R2: Shortage Loophole Closed | 2.5 | `market_events` contains a `SHORTAGE_RESOLVED` event for Semaglutide, detected by the FDA Shortage scraper when the drug was removed from the active shortage list. | `market_events` row -> `etl_run_id` -> `etl_runs` row with exact scraper URL and timestamp |
| R3: Competitor Phase 3 Active | 2.0 | `clinical_trials` contains active Phase 3 trials for competing GLP-1 drugs in the Obesity therapeutic area, fetched from ClinicalTrials.gov API v2. | `clinical_trials` row -> `source_url` = ClinicalTrials.gov API request URL |
| R5: Regulatory Headwind | 1.5 | `market_events` contains a `GUIDANCE_ISSUED` event within last 180 days for the GLP-1 therapeutic area. | `market_events` row -> `source_url` = FDA guidance page URL |

**LLM Critique:** Generated at query time by feeding the triggered factors and their source citations to GPT-4o. The LLM receives only: (a) the triggered factor names and weights, (b) the `explanation` text from each factor's `explain()` method, (c) relevant chunks from `knowledge_chunks` matching the drug and therapeutic area. It does not receive any pre-written critique text. The output will vary between runs but must only reference facts present in the provided context.

**Data Freshness:** Displayed from live `etl_runs` query -- shows actual last-successful-run timestamps per source, computed at render time.

### Validation Criteria

- [ ] All ETL pipelines have run successfully at least once before the demo (verified via `GET /admin/health`)
- [ ] `drugs` table contains a Semaglutide row with `patent_expiry_date` and `patent_number` sourced from FDA Orange Book (`source_api = 'fda_orange_book'`)
- [ ] `clinical_trials` table contains real NCT-numbered trials fetched from ClinicalTrials.gov API
- [ ] `market_events` table contains shortage status events with `source_url` pointing to the real FDA shortage page
- [ ] R1 (Patent Block) fires and the displayed patent number + expiry match the `drugs.patent_number` and `drugs.patent_expiry_date` fields (which came from Orange Book)
- [ ] R2 (Shortage Resolved) fires and the displayed resolution date matches a `market_events` row with `event_type = 'SHORTAGE_RESOLVED'`
- [ ] R3 (Competitor Phase 3) fires and the displayed NCT number exists in the `clinical_trials` table with `source_api = 'clinicaltrials_gov_v2'`
- [ ] Every source citation in the output can be verified by querying the DB row's `source_url` field and following it to the real external source
- [ ] LLM critique references only facts present in the triggered factors -- no hallucinated risks, no invented patent numbers, no made-up NCT IDs
- [ ] Data Freshness panel shows real `etl_runs` timestamps, not hardcoded values
- [ ] Adjusting one parameter (e.g., changing drug to Metformin, which has expired patents) and re-running produces a materially different score because the `drugs` table has different real data for Metformin

---

## 7. Tech Stack Summary

| Component | Technology | Justification |
|-----------|-----------|---------------|
| **Database** | PostgreSQL 16 + `pgvector` | Single store for relational data + vectors. ACID. HNSW indexing. |
| **Backend** | Python (FastAPI) | Async, auto-generated OpenAPI docs, strong ecosystem. |
| **Orchestration** | LangGraph | Cyclic state machine for multi-step agent workflows. |
| **Embeddings** | OpenAI `text-embedding-3-small` | Cost-effective, 1536-dim, good retrieval quality. |
| **LLM (Critique)** | GPT-4o | Used only for critique generation and research synthesis. Receives only DB-sourced context. |
| **Frontend** | React | Strategy input form, risk gauge, breakdown table, freshness indicator. |
| **ETL Scheduling** | Cron (MVP) / Airflow (Phase 2) | Simplicity for MVP; migrate when pipeline count grows. |
| **Monitoring** | `etl_runs` table + health endpoint | Lightweight, no external dependencies for MVP. |

### External Data Sources (all real, all public APIs)

| Source | API/Method | Auth | Data Provided | Frequency |
|--------|-----------|------|---------------|-----------|
| **NIH MeSH** | MeSH JSON-LD API (`id.nlm.nih.gov/mesh/`) + SPARQL | None | Therapeutic area taxonomy, mechanism of action terms, hierarchy | Monthly |
| **FDA Orange Book** | openFDA API (`api.fda.gov/drug/drugsfda.json`) + bulk data files (`patent.txt`, `exclusivity.txt`) | Optional free key | Drug approvals, patent numbers, patent expiry dates, exclusivity periods | Weekly |
| **ClinicalTrials.gov** | API v2 (`clinicaltrials.gov/api/v2/studies`) | None | Trial status, phase, sponsor, enrollment, termination reasons, descriptions | Daily |
| **FDA Drug Shortages** | openFDA API (`api.fda.gov/drug/shortages.json`) | Optional free key | Active/resolved shortages, shortage reasons, therapeutic categories | Daily |
| **SEC EDGAR** | `sec-edgar-downloader` lib + `data.sec.gov` submissions API | User-Agent header | 10-K/10-Q filings (Risk Factors, MD&A sections), filing metadata | Quarterly |
| **PubMed** | NCBI E-Utilities (`eutils.ncbi.nlm.nih.gov`) -- esearch (JSON) + efetch (XML) | Optional free key | Peer-reviewed literature, abstracts, MeSH terms with descriptor IDs | Weekly |

---

## 8. Phase 2 Roadmap (Post-MVP)

These items are explicitly deferred. They are documented here to prevent scope creep during MVP development.

| Item | Trigger to Start | Dependency |
|------|-----------------|------------|
| **Neo4j integration** | User story requiring 3+ hop traversal is validated | MVP stable, ETL running reliably |
| **Learned EBM scoring model** | 500+ labeled simulation examples collected | MVP rule engine baseline established |
| **Multi-therapeutic-area support** | Diabetes/Obesity vertical proven with paying pilot users | Seed data curation for new vertical |
| **Real-time financial data** | User demand for stock-correlated risk signals | Financial data vendor contract |
| **Multi-user + RBAC** | Second pilot customer onboarded | Auth infrastructure (e.g., Auth0) |
| **Open-source log schema** | Community/ecosystem strategy approved | Public repo setup, license decision |

---

## 9. SWOT Analysis

| Strengths | Weaknesses |
|-----------|------------|
| Every data point traces to a real, verifiable public source -- full provenance chain from UI to API call. Meets pharma compliance and audit requirements. | Vertical-specific: each new therapeutic area requires new ETL pipelines and rule calibration against real data sources. |
| Unified Postgres architecture eliminates data sync issues. No fabricated or synthetic data anywhere in the system. | Rule-based scoring has a ceiling; cannot discover novel risk patterns without the Phase 2 learned model. |
| Clear differentiation from "LLM wrapper" products. The scoring engine runs on structured, source-verified data, not LLM generation. | Dependent on external data source stability (FDA site structure, ClinicalTrials.gov API, PubMed E-Utilities). |
| Seven real public data sources integrated at MVP launch -- demonstrates serious data engineering, not a prototype. | Initial ETL development is front-loaded; Week 1 is heavy engineering before any visible UI progress. |

| Opportunities | Threats |
|--------------|---------|
| Pharma AI decision-tool spend growing rapidly; auditability is the #1 buyer concern -- and provenance is our core architecture, not a bolt-on. | Competitors with proprietary clinical trial databases have a data moat. |
| Expand to adjacent verticals (MedTech, Biotech licensing) by adding new ETL sources to the same architecture. | LLM providers could add native simulation features, compressing the differentiation window. |
| Open-source the scoring framework and ETL schema to build ecosystem and credibility. PubMed integration gives academic research credibility. | Regulatory changes to data access (e.g., ClinicalTrials.gov API restrictions, PubMed rate limits) could disrupt the ETL pipeline. |
