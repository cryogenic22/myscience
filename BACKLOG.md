# Market-Zero Platform Backlog

## Architecture Vision

Market-Zero is evolving from a pharma-specific intelligence pipeline into a **domain-agnostic dark-data-to-AI-ready engine**. The core pipeline (fetch → normalize → resolve → embed → store → cross-link) is reusable; domain-specific behavior is declared via **Domain Packs**.

```
┌─────────────────────────────────────────────────────────┐
│                   Applications                          │
│  Market-Zero (Pharma) │ Omics Pack │ Lab Data Pack │ …  │
├─────────────────────────────────────────────────────────┤
│                   Domain Packs                          │
│  EntitySchema · LinkRules · FieldMaps · MentionNorm     │
├─────────────────────────────────────────────────────────┤
│               Pipeline Engine (Generic)                 │
│  Connectors → Normalize → Resolve → Embed → Store      │
│  Hooks · Quality · HITL · Catalog · Cross-Link          │
├─────────────────────────────────────────────────────────┤
│           Infrastructure (Postgres + pgvector)          │
└─────────────────────────────────────────────────────────┘
```

---

## Implemented Features

### Core Pipeline Engine
- [x] 5-step ETL pipeline: fetch → normalize → resolve → embed → store → cross-link
- [x] BaseConnector interface with health checks and provenance
- [x] RawRecord universal contract (record_type, external_id, data, identifiers, provenance)
- [x] SHA-256 content hashing for change detection
- [x] ETL run lifecycle tracking (create → finalize/fail)
- [x] Pipeline hooks system (PRE_STORE, POST_STORE, ON_RUN_COMPLETE, ON_NEW_ENTITY, etc.)

### Domain Pack Architecture
- [x] EntitySchema dataclass — declares entity config in one place
- [x] DomainPack — bundles entities, link rules, field mappings, sources, ontologies
- [x] DomainRegistry — singleton for loading/switching domain packs
- [x] MentionNormalizer — pluggable name cleaning per entity type
- [x] Pharma domain pack — reference implementation extracting all pharma-specific config
- [x] Pipeline components wired to domain pack (normalizer, resolver, cross-linker, quality, hooks)
- [x] Backward-compatible: works with or without a domain pack registered

### Entity Resolution (6-Strategy Cascade)
- [x] Strategy 1: Exact ID lookup (NCT, PMID, NDA, MeSH, CIK, ORCID)
- [x] Strategy 2: Alias table lookup (previously confirmed matches)
- [x] Strategy 3: Fuzzy match (pg_trgm trigram similarity)
- [x] Strategy 4: Embedding similarity search (pgvector cosine distance)
- [x] Strategy 5: LLM-based analysis (GPT-4o-mini candidate selection)
- [x] Strategy 6: Auto-create entity (from credible sources)
- [x] Resolution audit trail (every decision logged)
- [x] Unresolved entity queue with suggested matches
- [x] Domain-configurable: lookup maps, fuzzy fields, skip terms, LLM prompt from pack

### Data Quality Engine
- [x] 6 evaluator types: completeness, freshness, consistency, cross_source, embedding_coverage, naming_consistency
- [x] 25 quality rules (seeded via seed_quality_and_catalog.py)
- [x] Composite scoring with severity weights
- [x] Per-record assessment + batch table scan
- [x] Quality results persisted to data_quality_results table
- [x] Domain-configurable: entity table maps from domain pack

### Pipeline Hooks
- [x] ValidationGateHook (PRE_STORE) — required/recommended field validation
- [x] ChangeDetectionHook (PRE_STORE) — skip unchanged records
- [x] QualityGateHook (POST_STORE) — quality assessment + HITL escalation
- [x] NewEntityReviewHook (ON_NEW_ENTITY) — auto-create approval
- [x] StalenessHook (ON_RUN_COMPLETE) — mark stale records
- [x] UnresolvedProcessorHook (ON_RUN_COMPLETE) — auto-resolve high-confidence entities
- [x] HITLEscalationHook (ON_QUALITY_FAIL) — priority-based review queue
- [x] Domain-configurable: validation schema, staleness map from domain pack

### HITL (Human-in-the-Loop)
- [x] Review queue with priority levels (10=critical, 40=warning, 80=info)
- [x] Review types: quality_failure, new_entity, entity_resolution, enrichment_needed
- [x] HITLReviewManager with get_pending, resolve, get_stats
- [x] Alias auto-creation on approval

### Connectors (10 Pharma Sources)
- [x] MeSH Ontology — therapeutic areas + mechanisms of action
- [x] FDA Orange Book (drugsfda) — drugs, regulatory milestones, patents
- [x] ClinicalTrials.gov — trials, outcomes, locations, investigators
- [x] PubMed — literature with MeSH terms
- [x] PMC — full-text articles
- [x] SEC EDGAR — company filings, financial data
- [x] FDA Drug Shortages — market events
- [x] OpenFDA FAERS — adverse events
- [x] OpenFDA Labels — drug labels
- [x] User Documents / URLs — uploaded content

### Data Normalization
- [x] Source name canonicalization (SOURCE_CANONICAL dict)
- [x] Field mapping per source type (FIELD_MAPS / domain pack)
- [x] Dot notation for nested field paths

### Embeddings
- [x] OpenAI text-embedding-3-small (1536 dimensions)
- [x] Per-entity embedding columns (molecule, strategy, protocol, abstract, scope_note)
- [x] Backfill script for retroactive embedding generation
- [x] 100% coverage across all entity types

### FAIR Compliance
- [x] 8-dimension FAIR analysis script (fair_analysis.py)
- [x] Source authority normalization (migration 012)
- [x] Expanded MeSH ontology (17 TAs, 25+ MoAs)
- [x] Quality scoring coverage (96.6%)
- [x] Unresolved entity batch processor (process_unresolved.py)

### Dataset Catalog
- [x] Croissant JSON-LD metadata generation
- [x] Completeness, freshness, and imbalance metrics
- [x] RAI framework compliance

---

## In Progress

### Entity Consolidation
- [ ] Drug deduplication (resolve 49-semaglutide problem)
- [ ] Company deduplication (merge hollow auto-created companies)
- [ ] Retroactive resolution sweep (clear 90% of unresolved queue via exact match)

### FAIR Score Improvement
- [ ] Target: 8.5/10 (currently 4.7/10)
- [ ] Key gaps: entity resolution (0.1), company enrichment (0.0), drug completeness (0.4)
- [ ] Patent data source (openFDA doesn't expose patents; need alternative)

---

## Planned

### P1: Generic Store Engine
- [ ] Generic `_store_entity()` method driven by EntitySchema column declarations
- [ ] Replaces 15 per-type `_store_*` methods with config-driven SQL generation
- [ ] COALESCE-based upsert pattern generated from schema
- [ ] Reduces ~800 lines of storage code to ~100

### P2: Entity Consolidation Engine
- [ ] EntityConsolidator class: find duplicates → merge → update references
- [ ] Merge strategy: keep richest record, absorb aliases from others
- [ ] Cross-link migration (update entity_links to point to canonical entity)
- [ ] Resolution audit trail for merges
- [ ] Configurable per domain pack (merge rules, dedup thresholds)

### P3: Mention Normalization in Pipeline
- [ ] Wire MentionNormalizer into EntityResolver._auto_create_drug()
- [ ] Apply before fuzzy matching to improve resolution rates
- [ ] Domain pack declares normalizer per entity type

### P4: Patent Data Alternative
- [ ] Orange Book patent data from FDA's direct download files (not openFDA API)
- [ ] Or: Google Patents API for broader coverage
- [ ] Patent → Drug linkage via application number

### P5: Retroactive Resolution Sweep
- [ ] SQL script to match unresolved entities against current DB by exact name
- [ ] Expected to resolve 90% of 42K unresolved entities
- [ ] Create aliases for all resolved matches

### P6: Company Enrichment Pipeline
- [ ] SEC EDGAR bulk CIK lookup for auto-created companies
- [ ] OpenCorporates API for international companies
- [ ] Enrich: ticker, CIK, country, SIC code, industry classification

### P7: Schema Migration Generator
- [ ] Generate SQL CREATE TABLE from EntitySchema declarations
- [ ] Auto-generate migration files for new domain packs
- [ ] Validate existing schema matches domain pack declarations

---

## Future / Aspirational

### Domain Packs

#### Genomics / Omics Domain Pack
- [ ] Entity types: Gene, Protein, Variant, Pathway, GO_Term, Disease
- [ ] Sources: NCBI Gene, UniProt, ClinVar, KEGG, Gene Ontology
- [ ] Ontologies: Gene Ontology (GO), Human Phenotype Ontology (HPO)
- [ ] Link types: IN_PATHWAY, TARGETS_PROTEIN, HOMOLOGOUS_TO, VARIANT_OF
- [ ] Mention normalizer: gene symbol cleaning (TP53 vs p53 vs tumor protein p53)
- [ ] Embedding: protein sequence embeddings (ESM-2), gene description embeddings

#### Lab Data / ELN Domain Pack
- [ ] Entity types: Sample, Assay, Instrument, Experiment, Batch, Protocol, Reagent
- [ ] Sources: ELN connectors (Benchling, Signals, LIMS), instrument parsers
- [ ] Link types: FROM_BATCH, PROCESSED_BY, USES_PROTOCOL, CONTAINS_RESULT
- [ ] Quality rules: sample integrity, calibration freshness, protocol version
- [ ] Mention normalizer: sample ID format validation, reagent name cleaning

#### Materials Science Domain Pack
- [ ] Entity types: Compound, Crystal, Property, Experiment, Instrument
- [ ] Sources: Materials Project API, ICSD, CSD, internal instruments
- [ ] Ontologies: Chemical Entities of Biological Interest (ChEBI)

#### Regulatory Affairs Domain Pack
- [ ] Entity types: Submission, Dossier, Module, Question, Response, Commitment
- [ ] Sources: eCTD parsers, regulatory correspondence, FDA/EMA databases
- [ ] CDISC/MedDRA ontology alignment

### Pipeline Engine Enhancements

#### Pre-Processing Layer
- [ ] OCR/HTR connector for scanned documents (Tesseract, Transkribus)
- [ ] Binary format parsers (NMR, HPLC, MS proprietary formats)
- [ ] Image metadata extraction (pathology slides, microscopy)
- [ ] PDF structure parser (section-aware extraction for CSRs/protocols)

#### Streaming Ingestion
- [ ] Real-time connector interface (WebSocket, Kafka)
- [ ] Micro-batch processing for high-frequency instrument data
- [ ] IoT sensor data pipeline (bioreactor monitoring)

#### Multi-Ontology Registry
- [ ] Pluggable ontology system beyond MeSH
- [ ] CDISC, MedDRA, OMOP, SNOMED-CT, Gene Ontology, UniProt
- [ ] Cross-ontology mapping (MeSH term ↔ SNOMED concept)
- [ ] Ontology version management

#### Advanced Entity Resolution
- [ ] Blocking strategies for large-scale entity matching
- [ ] Active learning: use HITL feedback to improve resolution models
- [ ] Cross-domain entity linking (drug ↔ gene target ↔ pathway)
- [ ] Graph-based resolution (leverage entity_links for transitive matching)

#### GraphRAG Module (Critical)
A first-class graph-aware retrieval-augmented generation layer that treats `entity_links` as a traversable knowledge graph.
- [ ] **Graph traversal engine** — BFS/DFS over entity_links with configurable depth, edge-type filters, and confidence thresholds
- [ ] **Subgraph extraction** — given a query entity, extract the N-hop neighborhood as context for LLM prompts
- [ ] **Graph-augmented retrieval** — hybrid retriever: vector similarity + graph proximity scoring (entities connected to query entity rank higher)
- [ ] **Path-based reasoning** — find and narrate paths between entities (e.g., "Drug A → targets mechanism M → shared by Drug B → investigated in Trial T")
- [ ] **Graph summarization** — LLM-generated summaries of entity neighborhoods for dashboard/API consumers
- [ ] **Pluggable graph backend** — abstract interface so the same GraphRAG logic works over Postgres entity_links, Neo4j, or Neptune

#### Ontology Layer Creator
Pluggable ontology management system that goes beyond MeSH to support arbitrary ontologies per domain pack.
- [ ] **OntologyRegistry** — register multiple ontologies per domain pack (MeSH, GO, SNOMED, MedDRA, custom)
- [ ] **Ontology ingestion connector** — generic OWL/OBO/SKOS parser that loads any ontology into a common schema (term, parent, tree_numbers, scope_note)
- [ ] **Cross-ontology mapping** — mapping table between terms across ontologies (MeSH C04 ↔ SNOMED 363346000)
- [ ] **Ontology-driven entity enrichment** — auto-tag entities with ontology terms based on text/embedding similarity
- [ ] **Hierarchical navigation** — tree traversal APIs (ancestors, descendants, siblings) for any registered ontology
- [ ] **Ontology version management** — track ontology versions, detect term deprecation, auto-update entity tags

#### Knowledge Graph Abstraction Layer
Switchable backend so the pipeline can use Postgres entity_links today and migrate to a dedicated graph DB when scale demands it.
- [ ] **GraphStore interface** — abstract class: `upsert_node()`, `upsert_edge()`, `traverse()`, `subgraph()`, `shortest_path()`
- [ ] **PostgresGraphStore** — implementation over existing `entity_links` + entity tables (current behavior)
- [ ] **Neo4jGraphStore** — implementation using Neo4j Bolt driver, nodes = entities, edges = entity_links
- [ ] **NeptuneGraphStore** — AWS Neptune/Gremlin implementation for cloud deployments
- [ ] **Graph sync pipeline** — hook that mirrors entity_links changes to the active graph backend in real-time
- [ ] **Temporal graph** — track relationship evolution over time (edge versioning with valid_from/valid_to)
- [ ] **Confidence-weighted traversal** — edge weights from resolution confidence + quality scores, used in path ranking

#### Quality & Governance
- [ ] GxP-compliant audit trails (21 CFR Part 11, Annex 11)
- [ ] Data lineage visualization (source → transform → output)
- [ ] Bias detection in training datasets
- [ ] Automated FAIR scoring per dataset (F-UJI integration)
- [ ] Data access control per entity type / source

#### AI-Ready Output Layer
- [ ] Vector store export (Pinecone, Weaviate, Qdrant)
- [ ] Knowledge graph export (RDF, JSON-LD)
- [ ] Training dataset generation (fine-tuning datasets from curated entities)
- [ ] Agentic API: tool-use endpoints for LLM agents
- [ ] Confidence-filtered views (only return data above threshold)

#### Cost Optimization
- [ ] SLM (Small Language Model) for entity resolution instead of GPT-4
- [ ] Knowledge distillation: train domain-specific resolution model
- [ ] Tiered embedding models (small for bulk, large for precision)
- [ ] Incremental embedding updates (only re-embed changed records)

#### Operational
- [ ] Scheduler (cron/Airflow) for periodic connector runs
- [ ] Dashboard: pipeline health, quality scores, HITL queue depth
- [ ] Alerting: stale data, quality degradation, connector failures
- [ ] Multi-tenant: isolated domain packs per organization
- [ ] API gateway for downstream consumers

---

## UI & Intelligence Upgrades

### UI-1: Table Export (CSV Download)
**Priority:** P1 | **Effort:** Low | **Files:** `ChatMessage.tsx`

Add a CSV download button to the DataTable component. When clicked, serializes visible columns/rows to CSV and triggers browser download.

**Spec:**
- Add a download icon button in the DataTable header area (next to title)
- `_exportCsv(columns, rows, title)` helper: builds CSV string with header row, escapes commas/quotes, triggers blob download
- Filename: `{title}-{YYYY-MM-DD}.csv`
- Only exports currently visible columns (respects column definitions)

### UI-2: Keyboard Shortcuts
**Priority:** P1 | **Effort:** Low | **Files:** `IntelligencePage.tsx`

Global keyboard shortcuts for common actions.

**Spec:**
- `Ctrl+K` / `Cmd+K` → focus the chat input
- `Ctrl+Enter` / `Cmd+Enter` → send query (already partial, ensure works from anywhere)
- `Escape` → close any open Drawer (already works), clear suggestions dropdown
- Register via a single `useEffect` with `keydown` listener on `window`
- No external dependency; plain event handling

### UI-3: Follow-Up Question Suggestions
**Priority:** P1 | **Effort:** Medium | **Files:** `api/routes/chat.py`, `ChatMessage.tsx`

After each assistant response, suggest 2-3 contextual follow-up questions.

**Spec:**
- Backend: add `_generate_followups(question, intent, narrative, entity_names) -> list[str]` in chat.py
  - Rule-based (no LLM call): pattern-match intent to generate templates
  - `compare` → "What trials are in Phase 3 for {entity}?", "Show the pipeline for {entity}"
  - `landscape` → "Which companies dominate {area}?", "Compare the top 2 mechanisms"
  - `pipeline` → "What's the success rate for {drug}?", "Compare {drug} vs competitors"
  - `general` → "Deep dive into {first_entity}", "Show related evidence"
- Include `followup_suggestions: list[str]` in the chat response JSON
- Frontend: render as clickable chips below the assistant message
- On click: populate input and auto-send

### UI-4: Dark Mode
**Priority:** P2 | **Effort:** Medium | **Files:** `index.css`, `tailwind.config.*`, multiple components

Theme toggle with CSS custom properties.

**Spec:**
- Define CSS variables in `:root` and `.dark` for surface, text, border, brand colors
- Replace hardcoded `bg-white`, `text-slate-*`, `border-slate-*` with CSS variable references in key surfaces (shell, panels, cards)
- Add toggle button in WorkspaceRail (sun/moon icon)
- Persist preference in `localStorage`
- Use `prefers-color-scheme` media query as default

### UI-5: Collapsible Conversation History Sidebar
**Priority:** P2 | **Effort:** Medium | **Files:** `IntelligencePage.tsx`, new `ConversationSidebar.tsx`

Slide-out panel from the workspace rail showing saved conversation titles.

**Spec:**
- Click the Chat icon in WorkspaceRail when already on chat → toggle sidebar
- Sidebar shows conversation list (already fetched in IntelligencePage: `conversations` state)
- Each item: title (first message truncated), timestamp, delete button
- Click to load conversation
- Slides over content (doesn't push), 280px wide, same blur/glass style
- Close on click outside or Escape

### UI-6: Graph Explorer Polish
**Priority:** P3 | **Effort:** Medium | **Files:** `GraphMini.tsx`

Improve the force-directed graph visualization.

**Spec:**
- Add edge type legend (color-coded by link_type)
- Node size proportional to connection count
- Click node → show tooltip with entity details
- Filter checkboxes for entity types (drug, trial, company, etc.)
- Zoom controls (+/- buttons)

### INT-1: Multi-Turn Conversation Memory
**Priority:** P1 | **Effort:** Medium | **Files:** `api/routes/chat.py`, `services/agent/graphs/query_graph.py`

Enrich follow-up queries with context from previous turns.

**Spec:**
- Track per-conversation: entities discussed, metrics shown, intents used
- On follow-up, inject context: "Previous discussion covered: {entities}. Metrics shown: {metrics_types}."
- Use the existing `_sqlContext` field plus new `_conversationContext` on Message
- Pass to `_synthesize()` as additional context block
- Limit to last 3 turns to avoid context bloat

### INT-2: Streaming Synthesis (SSE)
**Priority:** P2 | **Effort:** Medium-High | **Files:** `api/routes/chat.py`, `IntelligencePage.tsx`, `ChatMessage.tsx`

Stream LLM synthesis tokens to the frontend via Server-Sent Events.

**Spec:**
- New endpoint `POST /api/chat/stream` returning `text/event-stream`
- Tool execution phase: send `event: status` with progress messages ("Querying database...", "Searching evidence...")
- Synthesis phase: stream tokens as `event: token` with `data: {text}`
- Final event: `event: done` with full structured response (data, visualizations, etc.)
- Frontend: `EventSource` or `fetch` with `ReadableStream`, append tokens to message content in real-time
- Fallback: existing `/api/chat` endpoint unchanged

---

## UX & Intelligence Overhaul (v2)

> Root-cause analysis found 6 systemic problems:
> 1. **Visual clutter** — Every section wrapped in rounded bordered boxes creating "pill soup"
> 2. **Data dump responses** — LLM forced into prose mode; no tabular/structured output path
> 3. **Charts broken by default** — Insight Charts collapsed; Recharts gets 0-size container
> 4. **Navigation opaque** — Data Catalog and Graph Explorer lack purpose/guidance
> 5. **Intelligence is shallow** — No format-aware routing; metrics passed as raw JSON to LLM
> 6. **Response sections poorly ordered** — Table/chart buried under collapsed sections

### UX-01: Strip Visual Clutter from Response Cards
**Priority:** P0 | **Effort:** Low | **Files:** `ChatMessage.tsx`

The response area has 6+ nested `rounded-md border border-slate-200/80 bg-white/78` boxes stacked vertically. Every section (report, persona, table, charts, entities, metrics, graph, evidence) gets its own bordered pill. This creates overwhelming visual noise.

**Spec:**
- Remove the outer `rounded-md border bg-white/78` wrapper from: DataTable, VisualizationCard, PersonaCard, entity grid, metric grid, evidence section
- Instead use lightweight separators: a single `border-t border-slate-100 pt-3 mt-3` between sections
- Keep the section header (chevron + label) but style it as inline text, not a button inside a box
- The only sections that should keep a bordered container: the full Deep Research Brief (because it's long scrollable content) and individual EvidenceCards (because they're discrete items)
- Entity cards and metric cards keep their own borders (they're standalone cards), but their parent wrapper should have no border
- Result: cleaner visual hierarchy with content flowing naturally instead of box-in-box-in-box

**Before:** Box > Box > Box > Content
**After:** Content separated by subtle lines

### UX-02: Reorder Response Sections for Impact
**Priority:** P0 | **Effort:** Low | **Files:** `ChatMessage.tsx`

Currently: Report → Persona → Table → Charts → Entities → Metrics → Graph → Evidence. Charts are collapsed by default, so users never see them. Tables are buried below persona analyses.

**Spec:**
- New order: **Table → Charts → Entities+Metrics → Graph → Evidence → Report → Persona**
- Tables come first because they're the structured answer the user is most likely looking for
- Charts render immediately after tables (they visualize the same data)
- Charts should be **open by default** (remove the collapsed toggle; just render them)
- If there's only narrative (no table/chart/entity), the narrative stands alone — no empty sections
- Move the collapse toggle to Evidence only (it's supplementary) and Report (it's long)
- Entities and Metrics render in a single row: entities left, metrics right (on desktop)

### UX-03: Fix Chart Rendering (Recharts 0-Dimension Bug)
**Priority:** P0 | **Effort:** Low | **Files:** `ChatMessage.tsx`

Charts inside collapsed containers get `width=0, height=0` from Recharts' ResponsiveContainer because the parent has `display:none`. When expanded, Recharts doesn't re-measure.

**Spec:**
- Remove the collapse wrapper around charts entirely (per UX-02, charts are always visible)
- Add `minHeight: 200` to the chart container div as a CSS fallback
- Add `key={spec.id}` on ResponsiveContainer to force remount if data changes
- Guard: if `spec.data.length === 0` or all values are 0, don't render the chart at all (already partially done)
- For the donut chart: increase `outerRadius` from 62 to 80, `innerRadius` from 36 to 50 (it's too small)
- Add the chart legend (Recharts `<Legend>` component) so users know what each color means
- For bar chart: add `<Legend>` and increase bottom margin to prevent label truncation

### UX-04: Tabular Intent Detection + Table Generation
**Priority:** P0 | **Effort:** Medium | **Files:** `api/routes/chat.py`, `services/agent/presenter.py`

"Give me a tabular analysis" returns prose because:
1. No intent detection for format requests (table/structured/breakdown)
2. `presenter.py` only builds tables for >15 rows; 1-15 rows get charts
3. Most handlers (landscape, pipeline, portfolio) never produce `table_data`

**Spec:**

A) **Format hint detection** in `detect_intent()`:
- Add `detect_format_hint(question) -> str | None` — returns `"table"`, `"chart"`, or `None`
- Regex patterns: `r"\b(table|tabular|rows|columns|spreadsheet|csv|breakdown|list all)\b"` → `"table"`
- Regex patterns: `r"\b(chart|graph|plot|visualize|bar chart|pie chart)\b"` → `"chart"`
- Pass format_hint through the handler chain

B) **Presenter override** in `plan_presentation()`:
- If `format_hint == "table"` and SQL result has rows: always choose `display = "table"`, build `table_data`
- If `format_hint == "chart"`: keep existing chart logic
- If no hint: use existing data-shape heuristic

C) **Table generation in non-SQL handlers**:
- `_handle_landscape()`: Build `table_data` from segments (columns: Mechanism, TA, Drug Count, Trial Count, Pipeline Score)
- `_handle_pipeline()`: Build `table_data` from pipeline metrics (columns: Drug, Phase 1-4, Total, Score)
- `_handle_portfolio()`: Build `table_data` from portfolio rows (columns: Company, Drugs, Trials, Active, Articles, Score)
- All three: always include `table_data` in return dict, not just when user asks for table

D) **LLM prompt adjustment**:
- When `format_hint == "table"`, change synthesis instructions: "The user asked for tabular/structured output. Write 1-2 sentences summarizing the table below. Do NOT repeat the table contents in prose."
- When no format hint and table_data exists: "A data table is displayed below. Reference it naturally ('as shown in the table') rather than restating all numbers."

### UX-05: Data Catalog Redesign — Add Purpose and Guidance
**Priority:** P1 | **Effort:** Medium | **Files:** `DataCatalogPanel.tsx`

The Data Catalog shows raw database stats (row counts, source names, MeSH IDs) with no explanation of what the user should do with it or what the numbers mean.

**Spec:**
- Add a header description: "Data Catalog shows what's in the knowledge base — the sources, coverage, and entities that power the AI. Use it to understand data freshness and completeness."
- **Source Coverage section**:
  - Rename to "Data Sources & Freshness"
  - Add a freshness indicator per source (green/amber/red dot based on `last_retrieved`)
  - Show percentage of expected records pulled (if `total_records` available: `records/total_records * 100%`)
  - Add tooltip on each source: "Clinical trials data from ClinicalTrials.gov. Last pulled: {date}. {N} records."
- **System Tables section**:
  - Rename to "Knowledge Base Contents"
  - Show entity counts with human-readable labels: "1,672 Drugs" not "drugs: 1672"
  - Add a small bar proportional to count (visual indicator of relative size)
- **Therapeutic Areas section**:
  - Show drug_count and trial_count in each TA card as mini bar charts instead of just numbers
  - Add "Explore in Chat" button per TA → navigates to chat with pre-filled "What is the competitive landscape for {TA}?"
- **Mechanisms section**:
  - Replace raw entity_id display with just the mechanism name
  - Add "Ask about this" button → pre-fills chat query
- Remove monospace `entity_id` display from TA and Mechanism cards — users don't need UUIDs

### UX-06: Graph Explorer — Add Onboarding and Purpose
**Priority:** P1 | **Effort:** Medium | **Files:** `GraphExplorer.tsx`

The Graph Explorer drops users into an empty canvas with a search box and 4 "exploration objectives" that aren't explained. Users don't know what to do.

**Spec:**
- **Empty state**: Instead of blank canvas, show a centered guide:
  - "Search for a drug, company, or therapeutic area to explore its connections"
  - 3-4 clickable example entities (pre-populated from top drugs/companies in the database)
  - Brief explanation of each objective:
    - Adjacency: "See all direct relationships"
    - Trial Evidence: "Focus on clinical trials and publications"
    - Portfolio: "See company ownership and drug portfolios"
    - Mechanism: "Explore drug mechanisms and therapeutic areas"
- **Sidebar insight labels**: Replace "Exploration Insights" with actionable labels:
  - "Nodes" → "{N} entities found"
  - "Links" → "{N} relationships"
  - "Edge density" → "Connectivity: {dense/moderate/sparse}"
  - "Source domains" → "{N} data sources"
- **High-confidence neighbors**: Add "Ask about this" button next to each neighbor → opens chat with pre-filled question
- **Quick node insight panel** (bottom-right hover card): Add "Compare with {anchor}" button when both anchor and hovered node are same entity type

### UX-07: Domain-Aware LLM Prompts (Eliminate Data Dumps)
**Priority:** P0 | **Effort:** Medium | **Files:** `services/llm.py`

The SYSTEM_PROMPT forces "2-4 paragraphs, NO bullet points or lists, flowing prose." This makes every response feel like a Wikipedia article regardless of what the user asked.

**Spec:**

Replace the monolithic SYSTEM_PROMPT with a **prompt selector** based on intent + format:

A) **Comparison prompt**: "You are comparing {entities}. Structure your response as:
- Lead with the key differentiator (which entity is stronger/weaker and why)
- Use comparative language: 'X has 2.3x more trials', 'Y leads in Phase 3'
- Bold the winner on each dimension
- End with a 1-sentence verdict"

B) **Landscape/overview prompt**: "You are analyzing a market landscape. Structure:
- Lead with the concentration insight (fragmented vs dominated)
- Name the top 3 segments and their distinguishing metric
- Note any outliers or gaps
- Keep to 2-3 sentences; a table is displayed alongside"

C) **Pipeline/metrics prompt**: "You are reporting on pipeline metrics.
- Lead with the headline number and what it means
- Note the phase distribution (early vs late stage)
- Compare to benchmarks if available (e.g., typical Phase 2→3 success ~30%)
- 2-3 sentences max; the data table is shown below"

D) **General/dossier prompt**: "You are briefing an analyst.
- Lead with who/what the entity is
- Key metrics in bold
- Notable trial activity or recent developments
- 2-4 sentences"

E) **Tabular request prompt**: "The user explicitly asked for structured/tabular output. Write 1-2 sentences as a brief summary header. Do NOT restate numbers from the table. Simply describe what the table shows and call out any notable patterns."

F) All prompts: Remove "Do NOT use bullet points or lists" — allow lists when they serve the answer.

### UX-08: Landscape/Pipeline/Portfolio Always Return table_data
**Priority:** P1 | **Effort:** Medium | **Files:** `api/routes/chat.py`

Currently only the Compare handler builds `table_data`. Landscape, Pipeline, and Portfolio return only prose narratives, so the frontend never shows a DataTable or CSV button for these intents.

**Spec:**

A) **`_handle_landscape()`**: After computing segments, build:
```python
table_data = {
    "columns": [
        {"key": "mechanism_name", "label": "Mechanism", "type": "text"},
        {"key": "therapeutic_area", "label": "Therapeutic Area", "type": "text"},
        {"key": "drug_count", "label": "Drugs", "type": "number"},
        {"key": "trial_count", "label": "Trials", "type": "number"},
        {"key": "active_trial_count", "label": "Active Trials", "type": "number"},
        {"key": "total_pipeline_score", "label": "Pipeline Score", "type": "number"},
    ],
    "rows": top_segments,
    "title": "Competitive Landscape"
}
```

B) **`_handle_pipeline()`**: Build table from pipeline metrics:
- Columns: Drug, Phase 1, Phase 2, Phase 3, Phase 4, Total Trials, Pipeline Score, Active Score
- Rows: each drug's metrics

C) **`_handle_portfolio()`**: Build table from portfolio data:
- Columns: Company, Drugs, Trials, Active Trials, Articles, TAs, Pipeline Score
- Rows: each company's metrics

D) Each handler includes `"table_data": table_data` in its return dict.

### UX-09: Navigation — Make Workspace Rail Intuitive
**Priority:** P1 | **Effort:** Low | **Files:** `WorkspaceRail.tsx`

The sidebar shows icon-only navigation with no labels. Users can't tell what the icons mean.

**Spec:**
- Add text labels below each icon on `md:` breakpoint and wider: "Chat", "Search", "Graph", "Data"
- On small screens (`< md`), keep icon-only
- Add tooltip on hover (title attribute) for icon-only mode
- Active tab: keep the brand-color background + add a left border accent (3px brand-color left border)
- Add subtle group labels: top group = "Intelligence" (Chat, Search), bottom group = "Explore" (Graph, Data)
- The back arrow (top) should have a tooltip: "Back to Home"

### UX-10: Entity + Metric Cards — Inline Layout
**Priority:** P1 | **Effort:** Low | **Files:** `ChatMessage.tsx`

Entity cards and Metric cards each get their own grid section with their own bordered wrapper. This wastes vertical space and creates more "box soup."

**Spec:**
- Combine entities and metrics into a single section: "Key Entities & Metrics"
- Layout: responsive grid — on desktop (lg+), entities in left column, metrics in right column; on mobile, stack
- Entity cards: reduce padding from `px-4 py-4` to `px-3 py-2.5`; tighten the property list
- Metric cards: reduce padding similarly; show the key number large + phase bars, hide the expand-to-raw-data feature (it's dev-facing, not user-facing)
- If there are ≤2 entities and ≤2 metrics, use a single horizontal row instead of a grid
- Remove the "raw data" expandable section from MetricCard — users don't need to see `{drug_id: "uuid", ...}`

### UX-11: Evidence Section — Compact Default, Expandable
**Priority:** P2 | **Effort:** Low | **Files:** `ChatMessage.tsx`, `EvidenceCard.tsx`

Evidence cards take up too much space. 10 cards × 4 lines each = 40+ lines of supplementary content pushing the actual answer off-screen.

**Spec:**
- Show evidence section collapsed by default with summary: "Based on {N} evidence sources (Clinical Trials: {X}, Publications: {Y}, ...)"
- When expanded, show cards in a more compact layout:
  - Remove the large index badge (the number circle)
  - Single line per card: "[Source Type] Entity Name — Relevance: 85% — snippet..."
  - Expand individual card on click for full content
- Limit to 5 shown initially with "Show {N} more" button
- Move freshness badge inline with relevance (not on separate line)

### UX-12: Chat Empty State — Guided Onboarding
**Priority:** P2 | **Effort:** Low | **Files:** `IntelligencePage.tsx`

The empty state shows "Ask anything about pharma landscape" with 8 suggestion buttons. The suggestions are generic and don't demonstrate the system's analytical capabilities.

**Spec:**
- Organize suggestions into 3 categories with clear headers:
  - **Compare & Analyze**: "Compare semaglutide vs tirzepatide", "Tabular breakdown of GLP-1 landscape"
  - **Explore**: "What is semaglutide?", "Show me Novo Nordisk's portfolio"
  - **Deep Dive**: "Phase 3 trial analysis for diabetes drugs", "Which mechanisms are most crowded?"
- Each suggestion button should have a tiny icon indicating the type of response:
  - Table icon for queries that return tables
  - Chart icon for visualization queries
  - Document icon for dossier/narrative queries
- Show the current data stats inline: "Covering {N} drugs, {M} trials, {K} articles from {S} sources"

---

## Implementation Order (UX Overhaul v2)

| # | Item | Files | Effort | Why This Order |
|---|------|-------|--------|----------------|
| 1 | UX-01: Strip visual clutter | ChatMessage.tsx | Low | Immediate visual improvement |
| 2 | UX-02: Reorder sections | ChatMessage.tsx | Low | Tables/charts visible first |
| 3 | UX-03: Fix charts | ChatMessage.tsx | Low | Charts now visible and working |
| 4 | UX-10: Inline entity+metric layout | ChatMessage.tsx, MetricCard.tsx | Low | Tighter layout |
| 5 | UX-11: Compact evidence | ChatMessage.tsx, EvidenceCard.tsx | Low | Less clutter |
| 6 | UX-04: Tabular intent + table gen | chat.py, presenter.py | Medium | "Give me table" now works |
| 7 | UX-07: Domain-aware prompts | llm.py | Medium | Better narratives |
| 8 | UX-08: Always return table_data | chat.py | Medium | All intents get tables |
| 9 | UX-09: Navigation labels | WorkspaceRail.tsx | Low | Users know what tabs do |
| 10 | UX-05: Data Catalog redesign | DataCatalogPanel.tsx | Medium | Catalog has purpose |
| 11 | UX-06: Graph Explorer onboarding | GraphExplorer.tsx | Medium | Graph has guidance |
| 12 | UX-12: Chat empty state | IntelligencePage.tsx | Low | Better first impression |

---

## Prioritization Guide

| Priority | Item | Impact | Effort |
|----------|------|--------|--------|
| **P0** | Retroactive resolution sweep | Resolves 90% of unresolved entities | Low |
| **P0** | Entity consolidation (drug dedup) | Fixes 49-semaglutide problem | Medium |
| **P0** | UX-01: Strip visual clutter | Immediate readability improvement | Low |
| **P0** | UX-02: Reorder response sections | Tables/charts visible first | Low |
| **P0** | UX-03: Fix chart rendering | Charts actually display | Low |
| **P0** | UX-04: Tabular intent detection | "Give me table" works | Medium |
| **P0** | UX-07: Domain-aware LLM prompts | Eliminates data-dump narratives | Medium |
| **P1** | Generic store engine | Enables new domain packs without code changes | Medium |
| **P1** | Company enrichment pipeline | Fills biggest FAIR gap | Medium |
| **P1** | UX-05: Data Catalog redesign | Catalog has purpose and guidance | Medium |
| **P1** | UX-06: Graph Explorer onboarding | Graph has guidance | Medium |
| **P1** | UX-08: All handlers return table_data | Every intent gets tables + CSV | Medium |
| **P1** | UX-09: Navigation labels | Users know what tabs do | Low |
| **P1** | UX-10: Inline entity+metric layout | Tighter, less box soup | Low |
| **P2** | Mention normalization in pipeline | Prevents future duplicates | Low |
| **P2** | Patent data alternative | Fills empty patents table | Medium |
| **P2** | GraphRAG module | Graph-aware retrieval for LLM applications | Medium |
| **P2** | UX-11: Compact evidence cards | Less supplementary clutter | Low |
| **P2** | UX-12: Chat empty state redesign | Better first impression | Low |
| **P0** | SPEC-001: Autonomous Research Engine | Full pipeline redesign: CTX knowledge corpus + staged retrieve→reason→synthesize + autonomous research loop + conversation memory. 4 phases, 10 steps, ~23 days. Spec: `specs/SPEC_001_autonomous_research_engine.md`. Leverages CTX_mod (hydration, entity graph, context guard, grounding, agent session, benchmarks). | Very High |
| **P1** | Entity resolution consolidation | Deduplicate _resolve_entity across chat.py, search.py, graph.py into single shared service. Part of SPEC-001 Phase 2. | Medium |
| **P1** | Caching layer (Redis or in-memory) | Entity dossier does 6 DB calls per request with no caching. Add TTL cache for hot entities/metrics | Medium |
| **P2** | Materialized view auto-refresh | Hook into pipeline_hooks.py ON_RUN_COMPLETE to refresh metrics views automatically | Low |
| **P3** | Knowledge graph abstraction | Switchable Postgres/Neo4j/Neptune backend | Medium |
| **P3** | Genomics domain pack | First non-pharma domain proof-of-concept | High |
| **P5** | GxP compliance | Regulatory readiness | High |
| **P5** | Multi-tenant architecture | Enterprise deployment | Very High |
