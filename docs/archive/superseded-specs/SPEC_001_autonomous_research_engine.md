# SPEC-001: Autonomous Research Engine

> **Status**: Draft
> **Priority**: P1
> **Dependencies**: CTX_mod (C:\Users\kapil\Documents\CTX_mod), existing pipeline services
> **Inspired by**: karpathy/autoresearch (autonomous experiment loop pattern)

---

## Problem Statement

The current chat pipeline is a **single-pass request-response fork**:
- 8 hardcoded intent handlers, each independently fetching data and calling the LLM
- No reasoning step (sufficiency check, conflict detection, gap identification)
- No autonomous enrichment (pipeline only runs on demand)
- LLM used for polish, not reasoning — leading to hallucination when data is thin
- Conversation memory is a 500-char truncation hack
- CTX integration at ~5% of its capability (only L2 serializer)

## Solution: Staged Pipeline + Autonomous Research Loop

### Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  LAYER 1: CTX Knowledge Corpus (offline, nightly)            │
│                                                              │
│  DB entities ──► CTX Packer ──► L2 corpus + L3 index         │
│  (drugs, trials,    │           (~3.9K tokens/query           │
│   companies, ...)   │            vs 92K stuffed)              │
│                     │                                        │
│  Quality Gate: compression ratio ≥10x, entity coverage 100%  │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│  LAYER 2: Staged Query Pipeline (per-request)                │
│                                                              │
│  ┌─────────┐   ┌──────────┐   ┌────────┐   ┌────────────┐  │
│  │UNDERSTAND│──►│ RETRIEVE  │──►│ REASON │──►│ SYNTHESIZE │  │
│  │          │   │          │   │        │   │            │  │
│  │• NER     │   │• Hydrate │   │• Suff. │   │• Grounded  │  │
│  │• Coref   │   │• SQL agg │   │• Gaps  │   │• Cited     │  │
│  │• Decomp  │   │• Graph   │   │• Conf. │   │• Guarded   │  │
│  │• Classify│   │• Vector  │   │• Re-try│   │• Streamed  │  │
│  └─────────┘   └──────────┘   └────────┘   └────────────┘  │
│                                                              │
│  Quality Gate: ContextGuard pass, citation coverage ≥80%     │
└──────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌──────────────────────────────────────────────────────────────┐
│  LAYER 3: Autonomous Research Loop (background, continuous)  │
│                                                              │
│  Loop:                                                       │
│    1. Identify weak entities (low FAIR score, few links)     │
│    2. Plan enrichment (what to look up, where)               │
│    3. Execute (PubMed, ClinicalTrials, FDA, web)             │
│    4. Evaluate (did FAIR score improve?)                      │
│    5. Keep if improved, revert if not                        │
│    6. Log to research_results.tsv                            │
│                                                              │
│  Quality Gate: FAIR delta ≥ 0, no false link rate increase   │
└──────────────────────────────────────────────────────────────┘
```

---

## Implementation Phases

### Phase 1: CTX Knowledge Corpus (Foundation)
**Goal**: Replace ad-hoc context assembly with compiled CTX knowledge base

#### 1.1 Entity Packer
Export DB entities → YAML/JSON corpus → CTX L2 + L3

```python
# services/ctx_corpus.py
class PharmaCorpusBuilder:
    """Export market_zero entities to CTX-packable corpus."""

    def export_drugs(self, limit=None) -> list[dict]:
        """Export drugs with mechanism, company, therapeutic area."""

    def export_trials(self, limit=None) -> list[dict]:
        """Export trials with phase, status, endpoints."""

    def export_companies(self, limit=None) -> list[dict]:
        """Export companies with portfolio, pipeline scores."""

    def build_corpus_dir(self, output_dir: str) -> str:
        """Write entity YAML files to corpus directory."""

    def pack(self, output_dir: str) -> PackResult:
        """Run CTX packer on corpus → L2 + L3 documents."""
```

**Tests**:
- `test_export_drugs_completeness`: All drugs in DB appear in corpus
- `test_export_preserves_relationships`: Drug→mechanism, drug→company links intact
- `test_pack_compression_ratio`: Ratio ≥ 10x on full corpus
- `test_pack_entity_coverage`: Every entity type has ≥1 section
- `test_l3_index_size`: L3 < 2000 tokens (fits in any context window)
- `test_round_trip`: Pack → parse → validate = no errors

**Quality Gate**:
```
✅ Compression ratio ≥ 10x
✅ Entity coverage = 100% of DB entity types
✅ L3 index < 2000 tokens
✅ Zero E-level validation errors
✅ Zero data loss (all fields present in L2)
```

#### 1.2 Hydration Integration
Replace `_build_context_block` with CTX hydration

```python
# services/ctx_pipeline.py
class CTXQueryPipeline:
    """Staged query pipeline using CTX hydration."""

    def __init__(self, corpus_doc: CTXDocument, l3_doc: CTXDocument):
        self.hydrator = Hydrator(corpus_doc)
        self.entity_graph = EntityGraph.from_document(corpus_doc)
        self.keyword_index = KeywordIndex.from_document(corpus_doc)
        self.guard = ContextGuard(known_entity_names=...)
        self.grounding = GroundingWrapper(...)

    def understand(self, question: str, history: list) -> QueryPlan:
        """NER + coreference + decomposition + classification."""

    def retrieve(self, plan: QueryPlan) -> RetrievalResult:
        """Hydrate relevant sections + SQL + graph + vector."""

    def reason(self, retrieval: RetrievalResult) -> ReasoningResult:
        """Sufficiency check, conflict detection, gap identification."""

    def synthesize(self, reasoning: ReasoningResult) -> Response:
        """Grounded narrative with citations and guard check."""
```

**Tests**:
- `test_hydration_token_budget`: Injected tokens < 5000 per query
- `test_hydration_relevance`: Correct sections returned for known queries
- `test_entity_graph_traversal`: Drug→mechanism→trial path works
- `test_keyword_matching`: "GLP-1" → ENTITY-MECHANISM-GLP1-AGONISTS
- `test_guard_catches_hallucination`: Invented drug name → low_confidence
- `test_grounding_sandwich`: System prompt has TOP rules + BOTTOM checklist

**Quality Gate**:
```
✅ Hydration tokens/query < 5000 (vs 92K stuffed)
✅ Hydration relevance ≥ 80% (correct section in top-3)
✅ ContextGuard catches 100% of known hallucination patterns
✅ Grounding wrapper present in every LLM call
```

---

### Phase 2: Staged Query Pipeline (Core Refactor)
**Goal**: Replace 8 intent handlers with unified retrieve→reason→synthesize

#### 2.1 Understand Stage
```python
@dataclass
class QueryPlan:
    original_question: str
    resolved_question: str          # After coreference resolution
    entities_detected: list[str]    # NER results
    sub_queries: list[str]          # Decomposed if multi-part
    information_needs: list[str]    # What data is needed
    suggested_sources: list[str]    # Which services to query
```

**Tests**:
- `test_coreference_resolution`: "Which one is safer?" → "Which of semaglutide and tirzepatide is safer?"
- `test_multi_part_decomposition`: "Compare GLP-1 landscape and show top companies" → 2 sub-queries
- `test_entity_detection`: "semaglutide" → [("semaglutide", "drug")]
- `test_source_suggestion`: Pipeline question → ["metrics.drug_pipeline_strength"]

#### 2.2 Retrieve Stage
```python
@dataclass
class RetrievalResult:
    ctx_sections: list[Section]     # Hydrated from CTX corpus
    sql_results: list[dict]         # Aggregation queries
    graph_context: dict             # Neighborhood traversal
    vector_evidence: list[dict]     # Embedding search results
    token_count: int                # Total retrieval tokens
    sources_queried: list[str]      # Provenance
```

**Tests**:
- `test_retrieval_parallel`: SQL + hydration + vector run concurrently
- `test_retrieval_deduplication`: Same entity from multiple sources → single entry
- `test_retrieval_provenance`: Every fact has source attribution

#### 2.3 Reason Stage (THE KEY MISSING PIECE)
```python
@dataclass
class ReasoningResult:
    sufficient: bool                # Enough data to answer?
    gaps: list[str]                 # What's missing?
    conflicts: list[str]           # Contradicting sources?
    confidence: float              # 0-1 overall confidence
    refined_queries: list[str]     # If insufficient, what to look up next
    computed_insights: list[str]   # Pre-computed differentials, ranks
    retrieval: RetrievalResult     # Original data (passed through)
```

**Tests**:
- `test_sufficiency_detection`: Empty evidence → sufficient=False
- `test_conflict_detection`: Drug approved in FDA but "terminated" in trials → conflict flagged
- `test_gap_identification`: "Compare X vs Y" but only X has metrics → gap noted
- `test_requery_on_insufficient`: Triggers second retrieval with refined query
- `test_computed_insights`: Pre-computes "3.2x stronger pipeline" from raw numbers

**Quality Gate**:
```
✅ Sufficiency check runs on every query (never skipped)
✅ Conflicts detected with ≥90% recall on test set
✅ Gaps identified when coverage < 50% of query entities
✅ Re-query improves answer quality on 80%+ of insufficient cases
```

#### 2.4 Synthesize Stage
```python
@dataclass
class Response:
    narrative: str                  # Grounded, cited narrative
    table_data: dict | None         # Structured data
    visualizations: list[dict]      # Charts
    citations: list[Citation]       # Source-linked citations
    confidence: float               # From reasoning stage
    guard_result: GuardResult       # Post-synthesis hallucination check
    followups: list[str]            # Data-grounded suggestions
```

**Tests**:
- `test_citations_linked`: Every [N] marker maps to a real evidence item
- `test_guard_post_check`: Synthesized narrative passes ContextGuard
- `test_no_hallucinated_numbers`: Numbers in narrative all appear in retrieval data
- `test_followups_grounded`: Suggestions reference entities actually in the data

**Quality Gate**:
```
✅ Citation coverage ≥ 80% (claims have source)
✅ ContextGuard: zero "retry" signals on golden test set
✅ Hallucination rate < 5% on golden test set
✅ Response latency p95 < 8 seconds
```

---

### Phase 3: Autonomous Research Loop (Background Agent)
**Goal**: Continuously improve knowledge graph quality without human intervention

#### 3.1 Research Protocol
Inspired by autoresearch's `program.md`:

```markdown
# research_protocol.md — Agent Instructions

## Objective
Improve the Market Zero knowledge graph by finding and filling gaps.

## Loop
1. Query the FAIR analysis for entities with score < 6.0
2. Pick the highest-impact gap (most connections, lowest score)
3. Plan enrichment:
   - Missing mechanism? → Search PubMed for drug mechanism
   - Missing company? → Search SEC Edgar, FDA approvals
   - Few trials? → Query ClinicalTrials.gov
   - Stale data? → Re-fetch from source
4. Execute the enrichment (API calls, parsing)
5. Validate: Run FAIR scorer on the entity
6. If FAIR score improved AND no false links created → commit
7. If FAIR score unchanged or decreased → revert
8. Log result to research_results.tsv
9. Repeat

## Constraints
- Max 1 entity per iteration
- Max 5 API calls per iteration
- Never delete existing data, only add/update
- Flag uncertain enrichments for HITL review
```

#### 3.2 Research Agent
```python
# services/research_agent.py
class AutonomousResearchAgent:
    """Background agent that finds and fills knowledge gaps."""

    def __init__(self, db, pipeline, fair_scorer):
        self.db = db
        self.pipeline = pipeline
        self.fair = fair_scorer
        self.results_log = "research_results.tsv"

    def identify_target(self) -> ResearchTarget:
        """Find highest-impact entity with low FAIR score."""

    def plan_enrichment(self, target: ResearchTarget) -> EnrichmentPlan:
        """Decide what data to fetch and from where."""

    def execute_enrichment(self, plan: EnrichmentPlan) -> EnrichmentResult:
        """Fetch data from external sources."""

    def evaluate(self, target: ResearchTarget, result: EnrichmentResult) -> EvalResult:
        """Compute FAIR delta, check for false links."""

    def commit_or_revert(self, eval_result: EvalResult) -> bool:
        """Keep if improved, revert if not. Log either way."""

    def run_loop(self, max_iterations: int = 100):
        """Main autonomous loop. Runs until max_iterations or no targets."""
```

**Tests**:
- `test_identify_lowest_fair`: Returns entity with lowest FAIR score
- `test_plan_mechanism_gap`: Missing mechanism → PubMed search plan
- `test_plan_company_gap`: Missing company → SEC/FDA search plan
- `test_evaluate_improvement`: FAIR +0.5 → keep=True
- `test_evaluate_regression`: FAIR -0.1 → keep=False
- `test_revert_on_false_link`: New link to wrong entity → reverted
- `test_results_logging`: Every iteration logged with timestamp, target, action, delta

**Quality Gate (per iteration)**:
```
✅ FAIR delta ≥ 0 (never decrease quality)
✅ False link rate = 0 (no incorrect entity links)
✅ API call budget ≤ 5 per iteration
✅ Entity not already in HITL queue
```

**Quality Gate (aggregate, per run)**:
```
✅ Mean FAIR delta > 0 across all iterations
✅ ≤ 10% of iterations flagged for HITL review
✅ No entity enriched more than 3 times (prevent loops)
✅ Total API calls within rate limits
```

---

### Phase 4: Conversation Memory via CTX AgentSession
**Goal**: Replace 500-char truncation with token-budget-managed memory

#### 4.1 Session Manager
```python
# services/conversation_memory.py
class ConversationMemory:
    """CTX-based conversation memory with token budget."""

    def __init__(self, token_budget: int = 4000):
        self.session = AgentSession(
            domain="pharma-intelligence",
            token_budget=token_budget,
        )

    def add_exchange(self, question: str, response: Response):
        """Compress and add exchange to session."""

    def get_context(self) -> str:
        """Get current compressed context for LLM."""

    def get_entities_discussed(self) -> list[str]:
        """Extract all entities mentioned across session."""

    def resolve_reference(self, question: str) -> str:
        """Resolve coreferences using full session history."""
```

**Tests**:
- `test_budget_enforcement`: 20 exchanges → still under 4000 tokens
- `test_eviction_strategy`: Oldest low-salience exchanges evicted first
- `test_entity_tracking`: Entities from turn 1 still accessible in turn 10
- `test_reference_resolution`: "that drug" in turn 5 → entity from turn 2

---

## Evaluation Framework

### Golden Test Set
Build a curated set of 50 questions with known-good answers:

| Category | Count | Examples |
|----------|-------|---------|
| Single entity lookup | 10 | "What is semaglutide?" |
| Comparison | 8 | "Compare semaglutide vs tirzepatide" |
| Aggregation | 8 | "How many GLP-1 drugs in Phase 3?" |
| Landscape | 6 | "GLP-1 competitive landscape" |
| Multi-hop | 8 | "Which companies have drugs targeting GLP-1 in obesity?" |
| Follow-up chains | 5 | 3-turn conversations with coreference |
| Adversarial | 5 | "What is the MACE reduction for semaglutide?" (must say N/A) |

### Metrics (automated, per test run)

| Metric | Target | How Measured |
|--------|--------|-------------|
| **Factual accuracy** | ≥ 90% | Claims verified against DB |
| **Citation coverage** | ≥ 80% | Claims with source reference |
| **Hallucination rate** | < 5% | ContextGuard flagged claims |
| **Response latency (p95)** | < 8s | End-to-end timing |
| **Context tokens/query** | < 5000 | CTX hydration measurement |
| **Cost/query** | < $0.05 | Token count × model price |
| **Follow-up accuracy** | ≥ 85% | Coreference resolution correct |
| **FAIR score delta** | > 0 | Research loop improvement |

### A/B Comparison
Run golden test set against:
1. **Current pipeline** (8 intent handlers, legacy context)
2. **CTX pipeline** (staged, hydrated, guarded)

Report: side-by-side accuracy, cost, latency, hallucination rate.

---

## Implementation Order

| Step | Phase | Effort | Depends On | Deliverable |
|------|-------|--------|-----------|-------------|
| 1 | 1.1 | 3 days | — | PharmaCorpusBuilder + packed L2/L3 |
| 2 | 1.2 | 2 days | Step 1 | CTXQueryPipeline with hydration |
| 3 | Eval | 2 days | — | Golden test set (50 questions) |
| 4 | 2.1 | 2 days | Step 2 | Understand stage (NER, coref, decomp) |
| 5 | 2.2 | 2 days | Step 4 | Retrieve stage (parallel, deduplicated) |
| 6 | 2.3 | 3 days | Step 5 | Reason stage (sufficiency, conflicts, gaps) |
| 7 | 2.4 | 2 days | Step 6 | Synthesize stage (grounded, guarded) |
| 8 | A/B | 1 day | Steps 3+7 | Benchmark: old vs new pipeline |
| 9 | 4.1 | 2 days | Step 7 | Conversation memory via AgentSession |
| 10 | 3.1-3.2 | 4 days | Step 7 | Autonomous research loop |

**Total**: ~23 days, can be parallelized (eval set built while corpus packer is developed).

---

## Risk Mitigations

| Risk | Mitigation |
|------|-----------|
| CTX packer can't handle 1600+ drugs | Test with subset first (top 100), scale up |
| Hydration misses relevant sections | Keyword index + entity graph as fallback |
| Reasoning step adds latency | Cache reasoning results for repeated entity patterns |
| Research loop creates bad data | FAIR gate + HITL flag + max 3 enrichments per entity |
| CTX_mod dependency breaks | Zero runtime deps in core; pin version; vendor if needed |

---

## Success Criteria

The new pipeline is considered successful when the golden test set shows:

1. **Factual accuracy ≥ 90%** (up from estimated ~70% today)
2. **Hallucination rate < 5%** (down from estimated ~15% today)
3. **Cost/query reduced by ≥ 50%** (via CTX hydration vs context stuffing)
4. **Response latency p95 < 8s** (no regression from today)
5. **Follow-up accuracy ≥ 85%** (up from estimated ~60% today)
6. **Autonomous research loop improves mean FAIR score by ≥ 0.5 per nightly run**
