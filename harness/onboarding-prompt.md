# Market Zero — Session Onboarding

You are working on **Market Zero**, a pharma intelligence platform with GraphRAG, CTX-powered context management, and an autonomous research agent.

## Before you write ANY code:

1. Read `CLAUDE.md` for architecture and conventions
2. Read `.claude/codebase-map.md` for module structure
3. Read `.claude/rules/anti-slop.md` — **DO NOT create functions that already exist**
4. Read `.claude/rules/test-requirements.md` for testing patterns

## Search before coding:
- Use Grep/Glob to find existing implementations before writing new ones
- Read 2-3 sibling files to match patterns

## Testing:
- Backend: pytest (`python -m pytest tests/ -v`), 176 tests currently passing
- Write tests FIRST (TDD), then implement
- Use MockDB from `tests/test_ctx_corpus.py` for DB-free tests
- Use fixtures from `tests/conftest.py` (MockLLM, StubTool, make_*_result)

## Commit format:
```
feat(scope): description
fix(scope): description
chore: description
```

## Key architecture:
- **Backend**: FastAPI factory (`api/app.py:create_app`)
- **Frontend**: React + Tailwind (`frontend/src/`)
- **Services**: `services/` (search, graph, metrics, llm, query_engine)
- **CTX pipeline**: `services/ctx_corpus.py`, `services/ctx_pipeline.py`, `services/unified_handler.py`
- **Domain pack**: `domain/pharma/pack.py`
- **Specs**: `specs/SPEC_001_*.md` (research engine), `specs/SPEC_002_*.md` (UX revamp)

## Deploy:
- Railway: push to `main` → auto-deploy
- DB: Railway PostgreSQL (DATABASE_URL env var)

## Health check:
```bash
python harness/measure.py
```
