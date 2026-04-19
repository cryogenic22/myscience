# Execution Plan — April 2026 (REVISED)

*Date: 19 April 2026 (revised after intelligence remediation spec received)*
*Reconciles: `SPRINT_PLAN_2026-04.md` (5 SPECs) + gap audit + production transcript review + `SPEC_015_intelligence_remediation.md` (7 workstreams)*
*Source of truth for sequencing across the next 4-6 weeks*

## REVISION NOTE — 19 April 2026

After SPEC_010 (schema drift) and SPEC_011 (CTX default + A/B) shipped to production, a domain-expert review of a live system transcript revealed **fundamental intelligence-layer failures** (brand→generic resolution missing, intent slot validation absent, no provenance, internal contradictions, low-coverage verdicts). A code-cited remediation spec was produced (`SPEC_015_intelligence_remediation.md`) with 7 implementation-ready workstreams.

**Decision: defer SPEC_012 (OpenAlex), SPEC_013 (link confidence), SPEC_014 (document upload) until after the 7 remediation workstreams ship.** Rationale: feature/data improvements have negative ROI when the underlying chatbot is structurally broken on the most common user query pattern (brand-name lookups).

---

## Inputs Reconciled

| Source | Items | Action |
|--------|-------|--------|
| SPRINT_PLAN_2026-04.md | 5 SPECs (010-014) | Kept as primary spine |
| Gap audit (downloaded) | 12 GAPs | 6 overlap with SPECs (10/11/12/13/14); 6 are new |
| Memory + verification | Cross-checks | Audit had 1 false claim (GAP-12 conversation memory IS wired) |

## Verification Results from the Gap Audit

Before accepting the audit's claims, I verified the doubtful ones:

| Audit Claim | Verified? | Notes |
|-------------|----------|-------|
| GAP-01: CTX guard opt-in (config.py:168 false) | **TRUE** | Confirmed at config.py:168 |
| GAP-03: Schema drift, missing tables/columns | **PARTLY** | `agent_sessions/agent_events` exist via migration 029 (just need to apply); `primary_entity_id` genuinely missing → migration 032 |
| GAP-05: Feedback loops not auto-triggered | **TRUE** | No FeedbackLoopOrchestrator in api/app.py |
| GAP-07: CTX corpus stale via @lru_cache | **TRUE** | `get_unified_handler()` at deps.py:283 uses `@lru_cache()` |
| GAP-08: No vite code splitting | **TRUE** | No manualChunks in vite.config.ts |
| GAP-12: Conversation memory not wired | **FALSE** | api/routes/chat.py lines 161, 192, 218, 274 actively use it |

Net: gap audit is mostly accurate but had 1 false positive. Trust but verify each claim before acting.

## Status of Existing SPECs

| SPEC | Status | Notes |
|------|--------|-------|
| SPEC_010 (Schema Drift) | **IN PROGRESS** (local fixes done, tests pass) | Migration 032 created; 5 code fixes applied; awaiting prod migration apply |
| SPEC_011 (CTX Guard Default) | Not started | GAP-01 alias |
| SPEC_012 (OpenAlex Connector) | Not started | GAP-09 alias |
| SPEC_013 (Link Confidence) | Not started | GAP-04 alias; consider GAP-04 acceptance criteria as additions |
| SPEC_014 (Document Upload + NER) | Not started | GAP-02 alias |

## Phase Sequence (REVISED)

| Phase | Spec / WS | Description | Effort | Status |
|-------|-----------|-------------|--------|--------|
| 1 | SPEC_010 | Schema drift cleanup | 0.5d | ✅ Shipped (commits f23352f, 561302d) |
| 2 | SPEC_011 | CTX default + A/B rollout | 1d | ✅ Shipped (commit c593b62), monitoring 48h |
| **3** | **SPEC_015 WS-1** | **Entity Canonicalisation (brand→INN)** | **5-7d** | **NEXT — start now** |
| 4 | SPEC_015 WS-2 | Intent & NLU Layer (slot validation, meta intent) | 3-4d | After WS-1 |
| 5 | SPEC_015 WS-6 | Follow-Up Generation (validate before template) | 1-2d | After WS-2 |
| 6 | SPEC_015 WS-4 | Provenance & Citations (source IDs in evidence) | 3-4d | After WS-1 |
| 7 | SPEC_015 WS-5 | Numeric Guardrails + Cross-Turn Consistency | 3-4d | After WS-1 |
| 8 | SPEC_015 WS-3 | Coverage Diagnostics | 3-4d | After WS-1, WS-4 |
| 9 | SPEC_015 WS-7 | Eval Harness Overhaul | 4-5d | Last — tests everything |

**Total remediation effort: 22-30 days (single dev) / 12-16 days (parallel).**

## DEFERRED (re-prioritized)

| Spec | Original Phase | Why Deferred |
|------|---------------|---------------|
| SPEC_012 OpenAlex | Phase 6 | Adds data; doesn't fix retrieval bugs |
| SPEC_013 Link Confidence | Phase 4 | Partial overlap with WS-4 provenance; do as follow-on |
| SPEC_014 Document Upload + NER | Phase 7 | Feature work; non-blocking |
| GAP-07 CTX corpus refresh | Phase 3 (was) | Useful but not user-blocking |
| GAP-05 Feedback auto-trigger | Phase 5 (was) | Steward already runs; auto-trigger is nice-to-have |
| GAP-06 Frontend test coverage | Parallel | Continues as background work |
| GAP-08 Code splitting | Parallel | 30-min change, do anytime |

## Migration Numbering (Authoritative)

| # | Phase | Purpose | Status |
|---|-------|---------|--------|
| 032 | Phase 1 | `market_events.primary_entity_id` | ✅ Created |
| 033 | Phase 3 (WS-1) | Seed `entity_aliases` from `drugs.brand_name` | Next |
| 034 | Phase 6 (WS-4) | Source ID columns on EvidenceItem (if needed) | Pending |
| 035 | TBD | Reserved | — |

## Original Phase Sequence (KEPT FOR REFERENCE)

The original sprint plan (010 → 011 → 013 → 012 → 014) shipped Phases 1-2.

### Phase 1 — Foundation (SPEC_010 + GAP-03 cleanup)
**Status: COMPLETE locally, pending prod deploy**

- [x] Tests written (`tests/test_schema_drift_fix.py`, 14 tests)
- [x] Migration 032 created (`market_events.primary_entity_id`)
- [x] Code fixes: steward_signals.py, catalog.py, consolidate_drugs.py
- [x] All 7 static tests pass; 7 DB tests skip locally
- [x] Full suite: 1110 passing, no regressions
- [ ] **Deploy**: push to main, run `railway run python migrate.py` to apply 029 + 032
- [ ] **Verify**: monitor Railway logs 4 hours — zero `relation does not exist` errors

### Phase 2 — CTX Guard Default (SPEC_011 / GAP-01)
**1 day. No deps.**

Per SPEC_011:
- Flip `config.py:168` `MZ_UNIFIED_HANDLER` default to `true`
- Strengthen fallback in `api/routes/chat.py` (catch + telemetry on UnifiedChatHandler exception)
- Add guard suppression telemetry in `services/ctx_pipeline.py`
- Tests: `tests/test_ctx_guard_default.py` (write FIRST per TDD)
- Acceptance: chat queries return 200; `unified_handler_fallback` rate < 5% over 24h

### Phase 3 — CTX Corpus Refresh (GAP-07) — NEW
**1 day. Depends on Phase 2 (don't change CTX path while flipping default).**

- Replace `@lru_cache()` on `get_unified_handler()` in `api/deps.py:283` with a TTL cache (30 min)
- Add `rebuild()` method to `PharmaCorpusBuilder` in `services/ctx_corpus.py`
- Add `last_built` timestamp; expose via `/health` endpoint
- Optional: trigger corpus rebuild after successful pipeline run
- Tests: `tests/test_ctx_corpus_refresh.py` — TTL expiry, rebuild idempotency, non-blocking

### Phase 4 — Link Confidence Calibration (SPEC_013 / GAP-04)
**2-3 days. Ship before SPEC_012 so OpenAlex links inherit calibrated confidence.**

Per SPEC_013:
- New `integration/confidence.py` with calibration table
- Migration 033 (next available) — `traverse_graph(p_min_confidence)` + backfill
- Update `cross_linker.py` and `entity_resolver.py`
- Add `MZ_LINK_CONFIDENCE_FLOOR` env var
- Tests: `tests/test_link_confidence_calibration.py`

### Phase 5 — Feedback Loops Auto-Trigger (GAP-05) — NEW
**1 day. Depends on Phase 1 (steward must be working first).**

- Add `FeedbackLoopOrchestrator` to background loop in `api/app.py:261-429`
- Run every 6th cycle (alongside FAIR scoring)
- Wire as singleton dep in `api/deps.py`
- Tests: `tests/test_feedback_loop_scheduling.py` — runs on schedule, results logged, doesn't slow main loop

### Phase 6 — OpenAlex Connector (SPEC_012 / GAP-09)
**3-5 days. Depends on Phase 4 (link confidence) so new CITES/AFFILIATED_WITH links land calibrated.**

Per SPEC_012:
- New connector + migration 034 (next available; OpenAlex columns + institutions table)
- Domain pack: `institution` entity, `CITES`, `AFFILIATED_WITH` link rules
- Schedule: daily at 03:30 UTC
- Tests: `tests/test_openalex_connector.py` + `tests/test_openalex_schema.py`
- Initial backfill: ~30-60 min, expect ~50K records

### Phase 7 — Document Upload + NER (SPEC_014 / GAP-02)
**5-7 days. Largest new feature. Depends on stable pipeline (Phases 1-3).**

Per SPEC_014:
- New `services/document_extractor.py` (PDF/DOCX/HTML/text)
- New `services/document_ner.py` (LLM-based, chunked, deduped)
- New `connectors/user_document.py`
- New `/upload` endpoint
- Tests: 3 files (extractor, NER, end-to-end)
- LLM cost: <$0.05/document target

### Phase 8 — Conversation Memory Verification (GAP-12 alias) — NEW BUT MINOR
**0.5 day.**

GAP-12 claimed memory not wired. Verification showed it IS wired. But add integration tests to lock that in:
- `tests/test_chat_memory_integration.py` — multi-turn coreference resolution
- "tell me more about it" reference test
- Token budget eviction test (already covered in unit tests, add e2e)
- Session isolation test

## Parallel Tracks (no spec dependencies)

Throughout Phases 2-7, these run continuously:

### Track A — Frontend Test Coverage (GAP-06)
Target: 24% → 50% (17 → 36 of 72 components tested)

Per gap audit priority order:
1. `frontend/__tests__/components/chat/NarrativeMessage.test.tsx`
2. `frontend/__tests__/components/canvas/CanvasPanel.test.tsx`
3. `frontend/__tests__/components/layout/WorkspaceLayout.test.tsx`
4. `frontend/__tests__/components/DataCatalogPanel.test.tsx`
5. `frontend/__tests__/pages/WorkspacePage.test.tsx`

Cadence: +3 test files per phase. Don't block phase progression on this.

### Track B — Frontend Code Splitting (GAP-08)
0.5 day. Quick `vite.config.ts` change. Do alongside Track A early files.

### Track C — Error Boundaries (GAP-11)
1 day. Wrap `CanvasPanel`, `ChatPanel`, `DataCatalogPanel` in error boundaries with retry UI. Do during Phase 7 (doc upload may surface new error modes).

### Track D — Benchmark Coverage (GAP-10)
1-2 days. Add 5 compound-intent queries + 3 multi-turn flows to `benchmark/golden_queries.json`. Best done after Phase 6 (more data → richer queries).

## Migration Numbering (Authoritative)

Existing migrations go through 031. Next available are 032+.

| # | Phase | Purpose |
|---|-------|---------|
| 032 | Phase 1 | `market_events.primary_entity_id` (✅ created) |
| 033 | Phase 4 | `traverse_graph(p_min_confidence)` + link confidence backfill |
| 034 | Phase 6 | OpenAlex columns + `institutions` table |

## Test Count Trajectory

| Phase | Tests Added | Cumulative |
|-------|-------------|-----------|
| Baseline (today) | — | 1,110 backend + ~58 frontend |
| Phase 1 (✅) | +14 | 1,124 (with 7 skipped locally) |
| Phase 2 | +7-10 | ~1,134 |
| Phase 3 | +5 | ~1,139 |
| Phase 4 | +12 | ~1,151 |
| Phase 5 | +5 | ~1,156 |
| Phase 6 | +20 | ~1,176 |
| Phase 7 | +25 | ~1,201 |
| Phase 8 | +5 | ~1,206 |
| Frontend (Tracks A/C) | +30 | +30 frontend |

End-of-sprint target: ~1,200 backend tests, ~88 frontend tests, 0 unit failures.

## TDD Discipline (non-negotiable, applies to every phase)

1. Read the spec's "Tests First" section
2. Write the test file in `tests/`
3. Run `python -m pytest tests/test_<feature>.py -v` — confirm ALL FAIL
4. Implement minimum code to make tests pass
5. Run `python -m pytest tests/ -v` — confirm no regressions in baseline
6. Commit per phase with conventional message

Phase 1 demonstrated the value of this: my initial test patterns had 1 false positive AND missed real bugs in files outside my candidate list. Broadening the search across all `services/`, `scripts/`, `api/`, `integration/` Python files surfaced 5 real bugs vs the 4 I'd guessed from the crash logs.

## SWE Practice Improvements (from gap audit Section 4)

Adopt alongside Phase work, not as separate phases:

- **Pre-commit hooks** (gap §4.1): Add `ruff check` + `tsc --noEmit` + fast pytest subset. Do at end of Phase 2.
- **CLAUDE.md slimming** (gap §4.2): Move anti-slop catalogue into a Skill, keep CLAUDE.md under 80 lines. Do at end of Phase 4.
- **Verification patterns** (gap §4.4): Already implicitly enforced in spec acceptance criteria. Document in CLAUDE.md.
- **Worktree isolation** (gap §4.5): Use `git worktree add` for migration phases (1, 4, 6) to test in isolation before merging.

## Risk Register

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Migration 032 fails on prod | Low | High | Migration is idempotent; tested locally; safe to re-run |
| CTX default flip increases hallucinations | Medium | Medium | Phase 2 includes 24h fallback rate monitoring; revert via env var if needed |
| OpenAlex backfill hits rate limits | Medium | Low | Polite pool with mailto; retry logic; backfill is offline so failure isn't user-facing |
| Doc upload introduces NER cost spike | Low | Medium | Per-doc cost target $0.05; alert if monthly LLM spend grows >20% |
| Confidence calibration breaks evidence retrieval | Medium | High | Default `MZ_LINK_CONFIDENCE_FLOOR=0.0` (no filtering); ramp to 0.5 after 1 week |
| Test count regression from broad refactors | Medium | Medium | Per-phase test ratchet; CI rejects PRs that decrease test count |

## Definition of "Sprint Complete"

- [ ] All 8 phases shipped to production
- [ ] All 4 parallel tracks reach their targets (frontend 50%, splitting, boundaries, benchmark)
- [ ] Test count ≥1,200 backend, ≥88 frontend
- [ ] CI benchmark ≥75% (no regression)
- [ ] Production logs: zero `relation does not exist` errors for 7 days
- [ ] CTX fallback rate <5% for 24h continuous
- [ ] OpenAlex literature count ≥40K
- [ ] At least one document successfully uploaded + entity-resolved end-to-end

## What's NOT in This Sprint

Per `SPRINT_PLAN_2026-04.md` deferred backlog, plus gap-audit-noted items:

- Temporal graph queries (`valid_from`/`valid_until`)
- Conflict resolution policies in EntityConsolidator
- Pre-store quality gating
- ATC / RxNorm / SNOMED ontology supplements
- AutonomousResearchAgent wiring
- Pre-commit hooks (deferred to end of Phase 2 as a smaller add-on)
- CLAUDE.md restructure (deferred to end of Phase 4)
