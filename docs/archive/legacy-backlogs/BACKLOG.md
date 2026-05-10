# Market-Zero: Consolidated Backlog

**Date:** 2026-02-17
**Source:** Scenario test results + semantic backbone gap analysis + codebase review

---

## Current State

### What's Built and Working

| Module | Status | Notes |
|---|---|---|
| Data pipeline (6 connectors) | DONE | FDA, ClinicalTrials.gov, PubMed, SEC EDGAR, FDA Shortages, OpenPayments |
| Schema (19 tables) | DONE | PostgreSQL 17, pgvector, pg_trgm |
| Entity resolution (6-strategy) | DONE | 92% trial-drug linkage, 5,890 entity links |
| Data quality engine | DONE | Auditing, pipeline hooks, HITL |
| PharmaMetrics service | DONE | 5 materialized views, sub-10ms |
| HybridSearch service | DONE | Vector + metadata across 4 entity types |
| GraphTraversal service | DONE | N-hop BFS, path finding, entity summaries |
| QueryEngine (GraphRAG) | DONE | Composes search + graph + metrics |
| FastAPI (17 endpoints) | DONE | REST API with Pydantic validation |
| MCP Server (6 tools) | DONE | Agent-accessible via Model Context Protocol |

### Current Data Volumes

| Entity | Count | Linkage |
|---|---|---|
| drugs | 1,085 | company_id: 0%, mechanism_id: 0%, therapeutic_area_id: 0% |
| clinical_trials | 3,498 | drug_id: 92% |
| pubmed_articles | 368 | drug_id: linked |
| companies | 5 | - |
| market_events | 184 | drug_id: linked |
| entity_links | 5,890 | INVESTIGATES: 3,246, SPONSORS: 944, AUTHORED_BY: 710, HAS_MILESTONE: 557, EVIDENCE_FOR: 366, SHORTAGE_AFFECTS: 67 |
| therapeutic_areas | 4 | Referenced by: 0 drugs |
| mechanisms_of_action | 11 | Referenced by: 0 drugs |

### Link Types Missing

| Link Type | Expected | Actual | Impact |
|---|---|---|---|
| OWNS (company -> drug) | ~200+ | 0 | Company portfolio broken |
| IN_THERAPEUTIC_AREA (drug -> TA) | ~500+ | 0 | Competitive landscape broken |
| TARGETS_MECHANISM (drug -> mechanism) | ~300+ | 0 | Competitive landscape broken |

---

## Backlog: Priority Tiers

### Tier 1: Data Linkage (Unlocks Existing Features)

These gaps block features that are already built and tested. Fixing them requires no new services, just data enrichment.

---

#### B1: Company-Drug Ownership Links

**Priority:** P0 -- Highest
**Impact:** Unlocks company portfolio metric, company dossier drug counts, company pipeline scores
**Current state:** 0 OWNS links, 0 drugs with company_id FK
**Root cause:** Entity resolver resolves drug names and trial sponsors but never maps drugs to their owning/marketing companies

**What the infrastructure already supports:**
- `cross_linker._link_drug()` line 86 checks for `resolved.get("company_name")` and creates OWNS links
- `mv_company_portfolio` view already queries via OWNS links
- The code path works; it's just never triggered because entity_resolver doesn't populate `company_name` in resolved_links for drug records

**Approach:**
1. FDA drug data includes `openfda.manufacturer_name` and labeler information
2. Match manufacturer/labeler names against companies table using fuzzy matching
3. For the 5 target companies, also match known brand names (e.g., Ozempic -> Novo Nordisk)
4. Backfill: run resolution on all 1,085 drugs, create OWNS links + set company_id FK
5. Refresh `mv_company_portfolio` materialized view

**Verification:**
```sql
-- After fix:
SELECT link_type, COUNT(*) FROM entity_links WHERE link_type = 'OWNS' GROUP BY link_type;
-- Expect: OWNS ~50-200 links

SELECT company_name, drug_count, pipeline_score_total FROM mv_company_portfolio;
-- Expect: Novo Nordisk with drugs>0, pipeline_score>0
```

---

#### B2: Drug-Therapeutic Area Classification

**Priority:** P0
**Impact:** Unlocks competitive landscape metric (currently returns 0 rows), enriches pipeline metric with TA grouping
**Current state:** 0 drugs have therapeutic_area_id, despite 4 TAs existing in table
**Root cause:** No classification pipeline was run

**Approach:**
1. Therapeutic areas already in DB: Diabetes Mellitus, Diabetes Mellitus Type 2, Obesity (MeSH-based)
2. For drugs with linked PubMed articles, use article MeSH terms to classify
3. For drugs with linked clinical trials, use trial conditions text (already in DB)
4. For remaining drugs, use drug name + generic_name against known TA-drug mappings
5. Set `drugs.therapeutic_area_id` FK and create IN_THERAPEUTIC_AREA links

**Data signals available:**
- `clinical_trials.conditions` text field (e.g., "Type 2 Diabetes Mellitus")
- PubMed article MeSH terms (stored in keywords field)
- Drug generic names (many are self-classifying: "insulin glargine" -> Diabetes)

**Verification:**
```sql
SELECT ta.name, COUNT(d.id) FROM drugs d JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id GROUP BY ta.name;
-- Expect: Diabetes ~400+, Obesity ~100+
```

---

#### B3: Drug-Mechanism Classification

**Priority:** P1
**Impact:** Unlocks competitive landscape (mechanism-level competition is where pharma strategy happens)
**Current state:** 0 drugs have mechanism_id, despite 11 mechanisms in table
**Root cause:** No classification pipeline was run

**Approach:**
1. Mechanisms already in DB: GLP-1 RA, SGLT2 inhibitor, DPP-4 inhibitor, Insulin, etc.
2. Build keyword-based classifier using drug names and known mechanism mappings
3. For known drug classes, map directly:
   - semaglutide, liraglutide, exenatide, dulaglutide -> GLP-1 receptor agonist
   - dapagliflozin, empagliflozin, canagliflozin -> SGLT2 inhibitor
   - sitagliptin, saxagliptin, alogliptin -> DPP-4 inhibitor
   - insulin glargine, insulin lispro -> Insulin
   - pioglitazone, rosiglitazone -> Thiazolidinedione
   - metformin -> Biguanide
4. Set `drugs.mechanism_id` FK and create TARGETS_MECHANISM links
5. For unknown drugs, use PubMed article text or trial descriptions for classification

**Verification:**
```sql
SELECT moa.name, COUNT(d.id) FROM drugs d
JOIN mechanisms_of_action moa ON d.mechanism_id = moa.id
GROUP BY moa.name ORDER BY COUNT(d.id) DESC;
-- Expect: Insulin 100+, GLP-1 RA 50+, SGLT2i 40+, DPP-4i 30+
```

---

#### B4: Company Name Matching Improvement

**Priority:** P1
**Impact:** AstraZeneca and Pfizer currently show 0 trial sponsorships
**Current state:** Sponsor name matching only works for exact or near-exact matches
**Root cause:** ClinicalTrials.gov sponsor names differ from SEC EDGAR names

**Approach:**
1. Audit: query distinct sponsor_name values from clinical_trials that don't match any company
2. Add company alias table or expand fuzzy matching with known variants:
   - "AstraZeneca" = "AstraZeneca Pharmaceuticals LP" = "AstraZeneca PLC"
   - "Pfizer" = "Pfizer Inc." = "Pfizer Inc"
   - "Eli Lilly" = "Eli Lilly and Company" = "Lilly"
3. Re-run sponsor resolution for unmatched trials
4. Refresh SPONSORS links

**Verification:**
```sql
SELECT c.name, COUNT(el.id) FROM companies c
JOIN entity_links el ON el.source_entity_id = c.id::text AND el.link_type = 'SPONSORS'
GROUP BY c.name;
-- Expect: all 5 companies have SPONSORS links
```

---

### Tier 2: Data Quality (Improves Existing Feature Accuracy)

These improve the quality and utility of features that already work.

---

#### B5: Drug Canonicalization

**Priority:** P1
**Impact:** Fixes find_similar (returns dosage variants), improves metrics accuracy, reduces noise
**Current state:** 1,085 drug entries include many dosage/formulation variants of the same active ingredient
**Example:** semaglutide, semaglutide 50 mg, semaglutide injection, Semaglutide 2.4 mg, Semaglutide 3 mg -- all one drug

**Approach:**
1. Create `canonical_drugs` table: (id, generic_name, brand_names[], mechanism_id, therapeutic_area_id)
2. Add `drugs.canonical_drug_id` FK column
3. Build mapping:
   - Group by normalized generic_name (lowercase, strip dosage/form)
   - Manual review for ambiguous cases
4. Update materialized views to aggregate at canonical_drug level
5. Update find_similar to exclude same-canonical results

**Expected outcome:** ~1,085 drug entries -> ~200 canonical drugs

---

#### B6: Author/Investigator Entity Resolution

**Priority:** P2
**Impact:** Cleans "unknown" nodes in 2-hop graph traversal, enables investigator analysis
**Current state:** 710 AUTHORED_BY links exist, target entities are UUIDs with no label resolution
**Root cause:** Author entities stored in entity_links but no investigators table populated

**Approach:**
1. Extract unique author entity IDs from AUTHORED_BY links
2. Look up corresponding PubMed author data (already retrieved but not stored as entities)
3. Populate investigators table or add to v_entity_labels view
4. Update graph label resolution to include authors

---

#### B7: Expand Article Corpus

**Priority:** P2
**Impact:** 368 articles is thin; many drugs have <5 articles each
**Current state:** PubMed connector returns selective results per query

**Approach:**
1. Broaden PubMed queries: search by drug name + "clinical trial" OR "review"
2. Increase retmax per query (currently capped)
3. Add backfill pass for drugs with <5 linked articles
4. Re-run evidence_density materialized view refresh

---

### Tier 3: Platform Capabilities (New Features)

These are new capabilities that extend the platform's value.

---

#### B8: Embedding Cache

**Priority:** P1
**Impact:** Reduces search/query latency from 1-10s to <100ms for repeat queries
**Current state:** Every search call makes a fresh OpenAI API request

**Approach:**
1. LRU cache (in-memory dict, ~10K entries) keyed by query text hash
2. Check cache before calling OpenAI API
3. TTL of 24h (embeddings are deterministic, long-lived)
4. Optional: persist to Redis for cross-process sharing

**Verification:** Same query run twice; second call <50ms

---

#### B9: Enhanced Comparison (2-Hop Shared Connections)

**Priority:** P2
**Impact:** compare_entities currently shows 0 shared connections at 1-hop
**Current state:** Drugs connect to different trials/articles directly, so 1-hop overlap is zero

**Approach:**
1. In `query_engine.compare_entities()`, use 2-hop traversal instead of 1-hop
2. Filter shared connections by entity type (shared investigators, shared TAs, shared mechanisms)
3. Add "shared_by_type" field to comparison response

---

#### B10: Semantic Definitions Table

**Priority:** P2
**Impact:** Agents can understand what fields mean without hallucinating definitions
**Current state:** No machine-readable definitions for columns, phases, statuses

**Approach:**
1. Create `semantic_definitions` table: (table_name, column_name, definition, value_definitions JSONB)
2. Populate for key columns: clinical_trials.phase, clinical_trials.status, drugs.supply_status, etc.
3. Expose via API endpoint: GET /catalog/definitions
4. Add to MCP server as a resource

---

#### B11: Domain Business Rules

**Priority:** P3
**Impact:** Agents can apply pharma-specific logic without hard-coding
**Current state:** Phase weighting is hard-coded in SQL; no general rule engine

**Approach:**
1. Create `domain_rules` table: (rule_id, category, condition, action, weight, description)
2. Encode rules like:
   - "Phase 3 failure within 6 months of completion = high competitive signal"
   - "Patent expiry within 2 years = generic entry risk"
   - "Drug with >3 Phase 3 trials active = likely near-approval"
3. Expose via API and MCP

---

#### B12: Canonical IRIs

**Priority:** P3
**Impact:** Global addressability, linked data readiness
**Current state:** Local UUIDs only

**Approach:**
1. Add `canonical_iri TEXT` to drugs, companies, trials, articles
2. Pattern: `mz:drug/semaglutide`, `mz:trial/NCT04375227`, `mz:company/cik-0001000694`
3. Backfill from existing identifiers (NDA numbers, NCT IDs, CIKs)

---

#### B13: Document Ingestion Pipeline

**Priority:** P3
**Impact:** Enables ingestion of arbitrary PDFs, reports, filings
**Current state:** SEC filing chunking works, but no general document parser

**Approach:**
1. PDF text extraction (pymupdf or pdfplumber)
2. Semantic chunking (respect section/paragraph boundaries)
3. Entity resolution at chunk level
4. Store in knowledge_chunks with metadata

---

## Execution Order

```
Phase 1: Data Linkage (B1-B4) -- unlocks blocked features
  B1: Company-drug OWNS links        ← do first, highest ROI
  B2: Drug-TA classification          ← can run in parallel with B1
  B3: Drug-mechanism classification   ← depends on B2 patterns
  B4: Company name matching fix       ← independent, small scope

Phase 2: Data Quality (B5-B7) -- improves accuracy
  B5: Drug canonicalization           ← highest impact in this tier
  B8: Embedding cache                 ← quick win, big latency improvement
  B6: Author entity resolution        ← independent
  B7: Expand article corpus           ← independent

Phase 3: Platform Capabilities (B9-B13) -- extend value
  B9:  Enhanced comparison
  B10: Semantic definitions
  B11: Domain business rules
  B12: Canonical IRIs
  B13: Document ingestion
```

Phase 1 tasks can largely run in parallel. B1+B2+B3 together will unlock the competitive landscape metric and company portfolio -- the two most strategically valuable features that are currently returning empty results.

---

## Impact Matrix

| Task | Competitive Landscape | Company Portfolio | Dossier Quality | Search Quality | Latency |
|---|---|---|---|---|---|
| B1: OWNS links | - | UNLOCKS | +++ | - | - |
| B2: TA classification | UNLOCKS | ++ | ++ | + | - |
| B3: Mechanism classification | UNLOCKS | + | ++ | + | - |
| B4: Company matching | - | ++ | + | - | - |
| B5: Drug canonicalization | + | + | ++ | +++ | - |
| B8: Embedding cache | - | - | - | - | +++ |

---

## Completed (Reference)

Previously completed work that feeds into this backlog:

| Task | Completed |
|---|---|
| Migration 009 (materialized views, graph function) | 2026-02-17 |
| PharmaMetrics service | 2026-02-17 |
| HybridSearch service | 2026-02-17 |
| GraphTraversal service | 2026-02-17 |
| QueryEngine (GraphRAG) | 2026-02-17 |
| FastAPI (17 endpoints) | 2026-02-17 |
| MCP Server (6 tools) | 2026-02-17 |
| Entity resolution overhaul | 2026-02-16 |
| Data quality engine | 2026-02-15 |
| Dataset catalog + Croissant | 2026-02-15 |
