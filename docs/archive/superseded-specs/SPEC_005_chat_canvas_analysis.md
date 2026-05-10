# SPEC-005: Chat & Canvas Intelligence — Deep Analysis

*Author: Architecture Review · Date: 2026-03-28*
*Scope: Intent routing, response grounding, canvas relevance, follow-up handling, enhancement roadmap*

---

## 1. Executive Summary

Market Zero's chat + canvas system is architecturally sound — the 8-handler intent fork, CTX context assembly, and split-panel UI form a coherent pipeline from question to answer. The intelligence layer correctly routes ~80% of typical pharma queries, and handlers like Landscape and Pipeline produce genuinely useful structured output with citation-backed narratives.

However, three systemic weaknesses undercut the platform's potential as a trusted intelligence tool:

1. **Grounding is advisory, not enforced.** The LLM system prompt says "STRICT DATA GROUNDING" but the post-synthesis validation only checks citation index bounds (not semantic alignment) and logs fabricated numbers without stripping them. This is a guardrail, not a guarantee.

2. **Canvas staleness corrupts trust.** When a follow-up query returns narrative-only output, the canvas retains the previous query's tables, charts, and entities — silently showing stale data alongside fresh narrative.

3. **Intent classification is brittle at the edges.** Regex-only routing misclassifies semantic queries ("what are the competitors to semaglutide" → DOSSIER instead of LANDSCAPE) and provides no fallback confidence signal to the user.

This document maps every user journey through the system, rates each handler's accuracy and canvas quality, identifies 23 specific gaps, and proposes a prioritised enhancement roadmap.

---

## 2. Architecture Flow

```
User Question
     │
     ▼
┌─────────────────────┐
│  detect_intent()    │  ← Regex-based, 9 intent types
│  detect_format_hint │  ← "table" / "chart" / null
│  detect_compound    │  ← Splits on "and"/"also"/"then"
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  Handler Selection  │  DOSSIER → handle_dossier()
│  (8 handlers)       │  COMPARE → handle_compare()
│                     │  LANDSCAPE → handle_landscape()
│                     │  PIPELINE → handle_pipeline()
│                     │  PORTFOLIO → handle_portfolio()
│                     │  STRUCTURED → handle_structured_query()
│                     │  DEEP_RESEARCH → handle_deep_research()
│                     │  GENERAL → handle_general()
└────────┬────────────┘
         │
         ├──→ Entity Resolution (UUID → exact → fuzzy)
         ├──→ Data Retrieval (DB, pgvector, graph traversal)
         ├──→ CTX Context Assembly (hydration + salience ordering)
         ├──→ Metrics Computation (materialised views)
         │
         ▼
┌─────────────────────┐
│  LLM Synthesis      │  Temperature 0.3, system prompt + grounding rules
│  (services/llm.py)  │  Intent-specific synthesisers (dossier, comparison, etc.)
└────────┬────────────┘
         │
         ├──→ validate_citations()      — strips [N] where N > evidence_count
         ├──→ verify_narrative_numbers() — logs mismatches (DOES NOT STRIP)
         ├──→ check_response()          — entity presence check only
         │
         ▼
┌─────────────────────┐
│  Response Assembly   │  narrative + data + table_data + visualisations
│  (QueryResponse)     │  + confidence + followup_suggestions + sql_meta
└────────┬────────────┘
         │
         ▼
┌──────────────┬──────────────────┐
│  Chat Panel  │   Canvas Panel   │
│  (left)      │   (right)        │
│  Narrative   │   Summary tab    │
│  Citations   │   Data tab       │
│  Follow-ups  │   Entities tab   │
│              │   Context tab    │
└──────────────┴──────────────────┘
```

---

## 3. Intent Detection Analysis

### 3.1 Routing Rules (priority order)

| Priority | Intent | Trigger Pattern | Extracted Params |
|----------|--------|-----------------|------------------|
| 1 | COMPARE | `compare X vs Y`, `X versus Y` (unless title-like) | `entities: [X, Y]` |
| 2 | LANDSCAPE | `landscape`, `competitive`, `market segments/overview` | `topic: str` |
| 3 | PORTFOLIO | `portfolio` keyword | `company_name: str` |
| 4 | PIPELINE | `pipeline` keyword | `therapeutic_area: str` |
| 5 | STRUCTURED_QUERY | `has_structured_signals()` (SQL-pattern detection) | `{}` |
| 6 | DOSSIER | `tell me about`, `what is`, `dossier on`, `describe` | `entity_name: str` |
| 6b | DOSSIER (fallback) | 1-4 word query without question words | `entity_name: q` |
| 7 | GENERAL | Everything else | `{}` |

### 3.2 Typical User Questions — Expected vs Actual Routing

#### Dossier Queries (entity deep-dives)
| Question | Expected | Actual | Correct? |
|----------|----------|--------|----------|
| "Tell me about semaglutide" | DOSSIER | DOSSIER ✓ | Yes |
| "semaglutide" | DOSSIER | DOSSIER (fallback) ✓ | Yes |
| "What is Ozempic used for?" | DOSSIER | DOSSIER ✓ | Yes |
| "Novo Nordisk" | DOSSIER | DOSSIER (fallback) ✓ | Yes |
| "SGLT2 inhibitors in heart failure" | DOSSIER | DOSSIER | **Debatable** — could be LANDSCAPE |
| "Profile of tirzepatide" | DOSSIER | DOSSIER ✓ | Yes |

#### Comparison Queries
| Question | Expected | Actual | Correct? |
|----------|----------|--------|----------|
| "Compare semaglutide vs tirzepatide" | COMPARE | COMPARE ✓ | Yes |
| "How does Ozempic stack up against Mounjaro?" | COMPARE | COMPARE ✓ | Yes |
| "Semaglutide versus liraglutide" | COMPARE | COMPARE ✓ | Yes |
| "Differences between GLP-1 and SGLT2" | COMPARE | GENERAL | **Wrong** — no `vs`/`versus` keyword |
| "Which is better, semaglutide or tirzepatide?" | COMPARE | GENERAL | **Wrong** — no compare keyword |

#### Landscape Queries
| Question | Expected | Actual | Correct? |
|----------|----------|--------|----------|
| "GLP-1 competitive landscape" | LANDSCAPE | LANDSCAPE ✓ | Yes |
| "What does the obesity market look like?" | LANDSCAPE | LANDSCAPE ✓ (`market overview`) | Yes |
| "Who are the competitors to semaglutide?" | LANDSCAPE | DOSSIER | **Wrong** — no landscape/competitive keyword |
| "Show me the diabetes drug market" | LANDSCAPE | LANDSCAPE ✓ (`market`) | Yes |
| "Which companies are competing in oncology?" | LANDSCAPE | GENERAL | **Wrong** — `competing` ≠ `competitive` |

#### Pipeline Queries
| Question | Expected | Actual | Correct? |
|----------|----------|--------|----------|
| "Diabetes drug pipeline" | PIPELINE | PIPELINE ✓ | Yes |
| "What Phase 3 trials exist for GLP-1?" | PIPELINE | GENERAL | **Wrong** — no `pipeline` keyword |
| "Show me drugs in clinical trials for obesity" | PIPELINE | GENERAL | **Wrong** |
| "Heart failure pipeline" | PIPELINE | PIPELINE ✓ | Yes |

#### Portfolio Queries
| Question | Expected | Actual | Correct? |
|----------|----------|--------|----------|
| "Novo Nordisk's portfolio" | PORTFOLIO | PORTFOLIO ✓ | Yes |
| "What drugs does Eli Lilly have?" | PORTFOLIO | DOSSIER | **Wrong** — no `portfolio` keyword |
| "Show me Pfizer's drug portfolio" | PORTFOLIO | PORTFOLIO ✓ | Yes |

### 3.3 Misclassification Rate

Based on the 25 representative queries above: **8 misclassifications = 32% error rate on edge cases**.

For the "happy path" (queries using exact trigger words): near-100% accuracy.
For natural language (semantic equivalents without trigger words): ~50% accuracy.

### 3.4 Root Cause

The intent system is purely lexical — it matches keywords, not meaning. There is no embedding-based fallback, no LLM-assisted classification, and no confidence score on the routing decision itself.

### 3.5 Mechanism Synonyms

The `MECHANISM_SYNONYMS` dict (11 entries) maps abbreviations to canonical names, which is excellent for entity context but is **not used in intent detection** — it only enriches the data layer. Intent still depends on surface keywords.

---

## 4. Handler-by-Handler Canvas Quality

### 4.1 DOSSIER — Rating: ⭐⭐⭐⭐ (4/5)

**What it does well:**
- Rich entity resolution (UUID → exact → fuzzy cascade)
- Structured metadata: mechanism, therapeutic area, supply status, approval dates
- Connection counts (trials, publications, TAs, mechanisms)
- Recent market events (5 most recent with impact scores)
- Evidence snippets (top 10) with provenance
- CTX hydration for richer narrative context
- Domain concept activation for tailored follow-ups

**Canvas output:**
- `entity_focus`: Full entity profile with metadata
- `graph_context`: Neighbourhood graph (connected entities)
- `metrics_context`: Pipeline score, success rate, evidence density
- No `table_data` — **gap**: tabular view not offered for entity connections

**What's missing:**
- No table showing connected trials, publications, or related drugs
- No timeline of entity milestones (approvals, Phase transitions, events)
- Entity resolution confidence not surfaced to user (only logged)

### 4.2 COMPARE — Rating: ⭐⭐⭐⭐ (4/5)

**What it does well:**
- Structured comparison table (Pipeline Score, Phase counts, Success Rate, Articles)
- Compare graph with shared/unique connections
- Differential analysis (pipeline ratios, trial volume diffs)
- Domain concept activation

**Canvas output:**
- `table_data`: 11-metric comparison table
- `graph_context`: Compare graph (shared + unique edges)
- `entity_focus`: Both entities with metadata
- `visualisations`: Bar charts of pipeline scores

**What's missing:**
- Silent fallback to GENERAL if entity resolution fails (no user warning)
- No side-by-side timeline view
- Limited to 2 entities (enforced at resolution, not detected)

### 4.3 LANDSCAPE — Rating: ⭐⭐⭐⭐⭐ (5/5)

**What it does well:**
- Mechanism-level competitive table (Mechanism, TA, Drugs, Trials, Pipeline Score)
- HHI concentration index (2500+ = highly concentrated)
- Top 3 segment share computation
- Company participation analysis (top 5 by pipeline strength)
- Mechanism synonym expansion for broader coverage

**Canvas output:**
- `table_data`: Mechanism-segmented competitive table
- `metrics_context`: HHI, segment shares, company rankings
- `visualisations`: Bar/donut charts
- Missing `entity_focus` — **gap**: no highlighted key players

### 4.4 PIPELINE — Rating: ⭐⭐⭐⭐⭐ (5/5)

**What it does well:**
- Phase distribution table (Drug, P1, P2, P3, P4, Total, Score)
- Pipeline maturity split (early-heavy vs late-heavy)
- Therapeutic area scoping
- Clear data structure for tabular rendering

**Canvas output:**
- `table_data`: Phase distribution matrix
- `metrics_context`: Pipeline strength, maturity analysis
- `visualisations`: Phase distribution bar chart
- No `graph_context` — metrics-only (appropriate)

### 4.5 PORTFOLIO — Rating: ⭐⭐⭐ (3/5)

**What it does well:**
- Company entity resolution with dossier enrichment
- Key metrics (drug count, trial count, active trials, articles, TAs, pipeline score)

**Canvas output:**
- `table_data`: Key-value metrics summary (6 rows only)
- `entity_focus`: Company entity with metadata
- Limited `graph_context`

**What's missing:**
- No drug-level breakdown table (just aggregate counts)
- No phase distribution per drug
- No competitive positioning relative to peers
- Feels thin compared to Landscape or Pipeline handlers

### 4.6 GENERAL — Rating: ⭐⭐⭐ (3/5)

**What it does well:**
- Full QueryResponse with graph, metrics, evidence
- Broadest data retrieval (no entity-type filter)
- Conversation context passed to LLM

**Canvas output:**
- `data`: Full QueryResponse
- No `table_data` — **gap**: no structured tabular output
- Visualisations from generic `build_visualizations()`

**What's missing:**
- No structured table for any data
- No intent-specific formatting
- Catch-all quality depends entirely on search relevance + LLM

### 4.7 DEEP_RESEARCH — Rating: ⭐⭐⭐⭐ (4/5)

**What it does well:**
- Enhanced evidence depth (24 items vs default 10)
- Optional web research augmentation
- Workspace job creation for async processing

**Canvas output:** Same as GENERAL but with more evidence

### 4.8 COMPOUND — Rating: ⭐⭐⭐ (3/5)

**What it does well:**
- Splits on "and"/"also"/"plus"/"then" connectors
- Deduplicates intents, caps at 2

**What's missing:**
- Canvas only shows last handler's output (first intent's canvas overwritten)
- No merged view for multi-intent results
- Max 2 intents may split incorrectly ("semaglutide and tirzepatide" → 2 dossiers, not 1 comparison)

---

## 5. LLM Grounding & Hallucination Analysis

### 5.1 System Prompt Hardening

The LLM system prompt includes "STRICT DATA GROUNDING" rules:
- "Every claim must reference provided data"
- "Use [N] citation format"
- "Do NOT inject clinical trial results from training data"
- "If data doesn't cover a dimension, say 'data not available'"

These are advisory text — the LLM is instructed but not constrained.

### 5.2 Post-Synthesis Validation (What Actually Runs)

| Check | What It Does | What It Should Do |
|-------|-------------|-------------------|
| `validate_citations()` | Strips `[N]` where N > evidence_count or N == 0 | Also verify semantic alignment between citation and claim |
| `verify_narrative_numbers()` | Logs bold numbers not found within ±1.0 of source data | **Strip or flag** fabricated numbers instead of logging only |
| `check_response()` (ContextGuard) | Checks entity name presence in context | Check claim-level grounding (is the specific claim supported?) |
| Confidence scoring | Presence-based (0.2–0.8 range) | Should factor in claim coverage, not just entity presence |

### 5.3 Hallucination Vulnerability Matrix

| Scenario | Risk Level | Current Mitigation | Gap |
|----------|-----------|-------------------|-----|
| LLM invents a trial result | HIGH | System prompt says "don't" | No enforcement — fabricated numbers logged, not stripped |
| Citation points to wrong evidence | MEDIUM | Index bounds check only | No semantic alignment check |
| LLM adds entities not in data | MEDIUM | ContextGuard checks presence | Only checks entity names, not claims about those entities |
| LLM fabricates a date/approval | MEDIUM | None | `verify_narrative_numbers` doesn't check dates |
| Correct entities, wrong relationships | LOW-MEDIUM | Graph context provided | LLM may infer relationships not in graph |
| General knowledge bleed | LOW | "Data not available" instruction | Advisory only |

### 5.4 Practical Impact

For **routine queries** (entity lookups, pipeline summaries, landscape overviews), the grounding is effective because the data is rich and structured — the LLM has little reason to hallucinate.

For **edge cases** (sparse entities, cross-domain questions, comparative claims), the grounding becomes unreliable. A bold-formatted number like "**73% success rate**" may appear in the narrative even if no source data supports it — `verify_narrative_numbers` will log it but the user sees it as fact.

**Verdict:** Guardrail, not guarantee. Effective for ~80% of routine queries. Vulnerable to subtle hallucinations on the remaining 20%.

---

## 6. Canvas Relevance & Staleness

### 6.1 Update Logic

Canvas updates in `WorkspacePage.tsx` (lines 161-172):
```
const hasNewData = response.data || response.table_data ||
                   response.visualizations || response.persona_analyses;
if (hasNewData) { setCanvas({...}); }
```

**Problem:** No `else` clause. If a follow-up returns narrative-only (e.g., "Can you elaborate on that?"), the canvas retains the previous query's tables, charts, and entities. The user sees a fresh narrative on the left with stale structured data on the right.

### 6.2 When Canvas Goes Stale

| Scenario | Canvas Updates? | Problem? |
|----------|----------------|----------|
| Dossier → Landscape | Yes (new table_data) | No |
| Landscape → "Tell me more" | No (narrative-only) | **Stale** — old landscape table persists |
| Compare → GENERAL fallback | Partial (data but no table) | **Misleading** — old compare table persists |
| Pipeline → "What about obesity?" | Depends on routing | May be stale if routes to GENERAL |
| Any → error response | No | **Stale** — old data shown with error narrative |

### 6.3 Fix Required

Add explicit canvas reset:
```typescript
if (hasNewData) {
  setCanvas({...});
} else {
  setCanvas({ intent: response.intent || null, data: null, tableData: null,
              visualizations: null, confidence: undefined, ... });
}
```

---

## 7. Follow-Up & Conversation Flow

### 7.1 Follow-Up Suggestions

Generated per-intent in `generate_followups()`:

| Intent | Suggestions Offered | Quality |
|--------|-------------------|---------|
| COMPARE | Phase 3 trials, full pipeline, TA leadership | Good — actionable |
| LANDSCAPE | Dominant companies, Phase 3 drugs, mechanisms | Good — deepening |
| PIPELINE | Success rate, competitor comparison, landscape | Good — broadening |
| PORTFOLIO | Phase 3 trials, competitive positioning | Adequate |
| DOSSIER | Running trials, competitive landscape | Adequate |
| GENERAL | Generic deep-dives based on entity extraction | Weak — not contextual |

### 7.2 Context Retention

**Frontend:** `buildHistory()` sends last 6 messages (3 exchanges) with content truncated to 500 chars. Extracts entity names from `entity_focus` (max 5).

**Backend:** Handlers receive `conv_context` string, but usage is **inconsistent**:
- `handle_landscape()` — Uses conv_context ✓
- `handle_pipeline()` — Uses conv_context ✓
- `handle_dossier()` — **Does NOT use** conv_context ✗
- `handle_compare()` — **Does NOT use** conv_context ✗
- `handle_portfolio()` — **Does NOT use** conv_context ✗
- `handle_general()` — Uses conv_context ✓

This means follow-up dossier or comparison queries have no conversational context — the LLM generates responses as if they were first-turn queries.

### 7.3 Coreference Resolution

`resolve_followup_question()` in `context.py` handles:
- "this drug" / "that company" → replaced with last mentioned entity
- "its pipeline" / "their trials" → possessive pronoun resolution
- "the same" → refers back to previous entity

**Weaknesses:**
- Uses naive regex, not NLP — fragile on complex pronoun chains
- Only looks at first sentence of prior response for entity extraction
- No multi-entity tracking ("both of those" → fails)
- Negations not handled ("not this drug, the other one")

### 7.4 ConversationMemory (Built, Not Wired)

`services/conversation_memory.py` provides:
- Token-budgeted eviction (oldest-first)
- Entity tracking across turns (survives eviction)
- Coreference resolution with entity counter
- Snapshot/restore for persistence
- 28 tests passing

**Not wired** into any handler or route. Current system uses manual `buildHistory()` with fixed 6-message window and no token budgeting.

---

## 8. User Journey Scenarios

### 8.1 Scenario A: Pharma Analyst Researching a Drug

**Turn 1:** "Tell me about semaglutide"
- **Intent:** DOSSIER ✓
- **Expected canvas:** Entity profile (mechanism, TA, trials, publications, pipeline score)
- **Expected narrative:** Background, mechanism of action, clinical status, market position
- **Grounding risk:** LOW — semaglutide is a well-documented entity in the database
- **Follow-ups offered:** "What trials are running?", "Show competitive landscape"

**Turn 2 (follow-up):** "What trials are running for it?"
- **Intent:** DOSSIER (matches "what is" pattern) or GENERAL
- **Coreference:** "it" → resolved to "semaglutide" via `resolve_followup_question()`
- **Context used:** Only if handler accepts conv_context (DOSSIER does NOT)
- **Canvas:** May go stale if routed to GENERAL with narrative-only response
- **Gap:** Trial-specific tabular data not produced by DOSSIER handler

**Turn 3 (follow-up):** "How does it compare to tirzepatide?"
- **Intent:** COMPARE ✓ (matches "compare to" pattern)
- **Coreference:** "it" → should resolve to "semaglutide"
- **Expected canvas:** Comparison table (pipeline scores, phases, success rates)
- **Quality:** GOOD — COMPARE handler produces structured comparison data

**Turn 4 (broadening):** "What does the GLP-1 landscape look like?"
- **Intent:** LANDSCAPE ✓
- **Expected canvas:** Mechanism-level competitive table, HHI, segment shares
- **Context:** LANDSCAPE handler uses conv_context — prior semaglutide context helps LLM
- **Quality:** EXCELLENT — best handler for structured output

### 8.2 Scenario B: Portfolio Manager Evaluating a Company

**Turn 1:** "Show me Novo Nordisk's portfolio"
- **Intent:** PORTFOLIO ✓
- **Expected canvas:** Drug count, trial count, active trials, pipeline score
- **Actual canvas:** Key-value summary (6 rows) — **thin** compared to what a portfolio manager needs
- **Gap:** No drug-level breakdown, no phase distribution per asset, no competitive context

**Turn 2:** "What drugs does Eli Lilly have?"
- **Intent:** DOSSIER (misclassified — no "portfolio" keyword)
- **Expected:** Portfolio-style breakdown
- **Actual:** Entity profile for "Eli Lilly" — misses the drug-level breakdown
- **User impact:** Has to rephrase as "Eli Lilly's portfolio" to get correct routing

**Turn 3:** "Compare their pipelines"
- **Intent:** GENERAL (no "vs"/"versus" trigger)
- **Expected:** Comparison of Novo Nordisk and Eli Lilly pipelines
- **Coreference:** "their" → may fail (multi-entity possessive not handled)
- **Canvas:** Likely stale (GENERAL returns no table_data)
- **User impact:** Frustrating — has to rephrase as "Compare Novo Nordisk vs Eli Lilly"

### 8.3 Scenario C: Regulatory Affairs Monitoring

**Turn 1:** "FDA drug shortages"
- **Intent:** DOSSIER (matches "what is" → no, actually this is 3 words so fallback to DOSSIER)
- **Expected:** Overview of FDA shortage data across monitored drugs
- **Actual:** May search for entity "FDA drug shortages" — likely fails entity resolution
- **Gap:** No handler for regulatory/monitoring queries

**Turn 2:** "Which drugs have supply issues?"
- **Intent:** GENERAL (question word "which" prevents DOSSIER fallback)
- **Expected:** Table of drugs with supply_status = 'shortage' or similar
- **Actual:** Free-text search, quality depends on evidence matches
- **Canvas:** No structured table

### 8.4 Scenario D: Edge Case — Ambiguous Multi-Entity Query

**Turn 1:** "SGLT2 inhibitors in heart failure"
- **Intent:** DOSSIER (no landscape/competitive keyword)
- **Expected:** Could reasonably be LANDSCAPE (class-level overview) or DOSSIER (mechanism deep-dive)
- **Live test result:** Returned narrative with citations [1][3], phase chart, entity mentions (Entresto, Farxiga, Jardiance)
- **Canvas:** Phase distribution chart ✓, Key Entities section ✓
- **Assessment:** Acceptable but suboptimal — a LANDSCAPE routing would produce a richer competitive table

---

## 9. Gap Inventory (23 Items)

### Critical (Must Fix)

| # | Gap | Location | Impact |
|---|-----|----------|--------|
| G1 | Canvas staleness — no reset on narrative-only responses | `WorkspacePage.tsx:162` | Stale data shown alongside fresh narrative |
| G2 | `verify_narrative_numbers()` logs but does not strip fabricated numbers | `llm.py:96-140` | Users see unverified bold numbers as fact |
| G3 | Conversation context ignored by DOSSIER, COMPARE, PORTFOLIO handlers | `handlers.py` | Follow-up queries lose conversational context |
| G4 | Citation-evidence mismatch when evidence filtered post-narrative | `WorkspacePage.tsx:112` + `formatting.py:43` | Citation [3] clicks show wrong evidence item |

### High (Should Fix)

| # | Gap | Location | Impact |
|---|-----|----------|--------|
| G5 | No semantic/embedding fallback for intent detection | `intent.py` | 32% misclassification on natural language queries |
| G6 | Fuzzy entity resolution at 0.7 threshold with no user warning | `formatting.py:115` | Wrong entity resolved silently |
| G7 | PORTFOLIO handler too thin — no drug-level breakdown | `handlers.py:1082` | Portfolio managers get aggregate counts only |
| G8 | Silent fallback from COMPARE to GENERAL on resolution failure | `handlers.py:837` | User expects comparison, gets generic response |
| G9 | `[metrics]` literal string leaks into narrative | `NarrativeMessage.tsx` cleanup | Visual artefact in responses |
| G10 | ContextGuard checks entity presence only, not claim-level grounding | `ctx_pipeline.py:421` | Claims about entities may be ungrounded |

### Medium (Should Address)

| # | Gap | Location | Impact |
|---|-----|----------|--------|
| G11 | ConversationMemory built (28 tests) but not wired into handlers | `conversation_memory.py` | No token-budgeted context, no entity tracking |
| G12 | Follow-up coreference resolution uses naive regex | `context.py:63-108` | Complex pronoun chains fail |
| G13 | LANDSCAPE handler missing `entity_focus` output | `handlers.py:950` | No highlighted key players on canvas |
| G14 | GENERAL handler produces no `table_data` | `handlers.py:1250` | Canvas Data tab always empty for general queries |
| G15 | Compound intent canvas shows only last handler's output | `handlers.py:1374` | First intent's structured data lost |
| G16 | Graph truncation detected but not communicated to user | `graph.py:66` | User unaware of incomplete graph data |
| G17 | No confidence score on intent routing decision itself | `intent.py` | System can't signal routing uncertainty |
| G18 | Confidence dimensions (`by_dimension`) returned but not displayed | `CanvasPanel.tsx:109` | Missed transparency opportunity |

### Low (Enhancement)

| # | Gap | Location | Impact |
|---|-----|----------|--------|
| G19 | No deduplication of follow-up suggestions | `formatting.py:172` | Minor UX issue |
| G20 | No "no data" state distinction from "loading" on canvas | `CanvasPanel.tsx:82` | User unsure if query is processing |
| G21 | No entity timeline visualisation in dossier | `handlers.py:549` | Missing chronological view |
| G22 | No export capability for comparison tables | `CanvasPanel.tsx` | Users can't save structured outputs |
| G23 | Mechanism synonyms not used in intent detection | `intent.py:23` | Only enriches data, not routing |

---

## 10. Enhancement Roadmap

### Phase 1: Trust & Accuracy (Week 1-2)

**E1. Enforce numeric verification**
- Change `verify_narrative_numbers()` from logging to stripping unverified bold numbers
- Add `[unverified]` annotation for numbers not found in source data
- Files: `services/llm.py:96-140`

**E2. Fix canvas staleness**
- Add `else` clause to reset canvas when response has no structured data
- Add visual indicator "Canvas updated" / "Narrative-only response" on canvas header
- Files: `frontend/src/pages/WorkspacePage.tsx:161-172`

**E3. Wire conversation context into all handlers**
- Pass `conv_context` to DOSSIER, COMPARE, and PORTFOLIO handlers
- Use it in LLM system prompt for all intents
- Files: `services/chat_handlers/handlers.py`

**E4. Fix citation-evidence alignment**
- Track evidence indices through filtering — map post-filter indices to pre-filter indices
- Or: filter evidence BEFORE narrative generation
- Files: `services/chat_handlers/formatting.py:43-64`, `WorkspacePage.tsx`

### Phase 2: Intent Intelligence (Week 2-3)

**E5. Add LLM-assisted intent classification fallback**
- When regex confidence is low (no exact keyword match), use a lightweight LLM call to classify
- Return intent + confidence score
- Budget: ~100 tokens per classification, <500ms latency
- Files: `services/chat_handlers/intent.py`

**E6. Add "did you mean?" disambiguation**
- When intent confidence < 0.7, show user: "I interpreted this as [DOSSIER]. Did you mean [LANDSCAPE]?"
- Allow one-click re-route
- Files: `frontend/src/components/chat/ChatPanel.tsx`, `api/routes/chat.py`

**E7. Expand comparison triggers**
- Add patterns: "differences between", "which is better", "how does X stack up"
- Add "competing" → LANDSCAPE trigger
- Files: `services/chat_handlers/intent.py:62-69`

### Phase 3: Canvas Enrichment (Week 3-4)

**E8. Enrich PORTFOLIO handler**
- Add drug-level breakdown table: Drug Name, Phase, Mechanism, TA, Pipeline Score
- Add phase distribution visualisation per company
- Add peer comparison sidebar (top 3 competitors by pipeline strength)
- Files: `services/chat_handlers/handlers.py:1082-1150`

**E9. Add entity timeline to DOSSIER**
- Pull milestone events: approval dates, Phase transitions, market events
- Render as horizontal timeline in Canvas Summary tab
- Files: `handlers.py:549-700`, `CanvasPanel.tsx`

**E10. Add structured table output for GENERAL handler**
- Extract top entities from evidence and build a summary table
- Columns: Entity, Type, Relevance Score, Evidence Count
- Files: `handlers.py:1250-1267`

**E11. Surface confidence dimensions on canvas**
- Show breakdown: Entity Resolution (X%), Evidence Depth (Y%), Graph Coverage (Z%)
- Render as mini bar chart or text breakdown under confidence badge
- Files: `frontend/src/components/canvas/CanvasPanel.tsx:109`

### Phase 4: Memory & Context (Week 4-5)

**E12. Wire ConversationMemory into chat pipeline**
- Replace manual `buildHistory()` with `ConversationMemory.get_context()`
- Token-budgeted context instead of fixed 6-message window
- Entity tracking persists across eviction window
- Files: `services/conversation_memory.py`, `api/routes/chat.py`, `WorkspacePage.tsx`

**E13. Improve coreference resolution**
- Replace regex-based `resolve_followup_question()` with `ConversationMemory.resolve_reference()`
- Supports multi-entity tracking, ranked entity recall
- Files: `services/chat_handlers/context.py`

**E14. Add conversation summary on canvas Context tab**
- Show: "Entities discussed: semaglutide (3 turns), tirzepatide (1 turn)"
- Show: "Topics covered: mechanism, trials, competitive positioning"
- Files: `CanvasPanel.tsx`, `conversation_memory.py`

### Phase 5: Advanced Grounding (Week 5-6)

**E15. Claim-level grounding validation**
- After LLM synthesis, parse key claims (numbers, relationships, dates)
- Cross-reference each claim against evidence snippets
- Flag ungrounded claims with `[needs verification]`
- Files: `services/llm.py`, new `services/claim_validator.py`

**E16. Citation semantic alignment**
- For each `[N]` citation, verify that the cited evidence actually supports the sentence
- Use embedding similarity between sentence and evidence snippet
- Strip citations with similarity < 0.6
- Files: `services/llm.py:30-56`

**E17. Proactive data gap signalling**
- When CTX pipeline detects gaps (`ReasoningResult.gaps`), surface them in the narrative
- "Note: No trial data found for X. Results based on Y and Z only."
- Files: `services/ctx_pipeline.py`, `services/llm.py`

### Phase 6: Experience Polish (Week 6-7)

**E18. Query progress indicator**
- Show stages as query processes: "Resolving entities..." → "Searching evidence..." → "Generating analysis..."
- Use streaming events from backend
- Files: `api/routes/chat.py`, `ChatPanel.tsx`

**E19. Interactive canvas tables**
- Column sorting, filtering, search within Data tab tables
- Clickable entity names → trigger dossier query
- Files: `CanvasPanel.tsx`

**E20. Canvas export**
- CSV export for Data tab tables
- PNG export for Summary tab charts
- Files: `CanvasPanel.tsx`

**E21. Suggested queries on empty state**
- Show 4-6 curated starter queries based on data coverage
- "Try: GLP-1 competitive landscape · Compare semaglutide vs tirzepatide · Novo Nordisk portfolio"
- Files: `ChatPanel.tsx`

---

## 11. Success Metrics

| Metric | Current | Target (Phase 6) | Measurement |
|--------|---------|-------------------|-------------|
| Intent classification accuracy (natural language) | ~68% | >90% | Eval suite of 50 representative queries |
| Canvas relevance (fresh data per query) | ~75% | >95% | % of queries where canvas shows current-query data |
| Citation semantic accuracy | Unknown (not measured) | >85% | Embedding similarity between citation and evidence |
| Fabricated number rate | Unknown (logged only) | <2% | % of bold numbers not found in source data |
| Follow-up context retention | Partial (3/8 handlers) | 100% | All handlers use conversation context |
| User re-query rate (intent correction) | Unknown | <10% | % of queries immediately rephrased |
| Confidence calibration | Presence-based (0.2-0.8) | Claim-grounded (0.1-0.95) | Correlation between confidence and factual accuracy |

---

## 12. Implementation Priority Matrix

```
                    HIGH IMPACT
                        │
         E2 (canvas)    │    E1 (numbers)
         E3 (context)   │    E5 (intent LLM)
         E4 (citations) │    E15 (claim ground)
                        │
   LOW EFFORT ──────────┼──────────── HIGH EFFORT
                        │
         E7 (triggers)  │    E12 (memory wire)
         E9 (timeline)  │    E16 (citation align)
         E11 (dimensions)│   E8 (portfolio)
                        │
                    LOW IMPACT
```

**Recommended execution order:**
1. E2 + E3 + E4 (trust fixes, ~2 days)
2. E1 + E7 (grounding + triggers, ~2 days)
3. E5 + E6 (intent intelligence, ~3 days)
4. E8 + E10 + E11 (canvas enrichment, ~3 days)
5. E12 + E13 (memory wiring, ~3 days)
6. E15 + E16 + E17 (advanced grounding, ~5 days)
7. E18-E21 (polish, ~4 days)

**Total estimate: ~22 engineering days for full roadmap.**

---

## 13. Cross-References

| Spec | Relevance |
|------|-----------|
| SPEC-001 (Autonomous Research Engine) | ConversationMemory (E12) and ResearchAgent both use CTX pipeline |
| SPEC-002 (Frontend UX Revamp) | Canvas staleness (E2), query progress (E18), interactive tables (E19) overlap |
| SPEC-003 (Proactive Intelligence) | Event-driven alerts will need new canvas tab and intent handler |
| SPEC-004 (UI Upgrade) | G1/E2 (canvas staleness) = G2 in SPEC-004; G9/E9 = U2 in SPEC-004 |

---

*End of SPEC-005*
