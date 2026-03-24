# SPEC-005: Architecture Simplification + Data Engineering Sprint

> **Date**: 24 March 2026
> **Duration**: 4 hours, parallel agent execution
> **Principle**: Every service must directly improve data quality, retrieval, or presentation

---

## Phase 1: Service Consolidation (27 → 12 services)

### 1A. Audit + delete speculative services
Verify which of the 11 new services are test-only or speculative. Delete those with 0 imports from production code.

**Check list:**
- `concept_registry.py` — keep if wired, delete if speculative
- `data_steward.py` — keep if wired, delete if speculative
- `entity_agents.py` — keep if wired, delete if speculative
- `feedback_loops.py` — keep if wired, delete if speculative
- `few_shot_library.py` — merge into llm.py if useful, delete if unused
- `insight_engine.py` — keep if wired, delete if speculative
- `scenario_engine.py` — keep if wired, delete if speculative
- `steward_signals.py` — keep if wired, delete if speculative
- `query_telemetry.py` — merge into telemetry.py
- `literature.py` — keep (supports LiteratureExplorer)

**Rule**: If a service has 0 imports from api/routes/ or api/deps.py, it's not production code.

### 1B. Merge CTX into query pipeline
Keep `ctx_pipeline.py` and `ctx_context.py` but wire CTX context formatting directly into `query_engine.py` as the default context assembly method. Remove the A/B toggle complexity — just use CTX format always (with the threshold gate for small payloads that already exists).

### 1C. Merge telemetry
Combine `telemetry.py` + `query_telemetry.py` into one file.

### 1D. Target service list (12)
```
services/
  search.py              # Vector retrieval
  graph.py               # Graph traversal
  graph_analytics.py     # Influence scoring, clusters (keep — used by graph tab)
  metrics.py             # Materialized view KPIs
  query_engine.py        # Orchestration + CTX context assembly
  llm.py                 # LLM synthesis
  conversation_memory.py # Session memory
  workspace.py           # Session CRUD
  telemetry.py           # All telemetry (CTX + query)
  research_agent.py      # Autonomous enrichment
  literature.py          # Literature explorer support
  ctx_pipeline.py        # CTX hydration pipeline (kept per user request)
  ctx_corpus.py          # CTX corpus builder (kept — feeds pipeline)
```

---

## Phase 2: Data Engineering Hardening

### 2A. FAIR scorer — automated nightly quality assessment
Build a proper FAIR scorer that computes and persists quality metrics:
- Entity completeness per type (% of required fields populated)
- Link density (avg connections per entity)
- Source diversity (% entities with 2+ sources)
- Freshness (% records updated in last 30 days)
- Resolution rate (% of unresolved_entities cleared)

Store results in a `data_quality_snapshots` table. Track trend over time.

### 2B. Data connector robustness
- Verify retry logic is working on all 10 connectors
- Add health check dashboard data (last run, success rate, record count)
- Wire connector health into the Data Catalog admin view

### 2C. Entity resolution quality
- Run resolution sweep on remaining unresolved entities
- Compute resolution confidence distribution
- Flag entities with confidence < 0.5 for HITL review

### 2D. Materialized view refresh automation
- Wire MV refresh to trigger after pipeline runs
- Add staleness detection to the health endpoint
- Log refresh timestamps

---

## Phase 3: CTX Pipeline Integration

### 3A. Wire CTX context formatting as default in LLMSynthesizer
Remove the A/B mode toggle. CTX is always the format (with threshold gate).
Simplify `_build_context_block()` — it doesn't need to build both formats.

### 3B. Wire CTX hydration into dossier queries
For entity dossier queries, use CTX hydration to pull structured sections
instead of the current flat DB dump. This is where CTX adds the most value.

### 3C. Add CTX telemetry to quality dashboard
Surface CTX compression ratio and token savings in the Data Catalog admin.

---

## Phase 4: Test Coverage + Eval

### 4A. Test coverage for data engineering
- Entity resolver cascade: test each of 6 strategies individually
- Cross-linker: test each link type derivation
- MentionNormalizer: test edge cases (apostrophes, suffixes, abbreviations)
- FAIR scorer: test scoring calculation

### 4B. Eval baseline
- Run the existing benchmark suite
- Record baseline scores
- Identify worst-performing query categories

---

## Execution Plan (4 hours)

| Agent | Tasks | Files |
|---|---|---|
| Agent 1 | Phase 1A (audit + delete) + 1C (merge telemetry) | services/*.py, api/deps.py |
| Agent 2 | Phase 2A (FAIR scorer) + 2D (MV refresh) | New: services/fair_scorer.py, schema/migrations/ |
| Agent 3 | Phase 3A (CTX default) + 3B (hydration wiring) | services/llm.py, services/query_engine.py |
| Agent 4 | Phase 4A (tests) | tests/ |
| Main | Phase 1B (CTX merge), 2B-2C (connector/resolution), commit/push | Various |
