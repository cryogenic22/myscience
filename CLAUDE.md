# Market Zero — Claude Code Instructions

## Quick Start
Read these before writing ANY code:
1. This file (architecture + conventions)
2. `.claude/rules/anti-slop.md` — 577 utilities cataloged, DO NOT duplicate
3. `.claude/rules/test-requirements.md` — testing patterns
4. `specs/SPEC_001_autonomous_research_engine.md` — CTX pipeline architecture
5. `specs/SPEC_002_frontend_ux_revamp.md` — UI design system

## Architecture

### Backend (Python/FastAPI)
- **Entry**: `api/app.py` → `create_app()` factory
- **Chat orchestration**: `api/routes/chat.py` — 8 intent handlers + optional UnifiedChatHandler
- **Dependencies**: `api/deps.py` — singleton services via FastAPI DI
- **Database**: PostgreSQL + pgvector via `db.py` (Database class)
- **Config**: `config.py` → `AppConfig` singleton (`config`)

### Services Layer
| Service | File | Purpose |
|---|---|---|
| HybridSearch | `services/search.py` | pgvector similarity search |
| GraphTraversal | `services/graph.py` | SQL-based graph traversal (recursive CTEs) |
| PharmaMetrics | `services/metrics.py` | Pre-computed KPIs from materialized views |
| QueryEngine | `services/query_engine.py` | GraphRAG orchestration |
| LLMSynthesizer | `services/llm.py` | LLM narrative synthesis with CTX context assembly |
| CTXContextBuilder | `services/ctx_context.py` | CTX L2 context formatting (ACTIVE in production) |
| CTXQueryPipeline | `services/ctx_pipeline.py` | Staged understand→retrieve→reason (opt-in via MZ_UNIFIED_HANDLER) |
| UnifiedChatHandler | `services/unified_handler.py` | Single handler replacing 8-handler fork (opt-in) |
| PharmaCorpusBuilder | `services/ctx_corpus.py` | Exports DB entities → CTX L2/L3 corpus |
| ConversationMemory | `services/conversation_memory.py` | Token-budgeted session memory (built, not yet wired) |
| AutonomousResearchAgent | `services/research_agent.py` | Background knowledge gap filler (built, not yet wired) |
| Telemetry | `services/telemetry.py` | CTX metrics persistence |

### Frontend (React 19 + TypeScript + Tailwind v4)
- **Design system**: `frontend/src/index.css` — CSS custom properties, NOT Tailwind utilities for colors
- **Fonts**: Fraunces (serif display) + DM Sans (body) — loaded in `index.html`
- **Color tokens**: `var(--color-ink)`, `var(--color-surface)`, `var(--color-accent)`, `var(--color-line)`
- **Components use inline styles with CSS variables** (not Tailwind color classes)

### Key Frontend Files
| File | Purpose |
|---|---|
| `pages/WorkspacePage.tsx` | Main workspace orchestrator (chat + canvas) |
| `pages/LandingPage.tsx` | Landing with serif hero, metrics strip, pillar grid |
| `components/chat/ChatPanel.tsx` | Chat input + message list (Claude-style, no bubbles for assistant) |
| `components/chat/NarrativeMessage.tsx` | Message rendering with citations |
| `components/canvas/CanvasPanel.tsx` | Right panel with tabs (Summary/Data/Entities/Context) |
| `components/DataCatalogPanel.tsx` | Data catalog with browse, audit, curation |
| `components/layout/TopBar.tsx` | macOS-style segmented nav |
| `components/layout/WorkspaceLayout.tsx` | Resizable split panel |

### Domain Pack
- `domain/pharma/pack.py` → `get_pharma_pack()` — 9 entity types, 12 link rules
- `domain/pharma/mention_normalizer.py` — Drug/company name cleaning (wired into entity resolver)
- Entity types: drug, company, trial, literature, event, therapeutic_area, mechanism, investigator, patent

### ETL Pipeline
- `integration/pipeline.py` — fetch → normalize → resolve → embed → store → cross-link
- `integration/entity_resolver.py` — 6-strategy cascade (exact → alias → fuzzy → embedding → LLM → auto-create)
- `integration/cross_linker.py` — Declarative link rules from domain pack
- Connectors in `connectors/` — 9 active (ClinicalTrials.gov, PubMed, FDA, SEC, etc.)
- Migrations in `schema/migrations/` (001-014)

## Critical Conventions

### DO
- **TDD**: Write tests FIRST, then implement. 180 tests currently passing.
- **Check anti-slop.md** before creating any new function/component/utility
- **Use CSS custom properties** in frontend (`var(--color-ink)`, not `text-slate-900`)
- **Use inline styles** for critical layout in frontend (not Tailwind utility classes)
- **Match patterns**: Read 2-3 sibling files before writing new code
- **One logical change per commit**: Conventional format (`feat:`, `fix:`, `chore:`)

### DON'T
- Don't create Tailwind color utility classes (`bg-slate-*`, `text-slate-*`) — use CSS variables
- Don't add `!important` dark mode overrides — use CSS custom properties that switch via `@theme`
- Don't call `useMemo` inside `.map()` loops (React hooks rules violation, caused production crash)
- Don't duplicate entity types — use domain pack `EntitySchema`
- Don't hardcode source names — use canonical names from `SourceType` enum

## CTX Integration Status

### ACTIVE in production:
- `CTXContextBuilder` (services/ctx_context.py) — assembles LLM context in CTX L2 format
- `ctx_evidence.pack_evidence()` — compresses evidence snippets
- A/B benchmarking in "both" mode (default) — logs compression metrics
- `/chat/ctx-benchmark` endpoint for dev testing

### OPT-IN (set MZ_UNIFIED_HANDLER=true):
- `UnifiedChatHandler` — routes through CTXQueryPipeline (hydration + entity graph + guard)
- `PharmaCorpusBuilder` — builds CTX corpus from database
- Falls back to legacy 8-handler fork on error

### NOT YET WIRED:
- `ConversationMemory` — token-budgeted memory with eviction (28 tests passing)
- `AutonomousResearchAgent` — background gap filler (27 tests passing)

## Testing
- **Framework**: pytest 8.3.4
- **Run**: `python -m pytest tests/ -v`
- **Fixtures**: `tests/conftest.py` (MockLLM, StubTool, make_*_result)
- **Mock DB**: `tests/test_ctx_corpus.py` has `MockDB` for DB-free tests
- **Current**: 180 passing, 0 unit failures
- **Coverage ratchet**: Never decrease test count

## Environment Variables
| Var | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | — | Railway PostgreSQL connection (preferred over MZ_DB_* vars) |
| `OPENAI_API_KEY` | — | Embeddings + LLM |
| `MZ_UNIFIED_HANDLER` | `false` | Enable CTX pipeline for chat |
| `MZ_CTX_MODE` | `both` | CTX context mode: "ctx", "legacy", "both" |
| `MZ_DB_PORT` | `5432` | Database port (local dev) |
| `PORT` | `8020` | HTTP server port |

## Deployment
- **Platform**: Railway (auto-deploys from `cryogenic22/myscience` main branch)
- **Build**: Nixpacks (Python 3.13 + Node 22)
- **Frontend**: `vite build` (no tsc, types verified locally)
- **Start**: `uvicorn api.app:create_app --factory`
- **Health**: `GET /health`

## Harness
- **Refresh**: `python harness/generate.py --refresh` (after major changes)
- **Health check**: `python harness/measure.py`
- **Onboarding**: `harness/onboarding-prompt.md`

## Specs
- `specs/SPEC_001_autonomous_research_engine.md` — CTX pipeline + research agent + memory
- `specs/SPEC_002_frontend_ux_revamp.md` — Chat+Canvas split panel UX redesign

## Codebase Map
@.claude/codebase-map.md

## Anti-Slop Rules
@.claude/rules/anti-slop.md

## Test Requirements
@.claude/rules/test-requirements.md
