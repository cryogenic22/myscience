# Entity Library Vision — Ground-Up Redesign

*Date: 2026-03-31*
*Status: Design exploration*

---

## 1. The Insight

The Entity Library should not be a table of records. It should be a **living intelligence repository** where every drug, company, trial, mechanism, and molecular target has a rich profile — like a LinkedIn for pharma entities. Users don't just browse data; they discover relationships, assess quality, trace provenance, and ask questions.

The inspiration comes from three directions:

### A. Artist Discovery Platforms (WhyNotFamous)
- Each entity has a **profile page** with a unique identity
- Cross-platform signal aggregation (multiple data sources → unified view)
- Quality/underrated scoring → our **FAIR score** and **data quality**
- Category filtering → our **entity types**
- Grid + Map views → our **card grid + knowledge graph**

### B. Modern Data Catalogs ([Atlan](https://atlan.com/data-discovery-catalog/), [Collibra](https://www.collibra.com/), [data.world](https://data.world/))
- **Entity profiles** with metadata, lineage, quality scores, usage stats
- **Column-level lineage** → our entity_links provenance trail
- **Trust signals** per asset → our confidence scores + FAIR dimensions
- **Companion sidebar** → our Inspector panel concept
- **Natural language search** → our chat + search typeahead
- **AI-powered suggestions** → our research agent + steward signals
- **Certification/endorsement** → our quality_score + record_status

### C. Pharma Knowledge Graphs ([ONTOFORCE](https://www.ontoforce.com/knowledge-graph/accelerating-drug-discovery), [Causaly](https://www.causaly.com/), [Deep Intelligent Pharma](https://www.dip-ai.com/))
- **Causal knowledge graphs** with 500M+ relationships
- **Drug-target-disease** traversal as the core interaction
- **GraphRAG** — knowledge graph embeddings + LLM for explained reasoning
- **Natural language copilot** for scientists
- **Multi-agent R&D automation**

---

## 2. The Vision: Every Entity Has a Profile

### What an Entity Profile Looks Like

```
┌─────────────────────────────────────────────────────┐
│  ● Semaglutide                              Drug    │
│  GLP-1 Receptor Agonist · Novo Nordisk · Phase 4    │
│                                                      │
│  FAIR: 0.87 ▲  ━━━━━━━━━━━━━━━━━━━━━ 87%          │
│  AI Ready: ✓ embedding  ✓ linked  ✓ resolved       │
│                                                      │
│  ── Identity ─────────────────────────────────────  │
│  Generic: Semaglutide    Brand: Ozempic, Wegovy     │
│  PubChem: 56843331       ChEMBL: CHEMBL2108724     │
│  MW: 4114 Da             Formula: C187H291N45O59    │
│  SMILES: CCC(C)C(C(=O)NC(C)C(=O)NC...             │
│                                                      │
│  ── Knowledge Graph ──────────────────────────────  │
│  ┌─────────────────────────────────────────────┐   │
│  │  [Interactive KnowledgeGraph — 2 hop]        │   │
│  │  ● Novo Nordisk  ● GLP-1R  ● T2D  ● CVD   │   │
│  └─────────────────────────────────────────────┘   │
│  47 trials · 3 companies · 156 articles · 12 mechs │
│                                                      │
│  ── Data Provenance ──────────────────────────────  │
│  Sources: ClinicalTrials.gov, PubMed, FDA Orange    │
│           Book, ChEMBL, PubChem, OpenFDA FAERS     │
│  First seen: 2026-02-15  Last updated: 2h ago       │
│  Refresh: auto (daily from 6 sources)               │
│                                                      │
│  ── Quality Assessment ────────────────────────────  │
│  Completeness  ━━━━━━━━━━━━━━━━━━━  92%            │
│  Link density  ━━━━━━━━━━━━━━━━━━━  89%            │
│  Source diversity ━━━━━━━━━━━━━━━━  78%            │
│  Freshness     ━━━━━━━━━━━━━━━━━━━━ 96%            │
│  Resolution    ━━━━━━━━━━━━━━━━━━━━ 95%            │
│                                                      │
│  ── Connections (Top 10 of 47) ───────────────────  │
│  ● Novo Nordisk      OWNS           0.99 ████████  │
│  ● GLP-1 Receptor    TARGETS        0.95 ████████  │
│  ● Type 2 Diabetes   TREATS         0.92 ███████   │
│  ● Obesity            TREATS         0.88 ███████   │
│  ● NCT04082042       INVESTIGATES   0.85 ██████    │
│  ... [Show all 47]                                   │
│                                                      │
│  ── Evidence Trail ───────────────────────────────  │
│  156 articles · 47 trials · 12 FDA actions          │
│  Latest: "Semaglutide in NASH: Phase 3 Results"     │
│          Nature Medicine, 2026-03-15                 │
│                                                      │
│  ── AI Insights ──────────────────────────────────  │
│  "Semaglutide is the most connected entity in the   │
│   GLP-1 mechanism cluster. Its influence score       │
│   (0.94) ranks #1 among all drugs. Key risk:        │
│   patent expiry in 2032."                            │
│                                                      │
│  ── Actions ──────────────────────────────────────  │
│  [Ask in Chat]  [Explore Graph]  [Compare]           │
│  [Export Profile]  [Track Changes]  [Run Agent]      │
└─────────────────────────────────────────────────────┘
```

### What a Source Profile Looks Like

```
┌─────────────────────────────────────────────────────┐
│  ■ ClinicalTrials.gov                    API Source  │
│  Federal registry of clinical studies                │
│                                                      │
│  Health: ● Live   Schedule: Daily at 02:00 UTC      │
│  Last run: 2h ago  Records: 7,205                   │
│                                                      │
│  FAIR: 0.82 ▲  ━━━━━━━━━━━━━━━━━━━━ 82%           │
│                                                      │
│  ── What It Provides ─────────────────────────────  │
│  Entity types: trial (5,307), drug (1,200+),         │
│                investigator (1,100), trial_location   │
│  Link types: SPONSORS, INVESTIGATES, LOCATED_AT      │
│                                                      │
│  ── Data Quality ─────────────────────────────────  │
│  Phase coverage:     ━━━━━━━━━━━━━━━━━━━━ 97%      │
│  Sponsor resolution: ━━━━━━━━━━━━━━━━━   82%       │
│  Enrollment data:    ━━━━━━━━━━━━━━      71%       │
│  Condition mapping:  ━━━━━━━━━━━━━       68%       │
│                                                      │
│  ── Schema ───────────────────────────────────────  │
│  Fields: nct_id, title, phase, status, sponsor,     │
│          conditions, enrollment, start_date, ...     │
│  Embedding: protocol_embedding (1536d)               │
│                                                      │
│  ── Steward Activity ─────────────────────────────  │
│  ✓ 47 TA links backfilled (2h ago)                  │
│  ✓ 12 sponsor names cleaned (4h ago)                │
│  ⚠ 3 dedup candidates pending review                │
│                                                      │
│  ── Connections to Other Sources ─────────────────  │
│  trial → SPONSORS → company (via SEC EDGAR)         │
│  trial → INVESTIGATES → drug (via FDA Orange Book)  │
│  trial → EVIDENCE_FOR → literature (via PubMed)     │
│                                                      │
│  [Refresh Now]  [View Schema]  [Run Quality Check]  │
└─────────────────────────────────────────────────────┘
```

---

## 3. Design Principles

### Principle 1: Every Entity Is a First-Class Citizen
Not just drugs and companies. Mechanisms, molecular targets, investigators, biomarkers — each has a profile, a quality score, a provenance trail, and connections. The library doesn't privilege one type over another.

### Principle 2: Quality Is Visible Everywhere
Every entity shows its FAIR score. Every connection shows its confidence. Every source shows its freshness. Users never wonder "can I trust this data?" — the answer is always visible.

### Principle 3: The Graph Is the Navigation
Browsing isn't scrolling through a table. It's traversing the knowledge graph. Click a drug → see its connections → click a mechanism → see all drugs targeting it → click a company → see their portfolio. The entity profile IS the graph inspector.

### Principle 4: AI Explains, Not Just Displays
The steward agent doesn't just curate — it EXPLAINS. "This entity has low quality because its mechanism link is missing. The steward attempted to resolve it via fuzzy matching but confidence was only 0.45. Recommended action: verify mechanism manually."

### Principle 5: Sources Have Profiles Too
Each data source (ClinicalTrials.gov, ChEMBL, PubMed, etc.) has its own profile showing what it provides, how fresh it is, what quality dimensions it's strong/weak on, and how it connects to other sources.

---

## 4. Key Features

### 4.1 Entity Search & Discovery
- **Faceted search**: type, mechanism, TA, source, quality range, freshness
- **Natural language**: "drugs with high pipeline score but low evidence"
- **Similar entities**: "show me drugs similar to semaglutide"
- **AI suggestions**: "you might be interested in these 5 drugs based on your recent queries"

### 4.2 Entity Profile Pages
- **Identity card**: name, type, key identifiers, molecular data
- **Inline knowledge graph**: 2-hop neighborhood (KnowledgeGraph compact mode)
- **FAIR quality breakdown**: 5 dimensions with trend sparklines
- **Connection matrix**: grouped by entity type with confidence bars
- **Evidence trail**: linked literature, trials, events with recency
- **AI insights**: auto-generated summary of the entity's significance
- **Provenance**: which sources contributed what data, when
- **Change history**: audit trail of all modifications

### 4.3 Source Profiles
- **Health dashboard**: connector status, schedule, last run, record count
- **Schema explorer**: fields, types, coverage percentages
- **Quality dimensions**: per-field completeness, accuracy, consistency
- **Lineage view**: how this source's data flows into entity types
- **Steward activity log**: what the agent did with this source's data
- **Cross-source connections**: how this source links to others via entity_links

### 4.4 FAIR Scoring & AI Readiness
- **Overall FAIR score**: Findable, Accessible, Interoperable, Reusable
- **AI readiness indicators**: has embedding? resolved? linked? quality ≥ 0.7?
- **Trend sparklines**: 30-day FAIR history per entity type
- **Coverage gaps**: "23% of drugs missing mechanism links — steward scheduled"

### 4.5 Agentic Curation
- **Steward signals feed**: prioritized list of data quality issues
- **One-click resolution**: merge, keep both, reject for entity conflicts
- **Agent activity log**: what the data steward fixed automatically
- **Scheduled enrichment**: "ChEMBL enrichment for 50 drugs scheduled at 05:30"
- **Quality rules**: configurable thresholds for auto-curation

### 4.6 Observability & Audit
- **Pipeline monitoring**: connector health, throughput, error rates
- **Change log**: every field change, who/what made it, when
- **Data lineage**: field-level provenance (which source set which value)
- **Alerting**: "FAERS connector stale for 7 days", "Quality dropped 5%"

---

## 5. Views

### View 1: Entity Grid (default)
Card grid showing entities with mini-profile: name, type dot, FAIR score bar, connection count, source badges. Filterable by type, quality, freshness.

### View 2: Knowledge Graph
The same entities visualized as a graph. Click a node → profile opens as inspector. Browse by traversing connections.

### View 3: Source Dashboard
Grid of source cards (like CurateView) with health status, record counts, freshness, steward activity.

### View 4: Quality Dashboard
FAIR score trends, completeness heatmap by entity type × field, coverage gaps, steward activity log.

### View 5: Lineage View
Sankey diagram or directed graph showing: Sources → Entity Types → Link Types. Record counts as flow widths.

---

## 6. Research References

| Platform | Key Innovation | What We Take |
|----------|---------------|-------------|
| [Atlan](https://atlan.com/data-discovery-catalog/) | Companion sidebar, NL search, trust signals per asset | Entity profiles with quality signals |
| [Collibra](https://www.collibra.com/) | Governance workflows, policy modeling | HITL review queue, steward signals |
| [data.world](https://data.world/) | Knowledge graph architecture for catalog | Our graph IS the catalog |
| [ONTOFORCE](https://www.ontoforce.com/knowledge-graph/accelerating-drug-discovery) | Pharma KG with drug-target-disease traversal | Entity profile with graph navigation |
| [Causaly](https://www.causaly.com/) | 500M relationship KG + generative AI copilot | AI insights per entity, "ask about this entity" |
| [Deep Intelligent Pharma](https://www.dip-ai.com/) | Multi-agent R&D automation, NL interaction | Agentic curation, steward as AI agent |
| [OpenMetadata](https://open-metadata.org/) | Open-source catalog with quality framework | FAIR scoring, quality rules, profiling |
| WhyNotFamous | Entity profiles with cross-platform signals, scoring | Source diversity scoring, profile-first UX |

---

## 7. What Makes Ours Different

1. **The graph IS the catalog** — not a separate feature. Entities are graph nodes. Browsing is traversing.
2. **Every entity has molecular depth** — not just metadata. SMILES, binding data, genetic evidence alongside clinical and regulatory data.
3. **The steward is an agent, not a dashboard** — it doesn't just show quality issues, it fixes them autonomously and explains what it did.
4. **Sources have profiles** — not just a list of connectors. Each source has a schema, quality assessment, lineage, and steward activity log.
5. **FAIR + AI readiness** — not just data quality, but readiness for graph traversal, embedding search, and LLM synthesis.

---

## 8. Implementation Priority

| Phase | What | Impact |
|-------|------|--------|
| **Phase 1** | Entity profile page (replaces entity detail drawer) | Users see the full picture for any entity |
| **Phase 2** | Source profiles (replaces Overview connector cards) | Data librarian sees source health in depth |
| **Phase 3** | FAIR scoring + AI readiness indicators | Trust signals visible everywhere |
| **Phase 4** | Agentic curation UI (steward signals + actions) | Data quality becomes proactive, not reactive |
| **Phase 5** | Lineage view + observability dashboard | Full pipeline transparency |

---

*This is a vision document for discussion. No code changes yet.*
