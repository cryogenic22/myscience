# SPEC-006: Market Zero UX Strategy & UI Redesign

> **Date**: 27 March 2026
> **Author**: Development Team
> **Approach**: Clean worktree branch → validate → replace main

---

## 1. Current State Assessment

### What Works
The landing page is polished (Fraunces serif, metrics strip, pillar grid). The workspace split panel renders correctly. Starter queries, chat input, and canvas empty state all function. 822K records, 810K graph links powering the backend.

### What Doesn't Work
1. **API routes intercepted by SPA** — navigating to /metrics, /catalog, etc. in the browser returns HTML instead of JSON. The catch-all middleware needs a proper fix.
2. **No consistent component system** — some components use Tailwind classes, some use inline styles, some use CSS variables. Three different styling approaches in one codebase.
3. **Graph/Data tabs inherit legacy styling** — GraphExplorer and parts of DataCatalog still use old Tailwind slate classes mapped through a compatibility CSS layer.
4. **Information density** — the workspace shows too little above the fold. Starter cards are large, empty canvas wastes space, no context about what the platform can do.
5. **No progressive onboarding** — new users see 6 starter queries and nothing else. No explanation of the data graph, no entity counts, no "what's new" signal.
6. **Search page is disconnected** — it opens in a separate page instead of being part of the workspace flow.

---

## 2. Design Principles

### P1: One styling method
Every component uses **inline styles with CSS custom properties**. No Tailwind color classes. No mixed approaches. One system, one source of truth.

### P2: Progressive disclosure
Show the most important thing first (answer to the question). Then offer depth (table, chart, graph, evidence). Never show everything at once.

### P3: Entity-centric navigation
Everything revolves around entities (drugs, companies, trials). Every page should be reachable from an entity. Entity → connections → evidence → analysis.

### P4: Data-dense but not cluttered
Pharma professionals expect data density. But density != clutter. Use typography hierarchy (display font for titles, body font for content, monospace for data), whitespace between sections, and collapse/expand for secondary content.

### P5: Trust signals
Every AI response should show: confidence score, data sources used, citation count, entity coverage. Users need to know what the system knows and doesn't know.

---

## 3. Page Architecture

### Landing → Workspace → Entity
```
Landing (/)
├── Hero + metrics + pillars
├── "Open Workspace" → /workspace
└── "Explore" → /workspace?tab=search

Workspace (/workspace)
├── TopBar: [Intelligence] [Search] [Graph] [Data]
├── Intelligence tab (default):
│   ├── Chat panel (left 45%)
│   │   ├── Conversation with AI
│   │   └── Input bar
│   └── Canvas panel (right 55%)
│       ├── Tabbed: Summary | Data | Entities | Context
│       └── Adapts to intent (dossier, compare, landscape...)
├── Search tab:
│   ├── Full-width search with entity results
│   └── Click result → opens entity profile
├── Graph tab:
│   ├── Force-directed graph canvas
│   ├── Edge legend + path finding
│   └── Node click → entity profile sidebar
└── Data tab:
    ├── Library mode (default): entity browser + dossier drawer
    └── Admin mode: health dashboard, audit trail, curation
```

### Key UX Flows

**Flow 1: Question → Answer → Explore**
1. User types "Compare semaglutide vs tirzepatide"
2. Chat shows narrative answer
3. Canvas shows comparison table + metrics
4. User clicks "semaglutide" in canvas → Graph tab opens with semaglutide neighborhood
5. User clicks "Novo Nordisk" in graph → entity profile drawer opens
6. User clicks "Ask in Chat" → returns to chat with "Tell me about Novo Nordisk"

**Flow 2: Browse → Discover → Analyze**
1. User opens Data tab → sees entity library
2. Filters by "drug" type, mechanism "GLP-1"
3. Clicks "semaglutide" → dossier drawer opens
4. Sees pipeline, connections, evidence
5. Clicks "Explore in Graph" → sees full connection map
6. Notices a competitor → clicks "Compare in Chat"

**Flow 3: Executive Dashboard**
1. User opens workspace → sees recent entities + conversation history
2. Quick metrics strip: portfolio strength, trial activity, competitive alerts
3. "What's changed" section: new trials, FDA actions, publication alerts
4. Click any alert → opens relevant entity + evidence

---

## 4. Implementation Plan

### Phase 1: Fix the Foundation (Week 1)
**Branch: `ui-v2`** — clean worktree, no legacy code

1. **New index.css** — single CSS file with:
   - Complete design token set (colors, typography, spacing, shadows)
   - Reusable CSS classes (.btn, .badge, .card, .data-table, .input)
   - Zero Tailwind utility dependencies for colors/spacing
   - Dark mode via CSS variables (complete, not partial)

2. **Component library** — 10 base components:
   - Button (primary, secondary, ghost, accent, icon)
   - Badge (status colors + entity type colors)
   - Card (surface, float, inset)
   - DataTable (sortable, paginated, exportable)
   - Input (text, search, textarea)
   - Drawer (right-slide, with backdrop)
   - Tabs (segmented control)
   - Skeleton (loading states)
   - Toast (notifications)
   - Avatar (entity type icon)

3. **Layout system** — 3 layout components:
   - AppShell (topbar + content area)
   - SplitPanel (resizable, persisted)
   - ScrollArea (hidden scrollbars, virtualized for large lists)

### Phase 2: Core Pages (Week 2)
Build the 4 workspace tabs:

1. **Intelligence tab** — Chat + Canvas split
   - ChatPanel: Claude-style messages, streaming, followups
   - CanvasPanel: Tabbed (Summary/Data/Entities/Context), adapts to intent
   - Every entity is clickable → navigates to Graph or opens drawer

2. **Search tab** — Full-width entity search
   - Search input with entity type filter pills
   - Results as LinkedIn-style profile cards
   - Click result → entity profile drawer (not a separate page)

3. **Graph tab** — Knowledge graph explorer
   - Auto-load demo on first visit
   - Edge legend, path finding, node details
   - Clean left rail with search + filters

4. **Data tab** — Entity library
   - Browse with phase badges, quality bars
   - Library/Admin split
   - Entity dossier drawer
   - Dataset profile cards

### Phase 3: Polish + Validate (Week 3)
1. Playwright visual regression suite (20+ screenshots)
2. Dark mode completion
3. Mobile responsive layout
4. Loading skeletons on all panels
5. Error boundaries with retry
6. Performance: virtualize long lists, lazy-load Graph tab

### Phase 4: Promote to Main (Week 3-4)
1. A/B test: serve ui-v2 to subset of users
2. Compare: task completion time, error rate, user feedback
3. If validated: merge ui-v2 → main, delete legacy components

---

## 5. Success Metrics

| Metric | Current | Target |
|---|---|---|
| Pages with consistent styling | 40% | 100% |
| JS errors per session | 0-2 | 0 |
| Time to first useful answer | ~15s | <10s |
| Entity drill-down clicks available | 30% of entities | 100% |
| Trust signals visible | Sometimes | Always |
| Dark mode coverage | 60% | 100% |
| Mobile usable | No | Yes |
| Lighthouse performance score | Unknown | >80 |

---

## 6. Technical Decisions

### Why a clean branch instead of incremental fixes
The current codebase has 3 styling systems (Tailwind utilities, inline styles, CSS variables), 2 layout approaches (Tailwind flex classes, inline flex styles), and a 660-line CSS compatibility layer mapping old classes to new tokens. Every fix risks breaking something else.

A clean branch lets us:
- Start with the correct CSS system (inline styles + CSS variables only)
- Build components once, correctly
- Test in isolation before replacing main
- Keep main deployable throughout

### Why not a new framework (Next.js, Remix, etc.)
The backend is FastAPI serving a React SPA. This works. React 19 + Vite is fast enough. Adding a framework adds complexity without solving the actual problems (styling consistency, information architecture, component quality).

### Why inline styles over Tailwind
Tailwind v4's utility class generation has been unreliable in our production builds (px-6 not applying, color classes requiring a compatibility CSS layer). Inline styles are:
- Guaranteed to apply (no build step dependency)
- Debuggable (visible in browser DevTools)
- Composable (spread operator for merging)
- The same approach used by Apple, Linear, Vercel

---

## 7. What Makes Market Zero Successful

### The product is NOT the UI
Market Zero's value is the **connected pharma knowledge graph**: 822K records, 810K entity links, 10 data sources, automated curation, CTX-powered context assembly. No competitor has this data density with this quality.

### The UI is the delivery mechanism
The UI should make the data graph **accessible** to pharma executives who think in entities (drugs, companies, trials) and questions (who competes with whom, what's in Phase 3, where are the gaps).

### Three things the UI must do well
1. **Answer questions accurately** — chat grounded in real data, not hallucination
2. **Show connections** — every entity links to related entities, evidence, and analysis
3. **Build trust** — confidence scores, citation counts, data freshness, source attribution

Everything else (animations, dark mode, mobile) is secondary. Get these three right and the product works.
