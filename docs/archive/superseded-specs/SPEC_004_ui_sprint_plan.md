# SPEC-004: UI Enhancement Sprint Plan (10 Sprints)

> **Date**: 22 March 2026
> **Source**: `lead_notes_4_dev.md` analysis
> **Method**: Task-based, spec + test driven, parallel execution

---

## Sprint 1: Graph Empty State — Show Value Immediately (Q1)
**Goal**: Pre-render semaglutide 1-hop graph on first visit

- [ ] Auto-load semaglutide neighbourhood when Graph tab opens with no entity selected
- [ ] Show banner: "Showing semaglutide connections — search any entity to explore"
- [ ] Dismissible banner, entity search clears it
- **Test**: Playwright screenshot verifies graph renders nodes on empty state
- **Files**: `GraphExplorer.tsx`

## Sprint 2: Cross-Module Navigation — "View in Graph" (Q4)
**Goal**: One-click entity flow between Catalog, Chat, and Graph

- [ ] Add "View in Graph" button to Canvas entity cards
- [ ] Add "View in Graph" button to Catalog entity rows/drawer
- [ ] Add "View in Catalog" link in Graph node drawer
- [ ] WorkspacePage: accept `graphEntity` prop to pre-load Graph tab with entity
- **Test**: Click entity in canvas → Graph tab opens with that entity's neighbourhood
- **Files**: `CanvasPanel.tsx`, `DataCatalogPanel.tsx`, `GraphExplorer.tsx`, `WorkspacePage.tsx`

## Sprint 3: Node Selection Panel — Pin Insight on Click (Q5)
**Goal**: Persistent entity context during graph exploration

- [ ] Click node → pin NodeInsight card to left rail (not just hover tooltip)
- [ ] Show: entity name, type badge, degree, top 3 connections with link types
- [ ] Card updates when clicking different nodes
- [ ] "Open Dossier" button in pinned card → opens Drawer
- **Test**: Click node → insight card visible in rail, persists after cursor moves
- **Files**: `GraphExplorer.tsx`

## Sprint 4: Edge Colour Coding + Interactive Legend (Q3 + M5)
**Goal**: Make relationship types visible without clicking

- [ ] Colour-code edges by link_type: OWNS=amber, SPONSORS=teal, INVESTIGATES=blue, EVIDENCE_FOR=green, HAS_SIGNAL=red
- [ ] Add edge legend to Graph canvas (bottom-right)
- [ ] Legend items are toggleable — click to show/hide edge type
- [ ] Edge labels on OWNS and SPONSORS edges (small text on edge midpoint)
- **Test**: Graph renders coloured edges, legend toggles filter correctly
- **Files**: `ModernGraph.tsx`, `GraphExplorer.tsx`

## Sprint 5: Entity Dossier View in Catalog Drawer (M4)
**Goal**: Transform database inspector into intelligence card

- [ ] Entity drawer top: LLM-generated summary sentence (call api.chat with entity name)
- [ ] Structured sections: Identity, Clinical Pipeline, Evidence, Safety, Regulatory
- [ ] Collapsible "Technical Details" at bottom for raw key-value pairs
- [ ] Phase badges for drugs (Phase 1/2/3/Approved)
- [ ] Connection count badges by type
- **Test**: Open drug entity → summary visible, sections render, raw data collapsed
- **Files**: `DataCatalogPanel.tsx` (or extract to `EntityDrawer.tsx`)

## Sprint 6: Browse Tab — Pharma-Structured Entity Browser (Q6)
**Goal**: Group entities by mechanism/TA instead of flat alphabetical list

- [ ] Drugs: group by mechanism, show phase badge, trial count, company, completeness bar
- [ ] Companies: show portfolio size, pipeline strength, top drugs
- [ ] Trials: group by phase+status (Recruiting/Active/Completed/Terminated)
- [ ] Therapeutic Areas: hierarchical tree with entity counts
- [ ] Faceted filtering (mechanism, phase, TA, company)
- **Test**: Browse drugs → grouped by mechanism, phase badges visible
- **Files**: `DataCatalogPanel.tsx` (or extract to `EntityBrowser.tsx`)

## Sprint 7: Catalog Split — Library (users) vs Admin (data health) (M1)
**Goal**: Separate user-facing intelligence from internal data governance

- [ ] Default view: "Library" — entity browser, entity dossier, search
- [ ] Admin toggle (gear icon): reveals Overview (health), Audit Trail, Curation
- [ ] Curation queue hidden behind admin toggle
- [ ] "Data Quality" summary replaces Curation for non-admin: confidence per type, known gaps, freshness
- **Test**: Default view shows Library, admin toggle reveals health dashboard
- **Files**: `DataCatalogPanel.tsx`

## Sprint 8: Canvas → Graph Pipeline (L3)
**Goal**: "Explore connections" from chat results to graph

- [ ] Entity cards in Canvas: "Explore connections" button
- [ ] Landscape/compare results: "Visualise landscape" button → loads all entities into Graph
- [ ] Graph tab receives entity list, renders subgraph
- [ ] Breadcrumb in TopBar shows exploration trail
- **Test**: Landscape query → click "Visualise" → Graph renders competitive subgraph
- **Files**: `CanvasPanel.tsx`, `WorkspacePage.tsx`, `GraphExplorer.tsx`

## Sprint 9: Graph Layout Modes — Objective-Specific (L1)
**Goal**: Each objective produces a visually distinct layout

- [ ] Entity Neighbourhood: force-directed (current, default)
- [ ] Trial Evidence Map: timeline layout (left→right: drug→trials-by-phase→literature)
- [ ] Portfolio Network: radial layout (company centre, drugs ring 1, trials ring 2)
- [ ] Mechanism Landscape: hierarchical tree (mechanism→subclass→drugs)
- [ ] Layout selector in Graph controls rail
- **Test**: Select "Portfolio Network" → radial layout renders, not force-directed
- **Files**: `ModernGraph.tsx`, `GraphExplorer.tsx`

## Sprint 10: Polish + Search Page Redesign + Code Cleanup
**Goal**: Final polish, SearchPage migration, dead code removal

- [ ] SearchPage: migrate to new design system (inline styles + CSS variables)
- [ ] Remove WorkspaceRail (replaced by TopBar)
- [ ] Remove old IntelligencePage.tsx (replaced by WorkspacePage)
- [ ] Remove old ChatMessage.tsx (replaced by NarrativeMessage)
- [ ] Loading skeletons on all panels
- [ ] Error boundaries with retry
- [ ] Responsive layout audit (mobile stacking)
- [ ] Playwright regression suite (10+ screenshots, automated)
- **Test**: Full Playwright visual regression, 0 JS errors, build clean
- **Files**: `SearchPage.tsx`, dead file removal, responsive CSS

---

## Quality Gates (every sprint)

```
✅ Playwright screenshot verification (before/after)
✅ No new JS errors (pageerror handler)
✅ vite build clean (no TypeScript errors)
✅ pytest passes (backend unchanged = no regression)
✅ No useMemo inside .map() (React #310 guard)
✅ All new styles use CSS variables (no Tailwind color utilities)
✅ File size check: no file >500 lines without extraction plan
```
