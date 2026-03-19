# Market-Zero vs. Semantic Backbone for Enterprise AI: Gap Analysis

## Document Summary

"The Architecture of Meaning" is a 25-slide strategic framework by WisdomAI that argues enterprise AI fails not because of bad models but because of bad data architecture. Its core thesis: **the race for AI will be won by those with the most accessible, meaningful data, not the biggest models.** It proposes a 5-stage maturity ladder and a "Trusted Semantic Backbone" built on three pillars: **Semantics, Identity, and Governance**.

---

## Slide-by-Slide Assessment

### Slide 1: The Architecture of Meaning
**Concept:** Raw storage (unstructured chaos) must be transformed into structured meaning and connection for agentic intelligence.

**Market-Zero status: STRONG**
- We literally do this. 6 raw APIs (MeSH, FDA, ClinicalTrials.gov, FDA Shortages, PubMed, SEC EDGAR) are ingested through a universal pipeline and transformed into a connected knowledge layer with 19 tables, 5,890 entity_links, and 329K+ records.
- The `fetch -> normalize -> resolve -> embed -> store -> cross_link` pipeline is exactly the "raw chaos to structured meaning" transformation.

---

### Slide 2: The High Value Zone Gap
**Concept:** 2x2 matrix of Business Value (Relevant/Irrelevant) x Accessibility (Public/Private). Enterprise AI fails because it can't access the Private + Relevant quadrant ("High Value Zone": risk scores, customer history, real-time inventory).

**Market-Zero status: PARTIAL**
- We currently live in the **Core Knowledge** quadrant (Public + Relevant): SEC filings, FDA data, clinical trials, PubMed. Accessible but generic.
- The "High Value Zone" for pharma would be: proprietary clinical data, internal pipeline forecasts, competitive intelligence signals, real-time pricing data, formulary access data.
- **Gap:** No private/proprietary data integration yet. The USER_DOCUMENT and USER_URL SourceTypes exist in connectors/base.py but haven't been exercised.

**Suggestion:** The knowledge_chunks table and USER_DOCUMENT/USER_URL connectors are designed for this. Activating them would let users inject proprietary documents (internal pipeline reports, board decks, competitive intelligence) that get entity-resolved and cross-linked against the public backbone. This is what moves us from "Core Knowledge" to "High Value Zone."

---

### Slide 3: The "Schema-on-Read" Fallacy
**Concept:** Storing everything is easy; retrieving context is hard. Without a semantic map, LLMs treat data lakes as swamps. Risk: context collapse.

**Market-Zero status: STRONG**
- We explicitly rejected schema-on-read. Every record passes through:
  1. **Normalizer** (FIELD_MAPS per source type) - canonical field mapping
  2. **EntityResolver** (6-strategy cascade) - identity resolution
  3. **KnowledgeStore** (typed handlers per RecordType) - structured storage
- Every table has typed columns, not JSON blobs. `clinical_trials.phase`, `drugs.approval_date`, `companies.cik` - all semantically clear.
- Embeddings are on *meaningful* text (protocol descriptions, abstracts), not raw dumps.

---

### Slide 4: The Agentic Gap - Why Context is Non-Negotiable
**Concept:** Agents need a "structural conscience." Without business rules, a pricing agent can't distinguish catalog price from net price. Context must be encoded, not assumed.

**Market-Zero status: PARTIAL - KEY GAP**
- We have structural context (table schemas, entity relationships, FK constraints).
- We do NOT have a **business rules layer** that encodes pharma-specific domain logic. Examples of what's missing:
  - "Phase 3 trial completion for semaglutide should be weighted higher than Phase 1"
  - "An FDA approval event supersedes a clinical trial completion"
  - "'Completed' status on a trial with no results posted = suspicious"
  - "Patent expiry within 2 years = generic entry risk signal"

**Suggestion:** Create a `domain_rules` or `semantic_rules` table that encodes pharma business logic as structured rules an agent can query. This is the "structural conscience" the framework calls for. An agent asking "What's Novo Nordisk's competitive risk?" needs to know that patent expiry + generic pipeline activity + Phase 3 trial failures compound multiplicatively. Today our data can answer the components, but the *interpretation logic* isn't encoded.

---

### Slide 5: Layering Meaning Onto Data
**Concept:** 5-stage pipeline: Raw Data -> Metadata & Context -> Semantic Layer -> Knowledge Graph -> Agentic AI.

**Market-Zero status: Here's where we sit on each stage:**

| Stage | Status | Evidence |
|-------|--------|----------|
| Raw Data | DONE | 6 connectors fetching from public APIs |
| Metadata & Context | DONE | Provenance (SHA-256 hash, source URL, timestamps), Croissant JSON-LD, dataset_catalog, etl_runs |
| Semantic Layer | STRONG | Normalizer (canonical field maps), MeSH ontology (therapeutic areas, mechanisms), entity_aliases, data_quality_rules |
| Knowledge Graph | PARTIAL | entity_links table (5,890 links, 6 types). But it's a *relational graph*, not a true knowledge graph with typed RDF triples or property graph native storage |
| Agentic AI | NOT STARTED | No API layer, no MCP server, no agent-facing query interface |

**The biggest gap is the jump from Knowledge Graph to Agentic AI.** We have the graph data but no way for an AI agent to traverse it without writing raw SQL.

---

### Slide 6: The Grammar of Knowledge (Semantic Layer)
**Concept:** The semantic layer is the Rosetta Stone that decouples business logic from physical storage. Ensures "Customer" means the same thing to Finance, Marketing, and the AI agent. Components: Logic Mapping, Translation Matrix, Business Rule Engine, Contextual Enrichment.

**Market-Zero status: PARTIAL**
- **Translation Matrix**: Done via Normalizer's FIELD_MAPS. "lead_sponsor_name" (ClinicalTrials.gov) and "company_name" (SEC EDGAR) both map to the same company entity.
- **Logic Mapping**: Partially done via entity_resolver (6-strategy cascade maps raw names to canonical entity IDs).
- **Business Rule Engine**: NOT DONE. We have no encoded business rules that say "this trial phase means X" or "this regulatory milestone signals Y."
- **Contextual Enrichment**: Partially done via embeddings (semantic similarity) and entity_links (structural relationships). Missing: derived metrics, computed signals.

**Suggestion:** Build a `semantic_definitions` table that maps every column and entity type to a human-readable (and LLM-readable) definition. Example: `{"column": "clinical_trials.phase", "definition": "FDA clinical trial phase. Phase 1 = safety/dosage, Phase 2 = efficacy, Phase 3 = large-scale efficacy, Phase 4 = post-market"}`. This would let an agent understand what the data *means*, not just what it contains.

---

### Slide 7: Architecture Options
**Concept:** Three options: BI-Native (siloed, hard for AI), Platform-Native (centralized but vendor-locked, e.g., Snowflake), Universal/Headless (API-first, write once read everywhere). Recommends Universal/Headless.

**Market-Zero status: Currently BI-Native, architected for Universal**
- Today: Direct PostgreSQL access only. No API layer.
- But: The design is already headless-friendly. All logic is in Python modules (not locked to a BI tool or platform). PostgreSQL is the storage backend, not the logic layer.

**Suggestion:** A thin API layer (FastAPI) + MCP server would flip us to Universal/Headless overnight. The data model and integration logic don't need to change; we just need to expose them.

---

### Slide 8: Metrics vs. Semantics
**Concept:** AI agents need BOTH: Semantics to understand the world (entity relationships, the map), and Metrics to report on performance without hallucinating the math (calculated KPIs, the math).

**Market-Zero status: SEMANTICS = STRONG, METRICS = ABSENT**
- Semantics: entity_links graph, MeSH ontology, entity resolution, cross-source relationships. All solid.
- Metrics: We have zero pre-computed metrics. No "trial success rate for GLP-1 agonists," no "average Phase 3 duration for diabetes drugs," no "patent cliff exposure index."

**Suggestion:** Build a **metrics layer** - a set of SQL views or materialized views that compute domain-specific KPIs from the raw data. Examples:
- `drug_pipeline_strength`: count of active trials by phase, weighted by enrollment
- `patent_cliff_risk`: days to earliest patent expiry for each drug
- `evidence_density`: count of PubMed articles per drug, weighted by recency
- `trial_success_rate`: % of completed trials vs terminated/withdrawn per drug/TA
- `geographic_reach`: country count from trial_locations per drug

An agent could query these directly instead of needing to compute them from joins.

---

### Slide 9: Why LLMs Prefer Graphs
**Concept:** SQL JOINs are hard for LLMs to reason about. Knowledge graphs with labeled edges (Alice --Works_For--> Corporation) are linguistically natural. "Knowledge Graphs can triple LLM accuracy on enterprise data."

**Market-Zero status: HYBRID - entity_links is a graph, but stored relationally**
- Our `entity_links` table IS a property graph: `(source_entity_id) --[link_type]--> (target_entity_id)` with confidence and metadata.
- But it's queried via SQL joins, not via a graph query language (Cypher, SPARQL, Gremlin).
- An LLM would need to do `SELECT * FROM entity_links WHERE source_entity_id = X` which is clunky for multi-hop traversal.

**Suggestion:** Two options:
1. **Graph query views** - Create SQL functions that perform N-hop traversals: `SELECT * FROM traverse_graph('drug_uuid', 2)` returns all entities within 2 hops.
2. **Graph export** - Periodically export entity_links + entities to a graph format (RDF/Turtle, JSON-LD, or Neo4j-compatible CSV) for native graph querying.
3. **GraphRAG pattern** (see Slide 19) - Use entity_links to enrich vector search results with structural context before sending to LLM.

---

### Slide 10: The Foundation of Identity (IRIs)
**Concept:** In a database, identity is local. In an AI ecosystem, identity must be global. IRIs (Internationalized Resource Identifiers) allow agents to traverse data across siloed systems. Shows: CRM Card (ID: 123), ERP Card (C-123), Support Card (cust_123) all converge to `IRI: company:customer/123`.

**Market-Zero status: PARTIAL - We have multi-source identity resolution but no formal IRI scheme**
- Our entity_resolver does exactly this convergence: "NOVAVAX INC" (EDGAR), "Novo Nordisk" (ClinicalTrials.gov sponsor_name), CIK 0001000694 (SEC) all resolve to a single `companies.id` UUID.
- entity_aliases table stores the many-to-one mapping (1,983 aliases).
- resolution_audit logs every identity decision.
- **BUT:** Our IDs are PostgreSQL UUIDs (local), not IRIs (global). A drug's ID is `a7b3c9d1-...` not `mz:drug/semaglutide` or `https://market-zero.io/entity/drug/semaglutide`.

**Suggestion:** Add a `canonical_iri` column to core entity tables. Pattern: `mz:{entity_type}/{external_authority_id}`. For drugs: `mz:drug/nda-022686` (FDA NDA) or `mz:drug/semaglutide` (generic name). For trials: `mz:trial/NCT04375227` (already natural). For companies: `mz:company/cik-0001000694`. This makes entities globally addressable and linkable across systems, which is essential for future MCP/API exposure.

---

### Slide 11: Regulatory Consistency
**Concept:** Semantic layer standardizes definitions across sources. Example: "Total Credit Exposure" means different things to SEC vs EU regulators. Solution: semantic standard ensures consistency.

**Market-Zero status: STRONG**
- This is exactly what our Normalizer does. `lead_sponsor_name` (CT.gov), `company_name` (FDA), `company_name` (EDGAR) all map to the canonical `sponsor_name` or `company_name` field.
- MeSH ontology provides the controlled vocabulary for therapeutic areas and mechanisms.
- The 6-strategy entity resolver ensures "SITAGLIPTIN" (FDA), "sitagliptin phosphate" (CT.gov), and "Sitagliptin (MK0431)" (trial intervention) all resolve to the same drug.

---

### Slide 12: Unstructured Data Pipeline
**Concept:** 6-step pipeline for unstructured data: Collect -> Clean -> Split/Chunk -> Embed -> Store -> Retrieve.

**Market-Zero status: PARTIALLY IMPLEMENTED**
- Steps 1-5 are implemented for SEC EDGAR filings (knowledge_chunks table) and are *configurable* for USER_DOCUMENT/USER_URL.
- Step 6 (Retrieve) is not built - no vector search query interface exists yet.
- The pipeline handles structured API data extremely well but only has basic support for truly unstructured content (SEC 10-K sections).

**Suggestion:** The USER_DOCUMENT connector path is ready architecturally (SourceType.USER_DOCUMENT exists, knowledge_chunks table exists, embedder works). What's missing is: (a) a document parser (PDF/DOCX to text), (b) a chunking strategy beyond fixed-size, and (c) a retrieval interface.

---

### Slide 13: The Strategy of Chunking
**Concept:** Fixed-size chunking destroys context ("The defendant is NOT" / "guilty" = meaning lost). Semantic chunking respects document structure to preserve meaning.

**Market-Zero status: BASIC - Fixed-size only**
- Config has `chunk_size_tokens: 500` and `chunk_overlap_tokens: 50` - this is the fixed-size approach the document warns against.
- SEC EDGAR connector chunks by section headers (section_name field), which is a form of semantic chunking for filings.
- No paragraph-aware or sentence-boundary chunking for general documents.

**Suggestion:** When building the document ingestion path, implement semantic chunking that:
1. Splits on document structure (headers, sections, paragraphs)
2. Keeps related content together (e.g., a drug name + its trial results shouldn't be split)
3. Attaches parent context to each chunk (which section, which document, which entity)
4. Uses the entity_resolver to tag chunks with resolved entity IDs

---

### Slide 14: Metadata Enrichment
**Concept:** Raw text blobs are insufficient. NLP-extracted metadata (title, author, date, classification) enables "hybrid search" - filtering by metadata before vector search.

**Market-Zero status: STRONG for structured data, WEAK for unstructured**
- For PubMed articles: title, authors, journal, publication_date, MeSH terms, keywords - all structured metadata enabling precise filtering.
- For clinical trials: phase, status, conditions, interventions, sponsor - rich filterable metadata.
- For SEC filings in knowledge_chunks: only entity_type, entity_id, source_type, source_reference. Missing: filing_date, section_type, mentioned_drugs, sentiment.

**Suggestion:** For knowledge_chunks (SEC filings, future documents), add NLP-extracted metadata columns or a `chunk_metadata JSONB` field: detected entities, dates mentioned, sentiment, key topics. This enables the hybrid search pattern: "Find SEC filing sections mentioning semaglutide from 2024 with negative sentiment."

---

### Slide 15: Vector Embeddings - Mapping Meaning to Math
**Concept:** Embeddings find conceptual similarity, not just keyword matches. Domain-specific fine-tuning dramatically improves relevance.

**Market-Zero status: IMPLEMENTED but generic**
- text-embedding-3-small (1536 dims) across all entity types.
- HNSW indexes on all embedding columns for fast ANN search.
- 99-100% embedding coverage across tables.
- **BUT:** We use a general-purpose embedding model, not a pharma/biomedical fine-tuned one.

**Suggestion:** Consider swapping to a biomedical embedding model for drug/trial/article content. Options: PubMedBERT embeddings, BioLinkBERT, or fine-tuning text-embedding-3-small on pharma terminology. The entity resolution embedding strategy (Strategy 4) would particularly benefit - "insulin glargine (Lantus)" vs "INSULIN GLARGINE" cosine similarity would be higher with domain-tuned embeddings.

---

### Slide 16: The Croissant Standard
**Concept:** "Nutrition labels for data." Machine-readable standard ensuring agents digest only healthy, compliant data. Covers: Provenance (verified), Lineage (source system), Usage Policy (AI training allowed), Bias Check (passed).

**Market-Zero status: IMPLEMENTED (just built)**
- `dataset_catalog` table with Croissant JSON-LD per dataset (12 entries).
- Provenance verified: SHA-256 raw_response_hash on every fetch, source_api/source_url/retrieved_at on every row.
- Lineage: etl_runs table tracks every pipeline execution.
- Bias documented: 5 known biases in Croissant RAI extension.
- License tracking per source dataset.

---

### Slide 17: RAG vs. Fine-Tuning
**Concept:** Fine-tuning for form (how the model speaks). RAG for facts (what it knows). Verdict: use RAG for enterprise data.

**Market-Zero status: RAG-READY but not RAG-SERVING**
- All the data infrastructure for RAG is in place: embeddings, entity_links, provenance.
- No retrieval endpoint exists. An agent can't yet say "retrieve top-5 relevant trial descriptions for semaglutide Phase 3."

**Suggestion:** Build a RAG retrieval module that:
1. Takes a natural language query
2. Embeds it
3. Searches across relevant tables (vector similarity)
4. Enriches results with entity_links context (GraphRAG pattern)
5. Returns structured context for LLM consumption with provenance citations

---

### Slide 18: Beyond Basic Retrieval (Hybrid Search)
**Concept:** Combining metadata filtering with vector search ensures precision. Pipeline: All Documents -> Metadata Filtering (date, department) -> Vector Search (conceptual match) -> Precise Result.

**Market-Zero status: NOT BUILT (but infrastructure supports it)**
- We have both: rich metadata columns (phase, status, date, source) AND vector embeddings.
- We just lack the query layer that combines them.

**Suggestion:** SQL-native hybrid search is straightforward with our stack:
```sql
SELECT id, title, 1 - (abstract_embedding <=> query_vec) AS sim
FROM pubmed_articles
WHERE publication_date > '2023-01-01'
  AND drug_id = (SELECT id FROM drugs WHERE generic_name = 'semaglutide')
ORDER BY abstract_embedding <=> query_vec
LIMIT 10;
```
Wrap this pattern in a `HybridSearchEngine` class that accepts: query text, entity filters (drug, company, TA), date range, source type, and returns ranked results with provenance.

---

### Slide 19: GraphRAG - The Best of Both Worlds
**Concept:** Connecting fuzzy vector search with structural graph reasoning. Vector DB finds relevant chunks; Knowledge Graph provides structural context about how that chunk relates to entities. Together, an agent understands how a document impacts a database entity.

**Market-Zero status: ALL COMPONENTS EXIST, NOT CONNECTED**
- Vector DB: pgvector embeddings on 6 tables with HNSW indexes.
- Knowledge Graph: entity_links with 5,890 edges across 6 relationship types.
- The bridge between them (GraphRAG query) doesn't exist yet.

**Suggestion:** This is the highest-leverage enhancement. A GraphRAG query for "What's the competitive landscape for semaglutide?" would:
1. Vector search: find relevant articles, trial descriptions, SEC filing chunks mentioning semaglutide
2. Graph traversal: from semaglutide -> INVESTIGATES -> trials -> SPONSORS -> companies -> other drugs -> their trials
3. Synthesis: combine unstructured evidence (articles) with structured relationships (graph) into a comprehensive context package for the LLM

---

### Slide 20: The Context Layer - From 'What' to 'Why'
**Concept:** Extending semantics to include operational rules and user intent. Same question ("How did sales do?") gets different answers for Sales Rep (bookings) vs Finance (recognized revenue). The Context Layer sits above the Semantic Layer and encodes role-based interpretation.

**Market-Zero status: NOT IMPLEMENTED**
- We have no concept of user roles or intent-based query routing.
- All data is served uniformly regardless of who's asking or why.

**Suggestion:** For a pharma war-gaming engine, context matters:
- **Portfolio strategist** asking about semaglutide wants: competitive threats, patent cliffs, pipeline depth
- **Clinical operations** wants: trial site performance, enrollment rates, outcome measures
- **Regulatory affairs** wants: FDA milestones, submission history, approval probability

Build a `query_contexts` table that maps user intent/role to relevant entity types, relationship paths, metrics, and filters.

---

### Slide 21: Standardizing Connection (MCP)
**Concept:** Model Context Protocol (MCP) as "USB-C for AI applications." Allows agents (Claude, GPT-4, Llama) to query data using natural language, decoupling the model from the data source.

**Market-Zero status: NOT IMPLEMENTED - CRITICAL GAP FOR AGENTIC USE**
- No MCP server exists.
- No API of any kind exposes the knowledge layer.
- An AI agent today would need direct PostgreSQL access and knowledge of our schema.

**Suggestion:** Build an MCP server that exposes Market-Zero as a tool:
- `search_drugs(name, therapeutic_area)` -> drug records with entity_links
- `get_trial_landscape(drug_name, phase, status)` -> trial summaries
- `get_competitive_intel(company_name)` -> drugs, trials, patents, articles
- `find_evidence(query_text, filters)` -> hybrid search with provenance
- `get_entity_graph(entity_id, hops)` -> graph neighborhood

This is the single most impactful thing for making the data agentic.

---

### Slide 22: Governance as the Structural Conscience
**Concept:** "Trustworthy AI is not just about accuracy; it is about auditability." Three layers: Row-Level Security, Provenance, Audit Trail.

**Market-Zero status: STRONG on provenance and audit, WEAK on access control**
- **Provenance:** Every row has source_api, source_url, retrieved_at. Every entity resolution logged in resolution_audit (1,061 rows). Every data change in data_change_log.
- **Audit Trail:** etl_runs tracks every pipeline execution. resolution_audit tracks every entity decision. data_quality_results tracks every quality assessment.
- **Row-Level Security:** Not implemented. Single PostgreSQL user. No role-based access.

---

### Slide 23: The Semantic Maturity Model
**Concept:** 5 levels: L1 (BI-Native/Siloed) -> L2 (Shared Semantic Layer/Headless) -> L3 (Platform-Native Governance) -> L4 (Enterprise Knowledge Graph) -> L5 (Agentic Reasoning).

**Market-Zero current level: L3, approaching L4**

| Level | Description | Market-Zero Status |
|-------|------------|-------------------|
| L1: BI-Native Metrics | Siloed, per-tool definitions | Surpassed |
| L2: Shared Semantic Layer | Headless, canonical definitions | DONE - Normalizer, FIELD_MAPS, canonical schema |
| L3: Platform-Native Governance | Quality rules, audit, HITL | DONE - data_quality_rules, resolution_audit, hitl_review_queue, pipeline_hooks |
| L4: Enterprise Knowledge Graph | Connected entities with typed relationships | PARTIAL - entity_links exists (5,890 edges), but no graph query interface, no multi-hop traversal, no graph visualization |
| L5: Agentic Reasoning | AI agents query and reason over the graph | NOT STARTED - no API, no MCP, no RAG retrieval, no metrics layer |

---

### Slide 24: Implementation Roadmap
**Concept:** Phase 1 (Anchor Metrics) -> Phase 2 (Collaborative Governance) -> Phase 3 (Unstructured Integration) -> Phase 4 (Agentic Integration via API/MCP).

**Market-Zero mapping:**
- Phase 1 (Anchor Metrics): PARTIAL - we have data but no computed KPI metrics layer
- Phase 2 (Collaborative Governance): DONE - quality rules, HITL queue, audit trail
- Phase 3 (Unstructured Integration): PARTIAL - SEC filing chunks work, general document ingestion not built
- Phase 4 (Agentic Integration): NOT STARTED

---

### Slide 25: The Trusted Semantic Backbone
**Concept:** The bridge between Enterprise Data and AI Agent rests on three pillars: Semantics, Identity, Governance. "The race for AI will not be won by those with the biggest models, but by those with the most accessible, meaningful data."

**Market-Zero pillar assessment:**

| Pillar | Strength | Key Gap |
|--------|----------|---------|
| Semantics | 7/10 | Missing: business rules engine, metrics layer, semantic definitions table |
| Identity | 8/10 | Missing: formal IRI scheme, canonical URIs for external addressability |
| Governance | 8/10 | Missing: row-level security, access roles |

---

## Summary Scorecard

| Framework Concept | Slide | Status | Score |
|---|---|---|---|
| Raw-to-Structured Transformation | 1 | DONE | 9/10 |
| High Value Zone (private data) | 2 | PARTIAL | 3/10 |
| Schema-on-Write (not Read) | 3 | DONE | 9/10 |
| Structural Conscience (biz rules) | 4 | MISSING | 2/10 |
| 5-Stage Meaning Pipeline | 5 | 4 of 5 stages | 7/10 |
| Semantic Layer / Translation | 6 | STRONG | 8/10 |
| Universal/Headless Architecture | 7 | DESIGNED FOR, NOT EXPOSED | 5/10 |
| Metrics Layer | 8 | MISSING | 1/10 |
| Knowledge Graph / Graph Queries | 9 | DATA EXISTS, NO QUERY LAYER | 5/10 |
| Global Identity (IRIs) | 10 | LOCAL UUIDs ONLY | 4/10 |
| Regulatory Consistency | 11 | STRONG | 9/10 |
| Unstructured Data Pipeline | 12 | PARTIAL (SEC only) | 5/10 |
| Semantic Chunking | 13 | BASIC (fixed-size) | 3/10 |
| Metadata Enrichment | 14 | STRONG for structured | 7/10 |
| Vector Embeddings | 15 | DONE (generic model) | 7/10 |
| Croissant Standard | 16 | DONE | 9/10 |
| RAG Infrastructure | 17 | READY, NOT SERVING | 5/10 |
| Hybrid Search | 18 | NOT BUILT | 2/10 |
| GraphRAG | 19 | COMPONENTS EXIST, NOT CONNECTED | 3/10 |
| Context Layer (user intent) | 20 | NOT IMPLEMENTED | 1/10 |
| MCP / API Layer | 21 | NOT IMPLEMENTED | 0/10 |
| Governance (Provenance + Audit) | 22 | STRONG | 8/10 |
| Semantic Maturity Level | 23 | L3, approaching L4 | 6/10 |

**Overall alignment: ~55%** - Strong foundations (data, semantics, governance), weak on the agent-facing surface area (API, MCP, graph queries, metrics, hybrid search).

---

## Top Enhancement Priorities (Ranked by Impact)

### Priority 1: MCP Server + API Layer
**Impact: Unlocks all agentic use cases**

The single highest-leverage item. Without it, the entire knowledge layer is invisible to AI agents. Build a FastAPI service + MCP server that exposes:
- Entity lookup (drug, company, trial by name/ID)
- Graph traversal (N-hop neighborhood of any entity)
- Hybrid search (text query + metadata filters + vector similarity)
- Metrics queries (pre-computed KPIs)
- Provenance-annotated responses (every fact cites its source)

### Priority 2: Metrics Layer (Computed KPIs)
**Impact: Agents can report without hallucinating math**

Create materialized views or a metrics table for domain-specific indicators:
- `drug_pipeline_strength` - active trials by phase, weighted by enrollment
- `patent_cliff_exposure` - days to expiry, generic competition signals
- `evidence_density` - publication count/recency per drug
- `trial_success_rate` - completed vs withdrawn/terminated
- `competitive_intensity` - drugs per mechanism per TA
- `geographic_reach` - trial site country distribution

### Priority 3: GraphRAG Query Engine
**Impact: 3x improvement in LLM accuracy per the document's claim**

Connect the existing vector search (pgvector) with graph traversal (entity_links) into a single query path:
1. Embed the user query
2. Find top-K relevant records via vector search
3. For each result, traverse entity_links to gather structural context
4. Package vector results + graph context + provenance into a single context block
5. Return to agent/LLM for synthesis

### Priority 4: Semantic Definitions + Business Rules
**Impact: Agents understand what data means, not just what it contains**

Two tables:
- `semantic_definitions`: Human/LLM-readable definition for every column and entity type. "What does `clinical_trials.phase` mean? What does a Phase 3 failure signal?"
- `domain_rules`: Encoded pharma business logic. "If drug has Phase 3 completion + no FDA approval after 2 years, flag as potential regulatory risk." These rules become queryable context for agents.

### Priority 5: Canonical IRIs
**Impact: Global addressability for cross-system linking**

Add `canonical_iri TEXT` column to drugs, companies, clinical_trials, pubmed_articles. Pattern: `mz:drug/semaglutide`, `mz:trial/NCT04375227`, `mz:company/cik-0001000694`. This enables:
- RDF/JSON-LD export for true linked data
- External systems referencing our entities
- MCP tools returning globally unique identifiers

### Priority 6: Private Data Integration
**Impact: Moves from "Core Knowledge" to "High Value Zone"**

Activate the USER_DOCUMENT and USER_URL connectors with:
- PDF/DOCX parser (extract text + structure)
- Semantic chunking (paragraph/section-aware, not fixed-size)
- Entity resolution against the existing knowledge graph
- NLP metadata enrichment (detected drugs, companies, sentiment, dates)

### Priority 7: Hybrid Search Module
**Impact: Precision retrieval for RAG**

A `HybridSearchEngine` class that combines:
1. Metadata pre-filtering (date range, source type, entity filters)
2. Vector similarity search (pgvector cosine distance)
3. Result ranking (metadata relevance + vector similarity + graph centrality)
4. Provenance annotation (every result cites source, confidence, freshness)

---

## Conclusion

Market-Zero has built a **remarkably solid data backbone** - the Semantics and Identity pillars are strong, Governance is in place, and the 5-stage pipeline (Raw -> Metadata -> Semantic -> Graph) is implemented through Stage 4.

The critical gap is the **last mile to agentic AI**: the data is structured, connected, quality-scored, and provenance-tracked, but no AI agent can access it. Building the MCP/API layer, metrics layer, and GraphRAG query engine would complete the bridge from "enterprise data" to "agentic intelligence" that the Semantic Backbone framework describes.

On the maturity model: Market-Zero is solidly at **L3 (Platform-Native Governance)** and partially at **L4 (Enterprise Knowledge Graph)**. The path to **L5 (Agentic Reasoning)** requires the 7 enhancements listed above, with the MCP server being the most impactful single step.
