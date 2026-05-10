# SPEC-004: Intelligence Pipeline Enhancement

**Date**: 23 March 2026 | **Status**: Draft | **Owner**: Data Librarian + Science Lead

---

## Problem Statement

The intelligence pipeline is architecturally sound and data-grounded (7/10), but has three systemic gaps:
1. Users can't see response quality (no confidence in production handlers)
2. LLM narrative can drift from source data (no post-synthesis verification)
3. The two most valuable query types (landscape, pipeline) have no fallback when materialized views are stale
4. The graph — the platform's most valuable asset — is underutilized

This spec addresses all 17 recommendations from the consolidated review (R1–R17), organized into 4 implementation phases.

---

## Phase 1: Trust & Transparency (Sprint 1–2)

**Goal**: Every response tells the user how confident the system is, and the narrative provably matches the source data.

### 1.1 Confidence Scoring in All Handlers (R1)

**Problem**: Only UnifiedChatHandler (opt-in, no production traffic) computes confidence. All legacy handlers return `confidence: null`.

**Solution**: Add `compute_response_confidence()` to `services/chat_handlers/formatting.py`. Called by every handler before returning.

```python
def compute_response_confidence(
    entity_resolved: bool,
    entity_match_score: float | None,  # 0-1 from resolution
    evidence_count: int,
    graph_node_count: int,
    metrics_available: bool,
    graph_truncated: bool = False,
) -> float:
    """Compute response confidence from data quality signals."""
    score = 0.0

    # Entity resolution (0-0.3)
    if entity_resolved:
        score += 0.3 * (entity_match_score or 0.8)

    # Evidence depth (0-0.3)
    if evidence_count >= 10: score += 0.3
    elif evidence_count >= 5: score += 0.2
    elif evidence_count >= 1: score += 0.1

    # Graph context (0-0.2)
    if graph_node_count >= 20: score += 0.2
    elif graph_node_count >= 5: score += 0.1
    if graph_truncated: score -= 0.05

    # Metrics (0-0.2)
    if metrics_available: score += 0.2

    return round(min(1.0, max(0.0, score)), 2)
```

**Files**: `services/chat_handlers/formatting.py`, `services/chat_handlers/handlers.py` (all handlers), `api/routes/chat.py`
**Tests**: `tests/test_confidence_scoring.py` (~10 tests)
**Effort**: 2 days

### 1.2 Post-Synthesis Numeric Verification (R2)

**Problem**: LLM can write "pipeline score 12.5" when the MV returns 8.5. Nothing catches this.

**Solution**: Add `verify_narrative_numbers()` to `services/llm.py`. After synthesis, extract bold numbers from narrative, cross-check against metrics context. Flag mismatches.

```python
def verify_narrative_numbers(
    narrative: str,
    metrics_context: dict,
    evidence_snippets: list[str],
) -> dict:
    """Extract bold numbers from narrative and verify against source data.

    Returns: {"verified": int, "unverified": int, "mismatches": [...]}
    """
```

**Files**: `services/llm.py`
**Tests**: `tests/test_narrative_verification.py` (~8 tests)
**Effort**: 2 days

### 1.3 Citation Validation (R3)

**Problem**: LLM can cite `[99]` when only 10 evidence items exist.

**Solution**: Add `validate_citations()` to `services/llm.py`. After synthesis, regex-scan for `[N]` markers. Strip invalid citations. Log warnings.

```python
def validate_citations(narrative: str, evidence_count: int) -> str:
    """Remove citation markers that reference non-existent evidence items."""
```

**Files**: `services/llm.py`
**Tests**: `tests/test_citation_validation.py` (~6 tests)
**Effort**: 1 day

### 1.4 Materialized View Fallback (R4)

**Problem**: Landscape and pipeline queries return empty when MVs are stale, despite raw data existing in the graph.

**Solution**: In `handle_landscape()` and `handle_pipeline()`, if MV query returns ≤2 rows, fall back to real-time graph traversal:
- Landscape: query `entity_links` for drugs sharing mechanism+TA, compute drug_count/trial_count per segment
- Pipeline: query `drugs` + `clinical_trials` directly with phase grouping

```python
# In handle_landscape():
segments = metrics_svc.competitive_landscape(topic, limit=30)
if len(segments) < 3:
    # Fallback: real-time graph query
    segments = _landscape_from_graph(db, topic)
    extra_context += "\n[NOTE: Using real-time data — materialized views may be stale]"
```

**Files**: `services/chat_handlers/handlers.py`, `services/metrics.py` (add `_realtime_landscape`, `_realtime_pipeline`)
**Tests**: `tests/test_mv_fallback.py` (~8 tests)
**Effort**: 3 days

---

## Phase 2: Data Quality & Completeness (Sprint 3–5)

**Goal**: Fix known data bugs, add entity resolution confidence, temporal scoring, and graph transparency.

### 2.1 Fix Compare Handler Graph Emission (R5)

**Problem**: `graph_context` returned as `{nodes: [], edges: []}` despite shared/unique connections computed.

**Solution**: In `handle_compare()`, convert `shared_connections` and `unique_connections` to proper `nodes` + `edges` arrays.

**Files**: `services/chat_handlers/handlers.py`
**Tests**: Update `tests/test_entity_dossier.py` or add `tests/test_compare_graph.py`
**Effort**: 1 day

### 2.2 Entity Resolution Confidence (R6)

**Problem**: Fuzzy match can silently return wrong entity. No match_score exposed.

**Solution**: Modify `resolve_entity()` to return `(entity_id, entity_type, match_score)` tuple. If `match_score < 0.8`, add warning to LLM context.

**Files**: `services/chat_handlers/handlers.py` (resolve_entity), `services/search.py`
**Tests**: `tests/test_entity_resolution.py` (~6 tests)
**Effort**: 2 days

### 2.3 Graph Truncation Transparency (R8)

**Problem**: 100-node cap applied silently. Major entities get incomplete neighborhoods.

**Solution**: `traverse()` returns `{"nodes": [...], "truncated": true, "total_available": 347}`. Handlers pass this to confidence scoring and LLM context.

**Files**: `services/graph.py` (traverse), `services/chat_handlers/formatting.py`
**Tests**: `tests/test_graph_truncation.py` (~4 tests)
**Effort**: 1 day

### 2.4 Temporal Evidence Scoring (R9)

**Problem**: 2022 and 2026 evidence weighted equally.

**Solution**: Add recency scoring in `services/search.py` search results:
```
< 30 days: 1.0, 30-90d: 0.7, 90-365d: 0.4, > 1 year: 0.2
```
Sort evidence by `relevance × recency` before truncating to top N. Pass temporal metadata to LLM context.

**Files**: `services/search.py` (search method), `services/chat_handlers/handlers.py`
**Tests**: `tests/test_temporal_scoring.py` (~6 tests)
**Effort**: 2 days

### 2.5 SQL Template Library (R7)

**Problem**: LLM-generated SQL can be semantically wrong.

**Solution**: Create `services/agent/sql_templates.py` with pre-validated SQL for top 20 structured query patterns. Route pattern-matched queries to templates; fall back to LLM for novel queries.

```python
SQL_TEMPLATES = {
    "count_trials_by_phase": "SELECT phase, COUNT(*) FROM clinical_trials WHERE ...",
    "drugs_by_therapeutic_area": "SELECT d.generic_name FROM drugs d JOIN ...",
    ...
}
```

**Files**: `services/agent/sql_templates.py`, `services/agent/graphs/query_graph.py`
**Tests**: `tests/agent/test_sql_templates.py` (~12 tests)
**Effort**: 3 days

### 2.6 CTX Pipeline A/B Evaluation (R10)

**Problem**: CTX pipeline has confidence scoring + guard checks but no production data proving it's better.

**Solution**: Run 100 representative queries through both pipelines. Compare:
- Factual accuracy (manual review of 20 responses)
- Hallucination rate (LLM-judged)
- Latency (p50, p95)
- Token efficiency (compression ratios)

Store results in `reports/ctx_ab_evaluation.md`. Decision: enable by default or keep opt-in.

**Files**: `scripts/ctx_ab_eval.py`, `reports/ctx_ab_evaluation.md`
**Effort**: 3-5 days

---

## Phase 3: Graph Power (Sprint 6–8)

**Goal**: Transform the graph from a retrieval tool into an analytical engine.

### 3.1 Wire Graph into Landscape/Pipeline Queries (R12)

**Problem**: Most valuable queries bypass graph entirely.

**Solution**: New `services/graph_analytics.py` with:
```python
def competitive_segments_from_graph(db, mechanism_or_ta: str) -> list[dict]:
    """Real-time competitive landscape from entity_links traversal."""

def pipeline_from_graph(db, therapeutic_area: str) -> list[dict]:
    """Real-time pipeline strength from drugs + trials direct query."""
```

Wire as primary data source in handlers, with MVs as cache/fallback.

**Files**: `services/graph_analytics.py`, `services/chat_handlers/handlers.py`
**Tests**: `tests/test_graph_analytics.py` (~10 tests)
**Effort**: 1 week

### 3.2 Graph Analytics Module (R11)

**Problem**: No centrality, community detection, or weighted path-finding.

**Solution**: Add to `services/graph_analytics.py`:

```python
def entity_influence(db, entity_id: str) -> float:
    """PageRank-inspired influence score from connection count × confidence."""

def competitive_clusters(db, mechanism_id: str) -> list[dict]:
    """Group drugs into competitive clusters by shared TA + mechanism."""

def weighted_path(db, source_id: str, target_id: str) -> list[dict]:
    """Shortest path weighted by link confidence (not hop count)."""
```

**Files**: `services/graph_analytics.py`
**Tests**: `tests/test_graph_analytics.py` (extend)
**Effort**: 1 week

### 3.3 Compound Intent Support (R13)

**Problem**: "Show Pfizer's portfolio and compare top 3 drugs" fires PORTFOLIO only.

**Solution**: Add intent decomposition in `intent.py`:
```python
def detect_compound_intent(question: str) -> list[tuple[str, dict]]:
    """Detect and return multiple intents from a single question."""
```

Run handlers sequentially, merge responses. LLM synthesizes over combined context.

**Files**: `services/chat_handlers/intent.py`, `api/routes/chat.py`
**Tests**: `tests/test_compound_intent.py` (~8 tests)
**Effort**: 1 week

---

## Phase 4: Domain Richness & Proactive Intelligence (Sprint 9–12)

**Goal**: The system proactively surfaces insights, not just answers questions.

### 4.1 Citation Threading (R14)

**Problem**: No provenance chain from narrative sentence to source record.

**Solution**: Assign `evidence_id` to each data point in LLM context. Instruct LLM to cite these IDs. Frontend renders citations as clickable links to source records.

**Files**: `services/llm.py`, `services/ctx_context.py`, frontend canvas
**Effort**: 1-2 weeks

### 4.2 Temporal Graph Layer (R15)

**Problem**: Entity links lack timestamps. Can't answer "how has competition evolved?"

**Solution**: Add `valid_from TIMESTAMPTZ`, `valid_to TIMESTAMPTZ` to `entity_links` table. Populate from trial start_date, publication_date, approval_date. Enable temporal queries.

**Files**: New migration, `services/graph.py`, `services/graph_analytics.py`
**Effort**: 2 weeks

### 4.3 Proactive Insight Generation (R16)

**Problem**: Canvas answers "what data?" not "so what?"

**Solution**: New `services/insight_engine.py`:
```python
def detect_signals(db) -> list[Insight]:
    """Scan for actionable signals:
    - New safety signals (PRR spike in mv_safety_signals)
    - Pipeline milestones (Phase 3 completion, approval)
    - Competitive shifts (new entrant in concentrated segment)
    - Data freshness alerts (stale sources)
    """
```

Surface as "Recent Signals" strip in canvas empty state and as proactive context in responses.

**Files**: `services/insight_engine.py`, frontend canvas
**Effort**: 2-3 weeks

### 4.4 Calibrated Confidence with Feedback (R17)

**Problem**: Confidence thresholds are fixed (0.2-0.8), not calibrated against actual answer quality.

**Solution**: Log confidence alongside user feedback (thumbs up/down). Quarterly calibration: adjust thresholds so that displayed confidence matches observed accuracy rate.

**Files**: `services/query_telemetry.py`, `services/steward_signals.py`
**Effort**: Ongoing (quarterly cadence)

---

## Implementation Sequence

```
Phase 1 (Sprint 1-2): Trust & Transparency
├── 1.1 Confidence scoring (all handlers)
├── 1.2 Numeric verification (post-synthesis)
├── 1.3 Citation validation (post-synthesis)
└── 1.4 MV fallback (landscape + pipeline)

Phase 2 (Sprint 3-5): Data Quality
├── 2.1 Compare graph emission fix
├── 2.2 Entity resolution confidence
├── 2.3 Graph truncation transparency
├── 2.4 Temporal evidence scoring
├── 2.5 SQL template library
└── 2.6 CTX A/B evaluation

Phase 3 (Sprint 6-8): Graph Power
├── 3.1 Graph-powered landscape/pipeline
├── 3.2 Graph analytics (PageRank, clusters, weighted paths)
└── 3.3 Compound intent support

Phase 4 (Sprint 9-12): Domain Richness
├── 4.1 Citation threading
├── 4.2 Temporal graph layer
├── 4.3 Proactive insight engine
└── 4.4 Calibrated confidence
```

## Estimated Test Impact

| Phase | New Tests | Cumulative |
|-------|-----------|-----------|
| Phase 1 | ~32 | ~430 |
| Phase 2 | ~32 | ~462 |
| Phase 3 | ~26 | ~488 |
| Phase 4 | ~20 | ~508 |

## Success Metrics

| Metric | Baseline | Phase 1 Target | Phase 4 Target |
|--------|----------|----------------|----------------|
| Confidence returned | 0% of responses | 100% | 100% (calibrated) |
| Citation accuracy | Unknown | >95% valid | >99% valid |
| Landscape empty rate | ~10% (stale MV) | <1% (fallback) | 0% (graph-powered) |
| Graph utilization | 3 of 8 intents | 3 of 8 | 7 of 8 |
| User confidence visibility | None | Displayed | Calibrated to accuracy |
| Proactive insights | 0 | 0 | 3-5 per session |

---

*Based on consolidated review from Science & Medical Expert + Data Librarian, covering 17 pipeline files and 17 identified weaknesses.*
