# SPEC-002: Frontend UX Revamp

> **Status**: Draft
> **Priority**: P0
> **Source inspiration**: Scriptiva SCA (design system, accessibility, components) + Intelligent Enterprise (canvas, multi-view, AI patterns)

---

## Current State Assessment

The Market Zero frontend is **feature-rich but architecturally stressed**:
- 3 massive files (ChatMessage 900+, GraphExplorer 37KB, DataCatalogPanel 65KB)
- 15+ useState hooks in IntelligencePage (unmaintainable)
- No toast system, no error boundaries, no loading skeletons
- Dark mode half-implemented (50+ CSS overrides)
- No accessibility (no ARIA, no focus traps, no keyboard nav)
- Flat 3-page routing (landing → search → intelligence)
- Chat responses render data but layout breaks on wide tables and garbled text

---

## What to Steal

### From Scriptiva SCA (Design System + Polish)
| Pattern | What it does | Priority |
|---|---|---|
| **Command Palette** (Cmd+K) | Global search across entities, queries, pages | High |
| **Toast system** | Context-based toast with 4 variants, auto-dismiss, action buttons | High |
| **AlertDialog** | Focus-trapped confirmation dialogs | High |
| **Skeleton loaders** | Pulse animation loading states (text, card, table variants) | High |
| **DataTable** | Sort, pagination, selection, striped rows, fixed headers | High |
| **Badge system** | 10 color variants, semantic status badges | Medium |
| **Progress component** | Linear + circular with color variants | Medium |
| **SearchableSelect** | Multi-select with search, descriptions, keyboard nav | Medium |
| **Focus Mode** | Hide sidebar for immersive workspace (preserves state) | Medium |
| **Keyboard shortcuts** | Global + workspace-specific with help modal | Medium |
| **Optimistic saves** | Immediate feedback before server confirmation | Low |

### From Intelligent Enterprise (AI + Canvas + Navigation)
| Pattern | What it does | Priority |
|---|---|---|
| **Split-panel canvas** | Chat on left + live data preview on right | Critical |
| **Multi-view navigator** | 6 views of same data (map, catalog, tree, matrix, table, graph) | High |
| **Glass-morphism nav** | Frosted navbar with backdrop blur | Medium |
| **Force-directed graph** | D3 knowledge graph with analytics sidebar | High |
| **Process visualization** | Before/after comparison flows | Medium |
| **Role-based rendering** | Feature gating by user role | Low |
| **Smooth scroll (Lenis)** | Smooth page scrolling | Low |
| **Progressive onboarding** | Welcome tour, page tips, shortcut panel | Medium |
| **Search palette** | Fuse.js fuzzy search with weighted fields | High |
| **Segment-based AI prompting** | Different prompts per conversation phase | Medium |
| **Guard + re-hydration UI** | Show confidence signal, trigger re-query | High |

---

## Revamp Architecture

### New Layout: Intelligence Workspace

```
┌─────────────────────────────────────────────────────────────────┐
│  TopBar (56px, glass)                                           │
│  [Logo] [Cmd+K search] [breadcrumb] [confidence] [theme] [user]│
├──────┬──────────────────────────────────────────────────────────┤
│      │                                                          │
│  R   │  MAIN WORKSPACE (flex-1)                                 │
│  A   │                                                          │
│  I   │  ┌──────────────────────┬───────────────────────────┐   │
│  L   │  │                      │                           │   │
│      │  │  CHAT PANEL          │  CANVAS PANEL             │   │
│  56  │  │  (resizable, 40-60%) │  (resizable, 40-60%)      │   │
│  px  │  │                      │                           │   │
│      │  │  Messages            │  Live data preview:       │   │
│  I   │  │  + Input             │  • Entity dossier card    │   │
│  c   │  │  + Suggestions       │  • Comparison table       │   │
│  o   │  │                      │  • Landscape chart        │   │
│  n   │  │                      │  • Graph neighborhood     │   │
│  s   │  │                      │  • Pipeline waterfall     │   │
│      │  │                      │  • Evidence timeline      │   │
│      │  └──────────────────────┴───────────────────────────┘   │
│      │                                                          │
│      │  BOTTOM BAR (optional: entity breadcrumb trail)          │
├──────┴──────────────────────────────────────────────────────────┤
│  Status bar (24px): DB status • entities count • last refresh   │
└─────────────────────────────────────────────────────────────────┘
```

### Key Changes

1. **Split-panel chat + canvas** — The single biggest UX upgrade. Chat on the left, live structured data on the right. No more interleaved narrative + cards + tables + charts in one scroll.

2. **TopBar replaces WorkspaceRail** — Move from vertical icon rail to horizontal glass-morphism bar. Cmd+K search prominent. Confidence indicator shows guard status.

3. **Canvas panel renders structured data** — Tables, charts, entity cards, graph neighborhoods all render in the canvas, not inline in chat messages. Chat stays clean (narrative only).

4. **Resizable panels** — User drags divider to resize chat vs canvas. Persisted in localStorage.

5. **Entity breadcrumb trail** — As user explores entities, breadcrumb shows: `GLP-1 > semaglutide > Novo Nordisk > Phase 3 trials`. Click to go back.

---

## Implementation Phases

### Phase A: Design System Foundation (Day 1-2)

Build the shared component library from Scriptiva's patterns.

| Component | Source | Notes |
|---|---|---|
| `ui/Button.tsx` | Scriptiva | 4 variants: primary, secondary, ghost, danger + sizes |
| `ui/Badge.tsx` | Scriptiva | 10 color variants + sm/md sizes |
| `ui/Card.tsx` | Scriptiva | Compound: Card + CardHeader + CardBody |
| `ui/Toast.tsx` | Scriptiva | Context-based, 4 variants, auto-dismiss |
| `ui/Skeleton.tsx` | Scriptiva | text, title, avatar, card, table variants |
| `ui/AlertDialog.tsx` | Scriptiva | Focus-trapped, aria-labeled |
| `ui/DataTable.tsx` | Scriptiva | Sort + paginate + select + fixed headers |
| `ui/Progress.tsx` | Scriptiva | Linear + circular, 4 colors |
| `ui/Tabs.tsx` | Scriptiva | Segmented pill-style tabs |
| `ui/Popover.tsx` | Scriptiva | Floating menus with side/align config |

**Quality gate**: All components have TypeScript props, ARIA labels, keyboard support.

### Phase B: Layout Restructure (Day 2-3)

Replace the current flat routing + WorkspaceRail with the new layout.

1. **TopBar component** — Glass-morphism, search trigger, confidence indicator, theme toggle
2. **WorkspaceLayout component** — Split-panel with resizable divider
3. **CommandPalette** — Cmd+K search across entities, queries, pages (Fuse.js fuzzy)
4. **Remove WorkspaceRail** — Replaced by TopBar + keyboard shortcuts
5. **React Router integration** — Replace manual page state with proper routes

**Routes**:
```
/                    → Landing page
/workspace           → Intelligence workspace (chat + canvas)
/workspace/search    → Search with results
/workspace/graph     → Full graph explorer
/workspace/catalog   → Data catalog
/settings            → User preferences
```

### Phase C: Chat + Canvas Split (Day 3-5)

The core UX transformation.

#### Chat Panel (Left)
- **Clean narrative only** — No inline tables, charts, or entity cards
- **Citation markers** — [1] [2] inline, hover shows tooltip
- **Confidence badge** — Per-response confidence from reasoning stage
- **Guard indicator** — Warning icon if response flagged by ContextGuard
- **Follow-up chips** — Grounded suggestions from data
- **Streaming** — Real token streaming (not chunked)

#### Canvas Panel (Right)
Renders structured data from the response. Content type adapts to intent:

| Intent | Canvas Content |
|---|---|
| **Dossier** | Entity card + properties + connections graph mini + evidence timeline |
| **Compare** | Side-by-side table + radar chart + shared connections |
| **Landscape** | DataTable + bar chart + HHI gauge + top companies list |
| **Pipeline** | Waterfall chart (P1→P4) + DataTable + maturity indicator |
| **Portfolio** | Company card + KPI tiles + drug list + trial timeline |
| **Evidence** | Evidence cards grid + source breakdown donut + freshness distribution |
| **Graph** | Interactive mini-graph with force layout + neighbor list |

#### Panel Sync
- Chat sends a question → backend returns `{narrative, data, table_data, visualizations}`
- Chat panel renders `narrative` only
- Canvas panel renders `data` + `table_data` + `visualizations`
- Canvas updates in real-time as streaming completes

### Phase D: Data Visualization Upgrade (Day 5-6)

Replace Recharts-only charts with richer visualizations.

1. **Entity Dossier Card** — Rich card with properties, connections, quality score, freshness
2. **Comparison Radar** — Spider chart comparing entities across dimensions
3. **Pipeline Waterfall** — Phase progression visualization (P1→P2→P3→P4→Approved)
4. **Evidence Timeline** — Chronological evidence display with source icons
5. **Confidence Gauge** — Visual confidence indicator (0-100%)
6. **HHI Concentration Bar** — Visual market concentration indicator
7. **Graph Mini (D3)** — Force-directed mini-graph in canvas (from IE's ForceGraph pattern)

### Phase E: Search & Discovery (Day 6-7)

1. **Command Palette (Cmd+K)** — Global entity search with fuzzy matching
2. **Entity Autocomplete** — In chat input, show entity suggestions with type badges
3. **Search Page** — Full search with filters, results, and graph inspector (from current SearchPage, cleaned up)
4. **Recent entities** — Track recently viewed entities in localStorage

### Phase F: Polish & Accessibility (Day 7-8)

1. **Loading skeletons** — For chat, canvas, catalog, graph
2. **Error boundaries** — React error boundaries with retry
3. **Toast notifications** — API errors, save confirmations, guard warnings
4. **Keyboard shortcuts** — Help modal (Shift+?), workspace shortcuts
5. **Focus management** — Trap focus in modals/drawers
6. **ARIA labels** — All interactive elements
7. **Dark mode completion** — Design-token-driven, not CSS override
8. **Responsive layout** — Mobile: canvas collapses below chat

---

## Component File Structure

```
frontend/src/
├── components/
│   ├── ui/                      # Design system primitives
│   │   ├── Button.tsx
│   │   ├── Badge.tsx
│   │   ├── Card.tsx
│   │   ├── Toast.tsx
│   │   ├── Skeleton.tsx
│   │   ├── AlertDialog.tsx
│   │   ├── DataTable.tsx
│   │   ├── Progress.tsx
│   │   ├── Tabs.tsx
│   │   ├── Popover.tsx
│   │   ├── Drawer.tsx          # existing
│   │   └── Pill.tsx            # existing
│   │
│   ├── layout/                  # App chrome
│   │   ├── TopBar.tsx
│   │   ├── WorkspaceLayout.tsx  # split panel
│   │   ├── ResizableDivider.tsx
│   │   ├── StatusBar.tsx
│   │   └── CommandPalette.tsx
│   │
│   ├── chat/                    # Chat panel
│   │   ├── ChatPanel.tsx        # container
│   │   ├── ChatMessage.tsx      # narrative only (slimmed)
│   │   ├── ChatInput.tsx        # input bar + autocomplete
│   │   ├── CitationTooltip.tsx
│   │   ├── ConfidenceBadge.tsx
│   │   └── FollowupChips.tsx
│   │
│   ├── canvas/                  # Canvas panel
│   │   ├── CanvasPanel.tsx      # container + intent router
│   │   ├── DossierCanvas.tsx    # entity profile view
│   │   ├── CompareCanvas.tsx    # side-by-side view
│   │   ├── LandscapeCanvas.tsx  # competitive segments view
│   │   ├── PipelineCanvas.tsx   # phase waterfall view
│   │   ├── PortfolioCanvas.tsx  # company overview view
│   │   ├── EvidenceCanvas.tsx   # evidence grid view
│   │   └── GraphCanvas.tsx      # mini graph view
│   │
│   ├── visualization/           # Charts & graphs
│   │   ├── BarChart.tsx
│   │   ├── PieChart.tsx
│   │   ├── RadarChart.tsx
│   │   ├── WaterfallChart.tsx
│   │   ├── ForceGraph.tsx       # D3 mini graph
│   │   ├── ConfidenceGauge.tsx
│   │   └── EvidenceTimeline.tsx
│   │
│   ├── entity/                  # Entity display
│   │   ├── EntityCard.tsx       # existing, cleaned
│   │   ├── EvidenceCard.tsx     # existing, cleaned
│   │   └── MetricCard.tsx       # existing, cleaned
│   │
│   ├── search/                  # Search page
│   │   ├── SearchPanel.tsx
│   │   ├── ResultCard.tsx
│   │   └── ResultInspector.tsx
│   │
│   ├── catalog/                 # Data catalog (split from 65KB monolith)
│   │   ├── CatalogPanel.tsx     # overview
│   │   ├── EntityBrowser.tsx    # browse + search
│   │   ├── EntityDetail.tsx     # single entity view
│   │   ├── QualityRules.tsx     # quality dashboard
│   │   └── HITLQueue.tsx        # human review queue
│   │
│   └── graph/                   # Graph explorer (split from 37KB monolith)
│       ├── GraphExplorer.tsx    # container
│       ├── GraphCanvas.tsx      # D3 rendering
│       ├── GraphFilters.tsx
│       ├── GraphSidebar.tsx     # node details
│       └── GraphObjectives.tsx
│
├── hooks/
│   ├── useHealthStats.ts        # existing
│   ├── useTheme.ts              # existing
│   ├── useAnimatedNumber.ts     # existing
│   ├── useToast.ts              # new
│   ├── useCommandPalette.ts     # new
│   ├── useKeyboardShortcuts.ts  # new
│   ├── useResizablePanel.ts     # new
│   └── useEntityAutocomplete.ts # new
│
├── providers/
│   ├── ToastProvider.tsx
│   └── WorkspaceProvider.tsx    # global workspace state
│
├── pages/
│   ├── LandingPage.tsx          # existing, cleaned
│   ├── WorkspacePage.tsx        # new: chat + canvas
│   ├── SearchPage.tsx           # existing, refactored
│   ├── GraphPage.tsx            # existing GraphExplorer, standalone
│   └── CatalogPage.tsx          # existing DataCatalogPanel, standalone
│
├── lib/
│   ├── api.ts                   # existing, cleaned
│   ├── cn.ts                    # classname utility
│   └── constants.ts             # design tokens, entity colors, etc.
│
├── App.tsx                      # Router setup
├── main.tsx
└── index.css                    # Design tokens + global styles
```

---

## Success Criteria

| Metric | Current | Target |
|---|---|---|
| **Chat readability** | Narrative + data + charts mixed in scroll | Clean narrative left, structured data right |
| **Component file size** | 65KB (DataCatalog), 37KB (GraphExplorer) | No file > 300 lines |
| **Loading states** | None (blank or flash) | Skeleton loaders on all panels |
| **Error handling** | Console.error, raw messages | Toast notifications, retry buttons |
| **Accessibility** | None | ARIA labels, keyboard nav, focus traps |
| **Dark mode** | 50+ CSS overrides | Design-token-driven, complete coverage |
| **State management** | 15+ useState in one component | WorkspaceProvider + scoped state |
| **Search** | Type-and-submit only | Cmd+K global search + entity autocomplete |
| **Mobile** | Broken | Canvas stacks below chat |

---

## Implementation Priority

Start with Phase C (chat + canvas split) — it's the highest-impact UX change.
Then Phase A (design system) to make everything consistent.
Then Phase B (layout) + D (viz) + E (search) + F (polish).

**Estimated total: 8 working days.**
