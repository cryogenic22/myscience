# SPEC-007: Graph Explorer Visual & Intelligence Upgrade

*Author: Architecture Review · Date: 2026-03-28*
*Scope: Graph visualisation quality, colour semantics, detail cards, traversal UX, path display, layout engine*

---

## 1. Executive Summary

The Graph Explorer is Market Zero's most differentiating feature — a live, traversable knowledge graph connecting drugs, companies, trials, mechanisms, therapeutic areas, and literature across 12 relationship types with confidence-weighted edges. The backend is genuinely powerful: recursive CTE traversal up to 4 hops, Dijkstra weighted path finding, PageRank-inspired influence scoring, competitive cluster detection, and entity centrality ranking.

The current visualisation does not convey this power. Live testing reveals a graph that renders as a monochrome blob of same-coloured circles with invisible edge labels, no visual hierarchy, and no way to understand *what* the connections mean without clicking through to the sidebar. The system has rich metadata (link types, confidence scores, entity properties, influence scores) that never reaches the user's eyes.

This spec documents every visual and interaction issue observed in live testing and code review, then proposes a systematic upgrade to make the graph explorer the centrepiece experience it should be.

---

## 2. Current State — What Live Testing Reveals

### 2.1 Visual Issues Observed

**Issue V1: Monochrome node soup**
The graph renders with near-identical node colours. When viewing the semaglutide demo (literature entity), all 50 neighbours are green circles (`#16a34a` for literature). When viewing Novo Nordisk (company), all neighbours are slate/blue-grey circles. Because the demo loads 1-hop by default, and most 1-hop neighbours of a literature entity are other literature entities, the graph is a single-colour blob. The 6-colour type system (drug=blue, company=amber, trial=teal, mechanism=violet, TA=rose, literature=green) only becomes visible when entity types are mixed — which requires 2+ hops.

**Issue V2: No node labels visible**
In the ModernGraph canvas, labels are only shown if `isCenter || isHover || nodes.length < 20`. With 51 nodes loaded, only the centre node has a visible label. The user sees 50 anonymous circles and must hover each one individually to discover what it is. This defeats the purpose of a visual intelligence tool.

**Issue V3: Edges are invisible lines**
Edge rendering uses low-opacity strokes (`globalAlpha = 0.3 + conf * 0.5`), resulting in barely visible hairlines on the light `bg-slate-50` background. There are no edge labels, no arrowheads showing direction, and no visual distinction between "OWNS", "INVESTIGATES", "TARGETS", and "EVIDENCE_FOR" — all appear as faint grey-green lines.

**Issue V4: Centre node label obscured**
The centre entity "Anti-obesity medication with liraglutide or semaglutide" (a literature title) is rendered as a long label that overlaps with surrounding nodes. The label text has a white background pill but it clips behind adjacent nodes, making it partially unreadable.

**Issue V5: No visual hierarchy by importance**
All non-centre nodes are the same size (radius 8px). There is no visual signal for which nodes are more important (higher influence score), more connected (higher degree), or more confident (edge confidence). A drug with 47 connections looks identical to a literature node with 1 connection.

**Issue V6: Edge legend shows single type**
The bottom legend shows only the dominant edge type (e.g., "EVIDENCE FOR" for the literature graph, "HAS MILESTONE" for Novo Nordisk). Multiple edge types exist but only one appears in the legend, giving the false impression of a homogeneous graph.

**Issue V7: Light background washes out the graph**
ModernGraph uses `bg-slate-50` (very light grey) as the canvas background. GraphMini uses `bg-neutral-900` (dark). The light background makes thin edges and subtle colour differences nearly invisible. The dark-background GraphMini is actually more readable.

**Issue V8: "Data Sources: Exploring..." stuck**
The Graph Summary card shows "Data Sources: Exploring..." as a permanent state — it never resolves to actual source names. This appears to be a bug where `sourceDomains` extraction fails on non-URL `via` fields.

**Issue V9: No quick-insight on node click in main graph**
Clicking a node in the main ModernGraph immediately reloads the entire graph centred on that node, discarding the previous view. There's no intermediate hover card or click-to-inspect that preserves the current view while showing node details.

**Issue V10: Path result shows only hop count**
After running a path query, the result is a small text badge: "Path found: 3 hop(s)". The actual path edges, intermediate entities, and confidence per hop are not visualised — the user sees the same radial graph, not a linear path chain.

### 2.2 Interaction Issues

**Issue I1: No pan/zoom on ModernGraph**
ModernGraph (used in GraphExplorer) has no viewport controls — no pan, no zoom, no reset. If the force simulation spreads nodes beyond the visible area, they're lost. GraphMini (used in search EntityPreview) does have full pan/zoom/reset. The main explorer is missing this.

**Issue I2: Clicking a node destroys context**
Every node click triggers a full `loadGraph()` call, discarding the current graph and reloading from scratch. There's no way to inspect a node while keeping the current view. The "quick node insight" card exists but only appears for nodes in the *current* graph's `buildNodeInsight()`, and it's replaced immediately by the reload.

**Issue I3: Detail drawer requires manual open**
The full detail drawer (entity relationships, connection breakdown, external sources) doesn't open automatically when selecting a node. Users must click the separate document icon in the collapsed rail or the "Full details" button in the quick insight. Most users won't discover this.

**Issue I4: No undo/back navigation**
There's no way to go back to the previous graph view after clicking a node. The `graphTrail` concept exists in search's EntityPreview but is not implemented in GraphExplorer.

**Issue I5: Objective modes have no visual effect on the graph**
Switching between "Entity Neighborhood", "Trial Evidence Map", "Portfolio Network", and "Mechanism Landscape" changes the `preferredTypes` filter for node display, but this is only applied as a `nodeTypeFilter` in the controls section. The graph layout, colours, and emphasis don't change to reflect the chosen objective.

---

## 3. Two Graph Components — Comparison

Market Zero has two independent canvas-based graph renderers that duplicate logic:

| Feature | GraphMini (583 lines) | ModernGraph (338 lines) |
|---------|----------------------|------------------------|
| **Used in** | Search EntityPreview | GraphExplorer |
| **Background** | `bg-neutral-900` (dark) | `bg-slate-50` (light) |
| **Pan/zoom** | Full (pointer drag + wheel + keyboard + buttons) | None |
| **Node labels** | Conditional (centre, non-drug, high-degree, small graphs) | Conditional (centre, hover, < 20 nodes) |
| **Node sizing** | Variable (centre=8, non-drug=6, drug=3+0.5×degree, max 6) | Fixed (centre=20, hover=10, default=8) |
| **Edge colouring** | 4 categories (therapeutic/mechanism/ownership/other) | Per link_type from EDGE_COLORS map (9 types) |
| **Confidence opacity** | Not used | `globalAlpha = 0.3 + conf * 0.5` |
| **Node type legend** | Top-left with toggle buttons | None |
| **Edge type legend** | Bottom-right (4 categories) | Bottom-left (per-type toggle) |
| **Node type filtering** | Toggle per type (hide/show) | None (controlled externally) |
| **Hit testing** | Radius-based with best-match | Simple distance < 20px |
| **Force simulation** | 180 frames, then stops | Runs indefinitely (no stop) |
| **Hover tooltip** | Custom positioned div (label, type, link count) | None (only hoverNodeId state) |
| **Physics** | Centre gravity + repulsion + edge springs + velocity damping 0.82 | Similar but damping 0.9, weaker forces |
| **Max nodes** | 30 (keyNodes preference for non-drug or high-degree) | All nodes passed in |
| **Keyboard nav** | Arrow keys (pan), +/- (zoom), 0 (reset) | None |

**Verdict:** GraphMini is the more mature, more interactive component. ModernGraph is simpler but lacks essential features. They should be unified.

---

## 4. Backend Capabilities Not Surfaced

| Capability | Backend Method | Available Data | Currently Shown |
|------------|---------------|----------------|-----------------|
| **Influence score** | `entity_influence()` | 0-1 normalised | Not shown |
| **Competitive clusters** | `competitive_clusters()` | Grouped entities + HHI | Not shown |
| **Weighted paths** | `weighted_path()` | Dijkstra path + confidence per hop | Hop count only |
| **Centrality ranking** | `entity_centrality_batch()` | Top-N entities by influence | Not shown |
| **Entity properties** | `traverse()` → `properties` dict | brand_name, phase, status, ticker, approval_date | Not shown (only label) |
| **Connection breakdown** | `entity_summary()` → `connections_by_type` | Counts per link_type | In sidebar only |
| **Mechanism hierarchy** | `mechanism_hierarchy()` | Tree traversal | Not accessible from graph |
| **Drugs by mechanism** | `drugs_by_mechanism_class()` | Filtered drug list | Not accessible from graph |
| **Edge provenance** | `edge.via` field | Source URL or identifier | In drawer only (if URL) |
| **Edge confidence** | `edge.confidence` (0-1) | Per-edge quality signal | Opacity only, not labelled |

---

## 5. Proposed Visual Redesign

### 5.1 Unified Graph Renderer

Replace both GraphMini and ModernGraph with a single `KnowledgeGraph` component that combines the best of both:

- **From GraphMini:** Pan/zoom viewport, keyboard controls, type toggle filters, hover tooltips, node sizing by degree, capped node count (30), 180-frame simulation
- **From ModernGraph:** Per-link-type edge colouring (9 types), confidence-based opacity, responsive resize, edge type toggle legend
- **New:** Dark background (always), edge labels, arrowheads, node sizing by influence, property tooltips, path highlighting

### 5.2 Dark Canvas (Always)

Switch to dark background (`#0f172a` slate-900 or `#0a0a0a` neutral-950) for the graph canvas. Reasons:

- Coloured nodes and edges are dramatically more visible on dark backgrounds
- Current light `bg-slate-50` washes out low-opacity edges
- GraphMini already uses dark and looks better
- Matches the "intelligence tool" visual language (Bloomberg Terminal, Palantir, Neo4j Browser)

### 5.3 Node Visual Language

**Size = Influence/Degree:**
```
Centre node:     radius 20px, glow ring
High influence:  radius 12-16px (top quartile by degree or influence)
Standard:        radius 8px
Low-degree leaf: radius 5px
```

**Colour = Entity Type** (unchanged palette, but with higher contrast on dark):
```
Drug:              #3b82f6 (blue-500, brighter on dark)
Company:           #f59e0b (amber-500)
Trial:             #14b8a6 (teal-400)
Therapeutic Area:  #f43f5e (rose-500)
Mechanism:         #a78bfa (violet-400)
Literature:        #22c55e (green-500)
Event:             #ef4444 (red-500)
Investigator:      #06b6d4 (cyan-500)
Patent:            #8b5cf6 (purple-500)
```

**Shape differentiators (optional, Phase 2):**
- Drugs: circle (default)
- Companies: rounded square
- Trials: diamond
- Literature: hexagon

**Labels:**
- Always show labels for: centre node, high-degree nodes (≥3 edges), non-drug entities
- Truncate at 20 chars with ellipsis
- White text on dark canvas, 10px font, no background pill for leaves
- Centre node: 13px bold, subtle glow

### 5.4 Edge Visual Language

**Colour = Relationship Type** (mapped to distinct hues):
```
OWNS / MANUFACTURES:    #f59e0b (amber) — ownership
SPONSORS:               #14b8a6 (teal) — sponsorship
INVESTIGATES:           #3b82f6 (blue) — clinical
EVIDENCE_FOR:           #22c55e (green) — literature
TARGETS_MECHANISM:      #a78bfa (violet) — mechanism
IN_THERAPEUTIC_AREA:    #f43f5e (rose) — therapeutic
COMPETES_WITH:          #ef4444 (red) — competition
HAS_MILESTONE:          #f59e0b (amber) — regulatory
ASSOCIATED_WITH:        #64748b (slate) — generic
```

**Width = Confidence:**
```
confidence ≥ 0.9:  2.5px (strong)
confidence 0.7-0.9: 1.5px (moderate)
confidence < 0.7:   0.8px (weak)
```

**Opacity = Confidence:**
```
globalAlpha = 0.4 + confidence * 0.5
```
(Range: 0.4 for low confidence → 0.9 for high confidence)

**Arrowheads:**
Small triangular arrowhead at target end, same colour as edge. Shows directionality (OWNS goes from company → drug, INVESTIGATES goes from trial → drug).

**Edge labels on hover:**
When hovering over an edge midpoint (within 8px), show a tooltip:
```
┌──────────────────────────┐
│  OWNS · 95% confidence   │
│  via: SEC EDGAR           │
└──────────────────────────┘
```

### 5.5 Centre Node Treatment

The selected/centre node should be visually dominant:
```
┌─────────────────────────┐
│                          │
│    ╭ glow ring (type    │
│    │  colour at 15%     │
│    │  opacity, r+8px)   │
│    │                     │
│    ● Node (r=20px)       │
│    │  white 2px border   │
│    │                     │
│    ╰ Label below         │
│      13px bold white     │
│                          │
└─────────────────────────┘
```

### 5.6 Node Hover Card

On hover (not click), show a floating card near the node:

```
┌──────────────────────────────────┐
│  💊 Semaglutide                  │
│  Drug · GLP-1 Receptor Agonist   │
│                                   │
│  Phase 4 · Brand: Ozempic        │
│  12 connections · Influence: 0.87 │
│                                   │
│  Click to explore · Shift+click   │
│  for details                      │
└──────────────────────────────────┘
```

Data sources:
- Label, entity_type: from `GraphNode`
- Phase, brand: from `node.properties` (already loaded)
- Connections: edge count from current graph
- Influence: new API call (batch-load on graph load)

### 5.7 Path Visualisation Mode

When a path query returns results, switch from radial layout to **linear path layout**:

```
  ●─────OWNS─────●─────INVESTIGATES─────●─────TARGETS─────●
  Novo          Sema-     (0.92)       NCT04...   (0.95)  GLP-1
  Nordisk       glutide                             Receptor

  Path: 3 hops · Total confidence: 0.83
  Alternative paths: 2 found
```

Implementation:
- Arrange path nodes in a horizontal line, evenly spaced
- Draw thick coloured edges between them with link_type labels above
- Show confidence % below each edge
- Intermediate nodes labelled with entity name and type badge
- Non-path nodes (context) shown faded around the path
- "Show alternatives" button to cycle through alternative paths

### 5.8 Objective-Driven Layout Modes

Each objective should actively modify the graph layout and emphasis:

**Entity Neighbourhood (default):**
- Radial layout, centre node at middle
- All entity types visible, standard sizing

**Trial Evidence Map:**
- Trials and literature nodes enlarged (1.5×)
- Drug nodes at centre
- Non-trial/literature nodes faded (0.4 opacity)
- Edge colours emphasise INVESTIGATES and EVIDENCE_FOR

**Portfolio Network:**
- Company node at centre, enlarged
- Drug nodes arranged in arc below
- Trial nodes arranged in arc below drugs
- Other types faded
- OWNS edges highlighted (thicker, brighter)

**Mechanism Landscape:**
- Mechanism nodes at centre, arranged horizontally
- Drug nodes arranged radially around their mechanism
- TA nodes above
- Groups visually separated by spacing
- TARGETS_MECHANISM edges highlighted

---

## 6. Detail Panel Upgrade

### 6.1 Quick Inspect (Click, No Reload)

Replace the current "click = reload entire graph" behaviour with:

- **Single click:** Show quick inspect card (overlay, doesn't reload graph)
- **Double click:** Reload graph centred on this node (current behaviour)
- **Shift+click:** Open full detail drawer

Quick inspect card (positioned next to the clicked node):
```
┌──────────────────────────────────────┐
│  Semaglutide                    Drug │
│                                      │
│  Brand: Ozempic, Wegovy              │
│  Phase: 4 · Supply: Normal           │
│  Mechanism: GLP-1 Receptor Agonist   │
│                                      │
│  ── Connections (12) ────────────    │
│  ● 3 trials    ● 2 companies         │
│  ● 5 articles  ● 1 mechanism         │
│  ● 1 TA                              │
│                                      │
│  ── Top Links ───────────────────    │
│  → Novo Nordisk    OWNS       0.99   │
│  → GLP-1 Receptor  TARGETS    0.95   │
│  → Type 2 Diabetes TREATS     0.92   │
│                                      │
│  [Explore ↻]  [Details →]  [Chat 💬] │
└──────────────────────────────────────┘
```

### 6.2 Enhanced Detail Drawer

The existing drawer is functional but visually basic. Proposed enhancements:

**Header section:**
- Entity type icon + colour badge
- Full label (no truncation)
- Influence score as visual bar (0-100%)
- "Ask in Chat" button prominent

**Connection breakdown:**
- Visual bar chart (horizontal bars, coloured by link_type)
- Sorted by count descending
- Clickable — clicking a link type filters the graph to show only those edges

**Relationships table:**
- Sortable columns (link_type, target, confidence)
- Confidence shown as coloured badge (green ≥0.8, amber 0.5-0.8, red <0.5)
- "Load more" instead of hard cap at 14
- Clickable target entity → quick inspect

**Properties section (new):**
- Show all `node.properties` as key-value pairs
- Drug: brand_name, approval_date, supply_status, mechanism
- Company: ticker, CIK, country
- Trial: phase, status, sponsor, start_date, enrollment
- Literature: PMID, journal, publication_date

### 6.3 Graph Navigation Trail

Add a breadcrumb trail at the top of the graph canvas:

```
  Novo Nordisk → Semaglutide → GLP-1 Receptor → Diabetes
  [1]            [2]            [3]               [4]
```

- Clickable — jump back to any previous node
- Max 8 entries, oldest evicted
- Persists across graph reloads
- "Clear trail" button

---

## 7. Performance Improvements

### 7.1 Stop Infinite Animation Loop

ModernGraph's `render()` function runs `requestAnimationFrame` indefinitely. It should:
- Run 120-180 frames of force simulation
- Then stop, re-render only on interaction (pan, zoom, hover, click)
- Resume briefly if graph data changes

### 7.2 Batch Influence Loading

Instead of loading influence per-node on demand, batch-load when graph data arrives:
```typescript
// After traverse() returns:
const nodeIds = graphData.nodes.map(n => n.entity_id);
const influences = await api.batchInfluence(nodeIds); // New endpoint
// Apply to node rendering
```

New backend endpoint: `POST /graph/analytics/batch-influence` accepting `{entity_ids: string[]}`.

### 7.3 Node Cap Enforcement

Enforce max 30 rendered nodes (as GraphMini does) with intelligent selection:
1. Always include centre node
2. Include all nodes of the objective's preferred types
3. Include high-degree nodes (≥3 edges)
4. Fill remaining slots with highest-confidence neighbours
5. Show badge: "Showing 30 of 51 entities · [Show all]"

### 7.4 Edge Deduplication

The graph sometimes has duplicate edges (same source+target+link_type). Deduplicate on the frontend before rendering.

---

## 8. Component Architecture

### 8.1 New Component Structure

```
components/graph/
├── KnowledgeGraph.tsx        # Unified canvas renderer (replaces GraphMini + ModernGraph)
├── GraphControls.tsx         # Hops, objective, filters, path finder
├── NodeInspectCard.tsx       # Click-to-inspect overlay
├── NodeHoverTooltip.tsx      # Hover tooltip
├── PathVisualisation.tsx     # Linear path display mode
├── GraphNavigationTrail.tsx  # Breadcrumb trail
├── GraphDetailDrawer.tsx     # Enhanced detail panel
├── GraphSummaryStats.tsx     # Entities found, relationships, density
├── EdgeLegend.tsx            # Edge type legend with toggles
└── graph-constants.ts        # TYPE_COLORS, EDGE_COLORS, EDGE_LABELS (single source of truth)
```

### 8.2 Shared Constants

Currently `TYPE_COLORS` is defined 3 times (GraphMini, ModernGraph, GraphExplorer) with slightly different values. Extract to a single `graph-constants.ts`:

```typescript
export const NODE_COLORS: Record<string, string> = {
  drug: '#3b82f6',
  company: '#f59e0b',
  trial: '#14b8a6',
  therapeutic_area: '#f43f5e',
  mechanism: '#a78bfa',
  literature: '#22c55e',
  event: '#ef4444',
  investigator: '#06b6d4',
  patent: '#8b5cf6',
};

export const EDGE_COLORS: Record<string, string> = {
  OWNS: '#f59e0b',
  MANUFACTURES: '#f59e0b',
  SPONSORS: '#14b8a6',
  INVESTIGATES: '#3b82f6',
  EVIDENCE_FOR: '#22c55e',
  TARGETS_MECHANISM: '#a78bfa',
  IN_THERAPEUTIC_AREA: '#f43f5e',
  COMPETES_WITH: '#ef4444',
  HAS_MILESTONE: '#f59e0b',
  HAS_SIGNAL: '#ef4444',
  ASSOCIATED_WITH: '#64748b',
};

export const NODE_LABELS: Record<string, string> = { ... };
export const EDGE_LABELS: Record<string, string> = { ... }; // from brand.ts LINK_TYPE_LABELS
```

---

## 9. Implementation Phases

### Phase 1: Canvas Foundation (Week 1)
- Create unified `KnowledgeGraph.tsx` combining GraphMini + ModernGraph
- Dark background always
- Pan/zoom/reset viewport controls
- Node sizing by degree
- Labels for centre + high-degree + non-drug nodes
- Stop infinite animation loop (180 frames then pause)
- Extract shared `graph-constants.ts`
- **Outcome:** Graph immediately more readable and interactive

### Phase 2: Edge Semantics (Week 1-2)
- Per-link-type edge colouring (9 colours)
- Confidence-based width + opacity
- Edge arrowheads showing direction
- Edge hover tooltips (link_type + confidence + via)
- Interactive edge legend with toggles
- **Outcome:** Users can visually distinguish relationship types

### Phase 3: Node Intelligence (Week 2-3)
- Node hover card (entity properties + connection counts + influence)
- Single-click = quick inspect (no reload)
- Double-click = reload graph centred on node
- Shift+click = open detail drawer
- Batch influence loading on graph render
- Node sizing by influence score (not just degree)
- **Outcome:** Rich entity intelligence without leaving the graph

### Phase 4: Navigation & Path (Week 3-4)
- Graph navigation trail (breadcrumbs)
- Back button (undo last node navigation)
- Path visualisation mode (linear layout)
- Path confidence per hop displayed
- Alternative paths cycling
- **Outcome:** Graph traversal feels like navigating, not reloading

### Phase 5: Objective Layouts (Week 4-5)
- Trial Evidence Map layout (trials/literature emphasised)
- Portfolio Network layout (company → drugs → trials hierarchy)
- Mechanism Landscape layout (mechanism-grouped clusters)
- Smooth animated transitions between layouts
- **Outcome:** Each objective delivers a genuinely different visual experience

### Phase 6: Detail Panel Polish (Week 5-6)
- Enhanced detail drawer (influence bar, properties section, sortable relationships)
- Connection breakdown as horizontal bar chart
- Clickable relationship targets → quick inspect
- "Load more" pagination for relationships
- Export graph as PNG/SVG
- **Outcome:** Production-quality detail panel

---

## 10. Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Entity type visually distinguishable | Partial (monochrome for same-type neighbours) | 100% (colour + size + optional shape) | Visual inspection |
| Edge type visually distinguishable | 0% (all edges look the same) | 100% (colour + width + hover label) | Visual inspection |
| Node labels visible without hover | ~2% (centre only for > 20 nodes) | >60% (centre + high-degree + non-drug) | Count visible labels / total nodes |
| Click-to-inspect without reload | 0% (every click reloads) | 100% (single click = inspect) | Interaction test |
| Path visualisation quality | Text badge only ("3 hops") | Full linear path with edge labels | Feature presence |
| Pan/zoom on main graph | Not available | Full (drag, wheel, keyboard, buttons) | Feature presence |
| Influence score visibility | Not shown | On hover card + node sizing | Feature presence |
| Navigation trail | Not available | 8-entry breadcrumb | Feature presence |
| Graph components | 2 duplicated (GraphMini + ModernGraph) | 1 unified (KnowledgeGraph) | Code audit |
| TYPE_COLORS definitions | 3 duplicated copies | 1 shared constants file | Code audit |

---

## 11. Cross-References

| File | Relevance |
|------|-----------|
| `frontend/src/components/ModernGraph.tsx` | Replaced by KnowledgeGraph |
| `frontend/src/components/GraphMini.tsx` | Replaced by KnowledgeGraph |
| `frontend/src/components/GraphExplorer.tsx` | Major refactor: interaction model, detail drawer, layout modes |
| `frontend/src/brand.ts` | LINK_TYPE_LABELS, SOURCE_LABELS — migrate to graph-constants.ts |
| `frontend/src/api.ts` | New batch-influence endpoint, GraphNode type (add influence field) |
| `services/graph.py` | traverse(), path_between(), entity_summary() — unchanged |
| `services/graph_analytics.py` | entity_influence(), weighted_path(), competitive_clusters() — newly surfaced |
| `api/routes/graph.py` | New POST /graph/analytics/batch-influence endpoint |
| `SPEC-004 (UI Upgrade)` | G7 (graph isolation) addressed here; G10 (dark mode) aided by dark-always canvas |
| `SPEC-006 (Search Restructure)` | Graph cross-navigation, unified KnowledgeGraph shared with search EntityPreview |

---

## 12. Appendix: Colour Palette Reference

### Node Colours (on dark `#0f172a` background)

| Type | Hex | Preview Use |
|------|-----|-------------|
| Drug | `#3b82f6` | Primary entities — most common |
| Company | `#f59e0b` | Corporate entities |
| Trial | `#14b8a6` | Clinical evidence |
| Ther. Area | `#f43f5e` | Disease categories |
| Mechanism | `#a78bfa` | Biological targets |
| Literature | `#22c55e` | Published evidence |
| Event | `#ef4444` | Market events |
| Investigator | `#06b6d4` | People |
| Patent | `#8b5cf6` | IP assets |

### Edge Colours

| Relationship | Hex | Semantic Group |
|-------------|-----|----------------|
| OWNS / MANUFACTURES | `#f59e0b` | Ownership (amber) |
| SPONSORS | `#14b8a6` | Sponsorship (teal) |
| INVESTIGATES | `#3b82f6` | Clinical (blue) |
| EVIDENCE_FOR | `#22c55e` | Literature (green) |
| TARGETS_MECHANISM | `#a78bfa` | Biology (violet) |
| IN_THERAPEUTIC_AREA | `#f43f5e` | Disease (rose) |
| COMPETES_WITH | `#ef4444` | Competition (red) |
| HAS_MILESTONE | `#f59e0b` | Regulatory (amber) |
| ASSOCIATED_WITH | `#64748b` | Generic (slate) |

---

*End of SPEC-007*
