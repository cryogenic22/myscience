# SPEC-004: UI/UX Upgrade — From Functional to Exceptional

> **Status**: Draft
> **Priority**: P0
> **Dependencies**: SPEC-002 (design system established), SPEC-003 (intelligence feed)
> **Date**: 2026-03-28
> **Method**: Live site audit (https://myscience-production.up.railway.app/) + source code review of all frontend components

---

## Executive Assessment

Market Zero's frontend has successfully implemented the SPEC-002 chat+canvas split panel architecture and delivers genuinely impressive intelligence — the knowledge graph query responses are rich, the entity resolution is sharp, and the data canvas provides real analytical value. The platform is functional and the data story is compelling.

However, there is a significant gap between **the power of the backend intelligence** and **how effortlessly users can consume it**. The system has ~785K records, ~772K graph links, 5.3K clinical trials, and 1.5K companies — yet the UI sometimes makes this treasure trove feel harder to navigate than it should. The intelligence is there; the consumption experience needs to match.

This spec addresses every friction point found during the live audit and code review, organised into actionable upgrades.

---

## Audit Findings: What's Working

Before addressing problems, it's worth recording what the platform gets right — these are strengths to preserve and build upon.

**Landing page**: The Fraunces serif hero ("The intelligence layer pharma strategy needs") is distinctive and signals premium positioning. The animated metrics strip (784.6K records, 772.4K links, 5.3K trials, 1.5K companies) immediately communicates scale. The four-pillar grid (Ontology Core, GraphRAG Intelligence, Integrated Data Fabric, Agentic AI Ready) articulates the value proposition clearly. The design tone is calm, confident, and editorial — exactly right for a pharma intelligence tool.

**Chat+Canvas split**: The core architecture works well. Asking "What is the GLP-1 competitive landscape?" produces a narrative with bolded entities, inline metrics, and follow-up suggestion pills on the left, with a structured data table (mechanism, therapeutic area, drugs, trials, active trials, pipeline score) on the right. The canvas correctly activates Summary/Data/Entities tabs based on response content.

**Entity dossier**: Asking "Tell me about semaglutide" triggers a rich response — phase distribution bar chart, trial status donut chart, entity list with connection counts and "View in Graph →" links, and a "Visualise →" button for deeper exploration. The breadcrumb trail in the top bar (Oral semaglutide › Ozempic › New use of semaglutide…) provides spatial orientation.

**Search experience**: The Google-style search page with entity type filters (Drugs, Trials, Literature, Companies, Therapeutic Areas), Cards/Grid/List view modes, quality scores, and a detail panel with "Ask in Chat" / "Explore in Graph" / "View Source" actions is well-conceived and functional.

**Graph Explorer**: Entity Neighbourhood with force-directed visualisation, exploration objectives (Entity Neighbourhood, Trial Evidence Map, Portfolio Network, Mechanism Landscape), hop depth control, graph summary stats, and high-confidence neighbour listing all work.

**Data Catalog**: Entity Library with type tabs showing counts (Drugs 1,706 / Companies 1,461 / Trials 5,307), top-by-pipeline-score featured cards, sort controls, pagination, and admin/refresh controls.

---

## Audit Findings: Critical Gaps

### G1. First-Time User Disorientation

**Problem**: A new user landing in the workspace sees the "Pharma Intelligence" hero with 6 suggestion pills and an empty Data Canvas placeholder. There is no indication of what the system knows, what it's good at, or what they should try first. The suggestion pills are helpful but don't convey the depth of the platform.

**Evidence**: The workspace empty state shows "Tables, charts, and entities will appear here as you explore" — this is passive and generic. Compare this to the landing page which communicates scale (784.6K records) but that context is lost once you enter the workspace.

**Impact**: Users with access to 785K pharma records don't know how rich the system is until they happen to ask the right question.

### G2. Canvas Staleness and Empty State

**Problem**: The Data Canvas shows stale content from the previous query when the user starts typing a new one. If a response has no structured data, the canvas retains whatever was there before. The "Data Canvas — Tables, charts, and entities will appear here as you explore" empty state returns inconsistently.

**Evidence (code)**: `WorkspacePage.tsx` only updates canvas state when the response contains structured data (line ~160). If the LLM returns narrative-only, the canvas retains stale state from the previous query.

**Impact**: Users see data from a previous question alongside narrative from a different question — this is actively misleading.

### G3. No Loading/Progress Feedback During Queries

**Problem**: After submitting a query, there is a spinner but no indication of what's happening. The system is doing entity resolution, graph traversal, metrics computation, and LLM synthesis — but the user sees nothing until text starts streaming. For complex landscape queries this can be 5-8 seconds of silence.

**Evidence (code)**: `ChatPanel.tsx` sets `isLoading` to true and shows a spinner, but there's no staged progress indicator. The `onStatus` callback in `WorkspacePage.tsx` receives status updates from the backend but doesn't surface them to the user.

**Impact**: Users don't know if the system is working, stuck, or has failed. They may re-submit, creating duplicate requests.

### G4. Citation and Evidence Accessibility

**Problem**: Citation markers ([1], [2], [3]) in narrative text show evidence on hover only — no keyboard or touch support. The tooltip is positioned `bottom-full` and gets cut off when citations appear in the lower third of the viewport. The literal string "[metrics]" appears inline in some responses (visible in the GLP-1 landscape response).

**Evidence (live)**: The GLP-1 competitive landscape response shows "capturing 38.9% of the market share [metrics]" — the `[metrics]` tag is a literal string leak from the LLM prompt, not a rendered citation.

**Impact**: Evidence provenance — the platform's key differentiator — is hard to access for many users. The "[metrics]" leak undermines credibility.

### G5. Data Table Limitations

**Problem**: Canvas data tables lack sorting, column resizing, and meaningful interactivity. The Competitive Landscape table shows mechanism, therapeutic area, drugs, trials, active trials, pipeline score — but clicking a row does nothing. There's no way to drill from a table row into the entity it represents.

**Evidence (live)**: Clicking any row in the competitive landscape table has no effect. The table header columns are not sortable. CSV export exists but is the only interaction.

**Impact**: The structured data in the canvas is read-only and disconnected from the intelligence layer. Users can see the data but can't explore from it.

### G6. Graph Explorer Isolation

**Problem**: The Graph Explorer is a separate tab with its own search — it's disconnected from the chat conversation. Clicking "View in Graph →" from a canvas entity card does navigate there, but the graph always starts from a full entity neighbourhood view with all node types visible, which can be overwhelming (51 entities, 50 relationships in a single view).

**Evidence (live)**: The graph auto-loaded with an anchor entity containing primarily literature nodes (all green, "EVIDENCE_FOR" links). The single-colour, single-type display makes it hard to distinguish entity types at a glance. Only one legend entry ("EVIDENCE FOR") was visible despite 51 entities.

**Impact**: The graph — potentially the platform's most visually impressive feature — feels like a technical tool rather than an exploration surface. Non-technical pharma users won't engage with it.

### G7. Mobile and Responsive Gaps

**Problem**: The workspace assumes desktop-width (1280px+). The split panel, data tables, and graph all break or become unusable below ~900px. TopBar icons are 13px — well below the 44px recommended touch target.

**Evidence (code)**: `WorkspaceLayout.tsx` line ~119 uses 50/50 split on mobile with no resizable option. TopBar tab icons use `hidden sm:inline` to hide labels, leaving icon-only tabs that are too small to tap.

**Impact**: The platform is inaccessible on tablets and phones, which is where many pharma executives first encounter tools (in meetings, during conferences, on commute).

### G8. Dark Mode Incomplete

**Problem**: Dark mode toggle exists in the TopBar but the implementation is half-done. Border colours (`--color-line`, `--color-line-2`) in dark mode use identical values to light mode. Recharts chart colours are hardcoded (not theme-aware). There are 130+ lines of legacy Tailwind dark mode overrides in `index.css`.

**Evidence (code)**: `index.css` lines 81-82 set dark mode `--color-line` to the same value as light mode. `CanvasPanel.tsx` line 34 defines `CHART_COLORS` as a static array with no dark mode variants.

**Impact**: Dark mode — increasingly standard and expected — looks broken. Users who toggle it may assume the platform is buggy.

### G9. Data Catalog Performance

**Problem**: The Data Quality tab in the Data Catalog caused a browser hang during audit (Chrome timeout after 60s). The component has 11+ useState hooks tracking parallel loading states that can desynchronise.

**Evidence (code)**: `DataCatalogPanel.tsx` has 11 useState + 3 useEffect hooks with 5 separate loading states (`loading`, `refreshing`, `browseLoading`, `detailLoading`, `dsProfileLoading`). The "Data Quality" tab appears to trigger heavy API calls that block the main thread.

**Impact**: A power user exploring data quality can lock up their browser. This is the worst possible experience for the admin/data steward persona.

### G10. Accessibility Gaps

**Problem**: No ARIA roles on tabs (`role="tab"`, `aria-selected`), no skip-to-content links, no focus management in modals/drawers, citation tooltips not keyboard-accessible, chart legends too small (8px icon), no `prefers-reduced-motion` respect for animations.

**Evidence (code)**: TopBar tabs are plain `<button>` elements without `role="tab"`. CanvasPanel tabs use generic buttons without `aria-selected`. WorkspaceLayout divider has no ARIA label. LandingPage uses manual `onMouseEnter`/`onMouseLeave` instead of CSS `:hover`.

**Impact**: The platform fails basic WCAG 2.1 Level A requirements. Pharma enterprises typically require AA compliance for procurement.

---

## Upgrade Specification

### U1. Intelligent Workspace Onboarding

**Goal**: New users immediately understand the platform's depth and know what to try.

**Design**:

Replace the current "Pharma Intelligence" hero empty state with a **contextual onboarding panel** that shows:

```
┌─────────────────────────────────────────────────────┐
│                                                     │
│  ✦  Your Knowledge Graph                            │
│                                                     │
│  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐           │
│  │1,706 │  │5,307 │  │1,461 │  │  25  │           │
│  │Drugs │  │Trials│  │Cos.  │  │Mech. │           │
│  └──────┘  └──────┘  └──────┘  └──────┘           │
│                                                     │
│  Try asking about:                                  │
│                                                     │
│  ┌─────────────────────────┐  ┌────────────────┐   │
│  │ 🏥 GLP-1 competitive    │  │ 💊 Semaglutide  │   │
│  │    landscape             │  │    dossier      │   │
│  └─────────────────────────┘  └────────────────┘   │
│  ┌─────────────────────────┐  ┌────────────────┐   │
│  │ 📊 Compare semaglutide  │  │ 🧬 SGLT2 drugs  │   │
│  │    vs tirzepatide        │  │    in heart     │   │
│  │                          │  │    failure      │   │
│  └─────────────────────────┘  └────────────────┘   │
│                                                     │
│  Recently active: Novo Nordisk, Eli Lilly,          │
│  AstraZeneca (updated 2h ago)                       │
│                                                     │
└─────────────────────────────────────────────────────┘
```

**Implementation**:
- Fetch entity counts from `/api/catalog/stats` (already exists) to populate the metrics mini-strip
- Show 4-6 suggestion cards with intent-type icons and descriptive labels
- "Recently active" line fetches from most recent entity updates (new API: `GET /api/entities/recent-activity`)
- First-time users see this; returning users see their conversation history with a "New conversation" button
- Animate in with subtle fade (respecting `prefers-reduced-motion`)

**Files**: New `components/chat/WorkspaceOnboarding.tsx`, modify `WorkspacePage.tsx`

### U2. Canvas State Management Fix

**Goal**: Canvas always shows data relevant to the current response, never stale data.

**Design**:
- When a new query is submitted, **immediately clear the canvas** and show a skeleton loader
- If the response contains no structured data, show a contextual empty state: "This response is narrative-only. Ask about specific drugs, trials, or mechanisms to see structured data."
- If the response streams, populate canvas progressively: table first, then charts, then entities

**Implementation**:
```typescript
// In WorkspacePage.tsx — on submit
const handleSend = () => {
  // Clear canvas immediately
  setCanvasData(null);
  setTableData(null);
  setVisualizations(null);
  setConfidence(null);
  setCanvasState('loading'); // new state: 'loading' | 'populated' | 'empty'

  // After response completes
  onDone: (response) => {
    if (response.data || response.table_data || response.visualizations) {
      setCanvasState('populated');
    } else {
      setCanvasState('empty');
    }
  }
};
```

**Files**: Modify `WorkspacePage.tsx`, modify `CanvasPanel.tsx` to accept a `state` prop

### U3. Query Progress Indicator

**Goal**: Users see what the system is doing during the 3-8 second query processing window.

**Design**:

Replace the generic spinner with a **staged progress bar** that reflects the actual CTX pipeline stages:

```
┌──────────────────────────────────────────────┐
│  Understanding query...                       │  ← Stage 1
│  ████░░░░░░░░░░░░░░░░░░░░░░░░░░  15%        │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│  Retrieving evidence from 3 sources...        │  ← Stage 2
│  ██████████████░░░░░░░░░░░░░░░░  50%         │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│  Reasoning over 47 entities...                │  ← Stage 3
│  ████████████████████████░░░░░░  80%         │
└──────────────────────────────────────────────┘
```

**Implementation**:
- The backend already sends status events during streaming via the `onStatus` callback
- Surface these status strings in a compact progress bar below the chat input
- Use CSS transition for smooth progress animation
- Hide when streaming begins (text starts arriving)

**Files**: New `components/chat/QueryProgress.tsx`, modify `ChatPanel.tsx` and `WorkspacePage.tsx`

### U4. Citation System Overhaul

**Goal**: Evidence provenance is accessible via hover, click, keyboard, and touch.

**Design**:

Replace hover-only citation tooltips with a **click-to-expand citation panel**:

```
Narrative text with a citation marker [1] that when clicked...

┌──────────────────────────────────────────────┐
│  [1] ClinicalTrials.gov — NCT04563208        │
│  "Phase 3 study of oral semaglutide in..."   │
│  Registered: 2021-03-15 · Status: Completed  │
│  [View source ↗]  [Copy citation]             │
└──────────────────────────────────────────────┘
```

**Implementation**:
- Citation markers become `<button>` elements with `aria-expanded` state
- Click toggles an inline citation card (not a tooltip — avoids viewport clipping)
- Keyboard: focusable, Enter/Space to toggle, Escape to close
- Touch: tap to toggle (no hover dependency)
- Fix the `[metrics]` string leak: add a post-processing step in `NarrativeMessage.tsx` that strips or converts `[metrics]`, `[data]`, `[evidence]` tags before rendering
- Memoize `parseRichText` with `useMemo` to prevent re-parsing on every render

**Files**: Rewrite `NarrativeMessage.tsx` citation section, add `components/chat/CitationCard.tsx`

### U5. Interactive Data Tables

**Goal**: Canvas data tables become an exploration surface, not just a display.

**Design**:

Upgrade the canvas DataTable with:

| Feature | Behaviour |
|---------|-----------|
| **Sortable columns** | Click header to sort asc/desc. Visual indicator (▲/▼) |
| **Clickable rows** | Click a row to navigate: entity rows → dossier in chat, mechanism rows → landscape view |
| **Column highlighting** | Hover a column header highlights the entire column |
| **Inline sparklines** | Numeric columns optionally show a tiny sparkline for context |
| **Sticky headers** | Table header stays visible when scrolling long tables |
| **Responsive overflow** | Horizontal scroll with shadow indicators when table exceeds width |

**Implementation**:
- Extract `DataTable` from CanvasPanel into standalone `components/ui/DataTable.tsx`
- Add `sortable` prop per column definition
- Add `onRowClick` callback that emits the entity associated with that row
- Use CSS `position: sticky` for headers
- Use `overflow-x: auto` with `scroll-shadow` CSS technique for horizontal overflow

**Files**: New `components/ui/DataTable.tsx`, modify `CanvasPanel.tsx` to use it

### U6. Graph Explorer Polish

**Goal**: The graph becomes visually rich and approachable for non-technical users.

**Design**:

| Improvement | Detail |
|-------------|--------|
| **Multi-colour entity types** | Each entity type gets a distinct colour: drugs (blue), companies (amber), trials (green), literature (grey), mechanisms (purple), therapeutic areas (teal) |
| **Node size by importance** | Node radius proportional to connection count or pipeline score |
| **Rich legend** | Colour-coded legend showing all visible entity types + link types |
| **Node hover card** | Hovering a node shows a compact card: name, type, connection count, quality score |
| **Click-to-focus** | Clicking a node re-centres the graph on that entity and fetches its neighbourhood |
| **Smooth zoom** | Scroll-to-zoom with smooth transition. Double-click to zoom into a cluster |
| **Filter chips** | Quick-toggle entity types on/off: `[● Drugs] [● Companies] [● Trials] [○ Literature]` |
| **Mini-map** | Small overview in bottom-right showing full graph extent with viewport indicator |

**Implementation**:
- Define entity type → colour mapping in design tokens (`index.css`):
  ```css
  :root {
      --color-entity-drug: #3B82F6;
      --color-entity-company: #F59E0B;
      --color-entity-trial: #10B981;
      --color-entity-literature: #6B7280;
      --color-entity-mechanism: #8B5CF6;
      --color-entity-therapeutic-area: #14B8A6;
      --color-entity-investigator: #EC4899;
      --color-entity-patent: #EF4444;
      --color-entity-event: #F97316;
  }
  ```
- Graph component already uses D3 force layout — extend with multi-colour fill based on entity type
- Add hover card as absolutely-positioned div following mouse position
- Mini-map: render a 120×80px SVG in bottom-right with all node positions scaled down

**Files**: Modify graph rendering component (GraphExplorer area of `WorkspacePage.tsx` or its sub-components), add `components/graph/NodeHoverCard.tsx`, add `components/graph/GraphMiniMap.tsx`, update `index.css`

### U7. Responsive Layout

**Goal**: Platform is usable on tablet (768px) and functional on mobile (375px).

**Design**:

| Breakpoint | Layout |
|------------|--------|
| **≥1024px** (desktop) | Split panel: chat left, canvas right, resizable divider |
| **768–1023px** (tablet) | Stacked: chat full-width, canvas slides up from bottom as a sheet |
| **<768px** (mobile) | Chat full-screen, canvas accessed via bottom tab bar. Graph and Catalog available as separate views |

**Implementation**:
- `WorkspaceLayout.tsx`: Add CSS media queries for breakpoints
- Below 1024px: Replace side-by-side with stacked layout. Canvas becomes a bottom sheet (70% viewport height, swipeable)
- TopBar: Stack tabs into a bottom navigation bar on mobile. Increase touch targets to 48px minimum
- Data tables: Enable horizontal scroll with freeze-first-column on narrow screens
- Charts: Use Recharts `aspect` prop to maintain readable proportions

**Files**: Modify `WorkspaceLayout.tsx`, `TopBar.tsx`, `CanvasPanel.tsx`, add `components/ui/BottomSheet.tsx`

### U8. Dark Mode Completion

**Goal**: Dark mode is fully functional and visually polished.

**Design**:
- Fix `--color-line` dark mode values (currently identical to light mode)
- Make Recharts colours theme-aware: derive chart colours from CSS custom properties via `getComputedStyle`
- Remove all 130+ lines of legacy Tailwind dark mode overrides from `index.css`
- Ensure graph visualisation respects dark mode (node strokes, labels, background)
- Ensure search result cards, entity detail panels, and data catalog all switch cleanly

**Implementation**:
```css
/* Fix in index.css dark mode section */
@media (prefers-color-scheme: dark) {
    :root {
        --color-line: rgba(255, 255, 255, 0.12);
        --color-line-2: rgba(255, 255, 255, 0.06);
    }
}

/* Chart colours derived from CSS variables */
--color-chart-1: var(--color-accent);
--color-chart-2: #10B981;
--color-chart-3: #F59E0B;
--color-chart-4: #EF4444;
--color-chart-5: #8B5CF6;
```

**Files**: `index.css` (dark mode section + remove legacy overrides), `CanvasPanel.tsx` (chart colour retrieval), all components using hardcoded colours

### U9. Data Catalog Stabilisation

**Goal**: Data Catalog loads reliably and doesn't hang the browser.

**Design**:
- Consolidate 11 useState hooks into a single `useReducer` with clearly defined state transitions
- Lazy-load the Data Quality tab content (don't fetch until tab is clicked)
- Add error boundaries around each catalog section
- Show skeleton loaders during data fetches instead of blank space
- Paginate heavy operations (quality metrics computation) server-side

**Implementation**:
```typescript
// Replace 11 useState with useReducer
type CatalogState = {
  view: 'library' | 'quality';
  entityType: string;
  browseData: CatalogEntity[] | null;
  selectedEntity: string | null;
  entityDetail: CatalogEntityDetail | null;
  loading: { browse: boolean; detail: boolean; quality: boolean };
  error: string | null;
  page: number;
  sort: string;
};

type CatalogAction =
  | { type: 'SET_VIEW'; view: string }
  | { type: 'BROWSE_START' }
  | { type: 'BROWSE_SUCCESS'; data: CatalogEntity[] }
  | { type: 'BROWSE_ERROR'; error: string }
  | { type: 'SELECT_ENTITY'; id: string }
  | { type: 'DETAIL_SUCCESS'; detail: CatalogEntityDetail }
  // ...etc
```

**Files**: Rewrite `DataCatalogPanel.tsx` state management, extract sub-components

### U10. Component Architecture Cleanup

**Goal**: Eliminate the CanvasPanel monolith and establish sustainable component boundaries.

**Design**:

Split `CanvasPanel.tsx` (846 lines) into focused sub-components:

| New Component | Extracted From | Size |
|---------------|----------------|------|
| `canvas/SummaryTab.tsx` | CanvasPanel lines ~260-420 | ~160 lines |
| `canvas/DataTab.tsx` | CanvasPanel lines ~420-580 | ~160 lines |
| `canvas/EntitiesTab.tsx` | CanvasPanel lines ~580-720 | ~140 lines |
| `canvas/ContextTab.tsx` | CanvasPanel lines ~720-846 | ~120 lines |
| `canvas/VizCard.tsx` | CanvasPanel lines ~580-640 | ~60 lines |
| `canvas/CanvasShell.tsx` | CanvasPanel tab orchestration | ~100 lines |
| `ui/DataTable.tsx` | CanvasPanel table rendering | ~150 lines |

Each sub-component:
- Receives only the props it needs (no prop drilling of entire response)
- Has its own error boundary
- Uses skeleton loader during async operations
- Is independently testable with Vitest

**Files**: Create `components/canvas/` directory with new files, rewrite `CanvasPanel.tsx` as thin orchestrator

### U11. Accessibility Baseline

**Goal**: Achieve WCAG 2.1 Level AA compliance across all workspace views.

**Implementation checklist**:

| Area | Fix | Files |
|------|-----|-------|
| **Tab components** | Add `role="tab"`, `aria-selected`, `tabindex` to all tab groups (TopBar, Canvas, Catalog) | `TopBar.tsx`, `CanvasPanel.tsx`, `DataCatalogPanel.tsx` |
| **Skip navigation** | Add skip-to-content link at top of page | `App.tsx` |
| **Focus management** | Trap focus in Drawer, restore focus on close. Auto-focus chat input after navigation | `Drawer.tsx`, `ChatPanel.tsx` |
| **Keyboard shortcuts** | Add `Shift+?` to show keyboard shortcut modal. Support `J/K` for feed navigation | New `components/KeyboardShortcuts.tsx` |
| **Motion respect** | Wrap all animations in `prefers-reduced-motion` media query | `LandingPage.tsx`, `useAnimatedNumber.ts` |
| **Colour contrast** | Audit all text/background combinations for 4.5:1 contrast ratio | All components |
| **Chart accessibility** | Add `aria-label` to all charts. Provide data table alternative for every chart | `CanvasPanel.tsx` chart sections |
| **Touch targets** | Ensure all interactive elements are ≥44×44px on touch devices | `TopBar.tsx`, `ChatPanel.tsx`, pill components |

### U12. Error Handling and Feedback

**Goal**: Every failure state has a clear, actionable UI response.

**Design**:

Add a toast notification system and error boundaries:

| Scenario | Current Behaviour | New Behaviour |
|----------|------------------|---------------|
| API call fails | Silent failure, stale data | Toast: "Couldn't load data. [Retry]" + skeleton state |
| Chat query errors | Spinner hangs | Inline error: "Something went wrong. [Try again]" with retry button |
| Graph data too large | Browser hangs | Graceful limit: "Showing top 100 of 450 entities. [Load more]" |
| Data Catalog timeout | Browser freeze | Error boundary: "Data quality metrics are loading slowly. [Refresh]" |
| Network disconnect | No indication | TopBar status dot turns red. Reconnection toast when restored |

**Implementation**:
- Create `components/ui/Toast.tsx` — context-based toast with 4 variants (info, success, warning, error), auto-dismiss, action buttons
- Create `components/ui/ErrorBoundary.tsx` — React error boundary with retry callback and fallback UI
- Wrap each major section (Chat, Canvas, Graph, Catalog) in an ErrorBoundary
- Add `useToast` hook for programmatic toast triggers
- Health indicator in TopBar: poll `/health` every 30s, reflect status in the green dot (currently static)

**Files**: New `components/ui/Toast.tsx`, `components/ui/ErrorBoundary.tsx`, `hooks/useToast.ts`, modify `TopBar.tsx`

### U13. Search Experience Enhancement

**Goal**: Search becomes the fastest path to any entity in the system.

**Design**:

| Improvement | Detail |
|-------------|--------|
| **Instant search** | Results appear as user types (debounced 300ms), no need to click "Search" |
| **Entity autocomplete in chat** | Typing `@` in chat input triggers entity autocomplete dropdown with type badges |
| **Cmd+K global search** | Works from any page/tab. Shows recent entities, top suggestions, quick actions |
| **Search result actions** | Each result card has inline actions: "Ask about", "Compare with…", "View graph" |
| **Faceted filters** | Quality score range, source filter, freshness filter — not just entity type |
| **Zero-result state** | "No results for X. Try: [broader term] [different entity type] [ask in chat]" |

**Implementation**:
- Chat input: detect `@` prefix and show autocomplete overlay using `/api/search?q=...&limit=5` (debounced)
- Cmd+K: Already has keyboard listener in WorkspacePage — expand to show a full command palette with Fuse.js fuzzy search
- Instant search: Replace Search page form submit with live results as user types

**Files**: New `components/search/CommandPalette.tsx`, `components/chat/EntityAutocomplete.tsx`, modify search page components

---

## Implementation Plan

### Phase 1: Stability & State (Week 1)

Fix the things that are actively broken or misleading.

| Task | Upgrade | Files | Priority |
|------|---------|-------|----------|
| Fix canvas staleness | U2 | `WorkspacePage.tsx`, `CanvasPanel.tsx` | Critical |
| Fix `[metrics]` string leak | U4 | `NarrativeMessage.tsx` | Critical |
| Fix dark mode border colours | U8 | `index.css` | High |
| Add error boundaries | U12 | New `ErrorBoundary.tsx`, wrap in major components | High |
| Data Catalog useReducer rewrite | U9 | `DataCatalogPanel.tsx` | High |
| Canvas clear on new query | U2 | `WorkspacePage.tsx` | High |

**Exit criteria**: No stale canvas data. No literal `[metrics]` in responses. Data Catalog doesn't hang. Error boundaries catch crashes.

### Phase 2: Component Architecture (Week 2)

Decompose monoliths and establish the component library.

| Task | Upgrade | Files | Priority |
|------|---------|-------|----------|
| Split CanvasPanel into sub-components | U10 | New `canvas/` directory | High |
| Extract DataTable as standalone | U5 | New `ui/DataTable.tsx` | High |
| Create Toast system | U12 | New `ui/Toast.tsx`, `hooks/useToast.ts` | High |
| Create Skeleton components | U12 | New `ui/Skeleton.tsx` | Medium |
| Memoize NarrativeMessage parsing | U4 | `NarrativeMessage.tsx` | Medium |

**Exit criteria**: CanvasPanel < 150 lines. DataTable reusable. Toast system operational. No render-path performance regressions.

### Phase 3: Interaction Upgrades (Week 3)

Make the intelligence consumable and explorable.

| Task | Upgrade | Files | Priority |
|------|---------|-------|----------|
| Sortable + clickable data tables | U5 | `ui/DataTable.tsx`, `CanvasPanel.tsx` | High |
| Citation click-to-expand | U4 | New `CitationCard.tsx`, rewrite citation section | High |
| Query progress indicator | U3 | New `QueryProgress.tsx`, `ChatPanel.tsx` | High |
| Workspace onboarding | U1 | New `WorkspaceOnboarding.tsx` | Medium |
| Entity autocomplete in chat | U13 | New `EntityAutocomplete.tsx` | Medium |

**Exit criteria**: Tables are sortable with row click-through. Citations accessible via keyboard. Progress visible during queries. New users see entity counts and guided suggestions.

### Phase 4: Visual Polish (Week 4)

Make it look as good as the data behind it.

| Task | Upgrade | Files | Priority |
|------|---------|-------|----------|
| Graph multi-colour entity types | U6 | Graph components, `index.css` | High |
| Graph node hover cards | U6 | New `NodeHoverCard.tsx` | Medium |
| Dark mode chart colours | U8 | `CanvasPanel.tsx`, `index.css` | Medium |
| Remove legacy Tailwind overrides | U8 | `index.css` | Medium |
| Graph legend and filter chips | U6 | Graph components | Medium |

**Exit criteria**: Graph shows colour-coded entity types. Dark mode fully functional. No legacy CSS overrides.

### Phase 5: Accessibility & Responsive (Week 5)

Reach enterprise-grade polish.

| Task | Upgrade | Files | Priority |
|------|---------|-------|----------|
| ARIA roles on all tab groups | U11 | `TopBar.tsx`, `CanvasPanel.tsx`, `DataCatalogPanel.tsx` | High |
| Skip-to-content + focus management | U11 | `App.tsx`, `Drawer.tsx`, `ChatPanel.tsx` | High |
| Responsive breakpoints | U7 | `WorkspaceLayout.tsx`, `TopBar.tsx` | High |
| Touch target sizes | U7/U11 | `TopBar.tsx`, all button components | Medium |
| Motion reduction | U11 | `LandingPage.tsx`, `useAnimatedNumber.ts` | Medium |
| Keyboard shortcuts modal | U11 | New `KeyboardShortcuts.tsx` | Low |

**Exit criteria**: WCAG 2.1 AA audit passes. Platform usable on iPad. All interactions keyboard-accessible.

### Phase 6: Search & Discovery (Week 6)

Connect everything together.

| Task | Upgrade | Files | Priority |
|------|---------|-------|----------|
| Cmd+K command palette | U13 | New `CommandPalette.tsx` | High |
| Instant search (as-you-type) | U13 | Search page components | Medium |
| Search result inline actions | U13 | Search result components | Medium |
| Graph mini-map | U6 | New `GraphMiniMap.tsx` | Low |
| Health indicator live status | U12 | `TopBar.tsx` | Low |

**Exit criteria**: Cmd+K opens global search from any view. Search results update live. Every entity is reachable in ≤2 interactions.

---

## Success Metrics

| Metric | Current | Target | How to Measure |
|--------|---------|--------|----------------|
| Time to first meaningful query | ~15s (user reads suggestions, picks one) | <5s (onboarding surfaces contextual entries) | Session recording |
| Canvas shows relevant data | ~70% of responses (stale otherwise) | 100% (cleared on new query) | Automated test |
| Citation accessibility | Hover-only (mouse) | Click/keyboard/touch | Accessibility audit |
| WCAG 2.1 AA compliance | ~30% (estimate) | 100% | axe-core audit |
| Data Catalog load success | ~80% (hangs on quality tab) | 100% | Error monitoring |
| Mobile usability | 0% (layout breaks) | Functional on iPad, readable on iPhone | Manual testing |
| Dark mode completeness | ~60% (borders, charts broken) | 100% | Visual regression test |
| Component test coverage | 0 frontend tests | ≥1 Vitest test per new/modified component | Test count |

---

## Relationship to Other Specs

- **SPEC-002**: This spec is the _sequel_ to SPEC-002. Where SPEC-002 established the chat+canvas architecture and design system, SPEC-004 addresses the gaps found in the live implementation and pushes towards enterprise-grade polish.
- **SPEC-003 (Proactive Intelligence)**: The Intelligence Feed tab (SPEC-003) will be built on the component library established here — specifically Toast, ErrorBoundary, Skeleton, and DataTable. Phase 3-4 of SPEC-003 should begin after Phase 2 of SPEC-004 completes the component foundations.
- **SPEC-001 (Research Engine)**: The conversation memory and research agent status could surface in the workspace onboarding (U1) as "Research in progress" indicators once wired.
