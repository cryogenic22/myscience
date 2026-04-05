# SPEC-006: Search Section Restructure — Surfacing the Knowledge Graph

*Author: Architecture Review · Date: 2026-03-28*
*Scope: Search UX redesign, graph-first results, connection display, query types, output enrichment*

---

## 1. Executive Summary

Market Zero sits on a genuinely powerful intelligence layer: pgvector semantic search across 6 entity types, a knowledge graph with recursive CTE traversal (1–4 hops), confidence-weighted Dijkstra path finding, competitive cluster detection, influence scoring, and 12 relationship types connecting drugs, companies, trials, mechanisms, therapeutic areas, and literature. The backend can answer questions that most pharma intelligence tools cannot.

The search section does not yet show this. Currently it presents a flat list of entity cards ranked by cosine similarity — essentially a "better keyword search" — and hides the graph, connections, and intelligence behind a collapsible side panel that most users will never expand. The system's most differentiating capabilities (path finding, influence scoring, competitive clusters, multi-hop traversal) are invisible from the search page and only accessible via the separate GraphExplorer component, which has no integration with search results.

This spec proposes restructuring the search experience around three principles:

1. **Graph-first results** — every search result should immediately show its connections, not just its metadata. The knowledge graph is the product's moat; it should be the default view, not a hidden panel.

2. **Question-type routing** — the search bar should recognise different question types (entity lookup, relationship query, comparison, analytical) and adapt the results layout accordingly. A user typing "path between semaglutide and Novo Nordisk" should see a path visualisation, not a list of cards.

3. **Progressive depth** — surface the most important intelligence upfront (connections, influence, clusters) and let users drill down into raw data, evidence, and full graph exploration on demand.

---

## 2. Current State Assessment

### 2.1 What Works Well

The existing search section is technically solid and well-engineered:

- **Responsive, modular components** — SearchPage (732 lines), EntityPreview (1058 lines), SearchResults (491 lines), SearchFilters (250 lines) are cleanly separated with lifted state
- **Three view modes** — cards, grid, list with client-side sort (relevance, quality, recency)
- **Entity type filtering** — 5 type pills (drug, trial, literature, company, therapeutic_area) with therapeutic area faceting
- **EntityPreview side panel** — rich: key metrics, connections, knowledge graph (GraphMini), recent evidence, provenance, "Ask in Chat" action
- **Graph caching** — useRef Map prevents redundant graph API calls
- **Keyboard navigation** — arrow keys in graph neighbour list
- **Design system compliance** — CSS custom properties, inline styles, no Tailwind colour utilities

### 2.2 What Falls Short

| Gap | Description | Impact |
|-----|-------------|--------|
| **Flat result list** | Results ranked by cosine similarity only — no graph context, no connection counts, no influence scores in the card | Users see a Google-style list when they should see an intelligence map |
| **Graph hidden by default** | EntityPreview's knowledge graph is collapsed, requiring 2 clicks to see | The platform's core differentiator is invisible |
| **No query type routing** | Search bar treats every query identically — "semaglutide" and "path between semaglutide and diabetes" get the same flat list | Misses opportunity to show relationships, paths, clusters |
| **No faceted counts** | Backend computes per-type results but doesn't return facet counts in the response | User can't see "42 drugs, 18 trials, 7 articles" before filtering |
| **No influence/centrality signals** | `entity_influence()` and `entity_centrality_batch()` exist but are never called from search | High-impact entities look the same as obscure ones |
| **GraphExplorer disconnected** | Full graph explorer (path finding, objectives, Dijkstra weighted paths) is a separate page with no cross-navigation from search results | Two graph experiences that don't talk to each other |
| **No "similar entities"** | `find_similar()` endpoint exists but is never called from search UI | Users can't discover related entities |
| **No relationship search** | Can't search for "drugs that target GLP-1" or "companies with Phase 3 trials" — only text similarity | Misses the most valuable pharma intelligence queries |
| **Events excluded** | Event entity type has no embedding column, so events are invisible in search | Market events (FDA actions, approvals, shortages) can't be found |
| **No search suggestions** | No autocomplete, no query history, no "did you mean" | Cold start problem — users don't know what to search for |
| **Pagination-only** | PAGE_SIZE = 30 with prev/next buttons, no infinite scroll, no "load more" | Friction for exploratory browsing |
| **No query embedding cache** | Every search re-calls OpenAI embedding API | Repeated queries cost money and add 200-400ms latency |

### 2.3 Existing Backend Capabilities NOT Surfaced

| Capability | Backend Location | Current Frontend Usage |
|------------|-----------------|----------------------|
| `entity_influence()` | `services/graph_analytics.py:32` | GraphExplorer only |
| `competitive_clusters()` | `services/graph_analytics.py:88` | GraphExplorer only |
| `weighted_path()` | `services/graph_analytics.py:174` | GraphExplorer only |
| `entity_centrality_batch()` | `services/graph_analytics.py:323` | Not used anywhere |
| `find_similar()` | `services/search.py:302` | Not used in search UI |
| `drugs_by_mechanism_class()` | `services/graph.py:310` | Not used in search UI |
| `mechanism_hierarchy()` | `services/graph.py:330` | Not used in search UI |
| `rank_by_recency()` | `services/search.py:170` | Not used (sort is client-side) |
| Path finding (BFS + Dijkstra) | `services/graph.py:142`, `graph_analytics.py:174` | GraphExplorer only |
| `recency_score()` | `services/search.py:140` | Not used |

---

## 3. Search Query Types

The restructured search should recognise and route 6 distinct query types, each with an optimised results layout.

### 3.1 Query Type Detection

```
User Input
     │
     ▼
┌──────────────────────────┐
│  Search Query Classifier │  (frontend, pre-API)
│                          │
│  1. PATH query?          │  "path between X and Y", "connection from X to Y"
│  2. RELATIONSHIP query?  │  "drugs targeting GLP-1", "companies with Phase 3"
│  3. COMPARISON query?    │  "X vs Y", "compare X and Y"
│  4. CLUSTER query?       │  "competitive clusters in oncology", "market map"
│  5. ENTITY query?        │  Short (1-4 words), entity name pattern
│  6. EXPLORATORY query    │  Everything else — natural language question
│                          │
└──────────────────────────┘
```

### 3.2 Query Types and Expected Outputs

#### Type 1: ENTITY (default)
**Trigger:** Short queries (1-4 words), entity names, "what is X"
**Examples:** "semaglutide", "Novo Nordisk", "GLP-1 agonists"
**API call:** `POST /search` (existing)
**Results layout:** Entity cards with embedded connection preview (not flat cards)
**Canvas:** EntityPreview with graph auto-expanded

#### Type 2: RELATIONSHIP
**Trigger:** Structural patterns — "drugs that [verb]", "[type] with [condition]", "[type] linked to [entity]"
**Examples:** "drugs targeting GLP-1 receptor", "companies with obesity pipeline", "trials investigating semaglutide"
**API call:** `POST /search` with entity_type filter + graph post-filter
**Results layout:** Grouped by relationship type, showing link confidence
**Canvas:** Relationship map (mini graph centred on the relationship pattern)

#### Type 3: PATH
**Trigger:** "path between", "connection from X to Y", "how is X related to Y", "link between"
**Examples:** "path between semaglutide and cardiovascular disease", "how is Novo Nordisk connected to SGLT2"
**API call:** `GET /graph/analytics/weighted-path` + entity resolution
**Results layout:** Path visualisation (horizontal node chain with edge labels)
**Canvas:** Full path graph with confidence scores per hop

#### Type 4: COMPARISON
**Trigger:** "X vs Y", "compare X and Y", "differences between"
**Examples:** "semaglutide vs tirzepatide", "compare Novo Nordisk and Eli Lilly"
**API call:** `POST /search` for both entities + `GET /graph/traverse` for both
**Results layout:** Side-by-side entity cards + shared/unique connections
**Canvas:** Compare graph (shared connections highlighted)

#### Type 5: CLUSTER
**Trigger:** "clusters", "competitive map", "market segments", "who competes with"
**Examples:** "competitive clusters in diabetes", "market map for GLP-1", "who competes in obesity"
**API call:** `GET /graph/analytics/clusters` + optional mechanism/TA filter
**Results layout:** Cluster cards with member entities
**Canvas:** Cluster graph (grouped nodes by mechanism)

#### Type 6: EXPLORATORY (fallback)
**Trigger:** Natural language questions, long queries, analytical queries
**Examples:** "what are the latest developments in SGLT2 inhibitors?", "which drugs have the highest pipeline scores?"
**API call:** `POST /search` (vector similarity) + enrichment
**Results layout:** Standard entity cards with insight strip
**Canvas:** EntityPreview for selected result

---

## 4. Results Display Architecture

### 4.1 Entity Card Redesign

**Current card:** Title + type badge + snippet + quality score
**Proposed card:** Title + type badge + connection bar + influence indicator + snippet

```
┌─────────────────────────────────────────────────┐
│  💊 Semaglutide                    Influence: ●●●●○  │
│  Drug · GLP-1 Receptor Agonist                       │
│                                                       │
│  ┌──────────────────────────────────────────────┐    │
│  │  ●12 trials  ●3 companies  ●47 articles      │    │
│  │  ●2 mechanisms  ●4 therapeutic areas          │    │
│  └──────────────────────────────────────────────┘    │
│                                                       │
│  Semaglutide is a glucagon-like peptide-1 agonist    │
│  approved for type 2 diabetes and obesity...          │
│                                                       │
│  Similar: tirzepatide, liraglutide, dulaglutide      │
│  Cosine similarity: 0.89  ·  Quality: 0.85          │
└─────────────────────────────────────────────────┘
```

**New data per card (requires 2 API enrichments):**

1. **Connection bar** — counts by entity type from `entity_summary()` (already exists, just not called per-result)
2. **Influence indicator** — from `entity_influence()` (normalised 0-1, shown as 5 dots)
3. **Similar entities strip** — from `find_similar()` (top 3 names, loaded lazily)

### 4.2 Faceted Search Sidebar

Replace the current type-pill toolbar with a proper faceted sidebar:

```
┌─────────────────┐
│  ENTITY TYPES    │
│  ● Drug      42  │
│  ● Trial     18  │
│  ● Literature  7 │
│  ● Company    5  │
│  ● Mechanism   3 │
│  ● Ther. Area  2 │
│                   │
│  THERAPEUTIC AREA │
│  ● Diabetes   28  │
│  ● Obesity    15  │
│  ● Cardio      9  │
│  ● Oncology    4  │
│                   │
│  MECHANISM        │
│  ● GLP-1      12  │
│  ● SGLT2       8  │
│  ● DPP-4       6  │
│                   │
│  SOURCE           │
│  ● ClinicalTrials 22│
│  ● PubMed      15 │
│  ● FDA          8 │
│  ● SEC          3 │
│                   │
│  DATA FRESHNESS   │
│  ● < 30 days  14  │
│  ● 1-6 months 28  │
│  ● > 6 months 15  │
└─────────────────┘
```

**Backend change required:** Add `facets` field to SearchResponse:
```python
{
  "results": [...],
  "total": 77,
  "facets": {
    "entity_type": {"drug": 42, "trial": 18, "literature": 7, ...},
    "therapeutic_area": {"Diabetes": 28, "Obesity": 15, ...},
    "mechanism": {"GLP-1 Receptor Agonist": 12, ...},
    "source_api": {"clinical_trials": 22, "pubmed": 15, ...},
    "freshness": {"recent": 14, "moderate": 28, "stale": 15}
  }
}
```

### 4.3 Graph-First Inspector

The current EntityPreview has the knowledge graph collapsed by default. Restructure to show graph first:

```
┌───────────────────────────────────────────────────┐
│  Semaglutide — Entity Profile                      │
│  Drug · GLP-1 Receptor Agonist · ●●●●○ Influence  │
├───────────────────────────────────────────────────┤
│                                                     │
│  ┌─────────────────────────────────────────────┐   │
│  │          KNOWLEDGE GRAPH                     │   │
│  │     (GraphMini — auto-expanded, 320px)       │   │
│  │                                               │   │
│  │    [Novo Nordisk]──OWNS──●[Semaglutide]●     │   │
│  │                           │    │              │   │
│  │               INVESTIGATES│    │TARGETS       │   │
│  │                           │    │              │   │
│  │              [NCT04...]   [GLP-1 Receptor]   │   │
│  │                                               │   │
│  └─────────────────────────────────────────────┘   │
│                                                     │
│  ── Key Metrics ──────────────────────────────     │
│  12 trials · 3 companies · 47 articles · Phase 4   │
│                                                     │
│  ── Top Connections ──────────────────────────     │
│  ●  Novo Nordisk          OWNS         0.99        │
│  ●  GLP-1 Receptor        TARGETS      0.95        │
│  ●  Type 2 Diabetes       TREATS       0.92        │
│  ●  NCT04082042           INVESTIGATES 0.88        │
│  ●  Obesity               TREATS       0.85        │
│     Show all 67 connections →                       │
│                                                     │
│  ── Similar Entities ─────────────────────────     │
│  tirzepatide (0.91) · liraglutide (0.87) · ...     │
│                                                     │
│  ── Actions ──────────────────────────────────     │
│  [Ask in Chat]  [Full Graph Explorer]  [Compare]   │
└───────────────────────────────────────────────────┘
```

### 4.4 Path Visualisation (new component)

For PATH queries, render as horizontal chain:

```
┌───────────────────────────────────────────────────────┐
│  Path: Semaglutide → Cardiovascular Disease            │
│  3 hops · Confidence: 0.78                             │
│                                                         │
│  ●────────TARGETS────────●───TREATS───●──ASSOCIATED──● │
│ Sema-    (0.95)     GLP-1   (0.92)  T2D   (0.72)  CVD │
│ glutide            Receptor        Diabetes             │
│                                                         │
│  Alternative paths: 2 found                             │
│  Path 2: Semaglutide → Novo Nordisk → CVD trials (4 hops)│
└───────────────────────────────────────────────────────┘
```

### 4.5 Comparison Layout (new component)

For COMPARISON queries, side-by-side with shared connections:

```
┌──────────────────────┬──────────────────────┐
│  Semaglutide         │  Tirzepatide         │
│  Drug · GLP-1        │  Drug · GLP-1/GIP    │
│  Influence: ●●●●○    │  Influence: ●●●○○    │
├──────────────────────┴──────────────────────┤
│               SHARED CONNECTIONS             │
│  ● Type 2 Diabetes (TREATS)                  │
│  ● Obesity (TREATS)                          │
│  ● GLP-1 Receptor (TARGETS)                 │
├──────────────────────┬──────────────────────┤
│  UNIQUE TO SEMA      │  UNIQUE TO TIRZE     │
│  ● Cardiovascular    │  ● GIP Receptor      │
│  ● NASH/MASH         │  ● Dual agonist      │
│  ● Novo Nordisk      │  ● Eli Lilly         │
├──────────────────────┴──────────────────────┤
│               METRICS COMPARISON             │
│  Pipeline Score:   87  vs  72                │
│  Active Trials:    12  vs   8                │
│  Publications:     47  vs  23                │
│  Phase:             4  vs   3                │
└─────────────────────────────────────────────┘
```

### 4.6 Cluster View (new component)

For CLUSTER queries, grouped node layout:

```
┌─────────────────────────────────────────────────┐
│  Competitive Clusters: GLP-1 in Diabetes         │
│  HHI: 2,847 (Highly Concentrated) · 4 clusters  │
├──────────┬──────────┬──────────┬────────────────┤
│ Cluster 1│ Cluster 2│ Cluster 3│ Cluster 4      │
│ GLP-1 RA │ SGLT2i   │ DPP-4i   │ Insulin        │
│          │          │          │                │
│ •Sema    │ •Dapa    │ •Sita    │ •Insulin       │
│ •Tirze   │ •Empa    │ •Lina    │  glargine      │
│ •Lira    │ •Cana    │ •Saxa    │ •Degludec      │
│ •Dula    │          │          │                │
│          │          │          │                │
│ 12 drugs │ 8 drugs  │ 6 drugs  │ 4 drugs        │
│ 34 trials│ 22 trials│ 15 trials│ 8 trials       │
└──────────┴──────────┴──────────┴────────────────┘
```

---

## 5. Search Intelligence Features

### 5.1 Search Suggestions / Autocomplete

Add typeahead suggestions combining:
1. **Entity name prefix match** — `GET /entities/{type}?search=sema` across all types
2. **Recent searches** — stored in localStorage (session-scoped)
3. **Curated starter queries** — 10-15 high-value queries showing system capabilities

**Implementation:** New `GET /search/suggest?q=sema&limit=8` endpoint that queries entity labels with trigram similarity.

### 5.2 "Did You Mean?" for Low-Confidence Results

When search returns < 3 results with similarity > 0.7, show:
- "Did you mean **semaglutide**?" (fuzzy entity match)
- "Try: GLP-1 competitive landscape" (suggested reformulation)

### 5.3 Influence-Ranked Results

Add optional sort mode: "By influence" — uses `entity_centrality_batch()` to rank results by graph centrality rather than cosine similarity. This surfaces the most connected and important entities first.

### 5.4 "Related Searches" Strip

After results load, show:
```
Related: [GLP-1 landscape] [semaglutide vs tirzepatide] [Novo Nordisk portfolio] [diabetes pipeline]
```

Generated from:
- Entity type of top result → standard queries for that type
- Connected entities from graph → "path between X and Y"
- Mechanism/TA of top result → "competitive clusters in {TA}"

### 5.5 Evidence Density Indicator

Each result card shows evidence density: how many evidence items (literature, trials, events) are connected. Fetched from `evidence_density()` or computed from graph edge count.

```
Evidence: ████████░░ 47 items (strong)
Evidence: ███░░░░░░░ 12 items (moderate)
Evidence: █░░░░░░░░░  3 items (sparse)
```

### 5.6 Event Integration

Currently events have no embedding and are invisible in search. Two paths:

**Option A (quick):** Add a "Recent Events" section below search results that queries the `market_events` table with text ILIKE matching.

**Option B (proper):** Backfill event embeddings by concatenating `event_type + headline + entity_name` and embedding via OpenAI. Then events appear in normal search results.

Recommendation: Option B, as events are the most time-sensitive intelligence in the system.

---

## 6. Graph Integration Strategy

### 6.1 Merge GraphExplorer Into Search

Currently GraphExplorer is a separate page (766+ lines) with its own entity lookup, objectives (Adjacency, Trial Evidence Map, Portfolio Network, Mechanism Landscape), path finding, and graph rendering.

**Proposal:** Keep GraphExplorer as a dedicated "deep mode" but integrate its key features into the search inspector:

| GraphExplorer Feature | Integration Into Search |
|----------------------|------------------------|
| Entity lookup + suggestions | Use search bar (already exists) |
| 4 objective modes | Add as graph view presets in EntityPreview |
| Path finding (from → to) | Route PATH queries to path visualisation |
| Weighted paths | Show in path results |
| Dijkstra routing | Available via "Find path to..." action button |
| Node type/link type filtering | Already in EntityPreview (edge type filter) |

### 6.2 Cross-Navigation

Add seamless transitions between search and graph:

- **Search result → Graph:** "Explore in Graph" button opens GraphExplorer pre-loaded with that entity
- **Graph node → Search:** Right-click or long-press a graph node → "Search for this entity"
- **Path result → Graph:** "View full graph" expands path into GraphExplorer with both endpoints loaded
- **Cluster → Graph:** Click cluster → opens GraphExplorer with mechanism filter preset

### 6.3 Graph Mini Improvements

The current GraphMini (583 lines, canvas-based force simulation) is well-built but could be enhanced:

| Enhancement | Description |
|-------------|-------------|
| **Edge labels on hover** | Show link_type when hovering over an edge (currently only nodes have hover) |
| **Confidence opacity** | Edge opacity proportional to confidence (0.5 → faint, 1.0 → solid) |
| **Cluster colouring** | If nodes belong to different competitive clusters, use cluster colour |
| **Node size by influence** | Scale node radius by `entity_influence()` score |
| **Double-click to focus** | Double-click a node → it becomes centre, graph reloads around it |
| **Right-click context menu** | "Ask in Chat", "Find path to...", "View dossier", "Compare with..." |

---

## 7. Backend Enhancements Required

### 7.1 New Endpoints

**`GET /search/suggest`**
- Query: `q` (string, min 2 chars), `limit` (default 8)
- Response: `{suggestions: [{label, entity_type, entity_id, match_type}]}`
- Implementation: Trigram similarity on entity labels, sorted by similarity × influence

**`POST /search/enriched`**
- Like `/search` but includes per-result enrichment:
  - `connection_counts`: `{entity_type: count}` per result
  - `influence_score`: float (0-1)
  - `similar_entities`: top 3 labels
- Implementation: Batch `entity_summary()` + `entity_centrality_batch()` after search

**`GET /search/facets`**
- Query: `q` (search query), `entity_types` (filter)
- Response: Facet counts by entity_type, therapeutic_area, mechanism, source, freshness
- Implementation: COUNT queries grouped by relevant columns

### 7.2 Existing Endpoint Changes

**`POST /search` → add `facets` to response**
- Include facet counts in standard search response (reduces round trips)

**`GET /graph/analytics/clusters` → add `entity_details`**
- Include entity labels and types within each cluster (currently returns IDs only)

### 7.3 Performance Optimisations

**Query embedding cache:**
- Cache query → embedding mapping in Redis or in-memory LRU (128 entries)
- Same query within 1 hour returns cached embedding
- Saves ~200ms and API cost per repeated search

**Batch entity enrichment:**
- New internal `_batch_enrich_results()` that runs 1 SQL query for all result IDs
- Instead of N separate `entity_summary()` calls
- Uses `WHERE entity_id = ANY($1::uuid[])` for single round-trip

**ANN index consideration:**
- At current scale (~100k entities), exact cosine is fine
- At >500k, add IVFFlat or HNSW index on embedding columns
- Monitor via `pg_stat_user_indexes`

---

## 8. Frontend Component Plan

### 8.1 New Components

| Component | Purpose | Lines (est.) |
|-----------|---------|-------------|
| `SearchQueryClassifier.ts` | Client-side query type detection (regex patterns) | ~80 |
| `EnrichedResultCard.tsx` | Entity card with connection bar + influence | ~180 |
| `PathVisualisation.tsx` | Horizontal path chain with confidence scores | ~250 |
| `ComparisonView.tsx` | Side-by-side entity comparison layout | ~300 |
| `ClusterView.tsx` | Grouped cluster cards | ~200 |
| `FacetSidebar.tsx` | Faceted filter sidebar with counts | ~150 |
| `SearchSuggestions.tsx` | Typeahead dropdown with entity/history/curated | ~120 |
| `RelatedSearches.tsx` | Horizontal strip of related query pills | ~60 |
| `EvidenceDensityBar.tsx` | Mini bar showing evidence strength | ~30 |

### 8.2 Modified Components

| Component | Changes |
|-----------|---------|
| `SearchPage.tsx` | Add query classifier, route to different result layouts, integrate facet sidebar |
| `EntityPreview.tsx` | Graph auto-expanded by default, add "Find path to...", add "Compare with..." |
| `SearchResults.tsx` | Accept query type prop, render different layouts per type |
| `SearchFilters.tsx` | Replace type pills with facet counts from API |
| `GraphMini.tsx` | Add edge labels, confidence opacity, double-click focus |

### 8.3 Component Hierarchy (Proposed)

```
SearchPage
├── SearchBar + SearchSuggestions
├── FacetSidebar (left)
├── Results Area (centre)
│   ├── QueryType: ENTITY → EnrichedResultCard[]
│   ├── QueryType: PATH → PathVisualisation
│   ├── QueryType: COMPARISON → ComparisonView
│   ├── QueryType: CLUSTER → ClusterView
│   ├── QueryType: RELATIONSHIP → EnrichedResultCard[] (grouped by relation)
│   └── QueryType: EXPLORATORY → EnrichedResultCard[] + InsightStrip
├── RelatedSearches (below results)
└── EntityPreview (right inspector)
    ├── GraphMini (auto-expanded)
    ├── Key Metrics
    ├── Top Connections (sorted by confidence)
    ├── Similar Entities
    └── Action Buttons
```

---

## 9. Search Query Classifier (Client-Side)

```typescript
type SearchQueryType = 'entity' | 'relationship' | 'path' | 'comparison' | 'cluster' | 'exploratory';

function classifySearchQuery(query: string): SearchQueryType {
  const q = query.toLowerCase().trim();

  // PATH: explicit path/connection language
  if (/\b(path between|connection from|how is .+ (related|connected) to|link between)\b/.test(q))
    return 'path';

  // COMPARISON: vs / compare patterns
  if (/\b(compare|vs\.?|versus|differences? between)\b/.test(q))
    return 'comparison';

  // CLUSTER: competitive grouping language
  if (/\b(clusters?|competitive map|market (map|segments)|who competes)\b/.test(q))
    return 'cluster';

  // RELATIONSHIP: structural queries
  if (/\b(drugs? (that|which)|companies? (that|with)|trials? (for|investigating|studying))\b/.test(q))
    return 'relationship';
  if (/\b(targeting|linked to|associated with|owned by|manufactured by)\b/.test(q))
    return 'relationship';

  // ENTITY: short, likely a name
  if (q.split(/\s+/).length <= 4 && !/\b(how|why|when|where|which|what|who|is|are|do|does|can|show|list)\b/.test(q))
    return 'entity';

  return 'exploratory';
}
```

---

## 10. Implementation Phases

### Phase 1: Enriched Cards + Facets (Week 1-2)
- Add `facets` to search API response
- Build `FacetSidebar` component
- Build `EnrichedResultCard` with connection counts and influence dots
- Add `POST /search/enriched` endpoint with batch entity enrichment
- Auto-expand graph in EntityPreview
- **Outcome:** Search immediately shows the graph's power on every result card

### Phase 2: Search Suggestions + Query Routing (Week 2-3)
- Build `SearchQueryClassifier.ts`
- Build `SearchSuggestions.tsx` with typeahead
- Add `GET /search/suggest` endpoint
- Route ENTITY, COMPARISON, and EXPLORATORY queries to appropriate layouts
- Build `ComparisonView.tsx` for side-by-side display
- **Outcome:** Different question types get different, optimised result layouts

### Phase 3: Path + Cluster Views (Week 3-4)
- Build `PathVisualisation.tsx`
- Build `ClusterView.tsx`
- Integrate with existing `weighted_path()` and `competitive_clusters()` endpoints
- Add "Find path to..." action button in EntityPreview
- Route PATH and CLUSTER queries to dedicated views
- **Outcome:** The platform's most unique capabilities are now searchable

### Phase 4: Graph Enhancements (Week 4-5)
- GraphMini: edge labels on hover, confidence-based opacity, double-click focus
- Cross-navigation: search → graph explorer → search (seamless)
- "Related Searches" strip below results
- Event embedding backfill + event search integration
- Evidence density bar on result cards
- **Outcome:** Graph exploration is fluid and interconnected

### Phase 5: Performance + Polish (Week 5-6)
- Query embedding cache (LRU, 128 entries)
- Batch entity enrichment (single SQL query)
- Infinite scroll or "load more" to replace pagination
- View mode persistence (localStorage)
- Sort stability (secondary sort on entity_id for ties)
- Mobile-optimised facet sidebar (drawer on small screens)
- **Outcome:** Production-ready, performant search

---

## 11. Success Metrics

| Metric | Current | Target | Measurement |
|--------|---------|--------|-------------|
| Time to first graph insight | ~8s (expand panel, wait for load) | <2s (auto-expanded) | Interaction timing |
| Connection visibility | 0% (hidden by default) | 100% (on every card) | Default rendering |
| Query types supported | 1 (text similarity) | 6 (entity, relationship, path, comparison, cluster, exploratory) | Feature count |
| Faceted filtering | Type pills only (5 types) | 4 facet dimensions with counts | Feature count |
| Search suggestion coverage | 0 (no suggestions) | Entity prefix + history + curated | Feature availability |
| Backend capabilities surfaced | 3/10 | 10/10 | Feature audit |
| Average search-to-answer time | ~12s (search + click + expand + read) | <5s (graph visible on card) | Task completion timing |

---

## 12. Cross-References

| File | Relevance |
|------|-----------|
| `services/search.py` | HybridSearch, find_similar, recency_score — all needed |
| `services/graph.py` | GraphTraversal, entity_summary, path_between — integration points |
| `services/graph_analytics.py` | entity_influence, competitive_clusters, weighted_path, centrality — key features to surface |
| `services/query_engine.py` | QueryEngine.compare_entities — used for COMPARISON queries |
| `frontend/src/components/search/*` | All 5 files modified or extended |
| `frontend/src/components/GraphMini.tsx` | Enhanced with edge labels, confidence opacity |
| `frontend/src/components/GraphExplorer.tsx` | Cross-navigation integration |
| `frontend/src/components/ModernGraph.tsx` | Canvas graph shared with GraphExplorer |
| `api/routes/search.py` | New endpoints: /suggest, /enriched, /facets |
| `api/routes/graph.py` | Enhanced cluster response with entity details |
| `SPEC-004 (UI Upgrade)` | G7 (graph isolation) directly addressed here |
| `SPEC-005 (Chat Analysis)` | E19 (interactive tables), E21 (suggested queries) overlap |

---

*End of SPEC-006*
