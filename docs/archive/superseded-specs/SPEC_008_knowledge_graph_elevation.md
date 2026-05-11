# SPEC-008: Knowledge Graph Comprehensive Elevation

*Author: Claude + Cryogenic · Date: 2026-03-28*
*Cross-refs: SPEC-001 (CTX pipeline), SPEC-007 (graph visual upgrade)*

---

## 1. Thesis

Market Zero's knowledge graph is the core differentiator — it's what makes the platform more than a search engine. But the ontology was designed for an MVP with 3 therapeutic areas, and the data has since grown far beyond it. We now have 9 connectors producing 15 record types, but the ontology only captures 9 entity types with 12 link rules. Several tables created in migrations 015–027 (biomarkers, safety signals, drug pricing, company financials, mechanism hierarchy) sit as **orphaned data** — present in PostgreSQL but invisible to the knowledge graph, the entity resolver, the graph traversal service, and the frontend.

This spec addresses three layers simultaneously:

1. **Ontology expansion** — bring the domain pack in line with what the database already holds
2. **Unified graph renderer** — replace two duplicated canvas components with one
3. **Graph intelligence** — surface computed insights (influence, clusters, paths) visually

---

## 2. Ontology Audit: What We Have vs. What the KG Knows

### 2.1 Entity Types

| Entity | In DomainPack? | In ENTITY_TABLE_MAP (graph.py)? | In brand.ts? | In Resolver? | Status |
|--------|:-:|:-:|:-:|:-:|--------|
| drug | ✅ | ✅ | ✅ | ✅ | Complete |
| company | ✅ | ✅ | ✅ | ✅ | Complete |
| trial | ✅ | ✅ | ✅ | ✅ | Complete |
| literature | ✅ | ✅ | ✅ | ✅ | Complete |
| event | ✅ | ✅ | ✅ | ✅ | Complete |
| therapeutic_area | ✅ | ✅ | ✅ | ✅ | Complete |
| mechanism | ✅ | ✅ | ✅ | ✅ | Complete |
| investigator | ✅ | ❌ | ✅ | ✅ | **Graph-invisible** |
| patent | ✅ | ❌ | ✅ | ✅ | **Graph-invisible** |
| biomarker | ❌ | ❌ | ✅ (label only) | ❌ | **Orphaned** |
| adverse_event | ❌ (RecordType only) | ❌ | ❌ | ❌ | **Orphaned** |
| drug_label | ❌ (RecordType only) | ❌ | ❌ | ❌ | **Orphaned** |
| trial_outcome | ❌ (RecordType only) | ❌ | ❌ | ❌ | **Orphaned** |
| trial_location | ❌ (RecordType only) | ❌ | ❌ | ❌ | **Orphaned** |
| drug_pricing | ❌ | ❌ | ❌ | ❌ | **Orphaned** |
| company_financials | ❌ | ❌ | ❌ | ❌ | **Orphaned** |
| safety_signal (MV) | ❌ | ❌ | ❌ | ❌ | **Orphaned** |
| impact_assessment | ❌ | ❌ | ❌ | ❌ | **Orphaned** |

**Finding**: Of 18 distinct data entities in the database, only 7 are fully wired through all four layers. 2 more are partially wired (investigator, patent). 9 are completely orphaned from the knowledge graph.

### 2.2 Link Types

| LinkType | In DomainPack rules? | Created by cross-linker? | In brand.ts? | In graph frontend? | Status |
|----------|:-:|:-:|:-:|:-:|--------|
| OWNS | ✅ | ✅ | ✅ | ✅ | Complete |
| SPONSORS | ✅ | ✅ | ✅ | ✅ | Complete |
| INVESTIGATES | ✅ | ✅ | ✅ | ✅ | Complete |
| TARGETS_MECHANISM | ✅ | ✅ | ✅ | ✅ | Complete |
| IN_THERAPEUTIC_AREA | ✅ | ✅ | ✅ | ✅ | Complete |
| EVIDENCE_FOR | ✅ | ✅ | ✅ | ✅ | Complete |
| MENTIONED_IN | ✅ | ✅ | ✅ | ✅ | Complete |
| HAS_PATENT | ✅ | ✅ | ✅ | ❌ | **Frontend gap** |
| HAS_MILESTONE | ✅ | ✅ | ✅ | ❌ | **Frontend gap** |
| HAS_OUTCOME | cross_linker only | ✅ | ✅ | ❌ | **Frontend gap** |
| LOCATED_AT | cross_linker only | ✅ | ✅ | ❌ | **Frontend gap** |
| LED_BY | cross_linker only | ✅ | ✅ | ❌ | **Frontend gap** |
| AUTHORED_BY | cross_linker only | ✅ | ✅ | ❌ | **Frontend gap** |
| COMPETES_WITH | backfill script | ✅ | ✅ | ❌ | **Frontend gap** |
| SHORTAGE_AFFECTS | ✅ | ✅ | ✅ | ❌ | **Frontend gap** |
| HAS_ADVERSE_EVENT | ❌ | ❌ | ✅ | ❌ | **Not wired** |
| HAS_LABEL | ❌ | ❌ | ✅ | ❌ | **Not wired** |
| HAS_FULL_TEXT | ❌ | ❌ | ❌ | ❌ | **Not wired** |
| TAGGED | ❌ | ❌ | ❌ | ❌ | **Not wired** |
| USER_LINKED | ❌ | ❌ | ❌ | ❌ | **Not wired** |
| PATENT_BLOCKS | ❌ | ❌ | ❌ | ❌ | **Not wired** |

**Finding**: 20 link types defined in the enum, but only 7 are fully surfaced end-to-end. 8 exist in the database but the graph renderer treats them as invisible edges (no colour mapping, no filtering). 5 are defined in the enum but never created by any code path.

### 2.3 Missing Link Rules for New Data

These relationships exist in the data but lack LinkRules in the domain pack:

| Relationship | Source Table | Evidence |
|---|---|---|
| drug → biomarker (MEASURED_BY) | biomarkers.therapeutic_areas overlaps drug TA | Migration 017 has therapeutic_areas array |
| drug → adverse_event (HAS_ADVERSE_EVENT) | adverse_events.drug_id FK | FAERS connector stores drug_id |
| drug → drug_label (HAS_LABEL) | drug_labels.drug_id FK | OpenFDA labels connector |
| drug → drug_pricing (HAS_PRICING) | drug_pricing.drug_id FK | Migration 022 |
| company → company_financials (HAS_FINANCIALS) | company_financials.company_id FK | Migration 027 |
| trial → trial_outcome (HAS_OUTCOME) | trial_outcomes.trial_id | Cross-linker handles but no domain pack rule |
| trial → trial_location (LOCATED_AT) | trial_locations.trial_id | Cross-linker handles but no domain pack rule |
| drug → safety_signal (HAS_SIGNAL) | mv_safety_signals.drug_id | Migration 016 |
| mechanism → mechanism (PARENT_OF) | mechanisms_of_action.parent_mechanism_id | Migration 015 |
| drug → drug (PATENT_BLOCKS) | Derivable from shared patents with exclusivity | Currently in enum but never created |

---

## 3. Ontology Expansion Plan

### 3.1 New Entity Schemas for DomainPack

```python
# These need to be added to get_pharma_pack()

biomarker = EntitySchema(
    name="biomarker",
    table_name="biomarkers",
    record_types=["biomarker"],
    required_fields=["name", "category"],
    recommended_fields=["abbreviation", "unit", "clinical_significance"],
    exact_lookup_keys={},
    fuzzy_match_fields={"biomarker_name": "name"},
    embedding_column=None,
)

adverse_event = EntitySchema(
    name="adverse_event",
    table_name="adverse_events",
    record_types=["adverse_event"],
    required_fields=["drug_name", "reaction_meddra_pt"],
    recommended_fields=["serious", "outcome"],
    exact_lookup_keys={},
    fuzzy_match_fields={},
    embedding_column=None,
)

drug_label = EntitySchema(
    name="drug_label",
    table_name="drug_labels",
    record_types=["drug_label"],
    required_fields=["drug_name"],
    exact_lookup_keys={"set_id": "set_id"},
    fuzzy_match_fields={},
    embedding_column=None,
)
```

### 3.2 New Link Rules

```python
# Priority 1: Structural links (FK-based, high confidence)
LinkRule("biomarker", "therapeutic_area", "MEASURED_IN", "biomarker", "therapeutic_area", "source"),
LinkRule("adverse_event", "generic_name", "HAS_ADVERSE_EVENT", "drug", "adverse_event", "target"),
LinkRule("drug_label", "generic_name", "HAS_LABEL", "drug", "drug_label", "target"),

# Priority 2: Derived links (enrichment)
# PATENT_BLOCKS: drug A blocks drug B if A's patent covers B's mechanism
# HAS_PRICING: drug → pricing record
# HAS_FINANCIALS: company → financial record
```

### 3.3 ENTITY_TABLE_MAP Expansion (graph.py)

```python
# These entities are in the DB but invisible to graph traversal
ENTITY_TABLE_MAP = {
    # ... existing 7 entries ...
    "investigator": ("investigators", "id::text", "name", ["orcid", "affiliation"]),
    "patent": ("patents", "id::text", "patent_number", ["patent_type", "patent_expiry_date"]),
    "biomarker": ("biomarkers", "id::text", "name", ["abbreviation", "category", "unit"]),
    "adverse_event": ("adverse_events", "id::text",
                       "LEFT(reaction_meddra_pt, 60)", ["serious", "outcome"]),
    "trial_outcome": ("trial_outcomes", "id::text", "LEFT(measure, 60)", ["outcome_type"]),
    "trial_location": ("trial_locations", "id::text",
                        "COALESCE(facility_name, city)", ["country", "status"]),
}
```

### 3.4 Mention Normalizer Additions

Currently we only normalise drug and company mentions. We should add:

```python
# Biomarker normaliser: "HbA1c" = "Glycated Hemoglobin" = "glycated hemoglobin"
# Investigator normaliser: "Dr. John Smith MD" → "john smith"
```

---

## 4. Graph Traversal Upgrades

### 4.1 Current Limitations

1. **BFS only** — no support for weighted traversal based on confidence
2. **Max 4 hops** — fine for local neighbourhood, insufficient for competitive landscape analysis
3. **100 node cap** — aggressive for hub entities (semaglutide has 51 connections at 1 hop)
4. **No edge filtering** — can't say "show only COMPETES_WITH and OWNS" at the query level
5. **No temporal filtering** — can't filter by edge creation date or entity freshness
6. **No confidence threshold** — low-confidence fuzzy-matched links appear equal to exact matches

### 4.2 Proposed Enhancements

**A. Filtered traversal** — add `link_types` and `min_confidence` parameters:
```sql
-- Current: fetches ALL edges
WHERE source_entity_id = %s OR target_entity_id = %s

-- Proposed: filtered edges
WHERE (source_entity_id = %s OR target_entity_id = %s)
  AND link_type = ANY(%s)           -- optional link type filter
  AND confidence >= %s              -- optional confidence floor
  AND created_at >= %s              -- optional temporal filter
```

**B. Weighted path finding** — already implemented in `graph_analytics.py` with Dijkstra (cost = 1 - confidence). Needs to be surfaced in the UI.

**C. Subgraph extraction modes**:
- `neighborhood` — current BFS (keep)
- `competitive` — COMPETES_WITH + OWNS + TARGETS_MECHANISM edges only
- `evidence` — EVIDENCE_FOR + INVESTIGATES + HAS_OUTCOME edges only
- `regulatory` — HAS_MILESTONE + HAS_PATENT + HAS_LABEL edges only

**D. Entity importance scoring** — return `influence_score` with each node:
```python
# Already computed by graph_analytics.entity_influence()
# Should be included in traverse() response for node sizing
```

---

## 5. Unified Graph Renderer

### 5.1 Current State: Two Components, Duplicated Logic

| Feature | GraphMini (583 lines) | ModernGraph (338 lines) |
|---------|:-----:|:--------:|
| Background | Dark (`bg-neutral-900`) | Light (`bg-slate-50`) |
| Pan/Zoom | ✅ Full (pointer + wheel + keyboard) | ❌ None |
| Simulation | 180 frames then stops | Infinite `requestAnimationFrame` |
| Node colours | 6 entity types | 9 edge-type-based |
| Node sizing | Degree-based | Fixed |
| Labels | Hover tooltip | Only for center + hover + small graphs |
| Edge legend | ✅ 4 categories | ✅ 9 categories |
| Type toggle | ✅ Node type pills | ❌ |
| Used in | SearchPage EntityPreview | GraphExplorer |

### 5.2 Unified KnowledgeGraph Component

Merge the best of both into a single `KnowledgeGraph.tsx`:

**From GraphMini (keep)**:
- Dark canvas background
- Full pan/zoom with pointer + wheel + keyboard
- 180-frame simulation with stop
- Degree-based node sizing
- Hover tooltip with metadata
- Node type toggle pills

**From ModernGraph (keep)**:
- Edge colour mapping by link_type
- Edge legend with all categories

**New capabilities**:
- Semantic node colours from `TYPE_COLORS` map (6 entity types → 13 entity types)
- Influence-based node sizing (when influence scores available)
- Confidence-based edge opacity (0.3 → 1.0)
- Path highlight mode (glow along path edges, dim everything else)
- Node labels always visible for entities with influence > 0.7 or degree > 5
- Minimap for orientation in large graphs
- Click node → detail card overlay (not navigate away)

### 5.3 Colour System

```typescript
const ENTITY_COLORS: Record<string, string> = {
  drug:              '#2563eb',  // blue-600
  company:           '#d97706',  // amber-600
  trial:             '#0d9488',  // teal-600
  literature:        '#16a34a',  // green-600
  therapeutic_area:  '#e11d48',  // rose-600
  mechanism:         '#7c3aed',  // violet-600
  investigator:      '#ea580c',  // orange-600
  patent:            '#64748b',  // slate-500
  biomarker:         '#0891b2',  // cyan-600
  event:             '#dc2626',  // red-600
  adverse_event:     '#f43f5e',  // rose-500
  trial_outcome:     '#059669',  // emerald-600
  trial_location:    '#6366f1',  // indigo-500
};

const EDGE_COLORS: Record<string, string> = {
  OWNS:                '#d97706',  // amber — ownership
  SPONSORS:            '#d97706',  // amber — funding
  INVESTIGATES:        '#0d9488',  // teal — research
  EVIDENCE_FOR:        '#16a34a',  // green — literature
  TARGETS_MECHANISM:   '#7c3aed',  // violet — science
  IN_THERAPEUTIC_AREA: '#e11d48',  // rose — classification
  COMPETES_WITH:       '#ef4444',  // red — competition
  HAS_PATENT:          '#64748b',  // slate — IP
  HAS_MILESTONE:       '#f59e0b',  // amber — regulatory
  HAS_ADVERSE_EVENT:   '#f43f5e',  // rose — safety
  HAS_OUTCOME:         '#059669',  // emerald — results
  LED_BY:              '#ea580c',  // orange — people
  AUTHORED_BY:         '#ea580c',  // orange — people
  MENTIONED_IN:        '#94a3b8',  // slate-400 — reference
  SHORTAGE_AFFECTS:    '#dc2626',  // red — supply
};
```

### 5.4 Edge Semantic Grouping

For the legend and toggle controls, group 20 link types into 6 semantic categories:

| Category | Colour | Link Types |
|----------|--------|------------|
| Ownership & Funding | Amber | OWNS, SPONSORS |
| Research & Evidence | Green/Teal | INVESTIGATES, EVIDENCE_FOR, HAS_OUTCOME, LED_BY, AUTHORED_BY |
| Science & Classification | Violet/Rose | TARGETS_MECHANISM, IN_THERAPEUTIC_AREA, MEASURED_BY |
| Regulatory & IP | Slate/Amber | HAS_PATENT, HAS_MILESTONE, HAS_LABEL |
| Safety & Supply | Red | HAS_ADVERSE_EVENT, SHORTAGE_AFFECTS, HAS_SIGNAL |
| Competition | Red (dashed) | COMPETES_WITH, PATENT_BLOCKS |

---

## 6. Graph Intelligence Layer

### 6.1 Already Built (services/graph_analytics.py)

These exist but are NOT surfaced in the graph visualisation:

- **entity_influence()**: PageRank-inspired scoring (connections × avg_confidence × type_diversity)
- **competitive_clusters()**: Drugs grouped by mechanism + TA with HHI concentration index
- **weighted_path()**: Dijkstra shortest path with cost = 1 - confidence
- **entity_centrality_batch()**: Top-N most influential entities

### 6.2 Visual Integration

**Node sizing**: Map influence score to radius. Currently GraphMini uses `3 + 0.5 * degree` — replace with:
```
radius = baseRadius + (influenceScore * maxInfluenceBonus)
// baseRadius = 4, maxInfluenceBonus = 12
// So influence 0.0 → 4px, influence 1.0 → 16px
```

**Cluster colouring**: When viewing competitive_clusters, tint node backgrounds by cluster membership. Nodes in the same cluster share a subtle background glow.

**Path highlighting**: When weighted_path is computed, animate the path edges with a brighter stroke and pulsing glow. Dim all non-path edges to 0.15 opacity.

**Confidence bands**: Edge stroke width maps to confidence:
```
strokeWidth = 0.5 + (confidence * 2.0)
// confidence 0.3 → 1.1px (thin, uncertain)
// confidence 1.0 → 2.5px (thick, authoritative)
```

---

## 7. Implementation Phases

### Phase 1: Ontology Wiring (Week 1) — High Impact, Low Risk

**Backend changes**:
1. Add `investigator` and `patent` to `ENTITY_TABLE_MAP` in `graph.py`
2. Add `biomarker` to `ENTITY_TABLE_MAP` (new)
3. Add `biomarker` EntitySchema to `get_pharma_pack()` in `domain/pharma/pack.py`
4. Add missing LinkRules for HAS_ADVERSE_EVENT, HAS_LABEL to domain pack
5. Add `link_types` and `min_confidence` filter params to `graph.traverse()` and `graph.neighborhood()`

**Frontend changes**:
6. Expand `TYPE_COLORS` in GraphMini to cover all 13 entity types
7. Expand `EDGE_COLORS` to cover all 20 link types
8. Add missing entries to `brand.ts` ENTITY_TYPE_LABELS

**Tests**:
9. Test that traverse() returns investigator/patent/biomarker nodes
10. Test link_type filtering in traverse()

### Phase 2: Unified KnowledgeGraph Component (Week 2) — Core Deliverable

1. Create `frontend/src/components/KnowledgeGraph.tsx` merging GraphMini + ModernGraph
2. Dark canvas, full pan/zoom, 180-frame simulation
3. Entity-coloured nodes + link-type-coloured edges
4. Hover card with entity metadata
5. Node type toggle pills + edge category legend
6. Replace `ModernGraph` import in `GraphExplorer.tsx`
7. Replace `GraphMini` import in `EntityPreview.tsx`
8. Delete `ModernGraph.tsx` and update `GraphMini.tsx` → re-export from KnowledgeGraph
9. Verify both graph contexts render correctly

### Phase 3: Graph Intelligence Visuals (Week 3)

1. Include `influence_score` in traverse() API response
2. Node sizing by influence (radius = 4 + influence * 12)
3. Edge opacity by confidence (0.3 → 1.0)
4. Edge width by confidence (0.5 + confidence * 2.0)
5. Path highlight mode: bright animated path, dimmed non-path edges
6. Cluster tinting when competitive_clusters data available

### Phase 4: Derived Relationships (Week 4)

1. PATENT_BLOCKS derivation: drugs sharing a mechanism where one has active patents
2. MEASURED_BY links: biomarker ↔ drug via shared therapeutic area
3. HAS_PRICING links: drug → drug_pricing records
4. HAS_FINANCIALS links: company → company_financials records
5. Migration 028 for any new link types needed
6. Backfill script for derived links

### Phase 5: Subgraph Modes (Week 5)

1. Competitive mode: COMPETES_WITH + OWNS + TARGETS_MECHANISM only
2. Evidence mode: EVIDENCE_FOR + INVESTIGATES + HAS_OUTCOME only
3. Regulatory mode: HAS_MILESTONE + HAS_PATENT + HAS_LABEL only
4. Safety mode: HAS_ADVERSE_EVENT + SHORTAGE_AFFECTS + safety signals
5. Mode selector in GraphExplorer UI
6. Each mode has its own default layout emphasis

### Phase 6: Advanced Visualisation (Week 6)

1. Minimap for large graphs (>30 nodes)
2. Animated edge drawing on first render
3. Node detail card overlay (click without navigating away)
4. Graph snapshot export (PNG)
5. Temporal slider: filter edges by date range
6. Navigation breadcrumb trail

---

## 8. Ontology Strength Assessment

### What's Strong

The domain pack architecture itself is excellent. The `DomainPack` / `EntitySchema` / `LinkRule` abstraction means adding new entity types is purely declarative — no pipeline code changes needed. The 6-strategy entity resolution cascade is sophisticated and well-tested. The MeSH ontology integration provides semantic grounding that most competitors lack.

### What's Weak

1. **Coverage gap**: Only 7 of 18 entity types are fully wired. This means ~60% of the data we collect is invisible to the knowledge graph, which is the product's core value proposition.

2. **Single FK per drug**: Drugs can only link to ONE mechanism and ONE therapeutic area (via FK columns on the drugs table). In reality, many drugs have multiple mechanisms (e.g., semaglutide: GLP-1 RA + appetite suppression) and multiple TAs (diabetes + obesity + CV). The entity_links table supports many-to-many but the drug schema doesn't model this well.

3. **No temporal edges**: Links have `created_at` but no `valid_from` / `valid_to`. When a company sells a drug division, the OWNS link should expire. When a trial completes, the INVESTIGATES link should gain a `completed_at`. Currently all links are permanent.

4. **No edge properties**: The `entity_links.metadata` JSONB column exists but is rarely populated. Rich edge properties (e.g., patent expiry date on HAS_PATENT, trial phase on INVESTIGATES, price on HAS_PRICING) would enable much richer queries.

5. **Mechanism hierarchy underused**: Migration 015 added `parent_mechanism_id` and `mechanism_class` but these aren't used in graph traversal or competitive analysis. The hierarchy enables powerful queries like "show all drugs targeting any incretin-based mechanism" but this isn't possible today.

6. **No inverse link awareness**: The graph treats OWNS and SPONSORS as directed, but traversal doesn't infer that "if A OWNS B, then B is owned by A". This means neighbourhood queries from a drug don't show the owning company unless the edge direction matches.

7. **Biomarker island**: 12 biomarkers seeded in migration 017 with therapeutic_areas array, but no entity_links connect them to drugs or trials. They're completely disconnected from the graph.

### Recommended Ontology Evolution

**Short-term (this spec)**:
- Wire the 9 orphaned entity types into the domain pack
- Add filtered traversal with confidence thresholds
- Surface investigator, patent, biomarker in graph renderer

**Medium-term (SPEC-009)**:
- Multi-mechanism and multi-TA support for drugs (many-to-many via entity_links)
- Temporal edge validity (`valid_from`, `valid_to` on entity_links)
- Rich edge properties populated during cross-linking
- Mechanism hierarchy traversal in graph service

**Long-term (SPEC-010)**:
- Automated ontology expansion: when AutonomousResearchAgent discovers a new concept type, propose it as a candidate entity type
- Cross-domain linking: connect pharma KG to genomics, proteomics
- Confidence decay: link confidence decreases with age unless refreshed by new evidence

---

## 9. Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Entity types fully wired | 7/18 (39%) | 13/18 (72%) |
| Link types rendered in UI | 7/20 (35%) | 15/20 (75%) |
| Graph renderers | 2 (duplicated) | 1 (unified) |
| Node colour variety | 6 types | 13 types |
| Edge colour variety | 4 categories | 6 categories |
| Influence-based sizing | ❌ | ✅ |
| Confidence-based opacity | ❌ | ✅ |
| Path visualisation | Text only | Animated highlight |
| Filtered traversal | ❌ | ✅ (link type + confidence + temporal) |

---

## 10. Files Modified

### Backend
- `domain/pharma/pack.py` — add biomarker EntitySchema + new LinkRules
- `services/graph.py` — expand ENTITY_TABLE_MAP + add filtered traversal params
- `api/routes/graph.py` — add filter params to traverse/neighborhood endpoints
- `connectors/base.py` — add new LinkType values if needed
- `integration/cross_linker.py` — add domain pack rules for new link types

### Frontend
- `frontend/src/components/KnowledgeGraph.tsx` — **NEW**: unified graph renderer
- `frontend/src/components/GraphExplorer.tsx` — swap ModernGraph → KnowledgeGraph
- `frontend/src/components/search/EntityPreview.tsx` — swap GraphMini → KnowledgeGraph
- `frontend/src/components/GraphMini.tsx` — re-export shim then deprecate
- `frontend/src/components/ModernGraph.tsx` — delete
- `frontend/src/brand.ts` — add new entity/link labels
- `frontend/src/api.ts` — add filter params to traverse() call

### Tests
- `tests/test_graph_traversal_filters.py` — **NEW**: filtered traversal tests
- `tests/test_domain_pack_completeness.py` — **NEW**: assert all DB tables have EntitySchema
- `tests/test_knowledge_graph_component.py` — **NEW**: component render tests

---

## 11. Molecular Intelligence Layer — ChEMBL, PubChem, Open Targets

*Added 2026-03-28 after identifying that chemistry/toxicology sources were omitted from the initial ontology audit.*

### 11.1 Current State: Data Flows In, Structure Flows Out

Three connectors are **fully implemented and registered** in `connectors/__init__.py`:

| Connector | Source | What It Fetches | RecordType Emitted |
|-----------|--------|-----------------|-------------------|
| `ChEMBLConnector` | EBI ChEMBL | Molecule properties (SMILES, MW, logP), target proteins (ChEMBL IDs, action types, binding sites), bioactivities (IC50, Ki, EC50, pChEMBL) | `DRUG` for molecule data, `ONTOLOGY_TERM` for mechanisms + activities |
| `PubChemConnector` | NCBI PubChem | Compound identity (CID, SMILES, InChI, InChIKey), physicochemical properties (TPSA, HBD/HBA, rotatable bonds), synonyms | `DRUG` for all compound data |
| `OpenTargetsConnector` | EBI/Wellcome Open Targets | Target-disease associations (genetic evidence, association scores), druggability/tractability assessments, protein biotype | `ONTOLOGY_TERM` for all target-disease data |

The `integration/normalizer.py` has field mappings for all three (lines 232–263). The `api/routes/catalog.py` has dataset profiles declaring `entity_types: ["target"]` for ChEMBL and Open Targets — but **"target" does not exist as an entity type** in the domain pack, ENTITY_TABLE_MAP, brand.ts, or the entity resolver.

**The fundamental problem**: Rich molecular data with inherent graph structure (drug → binds → protein target → associated with → disease) is being compressed into flat records. ChEMBL bioactivities (IC50 = 2.3 nM against GLP-1R) become ONTOLOGY_TERM rows with no entity schema, no resolution cascade, no graph edges, and no frontend rendering. You cannot ask "which drugs bind GLP-1R with IC50 < 10 nM?" because the target isn't a node in the graph.

### 11.2 What This Data Represents

These sources provide the **molecular rationale layer** — the bridge between clinical (trials, approvals) and biological (targets, mechanisms, affinities) intelligence:

**Chemical Identity** (PubChem):
- Canonical SMILES and InChI enable structure-based similarity search
- Physicochemical properties (Lipinski descriptors) predict oral bioavailability
- Synonym mappings improve entity resolution (brand → generic → chemical name)

**Target Pharmacology** (ChEMBL):
- Drug-target binding measurements (IC50, Ki, Kd, EC50) with pChEMBL potency scores
- Mechanism of action with binding site specificity and selectivity comments
- Assay metadata (assay_type, assay_description) for reproducibility context
- Target organism data for species-selectivity analysis

**Genetic Validation** (Open Targets):
- Target-disease association scores from GWAS, rare disease, somatic mutations
- Druggability/tractability assessments per protein modality (small molecule, antibody, etc.)
- Genetic evidence is the strongest predictor of clinical trial success — drugs with genetically validated targets are 2× more likely to be approved

### 11.3 Proposed Entity Types

```python
# ── New entity type: molecular_target ──────────────────────────
# Represents a protein, receptor, enzyme, or ion channel that a drug binds to.
# Sources: ChEMBL (target_chembl_id), Open Targets (ensembl_id + gene symbol)
molecular_target = EntitySchema(
    name="molecular_target",
    table_name="molecular_targets",
    record_types=["molecular_target"],
    required_fields=["name", "target_type"],
    recommended_fields=[
        "gene_symbol", "ensembl_id", "chembl_id", "uniprot_id",
        "biotype", "organism", "tractability",
    ],
    exact_lookup_keys={
        "ensembl_id": "ensembl_id",
        "chembl_id": "chembl_id",
        "gene_symbol": "gene_symbol",
    },
    fuzzy_match_fields={"target_name": "name"},
    embedding_column="target_embedding",
)

# ── New entity type: bioactivity ───────────────────────────────
# Represents a measured drug-target interaction (IC50, Ki, EC50, etc.)
# Source: ChEMBL activity records
bioactivity = EntitySchema(
    name="bioactivity",
    table_name="bioactivities",
    record_types=["bioactivity"],
    required_fields=["drug_id", "target_id", "activity_type", "activity_value"],
    recommended_fields=[
        "activity_units", "pchembl_value", "assay_type",
        "assay_description", "activity_relation",
    ],
    exact_lookup_keys={"activity_id": "chembl_activity_id"},
    fuzzy_match_fields={},
    embedding_column=None,
)
```

**Why `molecular_target` and not just expanding `mechanism`?**

Mechanisms describe *how* a drug works (e.g., "GLP-1 receptor agonist"). Molecular targets describe *what* a drug physically binds to (e.g., "GLP1R protein, Ensembl ENSG00000112164"). A drug can have one mechanism but bind multiple targets. The relationship is mechanism → describes → target, not mechanism = target. Collapsing them loses the ability to query across targets independently of mechanism classification.

**Why not a separate `compound` entity type?**

PubChem chemical identity data (SMILES, InChI, physicochemical properties) maps naturally onto the existing `drug` entity. Adding compound as a separate type would create a confusing drug-vs-compound split for the same real-world molecule. Instead, we extend the drugs table schema to hold molecular identity fields.

### 11.4 Proposed Database Schema

```sql
-- Migration 028: Molecular targets and bioactivities

CREATE TABLE IF NOT EXISTS molecular_targets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,                    -- e.g., "Glucagon-like peptide 1 receptor"
    gene_symbol TEXT,                      -- e.g., "GLP1R"
    ensembl_id TEXT,                       -- e.g., "ENSG00000112164"
    chembl_id TEXT,                        -- e.g., "CHEMBL1985"
    uniprot_id TEXT,                       -- e.g., "P43220"
    target_type TEXT NOT NULL DEFAULT 'SINGLE PROTEIN',  -- SINGLE PROTEIN, PROTEIN COMPLEX, etc.
    organism TEXT DEFAULT 'Homo sapiens',
    biotype TEXT,                          -- protein_coding, etc.
    tractability JSONB,                    -- modality → score from Open Targets
    disease_associations JSONB,            -- top disease links from Open Targets
    target_embedding VECTOR(1536),         -- for semantic search
    source_api TEXT NOT NULL,
    retrieved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uix_target_ensembl ON molecular_targets(ensembl_id) WHERE ensembl_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uix_target_chembl ON molecular_targets(chembl_id) WHERE chembl_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uix_target_gene ON molecular_targets(gene_symbol) WHERE gene_symbol IS NOT NULL;

CREATE TABLE IF NOT EXISTS bioactivities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    drug_id UUID REFERENCES drugs(id),
    target_id UUID REFERENCES molecular_targets(id),
    chembl_activity_id TEXT,               -- ChEMBL activity primary key
    activity_type TEXT NOT NULL,            -- IC50, Ki, Kd, EC50
    activity_value DOUBLE PRECISION,       -- numeric measurement
    activity_units TEXT,                    -- nM, uM, etc.
    activity_relation TEXT DEFAULT '=',     -- =, <, >, <=, >=
    pchembl_value DOUBLE PRECISION,        -- -log10(molar), higher = more potent
    assay_type TEXT,                        -- B (binding), F (functional), A (ADME)
    assay_description TEXT,
    source_api TEXT NOT NULL DEFAULT 'chembl',
    retrieved_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_bioactivity_drug ON bioactivities(drug_id);
CREATE INDEX IF NOT EXISTS ix_bioactivity_target ON bioactivities(target_id);
CREATE INDEX IF NOT EXISTS ix_bioactivity_pchembl ON bioactivities(pchembl_value DESC NULLS LAST);

-- Extend drugs table for molecular identity from PubChem
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS pubchem_cid TEXT;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS canonical_smiles TEXT;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS inchi TEXT;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS inchi_key TEXT;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS molecular_formula TEXT;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS molecular_weight DOUBLE PRECISION;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS xlogp DOUBLE PRECISION;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS tpsa DOUBLE PRECISION;
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS hbd INTEGER;  -- H-bond donors
ALTER TABLE drugs ADD COLUMN IF NOT EXISTS hba INTEGER;  -- H-bond acceptors

CREATE UNIQUE INDEX IF NOT EXISTS uix_drug_pubchem ON drugs(pubchem_cid) WHERE pubchem_cid IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uix_drug_inchi_key ON drugs(inchi_key) WHERE inchi_key IS NOT NULL;
```

### 11.5 New Link Types and Rules

```python
# New LinkType enum values
BINDS_TO = "BINDS_TO"               # drug → molecular_target (from bioactivities)
GENETIC_ASSOCIATION = "GENETIC_ASSOCIATION"  # molecular_target → therapeutic_area (from Open Targets)
TARGET_OF_MECHANISM = "TARGET_OF_MECHANISM"  # mechanism → molecular_target

# New LinkRules for domain pack
LinkRule("molecular_target", "drug_name", "BINDS_TO",
         "drug", "molecular_target", "source"),

LinkRule("molecular_target", "mechanism_of_action", "TARGET_OF_MECHANISM",
         "mechanism", "molecular_target", "target"),

LinkRule("molecular_target", "disease_name", "GENETIC_ASSOCIATION",
         "molecular_target", "therapeutic_area", "source"),
```

### 11.6 New RecordTypes

```python
# Add to RecordType enum in connectors/base.py
MOLECULAR_TARGET = "molecular_target"
BIOACTIVITY = "bioactivity"
```

### 11.7 Connector Refactoring

The existing connectors need targeted changes to emit the correct RecordTypes:

**ChEMBLConnector changes**:
- `_molecule_record()` → keep as `RecordType.DRUG` (correct, molecular identity enriches drugs)
- `_fetch_mechanisms()` → change from `RecordType.ONTOLOGY_TERM` to `RecordType.MOLECULAR_TARGET`
- `_fetch_activities()` → change from `RecordType.ONTOLOGY_TERM` to `RecordType.BIOACTIVITY`

**PubChemConnector changes**:
- `_fetch_compound()` → keep as `RecordType.DRUG` (correct, adds SMILES/InChI to drugs table)
- Ensure PubChem CID and InChI populate the new drug columns via normaliser mapping

**OpenTargetsConnector changes**:
- `_make_record()` → change from `RecordType.ONTOLOGY_TERM` to `RecordType.MOLECULAR_TARGET`
- Include disease associations as JSONB on the target record
- Emit separate link records for target → disease genetic associations

### 11.8 Graph Traversal Integration

```python
# Add to ENTITY_TABLE_MAP in services/graph.py
"molecular_target": (
    "molecular_targets", "id::text", "COALESCE(gene_symbol, name)",
    ["target_type", "organism", "ensembl_id", "chembl_id"]
),
"bioactivity": (
    "bioactivities", "id::text",
    "activity_type || ' = ' || COALESCE(activity_value::text, '?') || ' ' || COALESCE(activity_units, '')",
    ["pchembl_value", "assay_type"]
),
```

### 11.9 Frontend Integration

```typescript
// Add to ENTITY_TYPE_LABELS in brand.ts
molecular_target: 'Molecular Target',
bioactivity: 'Bioactivity',

// Add to ENTITY_TYPE_COLORS in brand.ts
molecular_target: '#8b5cf6',  // violet-500 — biology
bioactivity: '#06b6d4',       // cyan-500 — measurement

// Add to LINK_TYPE_LABELS
BINDS_TO: 'Binding target',
GENETIC_ASSOCIATION: 'Genetic evidence',
TARGET_OF_MECHANISM: 'Molecular target',

// Add to LINK_TYPE_COLORS
BINDS_TO: '#8b5cf6',          // violet — biology
GENETIC_ASSOCIATION: '#14b8a6', // teal — genetics
TARGET_OF_MECHANISM: '#7c3aed', // violet — science

// Update EDGE_CATEGORIES.science
science: {
    label: 'Science & Classification',
    color: '#7c3aed',
    types: ['TARGETS_MECHANISM', 'IN_THERAPEUTIC_AREA', 'BINDS_TO',
            'TARGET_OF_MECHANISM', 'GENETIC_ASSOCIATION'],
},

// Add to SOURCE_LABELS
chembl: 'ChEMBL',
pubchem: 'PubChem',
open_targets: 'Open Targets Platform',
```

### 11.10 Mention Normaliser for Targets

```python
# New normaliser: normalize_target_mention()
# "Glucagon-like peptide 1 receptor" → "GLP1R"
# "GLP-1R" → "GLP1R"
# "SGLT2" = "SLC5A2" (gene symbol alias mapping from Ensembl)
# Uses a gene symbol alias table seeded from Open Targets data
```

### 11.11 Queries This Enables

Once wired, the molecular layer enables these previously impossible queries:

1. **"Which drugs bind GLP-1R with the highest potency?"**
   → Traverse drug → BINDS_TO → molecular_target(GLP1R), sort by pchembl_value DESC

2. **"What's the selectivity profile of semaglutide?"**
   → From semaglutide, traverse BINDS_TO edges, show all targets with activity values
   → Flag off-target binding (high pChEMBL against non-GLP1R targets)

3. **"Does empagliflozin's target have genetic evidence for diabetes?"**
   → drug → BINDS_TO → molecular_target → GENETIC_ASSOCIATION → therapeutic_area
   → Return Open Targets association score and evidence breakdown

4. **"Compare tirzepatide and semaglutide binding profiles"**
   → For each drug, collect BINDS_TO targets with pChEMBL values
   → Tirzepatide hits both GLP1R and GIPR; semaglutide hits GLP1R only
   → This is the core differentiator for dual-agonist competitive analysis

5. **"Which targets in the GLP-1 pathway are druggable?"**
   → From mechanism(GLP-1 receptor agonist) → TARGET_OF_MECHANISM → molecular_targets
   → Filter by tractability.small_molecule = true or tractability.antibody = true

6. **"Show all drugs that share a molecular target with semaglutide"**
   → semaglutide → BINDS_TO → GLP1R → BINDS_TO (reverse) → other drugs
   → This is target-based competitive analysis vs. the current mechanism-based approach

### 11.12 Implementation Phase (Week 7–8 of SPEC-008)

**Phase 7a: Schema & Migration (2 days)**
1. Create migration 028 for molecular_targets and bioactivities tables
2. Add molecular identity columns to drugs table
3. Add MOLECULAR_TARGET and BIOACTIVITY to RecordType enum
4. Add BINDS_TO, GENETIC_ASSOCIATION, TARGET_OF_MECHANISM to LinkType enum

**Phase 7b: Connector Refactoring (2 days)**
5. Update ChEMBLConnector to emit MOLECULAR_TARGET and BIOACTIVITY records
6. Update OpenTargetsConnector to emit MOLECULAR_TARGET records
7. Update PubChem normaliser mapping to populate new drug columns
8. Add molecular_target EntitySchema + bioactivity EntitySchema to domain pack
9. Add new LinkRules for BINDS_TO, GENETIC_ASSOCIATION, TARGET_OF_MECHANISM

**Phase 7c: Graph & Frontend (2 days)**
10. Add molecular_target and bioactivity to ENTITY_TABLE_MAP
11. Add entity type colours, labels, and link type colours to brand.ts
12. Add normalize_target_mention() to mention_normalizer.py
13. Update catalog dataset profiles to use correct entity types

**Phase 8: Backfill & Verification (2 days)**
14. Run ChEMBL + PubChem + Open Targets pipeline against existing drug set
15. Verify molecular_targets and bioactivities tables populate
16. Verify BINDS_TO edges appear in graph traversal
17. Verify KnowledgeGraph renderer shows molecular_target nodes in violet
18. Write tests for target resolution cascade and bioactivity link creation

### 11.13 Toxicology Extension (Future)

The SourceType enum does not currently include dedicated toxicology databases, but ChEMBL bioactivity data already contains toxicity-relevant signals:
- Off-target binding (high pChEMBL against safety-relevant targets like hERG, CYP enzymes)
- ADME assay results (assay_type = 'A') indicating metabolic liability

Future work could add connectors for:
- **ToxCast/ToxRefDB** (EPA) — in vitro toxicity assay results
- **DrugBank** — drug-drug interactions, adverse effect profiles
- **CTD** (Comparative Toxicogenomics Database) — chemical-gene-disease interactions

These would feed into the same molecular_target + bioactivity schema, with additional entity types like `toxicity_endpoint` and link types like `HAS_TOX_SIGNAL` if the data volume warrants it.

---

## 12. Revised Success Metrics

| Metric | Current | After §1–10 | After §11 (Molecular) |
|--------|---------|-------------|----------------------|
| Entity types fully wired | 7/18 (39%) | 13/18 (72%) | 15/20 (75%) |
| Link types rendered in UI | 7/20 (35%) | 15/20 (75%) | 18/23 (78%) |
| Chemistry sources producing graph nodes | 0/3 | 0/3 | 3/3 |
| Molecular target entities in graph | 0 | 0 | ~200–500 |
| Drug-target binding edges | 0 | 0 | ~1,000–5,000 |
| Queries requiring molecular data | Impossible | Impossible | Fully supported |
