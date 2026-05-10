# SPEC-016: Unified Agent Graph + IE-Pattern Grounding

*Date: 19 April 2026*
*Sources: Lead architecture review (lead_notes_4_dev.md, 19 Apr) + intelligent_enterprise CTX implementation analysis*
*Supersedes: SPEC_015 WS-2 (intent NLU layer with regex)*

---

## Why This Spec Exists

Two architectures coexist inside Market Zero:

- **Architecture A (agentic)**: `services/agent/graphs/query_graph.py` — production-grade LangGraph state machine with 4 tools (SQL, RAG, Graph, Metrics), LLM-driven planning, schema introspection, validate-and-enrich loop.
- **Architecture B (hardcoded)**: `services/chat_handlers/handlers.py` — 8 regex-matched intent handlers, fixed service-call sequences, LLM as text decorator.

**Architecture A handles 2 of 9 intents (STRUCTURED_QUERY, TEAM_EVAL). Architecture B handles 7 of 9.** The simple queries get the powerful infrastructure; the complex queries that need planning get rigid pipelines. This is backwards.

The transcript failures (Ozempic pipeline returns no data, contradictory trial counts, confabulated metrics, template echo bugs) are direct consequences of Architecture B's rigidity. The fix is **not** more regex (the original WS-2 plan) — it is to route all intents through the query graph that already exists and works.

In parallel, the `intelligent_enterprise` project demonstrates **bounded-catalog grounding patterns** that produce highly reliable LLM responses. Adopting those patterns gives Market Zero output guarantees that complement the architectural unification.

This spec combines both:
- **Track 1 (Architecture)** — unify routing through the agent graph (lead's 3-phase plan)
- **Track 2 (Grounding)** — adopt IE-pattern output constraints (sandwich grounding, click-through citations, retry-loop guard, catalog-wide query detection, title-ID mismatch detection)

The two tracks ship in parallel and are independently testable. Track 2 benefits the legacy handlers TOO before Track 1 retires them.

---

## Track 1 — Unify the Router (architecture)

### Phase 1 — Route all intents through query_graph (1-2 weeks)

Today the chat route's `if/elif` chain dispatches 7 of 9 intents to fixed handler functions. After Phase 1, **all 9 intents enter the query graph**, with intent-specific planning prompts that tell the LLM planner what tool combinations to consider.

**Implementation outline:**

1. Extend `services/agent/graphs/query_graph.py` to accept an `intent_hint` parameter
2. Add intent-specific system-prompt fragments for the planner node:
   - `dossier`: prefer SQLQueryTool for entity facts + RAGSearchTool for evidence
   - `compare`: parallel SQL + Metrics calls for each entity
   - `landscape`: MetricsQueryTool against materialized views
   - `pipeline`: MetricsQueryTool with drug_id OR therapeutic_area filters
   - `portfolio`: SQL on companies table + nested drug joins
   - `general`: hybrid (RAG + SQL)
   - `deep_research`: RAG primary + WebResearch tool fallback
3. In `api/routes/chat.py`, replace the existing `if/elif intent == ...` chain with a single call to `query_graph.invoke({"question": ..., "intent_hint": str(intent), ...})`
4. **Keep legacy handlers as fallback** — wrap the query_graph call in try/except, fall through to existing `handle_dossier`/`handle_compare`/etc. on failure. Mirrors the existing UnifiedChatHandler fallback pattern (SPEC_011).

**Acceptance**: every intent that previously worked still works (no regressions). At least 3 transcript-failure cases now succeed (Ozempic pipeline, brand-name comparison, "show competitive landscape for show" — caught at planner stage with clarification).

### Phase 2 — Sufficiency check loop (1-2 weeks)

Add a new graph node: `check_sufficiency`. After tool execution, the LLM evaluates whether the retrieved data answers the question. If not, it can issue additional tool calls within a budget (max 3 iterations).

**Implementation outline:**

1. New graph node between `execute` and `synthesize`: takes the original question + tool results, returns `{ sufficient: bool, gap_description: str, suggested_next_action: str | null }`
2. If `sufficient=false` and budget remaining: re-enter the `plan` node with the gap as additional context
3. If budget exhausted or LLM says no further action would help: proceed to synthesis with explicit coverage caveats
4. Coverage diagnostic from SPEC_015 WS-3 becomes a sub-call inside this node — rather than a standalone service

**Acceptance**: queries that today return sparse data ("compare X vs Y" with 2 trials each) get either (a) augmented retrieval, or (b) a coverage caveat in the response. Never a confident verdict on sparse data.

### Phase 3 — Retire hardcoded handlers (2-3 weeks)

Once the unified path is stable for 1 week (low fallback rate, no quality regressions), delete `services/chat_handlers/handlers.py` and the if/elif dispatch chain. Intent detection becomes a planning prompt, not a regex cascade. Net code reduction: ~900 lines.

**Acceptance**: chat route is one call to `query_graph.invoke()`. Intent regex retained only as a soft hint to the planner (or removed entirely if the planner doesn't need it).

---

## Track 2 — IE-Pattern Grounding (output constraints)

These ship in parallel with Track 1 and benefit BOTH the legacy handlers AND the unified query graph. Source patterns: `C:\Users\kapil\Documents\intelligent_enterprise\app\api\chat\route.ts` + `lib/ctx/catalog-context.ts` + `lib/ctx/context-guard.ts`.

### Priority 1 — quick wins (~3 days total)

**1A. Sandwich grounding in CTX system prompt** (~0.5d)
- After the corpus injection in `services/llm.py::_build_context_block()`, append a tail reminder:
  > "Before you respond: every entity ID you cite must appear in the corpus above. If it isn't there, say so explicitly. Every drug name should link to /entity/drug/{id} so users can navigate."
- Mirrors the IE pattern at `route.ts:148-153` ("REMINDER — BEFORE YOU RESPOND").

**1B. Click-through citation format** (~1d)
- Update LLM system prompt to require `[entity_name](/entity/{type}/{id})` markdown links for every entity mention
- Update `services/llm.py::validate_citations` to count entity-link presence per claim sentence
- Frontend renderer already handles markdown links → automatic clickability
- Replaces (or supplements) numeric `[N]` evidence indices

**1C. L3 directory always in system prompt** (~1d)
- New helper `services/ctx_corpus.py::get_l3_summary()` returns: "Universe: 1,247 drugs, 412 companies, 8,103 trials, 89 mechanisms. Full data hydrated below per query."
- Inject into every chat system prompt regardless of unified-handler routing
- Sets the LLM's expectation that the world is finite and bounded

### Priority 2 — guard improvements (~3 days total)

**2A. ContextGuard retry loop** (~1d)
- Port pattern from IE `route.ts:175-204`: when `runContextGuard` returns `verdict='retry'`, append correction message and call LLM once more
- If retry still fails (`verdict in {retry, new_session}`), serve original response with explicit "data quality warning" to the user
- Telemetry: log guard verdict, retry count, before/after violation count

**2B. Catalog-wide query detection** (~0.5d)
- Keyword list: `["how many drugs", "list all", "every company", "total number of trials", ...]`
- When matched, inject a strong-grounded count summary into the system prompt: "Total: 1,247 drugs. Of those, X have brand_name populated, Y have FDA approval. Use these exact counts."
- Prevents a common hallucination class (made-up totals)

**2C. Title-ID mismatch detection** (~1d)
- Add to existing `ContextGuard.check()`: scan response for `[Title](/entity/drug/{id})` patterns. For each, look up canonical name for that ID. If Dice coefficient between displayed title and canonical title < 0.7, flag as `title_id_mismatch`.
- Catches `[Semaglutide](/entity/drug/{tirzepatide-uuid})` type errors
- Reuses existing canonicalizer for ID lookup

### Priority 3 — telemetry + modes (~3 days total)

**3A. Per-query CTX telemetry overhaul** (~1d)
- Match IE's `HydrationTelemetry` schema: `{question_hash, matched_entity_ids, hydration_count, tokens_injected, guard_verdict, retry_triggered, latency_ms}`
- Persist to existing `ctx_events` table (migration 014)
- Build SQL view `v_ctx_quality_daily` for dashboard

**3B. Two-mode chat (explore vs structured)** (~2d, **deferred** if time-constrained)
- "Explore" mode: temp=0.3, allows reasoning over partial data with caveats
- "Structured" mode: temp=0, strict grounding, refuses to answer if data missing
- Default = explore; structured opt-in via API param
- Useful but not blocking — defer to backlog if Track 1 takes priority

---

## What This Spec Replaces / Reframes

| Item | Status |
|------|--------|
| SPEC_015 WS-2 (intent NLU + regex slot validation) | **REFRAMED** — was "more regex with validation"; now becomes Phase 1 of Track 1 (unify through query_graph) |
| SPEC_015 WS-3 (Coverage Diagnostic standalone service) | **MERGED** into Track 1 Phase 2 (sufficiency check graph node) |
| SPEC_015 WS-6 (Follow-up generation hardening) | **STILL APPLIES** — runs in parallel; entity validation in followups still needs hardening regardless of router |

What from SPEC_015 still ships independently:
- WS-1 (entity canonicalisation) — ✅ already shipped
- WS-4 (provenance & citations) — Track 2 Priority 1B addresses 80% of this
- WS-5 (numeric guardrails + cross-turn consistency) — still needed; Track 1 Phase 2 makes it easier
- WS-7 (eval harness overhaul) — must come last, tests both tracks

---

## Sequencing Rationale

The sequence below interleaves quick wins with longer architectural work, so user-visible improvements ship within days while the bigger migration progresses in the background.

| Step | Work | Effort | Why this order |
|------|------|--------|----------------|
| 1 | **Smoke test query_graph** against drug-pipeline queries | 30 min | Cheap reality check before committing to migration |
| 2 | **Pipeline-intent hotfix** in `handle_pipeline` (accept drug_id) | 1-2 hours | User-visible bug; doesn't conflict with Track 1 |
| 3 | **Track 2 Priority 1A + 1B + 1C** (grounding + citations + L3 dir) | 2-3 days | Quick wins; benefit BOTH architectures; low risk |
| 4 | **Track 1 Phase 1** (route all intents through query_graph + fallback) | 1-2 weeks | Largest single architectural lift |
| 5 | **Track 2 Priority 2A + 2B + 2C** (retry loop + catalog-wide + title-ID guard) | 3 days | Guard improvements ship after Track 1 settles |
| 6 | **Track 1 Phase 2** (sufficiency check loop) | 1-2 weeks | Builds on Phase 1 unified path |
| 7 | **WS-5 numeric guardrails + cross-turn consistency** | 3-4 days | Easier inside the unified path |
| 8 | **Track 1 Phase 3** (retire legacy handlers) | 2-3 weeks | Only after fallback rate stays < 1% for a week |
| 9 | **WS-7 eval harness overhaul** | 4-5 days | Last — exercises both tracks end to end |

**Total effort: ~6-8 weeks** for full migration. **First user-visible improvement: ~2 days** (pipeline hotfix + grounding wins).

---

## What to Preserve (lead's explicit list)

These stay deterministic — do NOT route through LLM:

- **Entity canonicalisation** (SPEC_015 WS-1, shipped) — DB lookup, not LLM inference
- **Presentation planning** — `services/agent/presenter.py::plan_presentation()` is well-designed
- **SQL safety** — DML/DDL blocking, table whitelist, LIMIT enforcement in `SQLQueryTool`
- **Materialised views** — pre-computed metrics; the agent CALLS them via `MetricsQueryTool`, not regenerates
- **Few-shot exemplars** — keep the library; consider making selection adaptive (embed query → nearest exemplars) instead of intent-filtered

---

## Tests First (per phase)

Each phase below opens with a TDD test contract. Phase-specific test files:

- `tests/test_query_graph_unified_routing.py` — Track 1 Phase 1
- `tests/test_query_graph_sufficiency.py` — Track 1 Phase 2
- `tests/test_ie_pattern_grounding.py` — Track 2 Priority 1
- `tests/test_context_guard_retry.py` — Track 2 Priority 2A
- `tests/test_catalog_wide_queries.py` — Track 2 Priority 2B
- `tests/test_title_id_mismatch.py` — Track 2 Priority 2C

Each phase has its own acceptance criteria documented in this spec. Test contracts get written before implementation per the sprint plan's TDD discipline rule.

---

## Definition of Done (full spec)

- All 9 intents flow through `query_graph` (Track 1 Phase 1+2)
- Legacy handlers deleted (Track 1 Phase 3)
- Every chat response includes click-through entity links (Track 2 Priority 1B)
- ContextGuard retry-loop catches at least 80% of multi-violation responses on first retry (measured via telemetry)
- Catalog-wide query test set ("how many drugs", "list all companies") returns exact counts that match SQL aggregates
- Title-ID mismatch detection catches synthetic test cases where title and ID are swapped
- Eval harness (WS-7) shows ≥ 80% composite score with the new query set
- Net code reduction: ~900 lines from removing handlers
- Production fallback rate (unified handler → legacy fallback) < 1% sustained for 7 days

## Open Questions

1. **Planner LLM model** — gpt-4o-mini for cost or gpt-4o for accuracy? Phase 1 should benchmark both.
2. **Sufficiency loop budget** — 3 iterations max? Or token-budget-based?
3. **Intent regex retention** — fully delete or keep as a cheap pre-classifier hint?
4. **Two-mode chat** — ship now or defer? Recommendation: defer (Priority 3B → backlog).
