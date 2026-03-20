# Market Zero — Session Onboarding

You are working on **Market Zero**, a pharma intelligence platform with GraphRAG, CTX-powered context management, and an autonomous research agent.

## Before you write ANY code:

1. Read `CLAUDE.md` — architecture, conventions, what's active vs opt-in
2. Read `.claude/rules/anti-slop.md` — **DO NOT create functions that already exist** (577 cataloged)
3. Read `.claude/rules/test-requirements.md` — testing patterns

## Critical rules:

### Backend
- **TDD**: Write tests FIRST. 180 tests currently passing. Never decrease.
- **CTX**: CTXContextBuilder is ACTIVE in production. UnifiedChatHandler is opt-in (MZ_UNIFIED_HANDLER=true).
- **Entity resolution**: Uses 6-strategy cascade with MentionNormalizer. Don't bypass normalization.
- **Telemetry**: CTX metrics persist to ctx_telemetry table (migration 014).

### Frontend
- **CSS variables ONLY** — use `var(--color-ink)`, NOT `text-slate-900`
- **Inline styles** for layout — NOT Tailwind utility classes for colors/borders
- **NO useMemo inside .map()** — caused production crash (React error #310)
- **NO !important dark mode overrides** — use CSS custom properties
- **Fonts**: Fraunces (display), DM Sans (body) — loaded in index.html
- **Build**: `vite build` only (no tsc -b in production)

## Key architecture decisions:
- Chat pipeline: 8 intent handlers in chat.py, optionally bypassed by UnifiedChatHandler
- Canvas: 4 tabs (Summary/Data/Entities/Context) for progressive disclosure
- Design system: CSS custom properties (--color-ink, --color-surface, --color-accent, --color-line)
- DB: Railway PostgreSQL with DATABASE_URL env var

## Not yet wired (built + tested, needs integration):
- ConversationMemory (services/conversation_memory.py) — 28 tests
- AutonomousResearchAgent (services/research_agent.py) — 27 tests

## Deploy:
Push to `main` → Railway auto-deploys. DB: Railway PostgreSQL.

## Health check:
```bash
python harness/measure.py
python -m pytest tests/ -q
```
