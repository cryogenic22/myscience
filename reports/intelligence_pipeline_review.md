# Market Zero Intelligence Pipeline — Deep Review

**Date**: 23 March 2026 | **Reviewer**: Data Librarian (Claude) | **Version**: 1.0

---

## Executive Summary

The intelligence pipeline is **well-grounded in actual data** — the system gathers structured evidence from search, graph, and metrics services before any LLM call. System prompts enforce strict "context-only" reasoning, CTX compression prevents lost-in-middle degradation, and multi-layer fallbacks ensure responses even when the LLM is unavailable.

However, **the user can't see the quality of that grounding**. Confidence scoring exists only in the opt-in UnifiedChatHandler. Citation validation is absent. Stale materialized views silently degrade landscape and pipeline queries. These gaps don't cause hallucination per se — they cause invisible uncertainty.

**Overall score: 7/10** — Strong data grounding, weak quality transparency.

---

## 1. How the Pipeline Works

### Request → Response Flow

```
User Question
    ↓
Intent Detection (regex, deterministic — services/chat_handlers/intent.py)
    ↓ returns: intent type + extracted params
Handler Selection (8 intent types — services/chat_handlers/handlers.py)
    ↓
Data Gathering (deterministic, no LLM involved):
    ├─ HybridSearch: vector similarity + metadata (services/search.py)
    ├─ GraphTraversal: N-hop BFS via SQL recursive CTEs (services/graph.py)
    └─ PharmaMetrics: pre-computed KPIs from materialized views (services/metrics.py)
    ↓
Context Assembly:
    ├─ CTXContextBuilder: salience-ordered L2 document (services/ctx_context.py)
    └─ Evidence compression via ctxpack (services/ctx_evidence.py)
    ↓
LLM Synthesis (services/llm.py):
    ├─ Intent-specific system prompt with anti-hallucination rules
    ├─ Primary model → fallback model → template narrative
    └─ CTX telemetry logged (tokens, compression, latency)
    ↓
Response: narrative + evidence + graph + metrics + table + visualizations + followups
```

**Key design principle**: All data is gathered deterministically BEFORE the LLM is called. The LLM's job is synthesis, not retrieval.

---

## 2. Grounding Assessment

### What the LLM Receives (Context Block)

For every query, the LLM receives a structured context containing:

| Section | Source | Grounding Level |
|---|---|---|
| Entity details | Direct DB query (drugs, companies, trials tables) | **Hard grounded** — exact field values |
| Metrics | Materialized views (mv_drug_pipeline_strength, etc.) | **Pre-computed** — deterministic, but can be stale |
| Graph summary | SQL recursive CTE traversal (entity_links) | **Hard grounded** — actual relationships |
| Evidence snippets | Vector similarity search (pgvector) | **Relevance-scored** — top N by cosine similarity |
| Conversation context | Token-budgeted memory (services/conversation_memory.py) | **Session-grounded** — from prior exchanges |

### System Prompt Anti-Hallucination Rules

All intents use these mandatory rules (services/llm.py:24-27):

> "STRICT DATA GROUNDING: ONLY use numbers, percentages, and facts that appear in the PROVIDED CONTEXT below. Do NOT supplement with knowledge from your training data."

> "If the data is thin, say so honestly ('limited data available for X') rather than padding with external knowledge."

> "Do NOT inject clinical trial results, efficacy percentages, MACE reductions, or any other statistics from your training data."

**Verdict**: Grounding rules are **strong**. The LLM is explicitly told to use only provided data. However, enforcement is by prompt instruction only — no post-hoc validation.

### Fallback Architecture

When the LLM fails or is unavailable, every handler has a **template fallback narrative** built from the same deterministic data:

```
"**semaglutide** (Ozempic) — owned by **Novo Nordisk**, a **GLP-1 agonist** targeting
**Obesity**. Pipeline score 42.5 across 47 trials, strongest in **Phase 3** (5 trials)."
```

This ensures the response is always data-grounded, even with zero LLM involvement.

---

## 3. Intent-by-Intent Analysis

### 3.1 Dossier ("Tell me about semaglutide")

| Data Source | Used? | What's Retrieved |
|---|---|---|
| Entity resolution | Yes | Fuzzy match on drug/company/trial tables |
| Search (vector) | Yes | Top 15 similar entities across all types |
| Graph (1-hop) | Yes | Connected companies, mechanisms, TAs, trials |
| Metrics | Yes | Pipeline score, trial success rate, evidence density |
| Evidence snippets | Yes | Top 10 search results with provenance |

**Canvas output**: Entity card + metrics table + graph visualization + evidence list
**Grounding**: Strong — all data from DB. Weakness: fuzzy entity resolution can silently match wrong entity.

### 3.2 Compare ("semaglutide vs tirzepatide")

| Data Source | Used? | What's Retrieved |
|---|---|---|
| Entity resolution | Yes | Both entities resolved independently |
| Search | Yes | Per-entity evidence |
| Graph | Partial | Shared + unique connections computed but **NOT returned as graph_context** |
| Metrics | Yes | Per-entity pipeline score, trials, success rate |
| Pre-computed insights | Yes | Differentials (5.2x stronger, +12 trials, etc.) |

**Canvas output**: Comparison table + metrics
**Grounding**: Strong for metrics. **Gap**: Graph tab is empty (graph_context returned as `{nodes: [], edges: []}` despite shared connections being computed internally).

### 3.3 Landscape ("GLP-1 competitive landscape")

| Data Source | Used? | What's Retrieved |
|---|---|---|
| Entity resolution | No | Topic keyword expansion only |
| Search | No | Not used |
| Graph | No | Not used |
| Metrics | **Yes (sole source)** | mv_competitive_landscape materialized view |
| Concentration analysis | Yes | HHI, top-3 share, market labels |

**Canvas output**: Competitive segments table + concentration metrics
**Grounding**: Depends entirely on materialized view freshness. **Critical gap**: If the MV is stale or empty for the topic, response is "No competitive landscape data available" — even though raw data exists in the graph.

### 3.4 Pipeline ("Drug pipeline for diabetes")

| Data Source | Used? | What's Retrieved |
|---|---|---|
| Metrics | **Yes (sole source)** | mv_drug_pipeline_strength filtered by TA |
| Phase maturity | Yes | Computed from metrics (late-stage vs early-stage) |
| Search | No | — |
| Graph | No | — |

**Canvas output**: Pipeline table with phase distribution
**Grounding**: Same MV dependency as landscape. No real-time fallback.

### 3.5 Portfolio ("Novo Nordisk portfolio")

| Data Source | Used? | What's Retrieved |
|---|---|---|
| Entity resolution | Yes | Company resolved |
| Search | Yes | Evidence linked to company |
| Graph (1-hop) | Yes | Company's drug/trial connections |
| Metrics | Yes | mv_company_portfolio (drug count, trial count, TAs) |

**Canvas output**: Portfolio metrics + entity card + evidence
**Grounding**: Strong — combines graph + metrics + evidence.

### 3.6 General (free-form questions)

| Data Source | Used? | What's Retrieved |
|---|---|---|
| Search (vector) | Yes | Top 15 across all entity types |
| Graph (1-hop) | Yes | Neighborhood for top 5 results |
| Metrics | Yes | For identified entities |
| Entity resolution | No | No pre-resolution — relies on search ranking |

**Canvas output**: Evidence list + graph + metrics (if entities found)
**Grounding**: Adequate but unvalidated. No confidence check that search results actually match the question. Ambiguous queries can produce mixed, irrelevant evidence.

---

## 4. Graph Power Assessment

### What the Graph Provides

| Operation | SQL Mechanism | Used By |
|---|---|---|
| 1-hop neighborhood | `traverse_graph(id, 1)` recursive CTE | Dossier, Portfolio, General |
| N-hop traversal | `traverse_graph(id, N)` BFS | Graph Explorer (frontend) |
| Shortest path | BFS with 4s timeout | Path-finding queries |
| Entity summary | Join graph + metrics | Entity detail views |
| Mechanism hierarchy | `IS_PARENT_OF` traversal | Mechanism landscape |
| Drugs by mechanism | mechanism → drugs via links | Mechanism grouping |

### Graph Utilization by Intent

| Intent | Graph Used? | How |
|---|---|---|
| Dossier | **Yes** | 1-hop to find connected entities, counts by type |
| Compare | **Computed but not returned** | Shared/unique connections computed, graph_context empty |
| Landscape | **No** | Pure metrics from materialized view |
| Pipeline | **No** | Pure metrics from materialized view |
| Portfolio | **Yes** | 1-hop company connections |
| General | **Yes** | 1-hop for top 5 search results |

**Assessment**: Graph is underutilized. Landscape and pipeline queries — the most strategically valuable — don't use the graph at all. They rely entirely on pre-computed materialized views. If the MV is stale, the graph data exists but isn't queried.

### Graph Limitations

- **100-node cap**: Traversal silently stops at 100 nodes. No warning to user or LLM.
- **No temporal edges**: Links don't have timestamps. Can't ask "what changed this month?"
- **No edge weights beyond confidence**: All EVIDENCE_FOR links weighted equally regardless of recency or impact factor.
- **21 link types, but only 5-6 used in queries**: OWNS, SPONSORS, INVESTIGATES, TARGETS_MECHANISM, IN_THERAPEUTIC_AREA, EVIDENCE_FOR dominate. Others (PATENT_BLOCKS, SHORTAGE_AFFECTS, HAS_LABEL) exist but aren't surfaced in intelligence queries.

---

## 5. Data Canvas Assessment

### What Goes to the Canvas

| Canvas Tab | Data Source | Quality |
|---|---|---|
| **Summary** | Top 5 rows of table + first visualization + 3 entities | Condensed view — good |
| **Data** | Full table + all visualizations (bar/pie charts) | Complete — good |
| **Entities** | Entity cards with type dots, connection counts, "View in Graph" | Structured — good |
| **Context** | Confidence assessment + persona analyses (team_eval only) | Often empty for non-team-eval queries |

### Table Data Generation

Table data is built by handlers, not by the LLM:

- **Landscape**: Competitive segments table (mechanism, TA, drug_count, trial_count, pipeline_score)
- **Compare**: Side-by-side metrics table (entity × metric)
- **Pipeline**: Drug pipeline table (drug_name, P1, P2, P3, P4, score)
- **Dossier**: No table — entity card instead
- **General**: No table unless structured_query returns SQL results

**Assessment**: Table data is always deterministic (from DB queries), never LLM-generated. This is a strength. However, tables are sparse — landscape tables often have only 3-5 rows when the underlying data has dozens of segments.

### Visualization Generation

Visualizations are auto-generated from table data (services/chat_handlers/formatting.py):

- **Bar chart**: If table has ≥3 numeric columns
- **Donut chart**: If table has a category + count structure
- **Graph network**: If graph_context has ≥3 nodes

**Assessment**: Visualizations are deterministic and data-accurate. But they're not analytically designed — they're auto-inferred from data shape, not from the question's intent.

---

## 6. Identified Weaknesses (Ranked by Impact)

### Critical

| # | Issue | Impact | File:Line |
|---|---|---|---|
| W1 | **No confidence scoring in legacy handlers** | Users can't tell if data is complete or uncertain | handlers.py (all handlers) |
| W2 | **No citation validation** | LLM can cite non-existent evidence numbers [99] | llm.py:24-27 |
| W3 | **Landscape/pipeline depend entirely on materialized views** | Silently return empty results if views are stale | handlers.py:818-930, 1001-1085 |

### High

| # | Issue | Impact | File:Line |
|---|---|---|---|
| W4 | **Compare handler omits graph data** | Graph tab empty despite shared connections computed | handlers.py:788 |
| W5 | **No temporal reasoning** | 2022 and 2026 evidence weighted equally | All handlers |
| W6 | **Entity resolution ambiguity** | Fuzzy match can silently return wrong entity | handlers.py:473-485 |
| W7 | **Graph truncated at 100 nodes silently** | Incomplete neighborhood for major entities | graph.py:82 |

### Medium

| # | Issue | Impact | File:Line |
|---|---|---|---|
| W8 | **General handler no entity validation** | Ambiguous queries produce mixed evidence | handlers.py:1088-1102 |
| W9 | **Metrics lag (daily refresh)** | Late-stage trial changes up to 24h stale | metrics.py |
| W10 | **UnifiedChatHandler opt-in only** | Confidence + guard checks available but not active | config.py |

---

## 7. Recommendations

### Priority 1 — Trust & Transparency

1. **Enable confidence scoring in all handlers** (not just UnifiedChatHandler)
   - Compute from: entity resolution success, evidence count, graph density, metric coverage
   - Return in every response → frontend shows confidence indicator
   - Estimated effort: 2-3 days

2. **Add citation validation post-LLM**
   - After synthesis, regex-scan for [N] markers
   - Verify N ≤ evidence count
   - Strip or flag invalid citations
   - Estimated effort: 1 day

3. **Materialized view fallback to real-time graph queries**
   - If `competitive_landscape()` returns empty, traverse graph for mechanism+TA pairs
   - If `drug_pipeline_strength()` returns empty, compute from raw trial data
   - Estimated effort: 3-4 days

### Priority 2 — Data Quality

4. **Temporal grounding**
   - Score evidence by recency: <30d = 1.0, 30-90d = 0.7, 90-365d = 0.4, >1y = 0.2
   - Sort evidence by recency before truncating to top N
   - Pass temporal metadata to LLM context
   - Estimated effort: 2 days

5. **Fix compare handler graph emission**
   - Convert `shared_connections` + `unique_connections` to proper `graph_context` nodes/edges
   - Frontend graph tab will show comparison network
   - Estimated effort: 1 day

6. **Entity resolution confidence score**
   - Return `match_score` (0-1) from resolution
   - If <0.8, include warning in LLM context: "Fuzzy match — verify entity"
   - Estimated effort: 1-2 days

### Priority 3 — Power & Depth

7. **Use graph for landscape/pipeline queries**
   - Not just materialized views — traverse from mechanism to drugs to trials
   - Compute real-time competitive position from graph structure
   - Estimated effort: 1 week

8. **Enable UnifiedChatHandler by default**
   - Set `MZ_UNIFIED_HANDLER=true` in production
   - Provides: confidence scoring, guard checks, CTX pipeline, entity detection
   - Estimated effort: 1 day (config change + testing)

9. **Graph truncation transparency**
   - If traverse hits 100-node cap, flag in response metadata
   - Deduct from confidence score
   - Show in frontend: "Showing top 100 of 347 connections"
   - Estimated effort: 1 day

---

## 8. Conclusion

Market Zero's intelligence pipeline is **architecturally sound**. The deterministic-first design (gather data → assemble context → synthesize) is the right pattern. System prompts enforce grounding. Fallback narratives ensure the system never produces an empty response.

The main gap is **quality transparency**. The system knows when it has strong evidence and when it doesn't — but it doesn't tell the user. Enabling confidence scoring, citation validation, and materialized view fallbacks would transform the pipeline from "generally trustworthy" to "formally auditable."

The graph is powerful but underused. Landscape and pipeline queries — the core strategic queries — bypass the graph entirely in favor of materialized views. Wiring the graph into these handlers would provide real-time, granular competitive intelligence instead of pre-computed snapshots.

**Bottom line**: The intelligence is grounded. The user just needs to be able to see how grounded it is.
