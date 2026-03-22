# Market Zero — Unified 90-Day Roadmap

**Date:** 22 March 2026
**Status:** Active
**Sources:** `lead_notes_4_dev.md` (strategic vision) + data audit (22 Mar 2026) + existing BACKLOG.md

---

## Current State (Data Audit Baseline)

| Metric | Value | Target |
|--------|-------|--------|
| Total records | 606,125 | — |
| Drug completeness | 37.5% | 80%+ |
| Company completeness | 30.2% | 65%+ |
| Quality failure rate | 57% | <15% |
| HITL queue (unreviewed) | 21,522 | <500 |
| TAs with entity links | 6 / 18 | 18 / 18 |
| Company duplicates | ~50 pairs | 0 |
| Drug name noise (raw interventions) | ~1,060 | 0 |
| Trial labels populated | 0% | 100% |
| Data freshness | ~30 days stale | <7 days |
| FAIR score | 4.7 / 10 | 8.0+ |
| Tests passing | 180 | 220+ |

---

## Phase 0 — Data Foundation (Week 1)

*Nothing else matters until the data is trustworthy.*

### 0.0 Run existing curation scripts against live database

**Scripts already built:** `scripts/clean_drug_names.py`, `scripts/dedup_companies.py`, `scripts/enrich_drugs.py`, `scripts/enrich_companies.py`, `scripts/backfill_ta_links.py`, `scripts/quality_scorecard.py`

**Actions:**
1. Run `clean_drug_names.py` → remove dosage-pattern drug names, mark placebo/study-drug entries as excluded
2. Run `dedup_companies.py` → merge Pfizer Inc./PFIZER, Novartis/Novartis Pharms Corp, etc.; exclude hospitals/universities
3. Run `backfill_ta_links.py` → populate 12 empty TAs using trial condition text matching + MeSH hierarchy
4. Run `enrich_drugs.py` → backfill brand_name, approval_date, company_id from Orange Book + Labels data
5. Run `enrich_companies.py` → add ticker/country/region for top 50 pharma companies
6. Fill trial labels: `UPDATE clinical_trials SET label = COALESCE(NULLIF(brief_title,''), nct_id) WHERE label IS NULL OR label = ''`
7. Resolve "unknown" entity_type nodes in entity_links
8. Run `quality_scorecard.py` → establish post-cure baseline

**Verification:**
- `pytest tests/test_domain_coverage.py -v` — all 18 TAs linked, no dosage drug names, no company dupes
- Quality scorecard: drug completeness ≥75%, company ≥60%, overall quality ≥0.75

**Effort:** 2-3 days (scripts exist; this is execution + debugging)

### 0.1 Auto-resolve high-confidence HITL items

**21,522 HITL items at zero review rate is a blocker.**

- Auto-approve entity resolutions with confidence ≥0.9 (estimated ~60% of queue)
- Auto-reject quality failures for excluded/merged entities
- Bulk-defer low-priority items (stale records, single-source entities)
- Target: queue reduced to <2,000 actionable items

**Effort:** 1 day (script: `scripts/auto_curate.py` already exists)

### 0.2 Refresh all data sources

- Run `scheduler/runner.py` with `run_now()` to pull fresh data from all 9 connectors
- Post-run: refresh materialized views, re-run quality scorecard
- Verify no connector failures (health checks)

**Effort:** 1 day (scheduler exists; this is monitoring the run)

---

## Phase 1 — Metabolic TA Definition + ConversationMemory (Week 2)

*From `lead_notes_4_dev.md` items 0.1 and 0.2 — the two highest-impact quick wins.*

### 1.1 Build metabolic/GLP-1 TA definition YAML

**File:** `domain/ta_definitions/metabolic.yaml`

The framework exists (`domain/ta_definitions/schema.py`, `oncology.yaml` as template). Create the metabolic TA definition with:

- **MeSH IDs:** All 17 from `config.py` (diabetes T1/T2, obesity, metabolic syndrome, HF, CKD, etc.)
- **Mechanism MeSH IDs:** All 27 from `connectors/mesh.py` MECHANISM_SEED_IDS
- **Target drugs (expanded):** Current 23 + next-gen pipeline:
  - Add: orforglipron (Lilly oral GLP-1), survodutide (BI dual agonist), retatrutide (Lilly triple agonist), CagriSema (Novo amylin/GLP-1), pemvidutide (Altimmune), efinopegdutide (Merck), cotadutide (AZ), mazdutide (Innovent)
- **Target companies (expanded):** Current 6 CIKs + add Viking Therapeutics, Amgen, Zealand Pharma, Altimmune, Structure Therapeutics
- **Target conditions (expanded):** Add MASH/NASH, sleep apnea, diabetic retinopathy, peripheral artery disease
- **PubMed queries (expanded):** Add GLP-1 + MASH, GLP-1 + cardiovascular outcomes, SGLT2i + CKD progression, incretin + weight loss
- **Condition keywords:** Map MeSH IDs to trial condition text patterns for TA backfill

Then update `config.py` to load from YAML instead of hardcoded lists (or validate that `scripts/onboard_ta.py` handles this).

**Effort:** 1 day

### 1.2 Wire ConversationMemory into production

**Status:** Built (28 tests passing), NOT connected to chat routes.

**Changes:**
- `api/routes/chat.py` — instantiate ConversationMemory per session, pass to handlers
- `api/deps.py` — add `get_conversation_memory()` dependency
- `services/unified_handler.py` — pass memory context to LLM synthesis
- Frontend already sends conversation_history (built in prior session)

**Effort:** 2-3 days

---

## Phase 2 — Domain Validation + Quality Gate (Week 3)

*Prove the curated dataset works before adding features.*

### 2.1 Domain validation test suite

**File:** `tests/test_domain_coverage.py` (enhance existing)

**Structural tests:**
- All 18 TAs have ≥1 drug linked
- All 25 mechanisms have ≥1 drug linked
- Top 10 drugs each have: company + TA + mechanism + trials + literature links
- No duplicate company names (normalized)
- No dosage-pattern drug names
- All trials have non-empty labels
- No 'unknown' entity_type in entity_links
- Each of 9 sources has >0 records

**Clinical domain tests:**
- Semaglutide: GLP-1 RA, T2DM + Obesity TAs, Novo Nordisk, ≥100 trials, ≥50 articles
- Empagliflozin: SGLT2i, T2DM + Heart Failure TAs, Boehringer Ingelheim
- Sacubitril/valsartan: ARNI, Heart Failure TAs, Novartis
- Each mechanism class has expected drugs (GLP-1: sema, lira, tirze, dula, exe, lixi)

**Value tests (end-to-end query):**
- "Pipeline for GLP-1 agonists" → ≥5 drugs with trials
- "Compare semaglutide vs tirzepatide" → both entities found with metrics
- "Eli Lilly portfolio" → ≥5 drugs
- "Competitive landscape for SGLT2 inhibitors" → ≥3 segments

**Effort:** 2 days

### 2.2 Quality gate automation

- Integrate quality scorecard into post-pipeline-run hook
- Fail pipeline run if quality drops >5% from baseline
- Alert if new HITL items exceed threshold
- Track quality metrics over time (new table or append to telemetry)

**Effort:** 1 day

---

## Phase 3 — Scientific Depth (Weeks 4-6)

*From `lead_notes_4_dev.md` Tier 1 — makes the product credible to domain experts.*

### 3.1 Biomarker entity type

**New entity type in domain pack:** `biomarker`
- Fields: name, unit, normal_range, clinical_significance, category (efficacy/safety/surrogate)
- Key instances: HbA1c, eGFR, LVEF, BMI, body weight, fasting plasma glucose, blood pressure, LDL-C, NT-proBNP
- Link rules: Trial → HAS_PRIMARY_ENDPOINT → Biomarker, Trial → HAS_SECONDARY_ENDPOINT → Biomarker, Drug → TARGETS_BIOMARKER → Biomarker
- Extraction: Parse ClinicalTrials.gov outcome_measures (already fetched by connector)
- Migration: `schema/migrations/015_biomarker_entity.sql`

**Effort:** 1-2 weeks

### 3.2 Mechanism-of-action hierarchy

**Current:** Flat MOA labels (25 mechanisms, no parent-child).
**Target:** Tree structure using MeSH tree_numbers:

```
Incretin-based therapies
├── GLP-1 receptor agonists
│   ├── Single agonist (semaglutide, liraglutide, exenatide)
│   └── Modified (oral semaglutide)
├── Dual GIP/GLP-1 agonists (tirzepatide)
├── Triple GIP/GLP-1/glucagon agonists (retatrutide)
└── Amylin/GLP-1 combinations (CagriSema)
```

- Add `parent_mechanism_id` column to `mechanisms_of_action` table
- Populate hierarchy from MeSH tree_numbers (already in schema)
- Update `services/graph.py` to traverse hierarchy
- Update competitive landscape to show mechanism families

**Effort:** 3-5 days

### 3.3 Safety signal scoring (pharmacovigilance)

**Compute standard disproportionality metrics from FAERS data:**
- PRR (Proportional Reporting Ratio)
- ROR (Reporting Odds Ratio)
- Lower bound of 95% CI (signals where lb > 1 are statistically significant)

- New materialized view: `mv_safety_signals`
- New endpoint: `GET /metrics/safety-signals?drug=semaglutide`
- Link to relevant TAs (GLP-1 + thyroid cancer signal, GLP-1 + pancreatitis signal)

**Effort:** 1 week

### 3.4 Regulatory milestone entity type

- Fields: drug_id, milestone_type (PDUFA, CRL, breakthrough, accelerated, priority review), date, description, source
- Extract from: FDA Orange Book regulatory_milestones (already in DB), SEC filing text
- Timeline visualization in frontend

**Effort:** 3-5 days

---

## Phase 4 — The Product (Weeks 7-9)

*From `lead_notes_4_dev.md` Tier 0 items 0.4-0.6 — the features that make it sellable.*

### 4.1 Harden MCP server

**Status:** `api/mcp_server.py` has 6 tools. Needs:
- Integration tests against live DB
- Edge case handling (missing entities, empty results)
- Add `compare_entities` and `get_landscape` tools
- Wire LangGraph agents to use MCP tools where appropriate
- Documentation for external AI agent discovery

**Effort:** 2-3 days

### 4.2 Streaming LLM synthesis (SSE)

- Replace blocking `synthesize()` with `synthesize_stream()` (already exists in `services/llm.py:326`)
- Wire SSE endpoint in `api/routes/chat.py`
- Frontend: consume EventSource stream, render tokens progressively
- Vite proxy SSE config already added (user modified `vite.config.ts`)

**Effort:** 3-5 days

### 4.3 Wire user document/URL connectors

**Status:** Connectors exist (`user_document`, `user_url` in SourceType enum, configs in domain pack).
- Build upload endpoint: `POST /catalog/upload` accepting PDF/DOCX/URL
- Route through pipeline: normalize → resolve → embed → store → cross-link
- Show uploaded documents in catalog with provenance
- Private data overlay is the enterprise pricing justification

**Effort:** 3-5 days

### 4.4 Launch Simulator MVP

**Prerequisite:** Biomarkers (3.1), mechanism hierarchy (3.2), safety signals (3.3), regulatory milestones (3.4)

- New intent handler in `api/routes/chat.py`
- Input: "What are the risks of launching a GLP-1 agonist targeting obesity in 2027?"
- Orchestrate: pipeline strength + competitive landscape + safety signals + regulatory timeline + evidence density
- Output: Risk Score (0.0-10.0) + breakdown by category + source citations + pivot suggestions
- LLM synthesis with structured analyst prompt

**Effort:** 2-3 weeks (depends on Phase 3 completion)

---

## Phase 5 — Catalog & Librarian Experience (Weeks 8-10, parallel with Phase 4)

### 5.1 Quality dashboard on Overview tab

- Quality gauge per entity type (not just average)
- Completeness bars per key field
- Freshness indicator per source (days since last pull)
- HITL queue depth with urgency coloring
- Stale data alert banner

### 5.2 Enhanced Browse tab

- Faceted filters: mechanism, TA, company, source, quality range
- Bulk select + tag/enrich/status-change
- Field completeness column per entity
- Quick-nav links: drug → trials → company → mechanism

### 5.3 Enhanced Curation tab

- Priority sorting (critical failures first)
- Bulk resolve with context panel
- Queue metrics: velocity, resolution time

### 5.4 Catalog API additions

- `POST /catalog/bulk-update` — batch entity updates
- `POST /catalog/bulk-resolve` — batch HITL resolution
- `GET /catalog/completeness` — per-field completeness rates
- `POST /catalog/run-enrichment` — trigger AI enrichment for entity set

**Effort:** 1-2 weeks total

---

## Phase 6 — TA Expansion + Automation (Weeks 10-12)

### 6.1 Onboard Oncology TA

- `oncology.yaml` already exists and is complete
- Run `python scripts/onboard_ta.py domain/ta_definitions/oncology.yaml`
- Monitor pipeline run (fetch all 9 connectors with oncology targets)
- Run domain validation tests for oncology entities
- Generate quality scorecard

**Effort:** 2-3 days (framework + script exist)

### 6.2 Wire AutonomousResearchAgent

**Status:** Built (27 tests passing), NOT connected to scheduler.

- Connect to scheduler as nightly job
- Identify entities with FAIR score < 5.0
- Plan enrichment (which sources to query, which fields to fill)
- Execute → evaluate (FAIR delta ≥ 0) → commit or revert
- Log all actions to research_jobs table

**Effort:** 1 week

### 6.3 Auto-curation pipeline

- Scheduled weekly via `scripts/auto_curate.py`:
  1. Company dedup scan → auto-merge high-confidence
  2. Drug name cleanup → auto-fix patterns
  3. TA linkage backfill → new trial conditions → TA links
  4. AI enrichment on entities with quality < 0.5
  5. Quality scorecard generation
- All actions logged to `data_change_log`

**Effort:** 3-5 days

### 6.4 Quality monitoring hook

- New `QualityMonitorHook(ON_RUN_COMPLETE)` in pipeline_hooks.py
- Compute quality delta vs previous run
- Alert on quality drop > 5%
- Track metrics in `pipeline_quality_history` table

**Effort:** 1-2 days

---

## 90-Day Success Criteria

1. A user asks *"What are the risks of launching a GLP-1 agonist targeting obesity in 2027?"* and receives a sourced, scored answer in <10 seconds
2. The answer includes data from ClinicalTrials.gov, PubMed, FDA, and SEC filings, all cross-linked through resolved entities
3. Every claim links to a verifiable source with provenance
4. Multi-turn follow-ups work: *"What about the thyroid cancer signal?"*, *"Compare semaglutide vs. tirzepatide safety profiles"*
5. Oncology TA is onboarded and queryable with same depth as metabolic
6. Data quality score ≥ 8.0 / 10 (up from 4.7)
7. Drug completeness ≥ 80%, company completeness ≥ 65%
8. HITL queue < 500 actionable items
9. All data sources refreshed within 7 days
10. Autonomous research agent runs nightly, improving weakest entities

---

## Implementation Timeline

```
Week 1   ████████ Phase 0: Data Foundation (cure the data)
Week 2   ████████ Phase 1: Metabolic TA YAML + ConversationMemory
Week 3   ████████ Phase 2: Domain validation + quality gate
Week 4   ████░░░░ Phase 3.1: Biomarker entity type
Week 5   ░░░░████ Phase 3.2: Mechanism hierarchy
Week 6   ████████ Phase 3.3-3.4: Safety signals + regulatory milestones
Week 7   ████████ Phase 4.1-4.2: MCP hardening + streaming
Week 8   ████████ Phase 4.3-4.4: User uploads + Launch Simulator (start)
Week 9   ████████ Phase 4.4: Launch Simulator (complete)
         ████████ Phase 5: Catalog UI upgrades (parallel)
Week 10  ████████ Phase 6.1: Oncology TA onboarding
Week 11  ████████ Phase 6.2-6.3: Research agent + auto-curation
Week 12  ████████ Phase 6.4: Quality monitoring + polish + demo prep
```

---

## Critical Dependencies

| Item | Depends On | Blocks |
|------|-----------|--------|
| Phase 0 (data cure) | Database access | Everything |
| 1.1 Metabolic YAML | Phase 0 complete | 1.2, 6.1 |
| 3.1 Biomarkers | Migration 015 | 4.4 Launch Simulator |
| 3.3 Safety signals | FAERS data refreshed | 4.4 Launch Simulator |
| 4.4 Launch Simulator | 3.1 + 3.2 + 3.3 + 3.4 | 90-day demo |
| 6.1 Oncology onboard | `onboard_ta.py` working | TA expansion |
| 6.2 Research agent | Scheduler working | Continuous improvement |

---

## Files Created / Modified by Phase

### Phase 0
- RUN: `scripts/clean_drug_names.py`, `scripts/dedup_companies.py`, `scripts/backfill_ta_links.py`, `scripts/enrich_drugs.py`, `scripts/enrich_companies.py`, `scripts/auto_curate.py`, `scripts/quality_scorecard.py`

### Phase 1
- CREATE: `domain/ta_definitions/metabolic.yaml`
- MODIFY: `api/routes/chat.py`, `api/deps.py`, `services/unified_handler.py`

### Phase 2
- MODIFY: `tests/test_domain_coverage.py`
- MODIFY: `integration/pipeline_hooks.py` (quality gate hook)

### Phase 3
- CREATE: `schema/migrations/015_biomarker_entity.sql`
- MODIFY: `domain/pharma/pack.py` (biomarker entity + mechanism hierarchy)
- CREATE: materialized views for safety signals, regulatory milestones
- MODIFY: `services/metrics.py`, `services/graph.py`
- MODIFY: `api/routes/metrics.py` (new endpoints)

### Phase 4
- MODIFY: `api/mcp_server.py`
- MODIFY: `api/routes/chat.py` (SSE streaming, Launch Simulator, upload)
- MODIFY: `services/llm.py` (stream wiring)
- MODIFY: frontend components (SSE consumer, upload UI)

### Phase 5
- MODIFY: `frontend/src/components/DataCatalogPanel.tsx`
- MODIFY: `api/routes/catalog.py` (bulk endpoints)

### Phase 6
- RUN: `scripts/onboard_ta.py domain/ta_definitions/oncology.yaml`
- MODIFY: `scheduler/runner.py` (research agent integration)
- MODIFY: `integration/pipeline_hooks.py` (quality monitor hook)
