# SPEC-007: Data Library — Next Generation Vision

> **Date**: 28 March 2026
> **Principle**: The library is the product. Chat and graph are consumption layers.

---

## 1. Why the Library Matters Most

The data library is where users:
- **Discover** what data exists (before they ask a question)
- **Trust** the data (by seeing quality, freshness, provenance)
- **Navigate** from entity to entity (following connections)
- **Curate** when they find errors (with permission)

A pharma VP opening Market Zero for the first time will go to the library — not the chat. They want to see: "What do you know about my competitor? How fresh is the trial data? Can I trust this for a board deck?"

If the library shows "0.9% Sodium-chloride" as the first entry, trust is lost in 3 seconds.

---

## 2. Design Principles

### P1: Curated default, raw available
Default view shows the most clinically significant, highest-quality entities. Not alphabetical. Not everything. The "show all" view exists but isn't the default.

### P2: Entity profile, not database row
Each entity renders like a LinkedIn profile — summary, key stats, connections, evidence — not a table of database fields.

### P3: Quality is visible but not alarming
Quality indicators help users assess reliability. Red badges on every row screams "broken database." Instead: green checkmarks on trusted data, subtle indicators on incomplete data, detailed quality only in expanded view.

### P4: Connected, not flat
Every entity shows its connections. A drug shows its company, mechanism, trials, and competitors. A company shows its portfolio. Clicking any connection navigates to that entity.

### P5: Search-first, browse-second
Most users come to the library looking for something specific. Search should be prominent and intelligent (fuzzy matching, synonym expansion, type-ahead suggestions). Browse is secondary.

---

## 3. Page Architecture

### 3A: Library Home (default view)

```
┌─────────────────────────────────────────────────────────────┐
│  Entity Library                                    [Admin]  │
│  822K records across 10 sources                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  🔍 Search entities...                    [⌘K]             │
│                                                             │
│  ┌─────────┬──────────┬────────┬───────┬──────┬─────────┐  │
│  │ All     │ Drugs    │ Companies│Trials│ TAs  │ More ▾  │  │
│  │ 822K    │ 1,706    │ 1,458  │5,307 │ 18   │         │  │
│  └─────────┴──────────┴────────┴───────┴──────┴─────────┘  │
│                                                             │
│  ── FEATURED ──────────────────────────────────────────     │
│                                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ semaglutide  │ │ tirzepatide  │ │ Novo Nordisk │       │
│  │ GLP-1 agonist│ │ GLP-1/GIP    │ │ 12 drugs     │       │
│  │ Novo Nordisk │ │ Eli Lilly    │ │ 595 trials   │       │
│  │ Phase 4 ✓    │ │ Phase 4 ✓    │ │ Pipeline: 320│       │
│  │ 142 trials   │ │ 98 trials    │ │              │       │
│  │ Quality: 92% │ │ Quality: 88% │ │ Quality: 85% │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
│                                                             │
│  ── ALL DRUGS ─── Sort: [Pipeline Score ▾] ──── 1/57 ──   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ ● semaglutide (Ozempic)                    Phase 4  │   │
│  │   GLP-1 Agonist · Novo Nordisk · Diabetes/Obesity   │   │
│  │   142 trials · 320 publications · Quality 92%       │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │ ● tirzepatide (Mounjaro)                   Phase 4  │   │
│  │   GLP-1/GIP Agonist · Eli Lilly · Diabetes/Obesity │   │
│  │   98 trials · 184 publications · Quality 88%        │   │
│  ├─────────────────────────────────────────────────────┤   │
│  │ ● metformin                                Phase 4  │   │
│  │   Biguanide · Multiple · Diabetes Mellitus          │   │
│  │   1,205 trials · 892 publications · Quality 95%     │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Key differences from current:
1. **Search is prominent** — full-width search bar at the top
2. **Type tabs show counts** — user knows the scope immediately
3. **Featured section** — top 3 entities by pipeline score (not alphabetical)
4. **Rich entity rows** — mechanism, company, TA, trial count, publication count on every row
5. **Default sort: pipeline score** — most clinically significant first
6. **Phase badge** — immediately visible clinical status
7. **Quality shown as checkmark/percentage** — not a red progress bar

### 3B: Entity Profile (drawer or full page)

```
┌─────────────────────────────────────────────────────────────┐
│  semaglutide                                          Drug  │
│  Brand: Ozempic, Wegovy, Rybelsus                          │
│                                                             │
│  A GLP-1 receptor agonist developed by Novo Nordisk for    │
│  type 2 diabetes and obesity. Approved in multiple          │
│  formulations. Highest pipeline score in the GLP-1 class.  │
│                                                             │
│  ┌────────┬────────┬────────┬────────┬────────┐           │
│  │ Phase  │ Trials │ Pubs   │ Score  │Quality │           │
│  │ 4 ✓   │ 142    │ 320    │ 85.2   │ 92%   │           │
│  └────────┴────────┴────────┴────────┴────────┘           │
│                                                             │
│  CONNECTIONS ──────────────────────────────────────         │
│                                                             │
│  Company       Novo Nordisk →                              │
│  Mechanism     GLP-1 Receptor Agonist →                    │
│  Indication    Diabetes Mellitus Type 2 →                  │
│                Obesity →                                    │
│  Competitors   tirzepatide · dulaglutide · liraglutide     │
│                                                             │
│  CLINICAL PIPELINE ────────────────────────────────        │
│                                                             │
│  Phase 1 ████░░░░░░  12 trials                             │
│  Phase 2 ██████░░░░  28 trials                             │
│  Phase 3 ████████░░  42 trials (STEP, SUSTAIN, PIONEER)   │
│  Phase 4 ██████████  60 trials                             │
│                                                             │
│  RECENT EVIDENCE ──────────────────────────────────        │
│                                                             │
│  📄 "SELECT trial: Semaglutide and cardiovascular..."      │
│     NEJM · Jan 2026 · Cited 142 times                      │
│  📄 "STEP HFpEF: Semaglutide in heart failure..."          │
│     Lancet · Nov 2025 · Cited 89 times                     │
│                                                             │
│  PROVENANCE ───────────────────────────────────────        │
│                                                             │
│  ClinicalTrials.gov ● Fresh (2d)  142 records              │
│  PubMed ● Fresh (2d)  320 articles                         │
│  FDA Orange Book ● Fresh (5d)  Label + milestones          │
│                                                             │
│  [Explore in Graph] [Ask in Chat] [Export Profile]          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

Key differences:
1. **Natural language summary** — not key-value pairs
2. **Horizontal metrics strip** — the 5 most important numbers at a glance
3. **Connections are navigable** — click Novo Nordisk → opens its profile
4. **Competitors shown** — from COMPETES_WITH links we already have
5. **Clinical pipeline visual** — phase distribution as horizontal bars
6. **Evidence with context** — journal, date, citation count
7. **Provenance per source** — not just "retrieved 16 Feb 2026"

### 3C: Company Profile

```
┌─────────────────────────────────────────────────────────────┐
│  Novo Nordisk                                      Company  │
│  Ticker: NVO · CIK: 353278 · Denmark                      │
│                                                             │
│  Global pharmaceutical company focused on diabetes,         │
│  obesity, and rare diseases. Largest GLP-1 agonist         │
│  portfolio by pipeline score.                               │
│                                                             │
│  ┌────────┬────────┬────────┬────────┐                    │
│  │ Drugs  │ Trials │ Pipeline│ TAs   │                    │
│  │ 12     │ 595    │ 320.5  │ 5     │                    │
│  └────────┴────────┴────────┴────────┘                    │
│                                                             │
│  PORTFOLIO ────────────────────────────────────────         │
│                                                             │
│  ● semaglutide      Phase 4  Score: 85.2  DM2/Obesity     │
│  ● liraglutide      Phase 4  Score: 45.0  DM2             │
│  ● insulin degludec  Phase 4  Score: 32.1  DM1/DM2        │
│  · · · 9 more drugs                                        │
│                                                             │
│  COMPETITIVE POSITION ─────────────────────────────        │
│                                                             │
│  vs Eli Lilly     Overlaps in GLP-1, 2 shared TAs          │
│  vs Sanofi        Overlaps in insulin, 1 shared TA         │
│  vs AstraZeneca   Overlaps in SGLT2, 1 shared TA          │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3D: Data Quality Dashboard (Admin only)

Keep current design — it's already good. Just add:
- **Actionable buttons** — "Refresh stale sources" next to freshness indicators
- **FAIR score trend** — chart showing quality improvement over time
- **Curation leaderboard** — entities most improved this week

---

## 4. What Needs to Change

### Backend Changes

1. **Rich entity list endpoint** — `/catalog/entities/{type}` should return joined data:
   - Drug: + mechanism_name, company_name, therapeutic_area_name, trial_count, publication_count
   - Company: + drug_count, trial_count, pipeline_score
   - Trial: + drug_name, sponsor_name, condition names

2. **Featured entities endpoint** — `/catalog/featured` returns top N entities by pipeline score per type

3. **Sort options** — pipeline_score, trial_count, quality_score, recently_updated, alphabetical

4. **Default sort: pipeline_score DESC** — not alphabetical

### Frontend Changes

1. **Rich entity rows** — show mechanism, company, TA, phase, trial count inline
2. **Featured cards** — top 3 entities as horizontal cards above the list
3. **Search as primary** — full-width search bar, type-ahead suggestions
4. **Quality as confidence** — green checkmark > 80%, amber > 50%, subtle grey < 50%
5. **Type tab counts** — show record count per entity type

---

## 5. Implementation Priority

| # | Change | Impact | Effort |
|---|---|---|---|
| 1 | Default sort by pipeline score | Highest — no more "0.9% Sodium-chloride" as first entry | 1 hour |
| 2 | Rich entity rows (mechanism + company + TA inline) | High — context without clicking | 3 hours |
| 3 | Featured entities section | High — immediate value signal | 2 hours |
| 4 | Search as primary input | Medium — faster entity finding | 2 hours |
| 5 | Entity profile redesign | Medium — better drill-down | 4 hours |
| 6 | Quality as confidence (green/amber/grey) | Medium — less alarming | 1 hour |
| 7 | Type tab counts | Low — scope awareness | 30 min |
| 8 | Competitor links in profile | Low — competitive intelligence | 2 hours |

---

## 6. Best Practices Borrowed

### From Collibra (enterprise data catalog)
- Entity profiles with business context, not just technical metadata
- Data quality scores shown as "trust level" (certified, warning, unknown)
- Lineage visualization (where does this data come from)

### From Atlan (modern data catalog)
- Search-first with instant type-ahead
- Rich preview cards before clicking
- Context columns (owner, freshness, popularity)

### From Bloomberg Terminal
- Dense but organized — every pixel has a purpose
- Color coding by asset class (= entity type)
- Keystroke navigation (power users don't click)

### From LinkedIn
- Entity profile with summary, key stats, connections
- "People also viewed" = related entities
- Progressive disclosure: summary → details → full profile

### From Scriptiva SCA
- Clean DataTable with sort, pagination, selection
- Badge system for status (10 color variants)
- Drawer for details without leaving the list
- Search with keyboard navigation
