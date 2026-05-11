# NewUI Comprehensive Analysis — Live Diagnosis & Fix Plan

**Date**: 29 March 2026
**Scope**: Full audit of the production newui at `myscience-production.up.railway.app/newui`

---

## 1. Executive Summary

The newui implementation is **structurally sound** — the team built 22 components that faithfully implement the SPEC-009 vision: graph-centric three-zone layout, glass-morphism overlay panels, entity mention highlighting, search typeahead, and a dual Explore/Curate lens. The CSS design system is complete and well-tokenised. The component architecture is clean with proper separation of concerns.

However, the **single most critical feature — the knowledge graph canvas — stays permanently empty**. This means the centrepiece of the entire design (the graph fills 100% of the viewport) shows nothing but a dark placeholder with "Ask a question to see the knowledge graph" text. The user experience collapses to a chat panel on the left with wasted space everywhere else.

**Root cause**: Not a single bug but a **chain of three issues** that compound to make the graph invisible.

---

## 2. Root Cause Analysis: Why the Graph Canvas Is Empty

### Issue 1: Intent Handlers Return Empty graph_context (3 of 6 handlers)

The chat system has 6 intent handlers. Three of them **hardcode empty graph_context**:

| Handler | Intent | graph_context | Why |
|---------|--------|---------------|-----|
| `handle_general` | GENERAL | **Real data** ✅ | Calls `QueryEngine.query()` → graph neighbourhood expansion |
| `handle_dossier` | DOSSIER | **Real data** ✅ | Calls `engine.entity_dossier()` → graph neighbourhood |
| `handle_compare` | COMPARE | **Real data** ✅ | Builds comparison graph from entity pairs |
| `handle_landscape` | LANDSCAPE | **Empty** ❌ | Returns `{"nodes": [], "edges": []}` hardcoded |
| `handle_pipeline` | PIPELINE | **Empty** ❌ | Returns `{"nodes": [], "edges": []}` hardcoded |
| `handle_portfolio` | PORTFOLIO | **Mixed** ⚠️ | Uses `_enrich_result` (has graph) but may fail if dossier returns sparse data |

A query like "What are the trials right now working in the GLP-1 space" contains "trials" but not "clinical trials" — so it routes to **GENERAL** intent, which *should* return real graph data. But if the search returns few results (e.g. because "GLP-1" isn't an exact entity name in the database), the graph neighbourhood expansion may return zero nodes.

### Issue 2: SSE Event Parsing Has a Fragile `eventType` Scope

In `api.ts` lines 609-632, the SSE reader declares `let eventType = ''` inside the `while(true)` loop. If the `event: done` line and `data: {...}` line arrive in separate TCP chunks (possible under network conditions), `eventType` resets to `''` before the data line is processed, silently dropping the `done` event. The `onDone` callback never fires, `response` stays `undefined`, and graph_context is never extracted.

### Issue 3: ModernGraph Is the Old Renderer

The newui uses `ModernGraph.tsx` — the legacy canvas-based force-directed renderer. The newer `KnowledgeGraph.tsx` component was designed in SPEC-008 with:
- 180-frame physics simulation (then stops, saving CPU)
- Pan/zoom controls
- Entity type toggle pills
- Edge category legend
- Path highlight mode
- Hover tooltips with metadata

`ModernGraph` lacks all of these and runs an infinite `requestAnimationFrame` loop that can freeze the renderer on large graphs.

### The Compounding Effect

Even when graph_context *is* returned correctly:
1. ModernGraph has no empty-state guidance (no "try clicking an entity" prompt)
2. No node count indicator tells the user data arrived
3. No animation draws attention to newly-populated nodes
4. The graph appears identical (dark canvas) whether it has 0 or 50 nodes — the user can't tell

---

## 3. What's Working Well

The team's implementation deserves credit. Here's what's production-ready:

**Layout & Architecture** (95% SPEC-009 compliant)
- Three-zone layout: dialogue (380px, left) | graph (fills) | inspector (360px, right, on-demand)
- Glass-morphism overlay panels with `backdrop-filter: blur(12px)`
- Responsive auto-collapse on narrow viewports (<1024px)
- Keyboard shortcuts: Cmd+K (search), Cmd+/ (toggle dialogue), Esc (close inspector)

**Chat (DialoguePanel + RichNarrative)** — Production-ready
- Streaming token display via SSE
- Auto-scroll to latest messages
- Follow-up suggestion pills
- Entity mention highlighting (case-insensitive matching)
- Bold text rendering, citation markers as superscript
- Relative timestamps ("just now", "5m ago")

**Inspector (InspectorPanel)** — Production-ready
- Collapsible sections: Properties, Relationships, Evidence, Actions
- Link grouping by entity type
- Evidence surface (literature, trials)
- EntityDot, Badge, ConfidenceBar integration
- Skeleton loading states

**Curate View** — Production-ready (but not graph-centric)
- Pipeline connector cards with Live/Stale/Error badges
- Knowledge graph stats (entity count, link distribution)
- Drug completeness progress bars
- Shimmer skeleton loading

**Design System (newui.css)** — Complete
- All CSS tokens: surfaces, text, entity colours, confidence, spacing, typography, radius, shadows, motion
- Dark mode support via `html.dark`
- Keyframe animations: shimmer, fade-in, slide-in, pulse-dot
- 4px spacing grid

**Component Library** — 12 primitives, all clean
- Badge, Button, Input, EntityDot, EntityMention, EntityCard, Panel, ErrorBoundary, Skeleton, ConfidenceBar, FAIRSparkline, SearchDropdown

---

## 4. What's Broken or Incomplete

### Critical (blocks the core experience)

1. **Graph canvas always empty** — the chain of issues described in §2
2. **No graph interaction** — ModernGraph lacks pan/zoom, drag, click-to-inspect, hover tooltips
3. **No edge legend** — users can't understand what connections mean
4. **SSE `eventType` scoping bug** — can silently drop the `done` event under network fragmentation

### Important (degrades the experience)

5. **CurateView is a card grid, not a supply chain graph** — SPEC-009 §15 envisioned the graph zone showing data lineage (source → normalise → resolve → store), not a flat list of connector cards
6. **No entity-click-to-graph flow** — clicking an entity mention in the narrative should expand its neighbourhood on the graph; currently it only opens the inspector
7. **No graph-populates-on-load** — when the page first loads, there's no seed graph. Even showing a small subgraph of recent entities would make the canvas feel alive
8. **Toolbar settings button has no handler** — dead click target

### Minor (polish)

9. **ModernGraph infinite RAF loop** — wastes CPU when graph is stable
10. **PipelineConnector/GraphSummary types duplicated** between NewWorkspace.tsx and CurateView.tsx
11. **No graph export** — no way to save/share the graph view
12. **No loading indicator on graph** — user doesn't know graph data is being fetched

---

## 5. Fix Plan — Priority-Ordered

### Phase 1: Make the Graph Appear (Critical — 1-2 days)

**Fix 1a: Harden SSE event parsing** (`api.ts`)
Move `eventType` outside the while loop so it persists across chunk boundaries:

```typescript
// BEFORE (buggy):
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  // ...
  let eventType = '';  // ← resets every chunk!
  for (const line of lines) { ... }
}

// AFTER (correct):
let eventType = '';  // ← persists across chunks
while (true) {
  const { done, value } = await reader.read();
  if (done) break;
  // ...
  for (const line of lines) { ... }
}
```

**Fix 1b: Ensure all intent handlers populate graph_context**

For `handle_landscape` and `handle_pipeline`, add graph neighbourhood expansion for the top entities mentioned in the response:

```python
# In handle_landscape, after computing top segments:
if include_graph and engine:
    graph_nodes, graph_edges = {}, []
    for seg in top[:5]:
        mech_name = seg.get("mechanism_name", "")
        # Find mechanism entity and expand neighbourhood
        resolved = resolve_entity(mech_name, "mechanism", db)
        if resolved:
            subgraph = engine.graph.neighborhood(resolved["entity_id"], "mechanism")
            # ... merge into graph_nodes, graph_edges
```

**Fix 1c: Add graph seed on page load**

When NewWorkspace mounts, fetch a small seed graph (e.g. top 20 entities by connection count) so the canvas isn't empty before any query:

```typescript
useEffect(() => {
  api.traverse('', '', 1).then(sub => {
    if (sub.nodes.length) setGraphData(sub);
  }).catch(() => {});
}, []);
```

### Phase 2: Swap ModernGraph → KnowledgeGraph (High impact — 2-3 days)

Complete the `KnowledgeGraph.tsx` implementation:
- 180-frame physics simulation, then stop
- Pan/zoom (pointer drag, wheel, keyboard)
- Click node → fire `onNodeClick` → open inspector
- Hover → tooltip with entity name, type, connection count
- Entity type toggle pills (filter node visibility)
- Edge category legend
- Path highlight mode
- Compact mode for small viewports

Then swap the import in NewWorkspace.tsx:
```typescript
// import ModernGraph from '../components/ModernGraph';
import KnowledgeGraph from '../components/KnowledgeGraph';
```

### Phase 3: Entity-Click-to-Graph Flow (Medium — 1 day)

When a user clicks an entity mention in the chat narrative:
1. Check if entity is already in the graph
2. If yes: centre the graph on that node + open inspector
3. If no: call `api.traverse(entityType, entityId, 1)` → merge new nodes into existing graph → centre on new node → open inspector

This creates the core interaction loop: **ask question → read narrative → click entity → explore graph → click neighbour → read inspector → ask follow-up**.

### Phase 4: Graph Feedback Indicators (Small — 0.5 day)

- Show node count badge on graph canvas ("47 entities, 112 connections")
- Animate new nodes appearing (scale from 0 → 1 with ease-out)
- Pulse effect on centre entity
- Loading spinner on graph while waiting for API response

### Phase 5: Curate Lens Supply Chain Graph (Medium — 2 days)

Replace the flat connector card grid with a graph showing the data pipeline:
- Nodes: data sources (left), processing stages (centre), entity tables (right)
- Edges: data flow with record counts as labels
- Node colour: green (healthy), amber (stale), red (error)
- Click source node → show connector detail in inspector
- Click entity table node → show entity count, completeness, FAIR score

### Phase 6: Polish (Ongoing)

- Fix ModernGraph infinite RAF → use KnowledgeGraph's 180-frame approach
- Deduplicate PipelineConnector/GraphSummary types
- Add graph export (SVG/PNG)
- Settings panel (theme, graph density, animation speed)

---

## 6. Does the Current Implementation Match the Vision?

**Architecture: Yes (90%).** The three-zone layout, glass-morphism overlays, dual-lens model, and component library are all faithful to SPEC-009.

**Experience: No (30%).** The graph — which is literally the product — is invisible. Without a populated, interactive graph canvas, the UI is functionally identical to a chat app with a dark background. The entire value proposition (graph-centric pharma intelligence) is unrealised.

**The gap is not architectural — it's plumbing.** The components exist, the data exists in the backend, the API endpoints work. The graph_context flows through the handler → serialiser → SSE → parser → state → renderer pipeline, but three weak links in that chain (empty handlers, fragile SSE parsing, legacy renderer) conspire to keep the canvas dark.

**Estimated effort to reach the vision**: 6-8 developer-days across the 6 phases above. Phase 1 alone (1-2 days) would transform the experience from "empty chat app" to "graph-powered intelligence platform".

---

## 7. Recommended Immediate Actions

1. **Fix the SSE `eventType` bug** — 15-minute fix, eliminates silent data loss
2. **Add `include_graph` + `engine` params to `handle_landscape` and `handle_pipeline`** — ensures all intents return graph data
3. **Add a seed graph on page load** — even 10-20 nodes transforms the first impression
4. **Swap to KnowledgeGraph** — the component was designed for this; ModernGraph was always a placeholder

These four changes, combined, would make the newui deliver on its promise.
