# Market Zero — Feature Testing Guide

**URL**: https://myscience-production.up.railway.app
**Date**: 2026-04-01

---

## 1. Entity Library (Data Quality tab)

### How to access:
1. Go to `/workspace`
2. Click **"Entity Library"** tab in the top navigation

### Test: Supply Chain Flow Strip
- Click **"Data Quality"** sub-tab (or "Overview" if in admin mode)
- You should see: **Sources → Records → Entities → Connections** flow strip at top
- Numbers show: 15 Sources (8 active), total records, total entities, 1.4M connections

### Test: Connector Status Cards
- Below the flow strip, see **Data Pipeline** grid
- Each card shows: connector name, status badge (Live/OK/Stale/Awaiting), records, last run
- **Click a connector card** → rich **SourceProfileCard** slides in from right showing:
  - Entity breakdown (which entity types this source produces)
  - Field completeness bars (per-field fill percentages)
  - Steward activity log
  - Cross-source connections
  - "Refresh Now" button

### Test: Entity Profiles
- Click **"Library"** sub-tab
- Browse entities (drugs, companies, trials, mechanisms, TAs)
- **Click any entity** → rich **EntityProfileCard** slides in showing:
  - FAIR Score with 5 dimensions (Completeness, Link Density, Source Diversity, Freshness, Resolution)
  - AI Readiness badges (Embedding ✓/✗, Linked ✓/✗, Resolved ✓/✗)
  - Identity fields (name, brand, approval date, etc.)
  - Connections grouped by entity type with sample names
  - Evidence trail (linked literature/trials)
  - Provenance sources (which data sources contributed)
  - Recent changes
  - "Ask in Chat" and "Explore Graph" action buttons

### Test: Quality Bars on Entity Cards
- In the Browse grid, each entity card shows a thin **colored quality bar**
- Green = ≥70%, Amber = ≥40%, Red = <40%

### Test: Agentic Curation
- Switch to admin mode (if available) and click **"Curation"** tab
- See **Data Steward Agent** section at top:
  - Green pulsing dot + "N actions this week"
  - Recent agent activity log
  - "Run Steward Now" and "Refresh All Sources" buttons
- Below: HITL queue with bulk approve/reject

---

## 2. Knowledge Graph Explorer

### How to access:
1. Go to `/workspace`
2. Click **"Graph"** tab

### Test: Interactive Graph
- Search for an entity (e.g., "semaglutide") in the left panel
- Click a suggestion → graph loads with **KnowledgeGraph** renderer
- **Pan**: drag the canvas with mouse
- **Zoom**: scroll wheel or +/- buttons (bottom right)
- **Reset**: click ⟲ or press 0
- **Hover**: move mouse over a node → tooltip shows name, type, connections
- **Node type pills**: top-left toggle buttons to hide/show entity types
- **Edge legend**: bottom-left shows relationship types with toggles
- **Node count badge**: top-right shows "N entities · M connections"

### Test: Graph Node Click
- Click any node → left panel shows entity detail
- Node details include: properties, connections, evidence

### Test: Loading Indicator
- While graph is loading, see dark overlay with spinner + "Loading graph..."

---

## 3. Chat (Workspace)

### How to access:
1. Go to `/workspace` (default tab is Chat)

### Test: Entity Mention Highlighting
- Ask: "Tell me about semaglutide"
- In the response, **drug names appear in blue**, **company names in amber**, **mechanisms in violet**
- These are colored inline spans with subtle underlines

### Test: Follow-up Suggestions
- After a response, see follow-up suggestion pills below the narrative
- Click one → sends that query

### Test: Citations
- Responses include **superscript citation numbers** [1], [2], etc.
- These link to evidence items

---

## 4. Search

### How to access:
1. Go to `/search`

### Test: Entity Preview with Graph
- Search for "semaglutide"
- Click a result → right panel shows entity preview
- The preview includes an **interactive KnowledgeGraph** (compact mode)
- Pan/zoom works in the preview graph

---

## 5. Intelligence Feed

### How to access:
1. Go to `/workspace`
2. Click **"Feed"** tab

### Test: Intelligence Events
- See recent intelligence events from pharma news
- Each event shows severity, description, source

---

## 6. API Testing (Direct)

### Entity Profile API
```
GET /catalog/entity-profile/drug/{drug_uuid}
```
Returns: FAIR scores, AI readiness, connections, evidence, provenance, changes

### Source Profile API
```
GET /catalog/source-profile/clinical_trials_gov
```
Returns: health, entity breakdown, field completeness, steward activity

### Pipeline Status
```
GET /catalog/pipeline-status
```
Returns: all 15 connectors with status, records, freshness

### Graph Traversal
```
GET /graph/traverse/drug/{drug_uuid}?hops=1&max_nodes=30
```
Returns: nodes + edges for the entity's neighborhood

### Steward Status
```
GET /steward/status
```
Returns: total actions, last completed run

---

## Known Issues

1. **High-connectivity graph traversal 500**: Traversing a therapeutic area with `hops=2` may timeout for high-connectivity nodes (e.g., Diabetes with 500+ connections). Use `hops=1` or `max_nodes=20` as workaround.

2. **PubChem molecular data**: Chemical structure fields (SMILES, molecular weight) are being written but may take one more data collection cycle to populate on existing drug records.

3. **Some new connectors (EMA, NADAC, Open Targets)**: API changes/deprecations mean 0 records from these sources. ChEMBL and PubChem are active and growing.
