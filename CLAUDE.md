# Market Zero — Claude Code Instructions

## Architecture
- **Backend**: FastAPI + psycopg2 + PostgreSQL (pgvector)
- **Frontend**: React 19 + TypeScript + Tailwind CSS + Recharts + Framer Motion
- **ETL Pipeline**: fetch → normalize → resolve → embed → store → cross-link
- **Domain Pack**: Pharma domain with 9 entity types, 12 link rules, 10 connectors
- **Services**: HybridSearch, GraphTraversal, PharmaMetrics, QueryEngine, LLMSynthesizer
- **Deployment**: Railway (Nixpacks), GitHub: cryogenic22/myscience

## Key Entry Points
- `api/app.py` → `create_app()` factory (FastAPI)
- `api/routes/chat.py` → Chat orchestration (intent detection → handler → LLM synthesis)
- `api/deps.py` → Dependency injection (singleton services)
- `frontend/src/App.tsx` → React root
- `frontend/src/pages/IntelligencePage.tsx` → Main workspace
- `config.py` → `AppConfig` singleton (`config`)
- `db.py` → `Database` class (fetch_one, fetch_all, execute)

## Code Patterns

### Backend
- **Always TDD**: Write tests first in `tests/`, then implement. 176 tests currently passing.
- **Entity resolution**: Use `_resolve_entity()` in chat.py (exact → fuzzy → embedding)
- **Metrics**: Pre-computed in materialized views (mv_drug_pipeline_strength, etc.)
- **LLM synthesis**: `services/llm.py` with intent-specific system prompts + anti-hallucination rules
- **Domain pack**: `domain/pharma/pack.py` → `get_pharma_pack()` for all pharma config
- **Migrations**: Numbered in `schema/migrations/` (001-013)
- **CTX integration**: `services/ctx_corpus.py`, `services/ctx_pipeline.py`, `services/unified_handler.py`

### Frontend
- **Tailwind CSS**: Utility-first, design tokens in `index.css` `:theme {}` block
- **Component location**: `frontend/src/components/`
- **API calls**: Via `frontend/src/api.ts` (get/post helpers)
- **Icons**: Lucide React
- **Charts**: Recharts (Bar, Pie, Line)
- **Animations**: Framer Motion
- **No external UI library** — all components are custom

### Conventions
- **Check anti-slop.md FIRST** before creating any new function, component, or utility
- **Match existing patterns**: Read 2-3 sibling files before writing new code
- **One logical change per commit**: Conventional commit format (`feat:`, `fix:`, `chore:`)
- **No untested backend code**: Every service change needs at least one test
- **Entity types**: Declared in domain pack EntitySchema, not scattered across files
- **Canonical source names**: `clinical_trials_gov` (not clinicaltrials_gov), `fda_orange_book`, etc.
- **Database**: PostgreSQL via `db.py` Database class. Railway provides `DATABASE_URL` env var.

## Testing
- **Framework**: pytest 8.3.4
- **Run**: `python -m pytest tests/ -v`
- **Fixtures**: `tests/conftest.py` (MockLLM, StubTool, ToolCallRecorder, make_*_result helpers)
- **Mock DB**: `tests/test_ctx_corpus.py` has `MockDB` class for DB-free tests
- **Current**: 176 passing, 4 skipped, 0 failures
- **Coverage ratchet**: Never decrease test count

## Specs
- `specs/SPEC_001_autonomous_research_engine.md` — CTX pipeline + research agent + memory
- `specs/SPEC_002_frontend_ux_revamp.md` — Chat+Canvas split panel UX redesign

## Harness
- **Refresh**: `python harness/generate.py --refresh` (after major changes)
- **Health check**: `python harness/measure.py` (weekly)

## Codebase Map
@.claude/codebase-map.md

## Anti-Slop Rules
@.claude/rules/anti-slop.md

## Test Requirements
@.claude/rules/test-requirements.md
