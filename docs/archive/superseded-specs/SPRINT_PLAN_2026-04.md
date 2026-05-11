# Sprint Plan: April 2026 — Pipeline Strengthening

*Date: 19 April 2026*
*Source: `specs/brainstorm_pubmed_and_db_crash.md` + `lead_notes_4_dev.md` review*

---

## Context

Database is restored on a 50 GB Railway volume (sufficient headroom for current data + WAL + temp). Previous crash was disk exhaustion during ETL bulk insert; root cause now eliminated. We can move on to strengthening the pipeline.

This sprint plan sequences the 5 highest-leverage improvements from the architecture review and brainstorm. Each task has its own SPEC document with full TDD plan. Specs follow a consistent shape:
1. Goal + why this matters
2. **Tests first** — exact test files and assertions to write *before* implementation
3. Implementation plan in dependency order
4. Acceptance criteria (measurable)
5. Rollout / rollback plan

## TDD Discipline (applies to all tasks)

For every spec in this plan, the workflow is non-negotiable:

1. **Read the spec's "Tests First" section.** Write the listed test files in `tests/` exactly as described.
2. **Run the tests** (`python -m pytest tests/test_<feature>.py -v`). Confirm they all FAIL with the expected error (missing module, missing function, wrong return value).
3. **Implement the minimum code** to make tests pass — one assertion at a time.
4. **Run the full suite** (`python -m pytest tests/ -v`). Confirm:
   - New tests pass.
   - No existing tests broke. The `180+` baseline must not regress.
5. **Commit per spec** with conventional message (`feat:`, `fix:`, `chore:`).

If you find yourself implementing without tests in place, stop and write the tests first. This is the convention in `CLAUDE.md` and `.claude/rules/test-requirements.md` — every change needs a test.

---

## Task Sequence

| # | Spec | Task | Priority | Effort | Blocks |
|---|------|------|----------|--------|--------|
| 1 | [SPEC_010](SPEC_010_schema_drift_cleanup.md) | Schema drift cleanup (missing tables/columns from crash logs) | P0 | 1 day | #2, #3 |
| 2 | [SPEC_011](SPEC_011_ctx_guard_default.md) | Wire CTX ContextGuard as the default chat path | P1 | 1 day | — |
| 3 | [SPEC_012](SPEC_012_openalex_connector.md) | OpenAlex connector — 25× literature expansion + citation graph | P1 | 3–5 days | #4 |
| 4 | [SPEC_013](SPEC_013_link_confidence_calibration.md) | Calibrate link confidence by discovery method | P2 | 2–3 days | — |
| 5 | [SPEC_014](SPEC_014_document_upload_ner.md) | Document upload connector + LLM-based NER (dark data) | P2 | 1 week | — |

**Recommended order:** #1 → #2 → #4 → #3 → #5

Rationale:
- **#1 first** because the missing schema is silently turning the Data Steward into a no-op every 2 hours and generating log noise.
- **#2 next** because it's a 1-day change that delivers the single largest hallucination-quality improvement (lead's Section 7.3).
- **#4 before #3** because OpenAlex (#3) introduces many new links — calibrating confidence first means those new links get correct confidence from day one (no backfill needed).
- **#3 before #5** because OpenAlex enriches the existing literature corpus, which is a higher-value foundation for the dark-data connector (#5) to build on.

## Out of Sprint (Backlog)

These are valuable but deferred so the sprint can finish. They have no specs yet — write them when the sprint above ships.

| Task | Why Deferred |
|------|--------------|
| Temporal graph queries (valid_from/valid_until) | Bigger schema change, less immediate ROI than #3/#4 |
| Conflict resolution policies in EntityConsolidator | Current behavior is "good enough"; only matters once OpenAlex doubles source overlap |
| Pre-store quality gating | Complementary to #4; cleaner to ship after link confidence is calibrated |
| ATC / RxNorm / SNOMED ontology supplements | 1+ week each; do after OpenAlex Topics are integrated |
| AutonomousResearchAgent wiring (built, not wired) | Best done after #1 ships so the steward + research agent can both run cleanly |

## Cross-Cutting Concerns

**Test count baseline**: 180 unit tests passing currently. The end of this sprint should add ~60-80 new tests across the 5 SPECs and ratchet to ~250 passing, 0 failing.

**Migration sequence**: Migrations 015 and 016 are needed (15 for schema cleanup, 16 for link confidence + citation link type). No migration conflicts expected with current main branch.

**Environment variables added by this sprint**:
- `MZ_UNIFIED_HANDLER` — flip to `true` as part of SPEC_011 rollout
- `OPENALEX_MAILTO` — required by OpenAlex polite pool (use kapilpant@gmail.com)
- `MZ_LINK_CONFIDENCE_FLOOR` — minimum confidence for evidence retrieval (default 0.5)
- `MZ_DOC_UPLOAD_MAX_MB` — max document upload size (default 25)

**Telemetry to add**:
- CTX guard activations / suppressions (SPEC_011)
- OpenAlex API call counts and rate-limit headers (SPEC_012)
- Confidence-filter exclusions in graph traversal (SPEC_013)
- Document upload events: pages, chunks, entities extracted (SPEC_014)

**Operational checks**:
- After SPEC_010, the DB error log should be quiet — no more `relation "agent_sessions" does not exist`.
- After SPEC_012, the literature record count should jump from ~2,000 to ~50,000.
- After SPEC_013, the average link confidence in `entity_links` should drop from ~1.0 to ~0.85, with measurable distribution across discovery methods.
