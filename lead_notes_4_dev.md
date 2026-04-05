
MARKET ZERO
Sprint Plan & Technical Assessment
Next 3 Sprints: From Infrastructure to Intelligence Experience

Architecture Review — 5 April 2026
CONFIDENTIAL
 
1. Where We Stand Today
After 40 commits, the codebase has grown to 145 source files, 1,078 backend tests, 29 database migrations, and a React 19.2 frontend with 50+ components. The session delivered genuine value across Entity Library redesign, Concept Registry integration, scorer tightening, data pipeline fixes, and the Agent Harness architecture. However, three structural gaps remain that will limit the platform’s trajectory if not addressed in the next cycle.
1.1 Scorecard
Area	Status	Quality	Gap
Entity Library redesign	Shipped	Solid	No frontend tests
Agent Harness (7 components)	Shipped	Excellent	Not wired into production
Concept Registry (15 concepts)	Shipped	Solid	In-memory only, no DB
Scorer tightening	Shipped	Solid	Need adversarial queries
FAIR Scorer	Shipped	Good	Integrated via DI
CTX value report	Shipped	Good	Requires telemetry data
Insight Engine (3 signals)	Shipped	Good	No UI integration
Entity Agents (4 types)	Shipped	Good	Not harness-managed
Benchmark v3	Live	Honest	81.6% — dossier needs work
Data pipeline fixes	Shipped	Solid	NADAC API deprecated
Frontend tests	Missing	—	0 tests on 50+ components
Graph consolidation	Needed	—	4 overlapping components

1.2 The Three Structural Gaps
Gap 1 — The Harness is shelf-ware. The session’s largest investment (7 components, 102 tests, migration 029) is never called in production. Chat handlers invoke LangGraph directly. DataSteward runs independently. No DI registration exists. Every week this sits unintegrated makes it harder to justify.

Gap 2 — Zero frontend test coverage. 50+ React components, several over 1,000 lines, with no Vitest/RTL tests despite the project’s own testing guide mandating them. A single regression in DataCatalogPanel (1,484 lines) or ChatMessage (906 lines) would ship to production uncaught.

Gap 3 — The UX is five tools in tabs, not one intelligence platform. Chat, Search, Graph, Feed, and Entity Library operate independently. Entity mentions in chat don’t link to graph context. Graph insights don’t feed back into chat. The knowledge graph—Market Zero’s core differentiator—is hidden behind a tab most users never click.

2. Sprint 1: Wire, Test, Stabilise (2 Weeks)
This sprint closes the infrastructure gaps from the last session. No new features. Every item here is about making what we built actually work in production and protecting it with tests.
2.1 Wire the Agent Harness
The harness needs three integration points to become production infrastructure rather than shelf-ware.
Task 1A: Add DI Registration
Add get_harness() to api/deps.py following the existing pattern (db+config constructor, @lru_cache). This is the entry point for all production usage.
Task 1B: Register Tool Executors
The ToolRegistry has 13 tool metadata declarations but zero executors. Register executor functions that delegate to existing services: sql_query delegates to QueryEngine, rag_search to HybridSearch, metrics_query to PharmaMetrics, steward_curate to DataSteward. The executor functions are thin wrappers—the logic already exists.
Task 1C: Route DataSteward Through Harness
Replace the direct DataSteward.run_loop() call in api/app.py’s background loop with harness.run(agent_type="data_steward", steps=[...]). This gives us session tracking, event logging, permission enforcement, and checkpoint recovery for the steward’s 2-hour autonomous cycle. The steward’s existing logic stays untouched—the harness wraps it.
Task 1D: Route LangGraph Agents Through Harness
In services/chat_handlers/handlers.py, replace direct get_query_graph().invoke() calls with harness.run(agent_type="query", steps=[...]). This activates the permission engine for chat queries and writes to agent_events so we have observability over what the LLM is doing.
Acceptance Criteria
•	agent_sessions and agent_events tables populated after a chat query
•	DataSteward background loop creates session records with checkpoints
•	GET /agent/events returns real production events, not empty arrays
•	All 1,078 existing tests still pass
2.2 Add Frontend Test Infrastructure
Task 2A: Vitest + RTL Setup
Install Vitest, @testing-library/react, and jsdom. Configure vitest.config.ts for the existing Vite + Tailwind + React 19 stack. Add a test script to package.json.
Task 2B: Tests for Critical Components
Write tests for the 5 highest-risk components based on line count and user impact:
1.	ChatMessage.tsx (906 lines) — test citation rendering, entity highlighting, chart embedding, error states
2.	DataCatalogPanel.tsx (1,484 lines) — test entity type filtering, FAIR bar rendering, profile drawer opening
3.	EntityProfileCard.tsx (751 lines) — test FAIR score display, connection rendering, loading/error states
4.	SearchResults.tsx (617 lines) — test result rendering, filter interactions, empty states
5.	KnowledgeGraph.tsx (774 lines) — test node rendering, zoom/pan interactions, tooltip display
Acceptance Criteria
•	vitest --run passes with ≥15 frontend test cases
•	Test coverage reported for the 5 critical components
•	CI can run frontend + backend tests in parallel
2.3 Global Error Boundary
Add a top-level ErrorBoundary component in App.tsx that catches unhandled exceptions, shows a user-friendly fallback (“Something went wrong. Refresh to continue.”), and logs the error to /feedback endpoint for tracking. This is a 2-hour task with outsized production impact—currently a single component crash kills the entire application.
2.4 Graph Component Consolidation
Merge GraphMini.tsx and ModernGraph.tsx into KnowledgeGraph.tsx with a mode prop (compact | full | explorer). Remove the two deprecated components. Update all import sites (EntityPreview, CanvasPanel, SearchResults). This eliminates 900+ lines of duplicate canvas-rendering code and establishes a single graph renderer the team can invest in.
2.5 Dossier Score to 85%
Dossier is at 70.3%—the weakest of the core intents. The lead notes correctly identify few-shot examples as the fix. Add 5–8 exemplar dossier responses to the system prompt in handle_dossier(), covering: drug dossier with citations, company dossier with portfolio metrics, mechanism dossier with competitive context. Re-run benchmark targeting ≥85% dossier score. Also add 3 adversarial dossier queries to the golden dataset that test for hallucinated numbers.
 
3. Sprint 2: Intelligence Experience (2 Weeks)
With the infrastructure stable and tested, this sprint focuses on the UX gap: making graph-based insights visible on every surface rather than hidden behind a tab.
3.1 Entity Mention Popovers in Chat
When the user hovers over a highlighted entity name in a chat response (drug: blue, company: amber, mechanism: violet), show a compact popover card with: entity type icon, FAIR score bar, top 3 connections with link types, and a “View Profile” action. This brings graph context into the reading flow. Implementation: extend EntityMention.tsx with a delayed hover trigger that fetches /graph/summary/{type}/{id} and renders a positioned popover. Use Framer Motion for smooth enter/exit.
3.2 Evidence Provenance Chips
Replace bare [1] [2] citation markers in NarrativeMessage.tsx with clickable chips showing the source type icon (PubMed beaker, ClinicalTrials.gov shield, FDA flag) and a confidence dot (green/amber/red based on source tier). Clicking a chip expands the evidence card inline beneath the paragraph. This makes trust visible without requiring users to scroll to a separate evidence section.
3.3 Chat ↔ Graph Bidirectional Handoff
Two complementary features that connect the chat and graph experiences:
•	Chat → Graph: After each response that mentions entities, show a “View in Graph” button. Clicking it opens GraphExplorer pre-seeded with those entities at 1-hop expansion.
•	Graph → Chat: Right-clicking a graph node offers “Ask about this”, “Compare with...”, and “Generate dossier”. These inject pre-formed questions into the chat input. The user sees the question and can edit before sending.
3.4 Inline Mini-Graph in Responses
For landscape, compare, and pipeline intent responses, embed a compact (300×200px) KnowledgeGraph directly in the chat message body. The graph shows the entities discussed and their relationships as a visual summary of the answer. Use KnowledgeGraph in compact mode (no controls, fixed layout, click-to-expand). This is the single highest-impact UX change—it makes the knowledge graph visible without requiring users to navigate away from chat.
3.5 Search Graph View Mode
Add a fourth view mode button (list | grid | detail | graph) to SearchResults.tsx. In graph mode, search results render as a force-directed graph where nodes are results (sized by influence, coloured by entity type) and edges show relationships between them. Users can see at a glance how their search results connect—which is the core value proposition of a knowledge graph platform. Uses KnowledgeGraph in full mode with the search result entities as seed nodes.
3.6 Entity Activity Feed
Add a “Recent Activity” section to EntityProfileCard.tsx showing the last 10 events for that entity: new trials, articles, safety signals, phase changes, steward actions. Source from the intelligence_events table via a new /catalog/entity-events/{type}/{id} endpoint. This transforms entity profiles from static data sheets into living intelligence cards.
Sprint 2 Acceptance Criteria
•	Entity hover popovers render within 200ms on cached data
•	Citation chips show correct source type icons for PubMed, ClinicalTrials.gov, and FDA sources
•	Chat-to-Graph button opens GraphExplorer with correct pre-seeded entities
•	Graph right-click menu correctly injects questions into chat input
•	Inline mini-graphs render for landscape/compare/pipeline responses
•	Search graph view shows entity relationships between results
•	Entity profiles show real activity events with timestamps
 
4. Sprint 3: Data Quality & Proactive Intelligence (2 Weeks)
This sprint focuses on two themes: making the data better and making the system proactively surface insights rather than waiting for users to ask.
4.1 Concept Registry Database Backing
The Concept Registry is currently 15 hardcoded concepts loaded in-memory. Move to database-backed storage with migration 030 creating a concepts table (id, name, description, computation_path, intents, entity_types, staleness_days, weight, active, created_at, updated_at). Modify ConceptRegistry to load from DB with in-memory cache and cache invalidation on write. This enables: adding concepts without deploys, A/B testing concept weights, tracking which concepts get activated most, and preparing for the feedback loop where query patterns adjust concept weights.
4.2 Feedback Loop: Query Patterns → Concept Weights
The query_telemetry table already captures every question, detected intent, and response quality. Build a scheduled job (hourly) that analyses the last 7 days of telemetry to identify: which concepts are activated most frequently, which concept activations correlate with high benchmark scores, and which intents have declining quality. Output: adjusted concept weights written to the concepts table. This is the first real feedback loop in the semantic layer vision—the system learns which analytical primitives are most valuable from actual usage.
4.3 Proactive Intelligence Feed
The InsightEngine (services/insight_engine.py) detects 3 signal types but the IntelligenceFeed component (151 lines) only renders them as a flat list. Upgrade to contextualised, actionable cards:
1.	Graph-enriched cards: each feed item includes a mini-graph showing the affected entity’s neighbourhood, so users see context without navigating away
2.	Impact indicators: wire InsightEngine’s severity scoring into visual pulses (critical=red pulse, high=amber, medium=blue)
3.	Actionable buttons: “View affected landscape”, “Compare before/after”, “Ask AI” on every card
4.	Digest mode: group related signals (e.g. 3 new trials for GLP-1 drugs) into a single summary card with expandable details
4.4 Temporal Graph Layer
Add a timeline slider to GraphExplorer that filters edges by date. Users scrub through time to see how the competitive landscape evolved: which drugs entered clinical trials, which companies made acquisitions, which mechanisms gained traction. Edges fade in/out based on their created_at timestamp. This transforms the graph from a static snapshot into a time-series visualisation of the pharma landscape. Requires: created_at on entity_links (already present), a date range filter parameter on /graph/traverse, and a slider UI component.
4.5 Scenario Primitives
Wire the existing ScenarioEngine into the graph UI. A “What if” toggle in GraphExplorer lets users remove an entity and see the graph recalculate: pipeline scores, competitive positions, market concentration (HHI). Removed entities render as dashed outlines with their former connections shown as dotted lines. This is the first step towards the decision digital twin vision—deterministic graph operations for “what if Drug X is withdrawn” reasoning without requiring causal modelling.
4.6 Benchmark CI Integration
Wire eval_runner.py --offline into the CI pipeline. On every push to main: capture responses from the staging environment, score with the honest scorers, fail the build if composite drops below 75%, and publish the report as a CI artefact. Add per-dimension regression alerts: if any single dimension drops more than 8 percentage points from the previous run, flag it even if the composite is stable. This prevents the scenario where one dimension silently degrades while others compensate.
Sprint 3 Acceptance Criteria
•	Concept Registry loads from DB with < 50ms cache hit
•	Feedback job adjusts at least 1 concept weight after 7 days of telemetry
•	Feed cards show mini-graphs for ≥80% of critical/high severity events
•	Timeline slider correctly filters edges by date range with smooth animation
•	Scenario removal recalculates pipeline scores within 2 seconds
•	CI benchmark gate rejects a PR that drops composite below 75%
 
5. Data Quality Priorities Across All Sprints
Data quality improvements should run in parallel with feature work. These are not sprint-specific—they’re continuous improvements that compound over time.
5.1 NADAC Pricing Connector Recovery
The NADAC API returned 404 (CMS migrated platforms). Investigate the new CMS Drug Spending Dashboard API or the NADAC data files published on data.cms.gov. The drug_pricing table and migration 022 are ready—only the connector needs updating. Until resolved, the Price Agent has no data source.
5.2 Open Targets Target Associations
Drug search works but target associations need a GraphQL query fix. This blocks molecular-level competitive analysis (which drugs target the same proteins). Fix the query and add 5 golden queries testing mechanism-level comparisons.
5.3 Entity Resolution Monitoring
The unresolved_entities queue needs a dashboard metric exposed through the FAIR scorer’s resolution rate dimension. Currently resolution failures are silent—the steward curates but there’s no alert when the queue grows beyond a threshold. Add: a /metrics/unresolved-count endpoint, an InsightEngine signal for unresolved queue > 50, and a feed card that surfaces it.
5.4 Evidence Freshness
The FAIR scorer computes freshness as “% records updated within 30 days.” For a pharma intelligence platform, 30 days is too generous. Differentiate by entity type: clinical trials should be stale after 7 days, PubMed articles after 14 days, company data after 30 days, drug master data after 60 days. Adjust the FAIR scorer’s freshness dimension to use entity-type-specific thresholds.
5.5 Materialised View Refresh Telemetry
The competitive_landscape fallback fires when MVs return ≤2 rows. Track fallback frequency: add a counter to the CTX telemetry or a dedicated mv_fallback_events table. If fallback fires on >20% of landscape queries, the MV refresh schedule needs attention. The new /metrics/refresh-views-with-timestamp endpoint helps but doesn’t track individual method fallbacks.
 
6. Benchmark Targets
Intent	Current	Sprint 1	Sprint 2	Sprint 3
Overall	81.6%	≥83%	≥86%	≥90%
Dossier	70.3%	≥85%	≥88%	≥90%
Landscape	79.5%	≥80%	≥85%	≥90%
Compare	100%	100%	100%	100%
Portfolio	100%	100%	100%	100%
Pipeline	~80%	≥82%	≥85%	≥88%
Structured Query	100%	100%	100%	100%
General	~85%	≥85%	≥88%	≥90%

The 100% scores on Compare, Portfolio, and Structured Query should be treated with scepticism until adversarial queries are added for those intents. When adversarial queries are introduced, expect a 5–10 point drop—this is healthy and honest.
7. Test Coverage Targets
Area	Current	Sprint 1	Sprint 2	Sprint 3
Backend tests	1,078	1,120+	1,180+	1,250+
Frontend tests	0	15+	40+	80+
Golden queries	57	65+	70+	80+
Adversarial queries	7	15+	20+	25+

8. Risk Register
Risk	Severity	Impact	Mitigation
Harness stays unwired	High	40% of session effort wasted	Sprint 1 priority 1
Frontend regression	High	No tests catch breaking changes	Sprint 1 Vitest setup
NADAC API permanent loss	Medium	Pricing feature has no US data	Investigate CMS alternatives
Graph perf at scale	Medium	Custom canvas chokes on 500+ nodes	Evaluate d3-force adoption
Benchmark score inflation	Medium	100% intents mask weak scorers	Add adversarial queries
CTX integration deferred too long	Low	Hydrator/ContextGuard not wired	Sprint 3 backlog item

9. Summary
The team delivered a strong session with genuine engineering quality across 40 commits. The Concept Registry, scorer tightening, Entity Library redesign, FAIR scorer integration, and CTX telemetry are all solid, production-integrated work. The benchmark’s honest trajectory (86.9% → 75.6% → 81.6%) reflects a team that values measurement over optics.
The next three sprints follow a deliberate sequence: Sprint 1 stabilises the infrastructure by wiring the harness, adding tests, and consolidating graph components. Sprint 2 transforms the UX from five separate tools into one connected intelligence experience by weaving graph context into every surface. Sprint 3 invests in data quality and proactive intelligence—feedback loops, temporal graphs, and scenario reasoning.
The north star is clear: Market Zero should feel like LinkedIn for pharma intelligence—a platform where every interaction reveals one more layer of the knowledge graph, where relationships are discovered naturally, and where the system proactively surfaces insights before users think to ask. The foundation is solid. The next 6 weeks determine whether it becomes a product.



MARKET ZERO
Intelligence Layer Deep Analysis
How Questions Become Answers: From Intent to Insight

Architecture Review — 5 April 2026
CONFIDENTIAL
 
1. Executive Summary
This document traces exactly how Market Zero transforms a user’s question into an intelligence response—from the first regex match in intent detection through to the final citation-validated narrative. The analysis identifies where the pipeline is strong, where it leaks quality, and what must change to make the intelligence layer genuinely trustworthy for pharma decision-making.
Core Finding: The pipeline’s deterministic data assembly (SQL → graph → metrics → materialised views) is excellent. The weakness is at the two boundaries: question interpretation (regex-driven, brittle on compound/ambiguous queries) and answer generation (post-hoc hallucination detection rather than pre-generation grounding). The data layer is approximately 70% AI-ready—good graph structure and MV coverage, but sparse embeddings and flat confidence scoring limit retrieval quality.

2. Question Interpretation: How Intent Is Determined
2.1 The Current Pipeline
Intent detection is a regex cascade in intent.py with fixed priority ordering. The system evaluates each question against pattern groups in sequence: title guard → compare → landscape → portfolio → pipeline → structured query → dossier → bare entity → general. The first match wins. Entity extraction happens inside each regex group via capture groups.
2.2 What Works
•	Compare detection is robust with 4 independent patterns covering “vs”, “versus”, “differences between”, “stack up against”, and “which X or Y”
•	Title guard prevents academic paper titles (containing “vs”) from false-triggering compare
•	Landscape topic extraction has 3 fallback strategies (direct match, prefix match, filler strip)
•	Compound intent detection splits on “and also” / “plus” / “then” and evaluates each clause independently
•	Bare entity fallback catches 1–4 word queries without question markers (e.g. “semaglutide” alone routes to dossier)
2.3 What’s Broken
Problem 1: Regex Intent Is Brittle on Real-World Queries
The patterns assume clean, well-formed queries. Real pharma analysts ask questions like “What’s happening with GLP-1s in obesity and how does Novo’s pipeline compare to Lilly’s?” This is a compound query crossing landscape + compare + portfolio intents. The compound detector caps at 2 intents and can’t handle nested references (“Novo’s pipeline” requires entity resolution before intent classification).
Problem 2: Topic Extraction Loses Context
When a landscape query says “Show me the obesity market segments,” the topic extractor produces “obesity”. But this strips the signal that the user wants market segmentation, not just a list of obesity drugs. The topic string is then passed to competitive_landscape() as a plain ILIKE filter—the nuance of “segments” vs “drugs” vs “companies” is lost entirely.
Problem 3: No Confidence Signal on Intent Match
The intent detector returns a hard classification with no confidence score. A query like “Tell me about semaglutide and tirzepatide” could be dossier (multi-entity) or compare. The system picks one with no signal to the downstream handler about ambiguity. The handler can’t hedge its response or ask for clarification.
Problem 4: Coreference Resolution Is String-Based
Follow-up resolution in context.py replaces pronouns (“this drug”, “their pipeline”) with the last mentioned topic—extracted from bold markers in the prior response. This is fragile: if the prior response mentions semaglutide in paragraph 1 and tirzepatide in paragraph 3, “this drug” resolves to whichever appeared first in bold, not whichever was the focus of the user’s interest.
2.4 Recommendations
1.	Add an intent confidence score (0–1.0) based on pattern specificity. Multi-pattern matches (e.g. compare has 4 patterns and the query matches 3 of them) should score higher than single-pattern matches.
2.	Replace bare-string topic extraction with structured topic objects: {topic: “obesity”, query_type: “segmentation”, entities_mentioned: [“Novo Nordisk”, “Eli Lilly”]}. This preserves the user’s analytical framing.
3.	For ambiguous queries (E09: “Tell me about semaglutide and tirzepatide”), detect multi-entity dossier vs compare using a lightweight heuristic: if both entities share the same type and no comparative language exists, default to compare but flag ambiguity.
4.	Move coreference resolution from string extraction to entity ID tracking. The conversation memory already maintains _entity_counts—use the most-discussed entity ID rather than the first bold match.
 
3. Data Retrieval: How Evidence Is Assembled
3.1 The Three-Source Architecture
Every handler assembles evidence from three independent sources before the LLM sees anything: hybrid search (vector + keyword), graph traversal (SQL CTEs over entity_links), and materialised view metrics (pre-computed KPIs). This deterministic-first design is the pipeline’s greatest strength—it means the LLM receives only verified, database-sourced facts.
3.2 Hybrid Search Assessment
Model: OpenAI text-embedding-3-small (1536 dimensions). Scoring: cosine similarity via pgvector’s <=> operator, multiplied by a recency score (1.0 for <30 days, declining to 0.2 for >1 year). Results ranked by combined score.
Strength: Record-Status Filtering
Search excludes merged and excluded records, ensuring only golden-record entities appear in results. This prevents hallucination from duplicate or retired entities.
Weakness: Sparse Embedding Coverage
Vector columns exist on 10 tables, but population is unverified for most. knowledge_chunks and therapeutic_areas (MeSH scope notes) are likely populated. But drug molecule_embeddings, trial protocol_embeddings, and company strategy_embeddings may be sparse or empty—which means vector search silently returns no results for those entity types, falling back to keyword-only matching with no signal to the user.
Weakness: Recency Bias Suppresses Foundational Evidence
The recency multiplier (similarity × recency_score) means a landmark Phase 3 trial paper from 2023 with 0.95 similarity gets scored 0.38 (0.95 × 0.4), while a minor 2026 blog post with 0.60 similarity scores 0.60 (0.60 × 1.0). For pharma intelligence, foundational evidence should not be penalised by age. Recommendation: apply recency only to news/events, not to trial or literature evidence.
3.3 Graph Traversal Assessment
Graph traversal uses a stored procedure (traverse_graph) with recursive CTEs supporting 1–4 hop expansion. Path finding uses a separate BFS CTE with cycle prevention (path array exclusion) capped at 6 hops.
Strength: Link Type Semantics
The entity_links table carries 11+ relationship types (OWNS, SPONSORS, INVESTIGATES, TARGETS_MECHANISM, IN_THERAPEUTIC_AREA, EVIDENCE_FOR, COMPETES_WITH, etc.) with provenance tracking per link. This enables meaningful traversal: “which companies sponsor trials for drugs that target GLP-1 receptors?” resolves via SPONSORS → INVESTIGATES → TARGETS_MECHANISM.
Weakness: Flat Confidence Scoring
All entity_links default to confidence=1.0 regardless of discovery method. A link created by exact_id match (FDA Orange Book confirms Company X owns Drug Y) has the same confidence as one created by LLM extraction from a news article. The graph traversal applies no confidence-weighted filtering—all edges are treated as equally reliable. This means an LLM-extracted “COMPETES_WITH” link (potentially spurious) ranks equally with an FDA-confirmed “OWNS” link.
Weakness: Truncation Is Silent
When traversal hits the max_nodes cap (default 100), results are silently truncated. detect_truncation() exists but is informational only—the LLM receives a partial graph with no signal that critical connections may be missing. For high-connectivity entities like semaglutide (potentially hundreds of connections), this means the LLM synthesises from an incomplete picture.
3.4 Materialised View Assessment
Five MVs cover the core pharma KPI space: pipeline strength (phase-weighted trial counts), trial success rate, evidence density (recency-weighted article counts), competitive landscape (drugs per mechanism × therapeutic area), and company portfolio. The MV fallback mechanism (realtime SQL when MV returns ≤2 rows) is well-designed.
Strength: Pre-Computed, Trustworthy Metrics
Because these are SQL aggregations, not LLM computations, the numbers are deterministically correct. Pipeline score = Σ(phase_weight × trial_count) with defined weights (P1=1, P2=2, P3=4, P4=1). The LLM cannot hallucinate these numbers because they arrive as structured data in the metrics_context, and post-synthesis validation strips any bold numbers that don’t match source data.
Weakness: Evidence Density Is Volume, Not Quality
mv_evidence_density counts articles and applies recency weighting, but treats all publications equally. A Nature Medicine Phase 3 results paper has the same weight as a conference abstract. For pharma intelligence, evidence quality (journal impact, study design, sample size) should differentiate signal from noise.
 
4. Answer Generation: How the LLM Produces Responses
4.1 The Synthesis Pipeline
After deterministic data assembly, the pipeline hands everything to LLMSynthesizer. The context block is assembled in layers: compressed evidence (via CTX packing or legacy inline format), metrics, graph summary, conversation history, concept hints, and up to 2 few-shot exemplars. This is injected as the user message alongside an intent-specific system prompt.
4.2 What the System Prompts Get Right
The system prompts are remarkably well-crafted. They enforce specific behavioural rules that directly address pharma intelligence needs:
•	Strict data grounding: “ONLY use numbers and facts from the PROVIDED CONTEXT below. Do NOT inject clinical trial results, efficacy percentages, MACE reductions, or any other statistics from your training data.”
•	Explicit fallback language: “If the data doesn’t cover a dimension, say ‘data not available’ rather than filling in from memory.”
•	Citation density targets: “AIM for at least 2 citations per paragraph when evidence is available. Every factual claim should be traceable to a source.”
•	Comparative framing: “Lead with the key differentiator—which entity is stronger/weaker and why. Compute and state differentials, don’t just list numbers side-by-side.”
•	Landscape orientation: “The data is segmented by THERAPEUTIC AREA, NOT by company. Do NOT say ‘dominated by companies.’”
4.3 The Critical Gap: Post-Hoc Validation, Not Pre-Generation Grounding
The most significant weakness in the intelligence layer is that hallucination prevention happens AFTER generation, not before. The LLM generates a full narrative, then validate_citations() strips invalid [N] markers and verify_narrative_numbers() removes bold formatting from unverified numbers. This means: (1) the LLM may fabricate plausible-sounding claims that contain no numbers and no citations—these pass all validation; (2) stripped citations and numbers create gaps in the narrative that the user never sees explained; (3) the system has no mechanism to regenerate or request clarification when validation fails.
What Post-Hoc Catches
•	Invalid citation markers: [N] where N > evidence_count or N = 0 are stripped
•	Unverified bold numbers: **42.5** where 42.5 doesn’t appear in metrics_context or evidence (within ±1.0 tolerance) gets de-bolded
What Post-Hoc Misses
•	Qualitative hallucination: “Semaglutide has shown remarkable efficacy in NASH trials”—true from training data, but not in the provided context. No citation, no number, passes all validation.
•	Causal claims: “The pipeline score increase was driven by 3 new Phase 3 trials”—plausible but fabricated causality that no validator catches.
•	Omission bias: The LLM may ignore low-confidence or unfavourable evidence in favour of a clean narrative. No check for evidence completeness in the generated response.
•	Temporal confabulation: “Recent trials show...” when the evidence is from 2022. No date verification against evidence timestamps.
4.4 Concept Registry Integration
The ConceptRegistry activates 15 pharma concepts per intent+entity_type, injecting hints like “Consider pipeline_strength (weight: 0.95), competitive_landscape (weight: 0.90)” into the LLM context. This shapes which analytical dimensions the LLM emphasises. The activation is deterministic (set-intersection filtering, weight-sorted). Currently in-memory only—no feedback loop adjusts weights based on response quality.
4.5 Confidence Scoring
Response confidence is computed additively: entity resolution quality (0–0.3) + evidence depth (0–0.3) + graph context (0–0.2) + metrics availability (0–0.2). This is a good start but has two issues: (1) it measures input quality, not output quality—a response with excellent input data but a hallucinated narrative still gets high confidence; (2) graph context gives full marks at ≥20 nodes, which is easily reached for well-connected entities regardless of whether those nodes are relevant.
 
5. Data Layer AI-Readiness
5.1 Readiness Scorecard
Dimension	Score	Strength	Gap
Graph topology	8/10	11+ link types, provenance tracked	Flat confidence (all 1.0)
Materialised views	9/10	5 MVs covering core pharma KPIs	Evidence density = volume only
External data sources	8/10	18 connectors across pharma data	NADAC deprecated, OT partial
Embedding coverage	4/10	Infrastructure exists (pgvector)	Likely sparse on core tables
Entity resolution	6/10	Exact + fuzzy + alias matching	No semantic deduplication
Quality monitoring	7/10	FAIR scorer, 5 dimensions	No automated remediation
Conversation memory	7/10	Token-budgeted, entity tracking	String-based coreference
Temporal modelling	3/10	Timestamps on records	No time-series analytics
Ontology alignment	5/10	MeSH-seeded TAs and mechanisms	No continuous sync, static hierarchy

5.2 The Embedding Gap
This is the single largest data-layer risk. Vector columns exist on 10 tables with HNSW indexes, but actual population is unverified for drugs, trials, companies, and articles. If molecule_embedding on the drugs table is empty, vector search for drug queries returns zero results and silently falls back to keyword matching—which means the user gets results based on string overlap rather than semantic relevance. The team should run a coverage audit: SELECT entity_type, COUNT(*) total, COUNT(embedding_col) populated, ROUND(COUNT(embedding_col)::numeric / COUNT(*) * 100, 1) AS pct FROM {table} for each entity type.
5.3 The Confidence Gap
All 11+ link types in entity_links share default confidence=1.0. In practice, an OWNS link from FDA Orange Book (near-certain) and a COMPETES_WITH link from LLM extraction (uncertain) are indistinguishable. This means graph traversal treats speculative relationships as facts. Fix: assign confidence tiers by provenance source: exact_id=1.0, structured_api=0.9, entity_resolution=0.8, cross_source_match=0.7, llm_extracted=0.5, heuristic=0.3. Apply minimum confidence thresholds in graph traversal (default 0.5).
5.4 The Temporal Gap
The data has timestamps (created_at, updated_at, trial start dates, publication dates) but no time-series infrastructure. Questions like “How has the GLP-1 landscape changed in the last year?” or “Is Novo Nordisk’s pipeline accelerating?” cannot be answered because there are no temporal aggregations, no change detection, and no trend MVs. The InsightEngine detects point-in-time signals (new trial, safety event) but cannot compute trajectories.
 
6. Per-Intent Quality Audit
6.1 Dossier (Benchmark: 70.3%)
The weakest core intent. The handler queries well (entity resolution → DB joins → graph 2-hop → metrics → similar entities), but the LLM synthesis often produces generic summaries that don’t leverage the structured data handed to it. The handler passes pipeline_score, success_rate, evidence_density, connection counts, and market events—but the generated narrative frequently ignores half of these dimensions.
Root cause: The system prompt for dossier is the weakest of all intents—it lacks the specific structural guidance that landscape and compare prompts have. It tells the LLM to “be comprehensive” without specifying which dimensions to cover in which order. Adding few-shot exemplars that demonstrate full-dimension coverage would likely close the gap to 85%+.
6.2 Compare (Benchmark: 100%)
The strongest intent, but the 100% score deserves scrutiny. Compare benefits from: (1) pre-computed differentials (pipeline_score ratio, trial volume difference, Phase 3 leadership) that the LLM can cite directly rather than computing; (2) a highly structured system prompt with explicit rules; (3) a comparison table displayed alongside the narrative, reducing the LLM’s burden. The risk is that the golden dataset only tests 6 compare queries, all with clean “X vs Y” phrasing. Adversarial cases (incomplete compare, multi-entity compare, cross-type compare) would likely reveal gaps.
6.3 Landscape (Benchmark: 79.5%)
Good but uneven. The handler assembles competitive segments from mv_competitive_landscape, computes HHI concentration, queries company portfolios, and expands top-5 segments via graph neighbourhood queries. The system prompt correctly frames results as therapeutic area segments, not company rankings. The MV fallback (original_topic parameter) handles edge cases where the expanded topic returns sparse results.
Remaining gap: Landscape queries about thin-data areas (rare diseases, neurology, cell therapy) still score poorly because the materialised views return empty. The fallback queries base tables but these may also be sparse. The system should explicitly acknowledge data coverage limits: “Our database covers 1,247 drugs across 45 therapeutic areas. For [rare disease X], we have limited coverage (3 drugs, 7 trials).”
6.4 Pipeline (Benchmark: ~80%)
Solid on well-covered therapeutic areas (diabetes, obesity, cardiovascular) where mv_drug_pipeline_strength has rich data. The phase-weighted scoring (P1=1, P2=2, P3=4, P4=1) is pharma-appropriate. Weakness: no distinction between active and completed trials in the narrative—an entity with 50 completed P2 trials and 0 active trials appears stronger than one with 3 active P3 trials, which is misleading for forward-looking pipeline assessment.
6.5 Structured Query (Benchmark: 100%)
Routes to LangGraph agent with SQL generation capability. The 100% score reflects that the golden queries are straightforward counting/listing queries. The risk is that more complex structured queries (joins, conditional aggregations, temporal filters) would challenge the SQL generation quality. Not enough adversarial cases in the benchmark to stress-test this.
 
7. Recommendations: Making Intelligence Trustworthy
7.1 Pre-Generation Grounding (Highest Impact)
Replace post-hoc validation with a pre-generation grounding mechanism. Before the LLM generates a response, build a structured fact sheet from the deterministic data:
1.	Extract key metrics as named facts: {pipeline_score: 42.5, source: mv_drug_pipeline_strength, entity: semaglutide}
2.	Extract entity relationships as triples: {semaglutide TARGETS GLP-1 receptor, confidence: 0.95, source: ChEMBL}
3.	Build a fact inventory with provenance: “You have 7 verified facts, 3 evidence snippets, and 2 graph paths to work with.”
4.	Inject this inventory alongside the raw context. Post-synthesis, verify that every factual claim in the narrative maps to an inventory item. Claims that don’t map get flagged (not silently passed).
7.2 Intent Confidence and Disambiguation
1.	Add a confidence score (0–1.0) to intent detection output, based on: number of patterns matched, specificity of match (full regex vs keyword only), presence of entity resolution support.
2.	For ambiguous queries (confidence < 0.7), generate responses for the top-2 intents and let the user choose, or hedge: “I’ve interpreted this as a comparison. If you wanted a dossier on both, let me know.”
3.	Replace string-based coreference with entity-ID tracking from ConversationMemory._entity_counts.
7.3 Embedding Backfill and Audit
1.	Run coverage audit across all 10 vector-enabled tables. Target: ≥90% population for drugs, trials, articles, companies.
2.	Schedule embedding refresh on data pipeline runs (not just initial backfill). New trials and articles should be embedded within 24 hours of ingestion.
3.	Remove recency multiplier from literature and trial search. Apply recency only to news/events where timeliness is the primary signal.
7.4 Link Confidence Tiers
1.	Assign confidence by provenance: exact_id=1.0, structured_api=0.9, entity_resolution=0.8, cross_source=0.7, llm_extracted=0.5, heuristic=0.3.
2.	Add a min_confidence parameter to graph traversal (default 0.5). This filters out speculative links before they reach the LLM.
3.	Surface confidence in the frontend: edges with confidence < 0.7 render as dashed lines in the graph. The user sees which relationships are certain vs inferred.
7.5 Dossier Prompt Improvement
1.	Add structured dimension ordering to the dossier system prompt: “Your response must cover these dimensions in order: (1) Identity and classification, (2) Pipeline position and strength, (3) Evidence depth and recency, (4) Competitive context, (5) Key risks or signals.”
2.	Add 3–5 few-shot exemplar dossiers that demonstrate full-dimension coverage with citation density ≥2 per paragraph.
3.	Add a post-synthesis dimension check: verify that the generated narrative mentions at least 4 of the 5 required dimensions. If not, append a note: “Note: Limited data available for [missing dimension].”
7.6 Evidence Quality Scoring
1.	Extend mv_evidence_density to include a quality dimension: journal impact factor (or tier), study design (RCT > observational > case report), sample size.
2.	Weight evidence in the LLM context by quality: a Nature Medicine RCT should appear before a conference abstract in the evidence list.
3.	Surface evidence quality in citations: [1, high-quality RCT] vs [2, conference abstract].
7.7 Temporal Intelligence Layer
1.	Add a mv_pipeline_velocity materialised view that computes month-over-month changes in pipeline_score, trial_count, and active_trial_count per drug and therapeutic area.
2.	Wire InsightEngine to detect velocity changes: “Glp-1 pipeline accelerating: +3 new P3 trials in 30 days” as proactive signals.
3.	Add a temporal filter to graph traversal: “Show me connections created in the last 90 days” to support trend-based questions.
 
8. Intelligence Maturity Model
The following model positions Market Zero’s current state and charts the path to each level:
Level	Name	Capability	Market Zero Status
L1	Data Retrieval	Find and display relevant records	Achieved — search, graph, MVs
L2	Grounded Synthesis	Generate narratives from verified data only	Partial — post-hoc validation, not pre-gen
L3	Analytical Intelligence	Surface nuance: differentials, trends, risks	Partial — compare has differentials; dossier/landscape don’t
L4	Proactive Intelligence	Detect signals and alert before users ask	Early — InsightEngine exists, 3 signal types
L5	Decision Support	Scenario modelling, what-if reasoning	Not started — scenario primitives designed, not built

The immediate priority should be solidifying L2 (pre-generation grounding) and extending L3 (analytical intelligence across all intents, not just compare). L4 and L5 can follow once the foundation is trustworthy.
9. Conclusion
Market Zero’s intelligence pipeline has excellent bones. The deterministic-first architecture (SQL → graph → materialised views → LLM) is the right approach for pharma intelligence where trust matters more than creativity. The 5 materialised views, 18 data connectors, 11+ link types, and Concept Registry create a rich analytical substrate.
The system’s intelligence is weakest at its two boundaries. On the input side, regex-based intent detection handles clean queries well but breaks on compound, ambiguous, or conversational questions—exactly the kind that senior analysts ask. On the output side, post-hoc hallucination detection catches numeric fabrication and invalid citations but misses qualitative hallucination, causal confabulation, and omission bias.
The data layer is 70% AI-ready. Graph structure and MV coverage are strong, but sparse embeddings limit semantic search quality, flat confidence scoring treats speculative links as facts, and the absence of temporal modelling means the system cannot answer the “how is this changing?” questions that drive real pharma decisions.
The seven recommendations in Section 7 chart a path from the current state to genuinely trustworthy pharma intelligence. Pre-generation grounding (7.1) and link confidence tiers (7.4) are the highest-impact changes. Together they would ensure the LLM works from verified facts with calibrated certainty—which is what pharmaceutical decision-makers need most.


MARKET ZERO
Intelligence Layer Deep Analysis
How Questions Become Answers: From Intent to Insight

Architecture Review — 5 April 2026
CONFIDENTIAL
 
1. Executive Summary
This document traces exactly how Market Zero transforms a user’s question into an intelligence response—from the first regex match in intent detection through to the final citation-validated narrative. The analysis identifies where the pipeline is strong, where it leaks quality, and what must change to make the intelligence layer genuinely trustworthy for pharma decision-making.
Core Finding: The pipeline’s deterministic data assembly (SQL → graph → metrics → materialised views) is excellent. The weakness is at the two boundaries: question interpretation (regex-driven, brittle on compound/ambiguous queries) and answer generation (post-hoc hallucination detection rather than pre-generation grounding). The data layer is approximately 70% AI-ready—good graph structure and MV coverage, but sparse embeddings and flat confidence scoring limit retrieval quality.

2. Question Interpretation: How Intent Is Determined
2.1 The Current Pipeline
Intent detection is a regex cascade in intent.py with fixed priority ordering. The system evaluates each question against pattern groups in sequence: title guard → compare → landscape → portfolio → pipeline → structured query → dossier → bare entity → general. The first match wins. Entity extraction happens inside each regex group via capture groups.
2.2 What Works
•	Compare detection is robust with 4 independent patterns covering “vs”, “versus”, “differences between”, “stack up against”, and “which X or Y”
•	Title guard prevents academic paper titles (containing “vs”) from false-triggering compare
•	Landscape topic extraction has 3 fallback strategies (direct match, prefix match, filler strip)
•	Compound intent detection splits on “and also” / “plus” / “then” and evaluates each clause independently
•	Bare entity fallback catches 1–4 word queries without question markers (e.g. “semaglutide” alone routes to dossier)
2.3 What’s Broken
Problem 1: Regex Intent Is Brittle on Real-World Queries
The patterns assume clean, well-formed queries. Real pharma analysts ask questions like “What’s happening with GLP-1s in obesity and how does Novo’s pipeline compare to Lilly’s?” This is a compound query crossing landscape + compare + portfolio intents. The compound detector caps at 2 intents and can’t handle nested references (“Novo’s pipeline” requires entity resolution before intent classification).
Problem 2: Topic Extraction Loses Context
When a landscape query says “Show me the obesity market segments,” the topic extractor produces “obesity”. But this strips the signal that the user wants market segmentation, not just a list of obesity drugs. The topic string is then passed to competitive_landscape() as a plain ILIKE filter—the nuance of “segments” vs “drugs” vs “companies” is lost entirely.
Problem 3: No Confidence Signal on Intent Match
The intent detector returns a hard classification with no confidence score. A query like “Tell me about semaglutide and tirzepatide” could be dossier (multi-entity) or compare. The system picks one with no signal to the downstream handler about ambiguity. The handler can’t hedge its response or ask for clarification.
Problem 4: Coreference Resolution Is String-Based
Follow-up resolution in context.py replaces pronouns (“this drug”, “their pipeline”) with the last mentioned topic—extracted from bold markers in the prior response. This is fragile: if the prior response mentions semaglutide in paragraph 1 and tirzepatide in paragraph 3, “this drug” resolves to whichever appeared first in bold, not whichever was the focus of the user’s interest.
2.4 Recommendations
1.	Add an intent confidence score (0–1.0) based on pattern specificity. Multi-pattern matches (e.g. compare has 4 patterns and the query matches 3 of them) should score higher than single-pattern matches.
2.	Replace bare-string topic extraction with structured topic objects: {topic: “obesity”, query_type: “segmentation”, entities_mentioned: [“Novo Nordisk”, “Eli Lilly”]}. This preserves the user’s analytical framing.
3.	For ambiguous queries (E09: “Tell me about semaglutide and tirzepatide”), detect multi-entity dossier vs compare using a lightweight heuristic: if both entities share the same type and no comparative language exists, default to compare but flag ambiguity.
4.	Move coreference resolution from string extraction to entity ID tracking. The conversation memory already maintains _entity_counts—use the most-discussed entity ID rather than the first bold match.
 
3. Data Retrieval: How Evidence Is Assembled
3.1 The Three-Source Architecture
Every handler assembles evidence from three independent sources before the LLM sees anything: hybrid search (vector + keyword), graph traversal (SQL CTEs over entity_links), and materialised view metrics (pre-computed KPIs). This deterministic-first design is the pipeline’s greatest strength—it means the LLM receives only verified, database-sourced facts.
3.2 Hybrid Search Assessment
Model: OpenAI text-embedding-3-small (1536 dimensions). Scoring: cosine similarity via pgvector’s <=> operator, multiplied by a recency score (1.0 for <30 days, declining to 0.2 for >1 year). Results ranked by combined score.
Strength: Record-Status Filtering
Search excludes merged and excluded records, ensuring only golden-record entities appear in results. This prevents hallucination from duplicate or retired entities.
Weakness: Sparse Embedding Coverage
Vector columns exist on 10 tables, but population is unverified for most. knowledge_chunks and therapeutic_areas (MeSH scope notes) are likely populated. But drug molecule_embeddings, trial protocol_embeddings, and company strategy_embeddings may be sparse or empty—which means vector search silently returns no results for those entity types, falling back to keyword-only matching with no signal to the user.
Weakness: Recency Bias Suppresses Foundational Evidence
The recency multiplier (similarity × recency_score) means a landmark Phase 3 trial paper from 2023 with 0.95 similarity gets scored 0.38 (0.95 × 0.4), while a minor 2026 blog post with 0.60 similarity scores 0.60 (0.60 × 1.0). For pharma intelligence, foundational evidence should not be penalised by age. Recommendation: apply recency only to news/events, not to trial or literature evidence.
3.3 Graph Traversal Assessment
Graph traversal uses a stored procedure (traverse_graph) with recursive CTEs supporting 1–4 hop expansion. Path finding uses a separate BFS CTE with cycle prevention (path array exclusion) capped at 6 hops.
Strength: Link Type Semantics
The entity_links table carries 11+ relationship types (OWNS, SPONSORS, INVESTIGATES, TARGETS_MECHANISM, IN_THERAPEUTIC_AREA, EVIDENCE_FOR, COMPETES_WITH, etc.) with provenance tracking per link. This enables meaningful traversal: “which companies sponsor trials for drugs that target GLP-1 receptors?” resolves via SPONSORS → INVESTIGATES → TARGETS_MECHANISM.
Weakness: Flat Confidence Scoring
All entity_links default to confidence=1.0 regardless of discovery method. A link created by exact_id match (FDA Orange Book confirms Company X owns Drug Y) has the same confidence as one created by LLM extraction from a news article. The graph traversal applies no confidence-weighted filtering—all edges are treated as equally reliable. This means an LLM-extracted “COMPETES_WITH” link (potentially spurious) ranks equally with an FDA-confirmed “OWNS” link.
Weakness: Truncation Is Silent
When traversal hits the max_nodes cap (default 100), results are silently truncated. detect_truncation() exists but is informational only—the LLM receives a partial graph with no signal that critical connections may be missing. For high-connectivity entities like semaglutide (potentially hundreds of connections), this means the LLM synthesises from an incomplete picture.
3.4 Materialised View Assessment
Five MVs cover the core pharma KPI space: pipeline strength (phase-weighted trial counts), trial success rate, evidence density (recency-weighted article counts), competitive landscape (drugs per mechanism × therapeutic area), and company portfolio. The MV fallback mechanism (realtime SQL when MV returns ≤2 rows) is well-designed.
Strength: Pre-Computed, Trustworthy Metrics
Because these are SQL aggregations, not LLM computations, the numbers are deterministically correct. Pipeline score = Σ(phase_weight × trial_count) with defined weights (P1=1, P2=2, P3=4, P4=1). The LLM cannot hallucinate these numbers because they arrive as structured data in the metrics_context, and post-synthesis validation strips any bold numbers that don’t match source data.
Weakness: Evidence Density Is Volume, Not Quality
mv_evidence_density counts articles and applies recency weighting, but treats all publications equally. A Nature Medicine Phase 3 results paper has the same weight as a conference abstract. For pharma intelligence, evidence quality (journal impact, study design, sample size) should differentiate signal from noise.
 
4. Answer Generation: How the LLM Produces Responses
4.1 The Synthesis Pipeline
After deterministic data assembly, the pipeline hands everything to LLMSynthesizer. The context block is assembled in layers: compressed evidence (via CTX packing or legacy inline format), metrics, graph summary, conversation history, concept hints, and up to 2 few-shot exemplars. This is injected as the user message alongside an intent-specific system prompt.
4.2 What the System Prompts Get Right
The system prompts are remarkably well-crafted. They enforce specific behavioural rules that directly address pharma intelligence needs:
•	Strict data grounding: “ONLY use numbers and facts from the PROVIDED CONTEXT below. Do NOT inject clinical trial results, efficacy percentages, MACE reductions, or any other statistics from your training data.”
•	Explicit fallback language: “If the data doesn’t cover a dimension, say ‘data not available’ rather than filling in from memory.”
•	Citation density targets: “AIM for at least 2 citations per paragraph when evidence is available. Every factual claim should be traceable to a source.”
•	Comparative framing: “Lead with the key differentiator—which entity is stronger/weaker and why. Compute and state differentials, don’t just list numbers side-by-side.”
•	Landscape orientation: “The data is segmented by THERAPEUTIC AREA, NOT by company. Do NOT say ‘dominated by companies.’”
4.3 The Critical Gap: Post-Hoc Validation, Not Pre-Generation Grounding
The most significant weakness in the intelligence layer is that hallucination prevention happens AFTER generation, not before. The LLM generates a full narrative, then validate_citations() strips invalid [N] markers and verify_narrative_numbers() removes bold formatting from unverified numbers. This means: (1) the LLM may fabricate plausible-sounding claims that contain no numbers and no citations—these pass all validation; (2) stripped citations and numbers create gaps in the narrative that the user never sees explained; (3) the system has no mechanism to regenerate or request clarification when validation fails.
What Post-Hoc Catches
•	Invalid citation markers: [N] where N > evidence_count or N = 0 are stripped
•	Unverified bold numbers: **42.5** where 42.5 doesn’t appear in metrics_context or evidence (within ±1.0 tolerance) gets de-bolded
What Post-Hoc Misses
•	Qualitative hallucination: “Semaglutide has shown remarkable efficacy in NASH trials”—true from training data, but not in the provided context. No citation, no number, passes all validation.
•	Causal claims: “The pipeline score increase was driven by 3 new Phase 3 trials”—plausible but fabricated causality that no validator catches.
•	Omission bias: The LLM may ignore low-confidence or unfavourable evidence in favour of a clean narrative. No check for evidence completeness in the generated response.
•	Temporal confabulation: “Recent trials show...” when the evidence is from 2022. No date verification against evidence timestamps.
4.4 Concept Registry Integration
The ConceptRegistry activates 15 pharma concepts per intent+entity_type, injecting hints like “Consider pipeline_strength (weight: 0.95), competitive_landscape (weight: 0.90)” into the LLM context. This shapes which analytical dimensions the LLM emphasises. The activation is deterministic (set-intersection filtering, weight-sorted). Currently in-memory only—no feedback loop adjusts weights based on response quality.
4.5 Confidence Scoring
Response confidence is computed additively: entity resolution quality (0–0.3) + evidence depth (0–0.3) + graph context (0–0.2) + metrics availability (0–0.2). This is a good start but has two issues: (1) it measures input quality, not output quality—a response with excellent input data but a hallucinated narrative still gets high confidence; (2) graph context gives full marks at ≥20 nodes, which is easily reached for well-connected entities regardless of whether those nodes are relevant.
 
5. Data Layer AI-Readiness
5.1 Readiness Scorecard
Dimension	Score	Strength	Gap
Graph topology	8/10	11+ link types, provenance tracked	Flat confidence (all 1.0)
Materialised views	9/10	5 MVs covering core pharma KPIs	Evidence density = volume only
External data sources	8/10	18 connectors across pharma data	NADAC deprecated, OT partial
Embedding coverage	4/10	Infrastructure exists (pgvector)	Likely sparse on core tables
Entity resolution	6/10	Exact + fuzzy + alias matching	No semantic deduplication
Quality monitoring	7/10	FAIR scorer, 5 dimensions	No automated remediation
Conversation memory	7/10	Token-budgeted, entity tracking	String-based coreference
Temporal modelling	3/10	Timestamps on records	No time-series analytics
Ontology alignment	5/10	MeSH-seeded TAs and mechanisms	No continuous sync, static hierarchy

5.2 The Embedding Gap
This is the single largest data-layer risk. Vector columns exist on 10 tables with HNSW indexes, but actual population is unverified for drugs, trials, companies, and articles. If molecule_embedding on the drugs table is empty, vector search for drug queries returns zero results and silently falls back to keyword matching—which means the user gets results based on string overlap rather than semantic relevance. The team should run a coverage audit: SELECT entity_type, COUNT(*) total, COUNT(embedding_col) populated, ROUND(COUNT(embedding_col)::numeric / COUNT(*) * 100, 1) AS pct FROM {table} for each entity type.
5.3 The Confidence Gap
All 11+ link types in entity_links share default confidence=1.0. In practice, an OWNS link from FDA Orange Book (near-certain) and a COMPETES_WITH link from LLM extraction (uncertain) are indistinguishable. This means graph traversal treats speculative relationships as facts. Fix: assign confidence tiers by provenance source: exact_id=1.0, structured_api=0.9, entity_resolution=0.8, cross_source_match=0.7, llm_extracted=0.5, heuristic=0.3. Apply minimum confidence thresholds in graph traversal (default 0.5).
5.4 The Temporal Gap
The data has timestamps (created_at, updated_at, trial start dates, publication dates) but no time-series infrastructure. Questions like “How has the GLP-1 landscape changed in the last year?” or “Is Novo Nordisk’s pipeline accelerating?” cannot be answered because there are no temporal aggregations, no change detection, and no trend MVs. The InsightEngine detects point-in-time signals (new trial, safety event) but cannot compute trajectories.
 
6. Per-Intent Quality Audit
6.1 Dossier (Benchmark: 70.3%)
The weakest core intent. The handler queries well (entity resolution → DB joins → graph 2-hop → metrics → similar entities), but the LLM synthesis often produces generic summaries that don’t leverage the structured data handed to it. The handler passes pipeline_score, success_rate, evidence_density, connection counts, and market events—but the generated narrative frequently ignores half of these dimensions.
Root cause: The system prompt for dossier is the weakest of all intents—it lacks the specific structural guidance that landscape and compare prompts have. It tells the LLM to “be comprehensive” without specifying which dimensions to cover in which order. Adding few-shot exemplars that demonstrate full-dimension coverage would likely close the gap to 85%+.
6.2 Compare (Benchmark: 100%)
The strongest intent, but the 100% score deserves scrutiny. Compare benefits from: (1) pre-computed differentials (pipeline_score ratio, trial volume difference, Phase 3 leadership) that the LLM can cite directly rather than computing; (2) a highly structured system prompt with explicit rules; (3) a comparison table displayed alongside the narrative, reducing the LLM’s burden. The risk is that the golden dataset only tests 6 compare queries, all with clean “X vs Y” phrasing. Adversarial cases (incomplete compare, multi-entity compare, cross-type compare) would likely reveal gaps.
6.3 Landscape (Benchmark: 79.5%)
Good but uneven. The handler assembles competitive segments from mv_competitive_landscape, computes HHI concentration, queries company portfolios, and expands top-5 segments via graph neighbourhood queries. The system prompt correctly frames results as therapeutic area segments, not company rankings. The MV fallback (original_topic parameter) handles edge cases where the expanded topic returns sparse results.
Remaining gap: Landscape queries about thin-data areas (rare diseases, neurology, cell therapy) still score poorly because the materialised views return empty. The fallback queries base tables but these may also be sparse. The system should explicitly acknowledge data coverage limits: “Our database covers 1,247 drugs across 45 therapeutic areas. For [rare disease X], we have limited coverage (3 drugs, 7 trials).”
6.4 Pipeline (Benchmark: ~80%)
Solid on well-covered therapeutic areas (diabetes, obesity, cardiovascular) where mv_drug_pipeline_strength has rich data. The phase-weighted scoring (P1=1, P2=2, P3=4, P4=1) is pharma-appropriate. Weakness: no distinction between active and completed trials in the narrative—an entity with 50 completed P2 trials and 0 active trials appears stronger than one with 3 active P3 trials, which is misleading for forward-looking pipeline assessment.
6.5 Structured Query (Benchmark: 100%)
Routes to LangGraph agent with SQL generation capability. The 100% score reflects that the golden queries are straightforward counting/listing queries. The risk is that more complex structured queries (joins, conditional aggregations, temporal filters) would challenge the SQL generation quality. Not enough adversarial cases in the benchmark to stress-test this.
 
7. Recommendations: Making Intelligence Trustworthy
7.1 Pre-Generation Grounding (Highest Impact)
Replace post-hoc validation with a pre-generation grounding mechanism. Before the LLM generates a response, build a structured fact sheet from the deterministic data:
1.	Extract key metrics as named facts: {pipeline_score: 42.5, source: mv_drug_pipeline_strength, entity: semaglutide}
2.	Extract entity relationships as triples: {semaglutide TARGETS GLP-1 receptor, confidence: 0.95, source: ChEMBL}
3.	Build a fact inventory with provenance: “You have 7 verified facts, 3 evidence snippets, and 2 graph paths to work with.”
4.	Inject this inventory alongside the raw context. Post-synthesis, verify that every factual claim in the narrative maps to an inventory item. Claims that don’t map get flagged (not silently passed).
7.2 Intent Confidence and Disambiguation
1.	Add a confidence score (0–1.0) to intent detection output, based on: number of patterns matched, specificity of match (full regex vs keyword only), presence of entity resolution support.
2.	For ambiguous queries (confidence < 0.7), generate responses for the top-2 intents and let the user choose, or hedge: “I’ve interpreted this as a comparison. If you wanted a dossier on both, let me know.”
3.	Replace string-based coreference with entity-ID tracking from ConversationMemory._entity_counts.
7.3 Embedding Backfill and Audit
1.	Run coverage audit across all 10 vector-enabled tables. Target: ≥90% population for drugs, trials, articles, companies.
2.	Schedule embedding refresh on data pipeline runs (not just initial backfill). New trials and articles should be embedded within 24 hours of ingestion.
3.	Remove recency multiplier from literature and trial search. Apply recency only to news/events where timeliness is the primary signal.
7.4 Link Confidence Tiers
1.	Assign confidence by provenance: exact_id=1.0, structured_api=0.9, entity_resolution=0.8, cross_source=0.7, llm_extracted=0.5, heuristic=0.3.
2.	Add a min_confidence parameter to graph traversal (default 0.5). This filters out speculative links before they reach the LLM.
3.	Surface confidence in the frontend: edges with confidence < 0.7 render as dashed lines in the graph. The user sees which relationships are certain vs inferred.
7.5 Dossier Prompt Improvement
1.	Add structured dimension ordering to the dossier system prompt: “Your response must cover these dimensions in order: (1) Identity and classification, (2) Pipeline position and strength, (3) Evidence depth and recency, (4) Competitive context, (5) Key risks or signals.”
2.	Add 3–5 few-shot exemplar dossiers that demonstrate full-dimension coverage with citation density ≥2 per paragraph.
3.	Add a post-synthesis dimension check: verify that the generated narrative mentions at least 4 of the 5 required dimensions. If not, append a note: “Note: Limited data available for [missing dimension].”
7.6 Evidence Quality Scoring
1.	Extend mv_evidence_density to include a quality dimension: journal impact factor (or tier), study design (RCT > observational > case report), sample size.
2.	Weight evidence in the LLM context by quality: a Nature Medicine RCT should appear before a conference abstract in the evidence list.
3.	Surface evidence quality in citations: [1, high-quality RCT] vs [2, conference abstract].
7.7 Temporal Intelligence Layer
1.	Add a mv_pipeline_velocity materialised view that computes month-over-month changes in pipeline_score, trial_count, and active_trial_count per drug and therapeutic area.
2.	Wire InsightEngine to detect velocity changes: “Glp-1 pipeline accelerating: +3 new P3 trials in 30 days” as proactive signals.
3.	Add a temporal filter to graph traversal: “Show me connections created in the last 90 days” to support trend-based questions.
 
8. Intelligence Maturity Model
The following model positions Market Zero’s current state and charts the path to each level:
Level	Name	Capability	Market Zero Status
L1	Data Retrieval	Find and display relevant records	Achieved — search, graph, MVs
L2	Grounded Synthesis	Generate narratives from verified data only	Partial — post-hoc validation, not pre-gen
L3	Analytical Intelligence	Surface nuance: differentials, trends, risks	Partial — compare has differentials; dossier/landscape don’t
L4	Proactive Intelligence	Detect signals and alert before users ask	Early — InsightEngine exists, 3 signal types
L5	Decision Support	Scenario modelling, what-if reasoning	Not started — scenario primitives designed, not built

The immediate priority should be solidifying L2 (pre-generation grounding) and extending L3 (analytical intelligence across all intents, not just compare). L4 and L5 can follow once the foundation is trustworthy.
9. Conclusion
Market Zero’s intelligence pipeline has excellent bones. The deterministic-first architecture (SQL → graph → materialised views → LLM) is the right approach for pharma intelligence where trust matters more than creativity. The 5 materialised views, 18 data connectors, 11+ link types, and Concept Registry create a rich analytical substrate.
The system’s intelligence is weakest at its two boundaries. On the input side, regex-based intent detection handles clean queries well but breaks on compound, ambiguous, or conversational questions—exactly the kind that senior analysts ask. On the output side, post-hoc hallucination detection catches numeric fabrication and invalid citations but misses qualitative hallucination, causal confabulation, and omission bias.
The data layer is 70% AI-ready. Graph structure and MV coverage are strong, but sparse embeddings limit semantic search quality, flat confidence scoring treats speculative links as facts, and the absence of temporal modelling means the system cannot answer the “how is this changing?” questions that drive real pharma decisions.
The seven recommendations in Section 7 chart a path from the current state to genuinely trustworthy pharma intelligence. Pre-generation grounding (7.1) and link confidence tiers (7.4) are the highest-impact changes. Together they would ensure the LLM works from verified facts with calibrated certainty—which is what pharmaceutical decision-makers need most.

That's the right question to be asking, and the honest answer is: no, not yet. What you have is a property graph with good structural bones but almost no semantic layer. Let me be specific about what's there and what's missing.This is fascinating — and changes my assessment significantly. You actually have *two* codebases here, and they're living very different lives.

Your **sdk_core** package (under `packages/sdk_core`) has genuinely sophisticated ontology infrastructure: formal `EntitySchema` with validation and lookup keys, `LinkRule` with directionality and SQL join paths, a `TerminologyRegistry` with hierarchical concepts (parent/child), a multi-strategy `EntityResolver` cascade, temporal properties on graph edges (`valid_at`/`invalid_at`), and even a rule-based `OntologyEngine` for inference. The architecture is clean — frozen dataclasses, protocol-based injection points for external terminologies, audit trails on resolution decisions.

But the **production application** — the code actually serving users on Railway — isn't using any of it. Let me be blunt about the gap.

**What's live in production:**

The `services/graph.py` that runs your chat handlers uses a flat `entity_links` table with string-typed `link_type` values and uniform `confidence=1.0`. There's no formal entity schema — entity types are inferred from which database table a record lives in. The concept registry in `services/concept_registry.py` is 15 hardcoded pharma concepts instantiated in memory on startup with no connection to MeSH, ATC, or SNOMED. Entity resolution in the chat pipeline is basic string matching against database columns — not the sophisticated multi-strategy cascade in sdk_core. There's no hierarchy, no synonym expansion, no temporal modelling on relationships.

So your ontology story is really two stories: a well-designed but unintegrated SDK, and a production system running on structural shortcuts.

**Why this matters for intelligence quality:**

Without a proper meaning layer, every downstream component suffers in ways that are hard to see from the outside but corrosive to answer quality.

*Entity resolution* — when a user asks about "Keytruda," the production system has to hope that exact string appears in the database. If the record is stored as "pembrolizumab" with no alias table wired up, the query silently returns thin results. The user gets a vague answer and assumes your platform doesn't know about a blockbuster drug. The sdk_core `EntityResolver` solves this with its normalisation cascade (strip dosage forms, try aliases, fall back to fuzzy matching), but that code isn't called.

*Hierarchical reasoning* — if someone asks "what's the competitive landscape for GLP-1 agonists," the system needs to know that semaglutide, tirzepatide, and liraglutide all belong to that mechanism class. Without a taxonomy linking drugs to mechanism hierarchies, your landscape handler can only find competitors if the exact phrase "GLP-1" appears in the right database fields. The sdk_core `Concept` model supports parent/child hierarchies that would let you traverse upward from a specific drug to its mechanism class and then back down to all siblings — but again, not wired.

*Link semantics* — your production entity_links treat all relationships as equivalent. An "OWNS" link (Lilly owns tirzepatide) and a "TARGETS_MECHANISM" link (tirzepatide targets GIP/GLP-1) carry the same confidence and no temporal metadata. This means the graph traversal can't distinguish between a current ownership relationship and a historical licensing deal that ended in 2019. The sdk_core `GraphEdge` has `valid_at`/`invalid_at` fields specifically for this, plus weighted edges — but the production graph doesn't use them.

*Concept grounding for LLM prompts* — right now, the concept registry injects hints like "pipeline_strength" or "competitive_landscape" into the LLM system prompt based on intent matching. These are useful navigation signals but they're not grounded in a formal ontology. The LLM receives a hint that says "consider pipeline strength" but has no structured definition of what pipeline strength means in terms of phase distribution, success probability, or therapeutic area coverage. A proper concept model would let you inject machine-readable definitions that constrain the LLM's reasoning.

**What I'd recommend:**

The sdk_core infrastructure is the right design. The gap isn't architectural imagination — it's integration. The priority should be wiring the existing sdk_core components into the production pipeline, not building new ontology infrastructure from scratch. Concretely:

First, get the `EntityResolver` from sdk_core into the chat handler pipeline, replacing the current string-match resolution. This alone would dramatically improve hit rates for drug queries where users use brand names, abbreviations, or informal terms. The alias store needs to be populated from your FDA and ClinicalTrials.gov connectors — both sources provide canonical name-to-brand mappings that can seed the registry automatically during ingestion.

Second, populate the `TerminologyRegistry` with MeSH descriptors for therapeutic areas and mechanisms. You already have MeSH as one of your 18 connectors. The registry's `TerminologyPort` protocol means you can start with an in-memory snapshot of the MeSH tree for your core therapeutic areas and progressively expand it. This gives you hierarchical traversal — "find all drugs targeting GLP-1 receptor agonism" becomes a tree walk rather than a keyword match.

Third, migrate `entity_links` to carry typed confidence scores and temporal validity. Not every link needs a timestamp on day one, but the schema should support it so that ingestion pipelines can start writing temporal metadata as they encounter it. FDA approval dates, patent expiry dates, licensing deal timelines — all of these are available in your existing data sources and would immediately enrich the graph.

Fourth, wire the `OntologyEngine` inference rules into the post-retrieval pipeline, between data gathering and LLM synthesis. Rules like "if a drug has Phase 3 trials in 3+ indications AND annual revenue > $1B, classify as franchise asset" would give the LLM structured judgements to work with rather than asking it to infer these patterns from raw data.

The fundamental issue isn't that you lack ontology capability — the sdk_core proves you don't. It's that the production system was built on a faster path that skipped the semantic layer, and now every intelligence feature is working harder than it should to compensate for that missing foundation. Closing this gap is probably the single highest-leverage investment for answer quality.