# SPEC-015 — Competitive Intelligence Agent: Backend Reuse & Frontend Strategy

**Status:** Assessment / Architectural Decision Document
**Inputs:** `comp_intelligence.md` (design doc), `comp_intel.tsx` (UX mockup), Market-Zero codebase
**Decision sought:** Should we extend the existing Market-Zero backend to deliver the Pharma Competitive Intelligence Agent, or build a new system? If extend, what is the minimal viable shape, and what frontend goes on top?

---

## 0. Executive verdict

**Extend the Market-Zero backend. Build a new frontend from the ground up. Run the new CI surface alongside the existing workspace, sharing the data plane.**

Three sentences for why:

1. The CI design's canonical data model (Document → Entity → Event → Signal) is structurally what we already have (`source_records → drugs/companies/trials/... → market_events → impact_assessments`), with about **60–70% of the entity layer and 40% of the event layer already implemented**. Throwing it away is wasteful.
2. The CI design's *unit of work* — the **Signal**: deduplicated, KBQ-tagged, dual-tier-scored, evidence-cited — does not exist in our schema yet, but it sits naturally on top of `market_events` + `impact_assessments` with one new table and a scoring/dedup service. Net new code ~3 weeks.
3. The current frontend (chat + canvas, Fraunces serif, single-question Q&A over a pharma graph) is **the wrong shape** for an analyst workflow that is dashboard-centric, watchlist-driven, push-alerted, and brief-composing. The `comp_intel.tsx` mockup is closer in spirit but hits Anthropic/MCP directly from the browser and has no concept of Signals, watchlists, or briefs. Both are inputs, neither is the answer.

**Recommended shape:** A second product surface (`/ci`) on the same backend. Existing `/research` (chat+canvas) keeps working for general pharma Q&A; new CI surface handles digest, signal detail, brief, alert, watchlist, reviewer queue.

---

## 1. The CI design's four convictions, reread against our codebase

The CI doc rests on four convictions. Each lands very differently against the current platform:

| CI conviction | Status in Market-Zero today |
|---|---|
| **The hard problem is canonicalisation and linking, not collection.** | ✅ Already our investment thesis. We have a 6-strategy entity resolver, mention normalizer, cross-linker with declarative `LinkRule`s and provenance, and 9 entity types in the pharma domain pack. This is our largest existing asset. |
| **Tiering must be enforced at the rule level (per KBQ), not the source level.** | ⚠️ Partially modeled. `market_events.source_tier` and `trust_score` exist (migration 026) but tier semantics are static per source, not per-KBQ rule. We will need a rule engine on top — does not exist. |
| **The unit of output is the Signal, not the Article.** | ❌ Not yet. We surface evidence items, query results, dossiers, and "insights" (`InsightEngine`), but we do not have a deduplicated, dual-tier-scored, KBQ-tagged Signal entity with an explicit superseded_by chain. This is the single largest missing concept. |
| **Build MVP on Tier 1 free structured sources (~70% of high-value signals).** | ✅ Already our connector strategy. We have 17 active connectors, most Tier 1. The CI MVP cut (SEC, Drugs@FDA, CT.gov, PubMed, DailyMed, Orange Book, MedWatch, PatentsView, news RSS) overlaps ours by ~6/9. |

**Read:** the platform's bone structure already matches the CI design. What's missing is the rule layer, the Signal entity, and ~5 KBQ-specific connectors. That's an extension, not a rewrite.

---

## 2. Capability mapping — CI requirement → what exists today

### 2.1 Connector coverage

| CI MVP source | Status | Notes |
|---|---|---|
| SEC EDGAR (XBRL 10-K/10-Q) | ✅ Have | `connectors/sec_edgar.py` pulls XBRL companyfacts → `company_financials` table. Company-level revenue, R&D, profit. |
| SEC EDGAR (8-K item-code parsing: 1.01 deals / 2.02 earnings / 5.02 exec) | ❌ Missing | We fetch 8-Ks but don't parse item codes. **This is the highest-leverage gap** — three KBQs depend on it (deals, financials, exec). |
| SEC DEF 14A | ❌ Missing | Needed for governance / annual exec confirmation. |
| Drugs@FDA / openFDA approvals | ✅ Have | `connectors/openfda_labels.py`, `openfda_faers.py`. |
| ClinicalTrials.gov v2 | ✅ Have | `connectors/clinical_trials.py`. Status-change diffing not yet wired as Events though. |
| AACT (CT.gov SQL mirror) | ❌ Missing | Optional; v2 API may suffice for MVP. |
| EU CTR (CTIS) | ❌ Missing | Phase 2. |
| PubMed E-utilities | ✅ Have | `connectors/pubmed.py`, with NCT cross-walk. |
| PubMed Central full-text | ✅ Have | `connectors/pmc.py`. |
| DailyMed SPL XML + diff | ⚠️ Partial | We have `openfda_labels` (text extracts) but not raw SPL XML diff. Missed signal: label changes. |
| FDA Orange Book | ✅ Have | `connectors/orange_book.py`. |
| FDA Purple Book | ❌ Missing | Biosimilars. Phase 2 priority. |
| FDA MedWatch RSS | ⚠️ Partial | `connectors/news.py` pulls FDA press RSS; MedWatch dedicated feed not separately ingested. |
| FDA Drug Shortages | ✅ Have | `connectors/fda_shortages.py`. |
| FDA AdCom calendar | ❌ Missing | Phase 2. |
| FDA designations (BTD, Fast Track, Priority Review, Orphan) | ❌ Missing | Phase 1.5; partly press-release-driven. |
| EMA (EPAR + CHMP opinions) | ⚠️ Partial | `connectors/ema.py` exists; CHMP opinion scraper specifically does not. |
| CMS NCD/LCD | ❌ Missing | Phase 2. The MCP listed in CI doc could short-circuit this. |
| CMS IRA selected-drugs list | ❌ Missing | Annual but high impact. Phase 2. |
| HTA agencies (NICE, IQWiG, HAS, CADTH, PBAC) | ❌ Missing | Phase 2. |
| Payer formulary PDFs | ❌ Missing | Phase 2 — known to be hard (PDF diff). |
| USPTO PatentsView | ❌ Missing | Phase 1.5. |
| USPTO PTAB | ❌ Missing | Phase 2. |
| WIPO / Espacenet | ❌ Missing | Phase 2. |
| Per-company IR scrapers | ❌ Missing | Phase 2 — known operational tax. |
| Conference abstract scrapers (ASCO/ESMO/AACR/ASH…) | ❌ Missing | Phase 2 — seasonal jobs. |
| Earnings call transcripts | ❌ Missing | Tier 2/3 — gated by AlphaSense or fragile Seeking Alpha scraping. Phase 2/3. |
| News (BioPharma Dive, FiercePharma, Endpoints, Reuters Health, STAT, FirstWord) | ⚠️ Partial | `connectors/news.py` covers Google News + FDA press RSS. Per-outlet RSS not yet split. |
| PR Newswire / Business Wire / GlobeNewswire | ❌ Missing | Phase 2. |
| ChEMBL, PubChem, MeSH, Open Targets | ✅ Have (bonus) | Not on CI's MVP list but useful for entity grounding. |

**Score:** ~9 of CI's MVP-tier-1 connectors are in some form already; ~6 are gaps; ~10 Phase-2 sources are gaps. Effort to close the MVP-tier gap: **~4–5 weeks for one backend engineer** (8-K item parser is the biggest single lift, ~1.5 weeks).

### 2.2 Entity model coverage

CI's canonical entities vs ours:

| CI entity | Market-Zero equivalent | Gaps |
|---|---|---|
| `Company` | `companies` (id, cik, ticker, name, country, sic_code) | Missing: LEI, DUNS, parent_company_id self-FK, `aliases[]`, `external_ids` jsonb bag. Easy migration. |
| `Product` | `drugs` | Strong: NDA, mechanism_id, brand+generic. Missing: modality enum, ATC codes, NDC list, UNII, ChEMBL/DrugBank IDs, licensor_history, status taxonomy aligned with CI's. Migration + backfill. |
| `Indication` | `therapeutic_areas` (looser) | Gap: CI wants ICD-10 + SNOMED on indication; we have MeSH + TA. Need an `indications` table layered above TAs, or extend TA. |
| `Trial` | `clinical_trials` | Strong: nct_id, phase, status, sponsor. Missing: `status_history[]` (we don't keep prior states), eudract, primary_endpoints structured, results_posted bool. Migration + ETL change. |
| `Person` | `investigators` (entity type exists in domain pack) | Weak: we don't keep `roles_history[]` per company; investigators are linked to trials, not company-role timelines. Significant extension for KBQ #2. |
| `Patent` | ❌ None | Mentioned in domain pack as 9th entity type but no table or connector. Phase 1.5. |
| `Deal` | ❌ None | New table. Tightly coupled to 8-K Item 1.01 parsing. |
| `Event` | `market_events` (✅ closely aligned) | Already extended in migration 026 with `source_tier`, `trust_score`, `primary_entity_type/id`, `status`, `event_hash`, `corroborating_sources`, `verified_at`. **This is the closest existing structure to the CI Event spine.** |
| `Document` | `source_records` | Have provenance, hash, raw payload. No `normalised_text` column for NLP — text lives in entity-typed tables. Adequate for MVP. |
| `Document-to-Entity link` | `entity_links` (with `link_via`, `confidence`, `provenance_source`) | Already a first-class table. |

**Score:** entity layer is **70% there**. Migrations to close: add aliases/external_ids on company, modality/codes on drug, status_history on trial, roles_history on person, new patent + deal tables. ~1 week of schema work + backfill.

### 2.3 Event spine

CI's event taxonomy (~20 event types) vs current `market_events`:

| Event type | Today |
|---|---|
| `regulatory_approval`, `regulatory_submission`, `regulatory_crl` | Partial — captured via news + openFDA but not as typed events with structured fields. |
| `trial_status_change`, `trial_results_posted` | ❌ Not emitted as events. CT.gov ETL writes/updates trial rows but doesn't diff and emit. **High-leverage fix.** |
| `label_change`, `safety_alert` | ❌ Need DailyMed SPL diff + MedWatch typed event. |
| `loe_event` | ❌ Compute from Orange Book patent expiry + exclusivity. |
| `deal_announced`, `deal_closed` | ❌ Need 8-K Item 1.01 parser. |
| `exec_change` | ❌ Need 8-K Item 5.02 parser. |
| `financial_disclosure`, `guidance_change` | Partial — XBRL captured into `company_financials`, but guidance diff engine and 8-K Item 2.02 parser not yet built. |
| `strategic_signal` | ❌ Phase 2 (NLP-heavy). |
| `event_participation` | ❌ Phase 2 (conference connectors). |
| `pricing_change`, `formulary_change` | ❌ Phase 2 (HTA + PDF diff). |
| `mfg_event` (483, warning letter, shortage) | Partial — shortages we have; 483/warning letters need FDA scraping. |
| `esg_disclosure` | ❌ Phase 2/3. |

**Read:** the `market_events` table is the right home; the gap is **event-emission logic** (diff engines, item parsers) and **a typed event taxonomy**, not new schema.

### 2.4 Signal layer

This is the largest conceptual gap. CI's `Signal` is the unit of output: deduplicated across documents, dual-scored (confidence tier + impact tier), KBQ-tagged, with explicit `superseded_by_signal_id`.

What we have:
- `InsightEngine` (services/insight_engine.py) emits `Insight` dataclasses by scanning materialized views — closest analog, but ephemeral (not persisted in this shape) and not deduplicated across sources.
- `impact_assessments` table (migration 026) stores impact magnitude + direction + narrative — could be repurposed but is per-event-per-affected-entity, not the canonical "1 Signal per real-world event" we want.

**What's missing:**
- A `signals` table (or `intelligence_signals`) keyed off `event_id`, with `kbq_tags[]`, `confidence_tier` enum, `impact_tier` enum, `headline`, `summary`, `superseded_by_signal_id`, `reviewed_by`, `shipped_to[]`.
- A deduplication / clustering service that groups facts on (event_type, primary_entity, event_date ± window) and selects an anchor by confidence tier.
- A YAML-driven impact-rule registry (analysts tune; engineering does not redeploy).
- Confidence-tier derivation rule (the static lookup in §5.4 of the CI doc) — currently we do per-source `trust_score` floats; need to add the tier enum + lookup.

**Effort:** ~2 weeks for the table + clustering service + rule engine, leveraging existing `event_hash` and `corroborating_sources` columns.

### 2.5 Intelligence layer

CI's pipeline: Extraction → Resolution → Linking → Dedup/Clustering → Scoring/Synthesis. Map onto ours:

| Stage | Existing asset | Gap |
|---|---|---|
| Extraction | Per-connector `normalize()`; LLM-based extraction in `services/llm.py`; user_document NER | Per-event-type extraction schemas (one per Item code, one per HTA decision form) — ad hoc today. |
| Resolution | `EntityResolver` 6-strategy cascade with mention normalizer + alias table | Strong; expand alias seeding for trial acronyms (KEYNOTE-189 etc.). Migration 033 already seeds brand aliases. |
| Linking | `CrossLinker` declarative `LinkRule`s | Strong; extend rules for trial↔publication via PubMed `[si]` tag, deal↔filing↔PR window matching. |
| Dedup/Clustering | `EntityConsolidator` for entities; `event_hash` for events | Event-level clustering service (not just hash equality but ±window) is missing. |
| Scoring | `FAIRScorer`, trust_score on events, severity on Insights | Composite impact score with magnitude/recency/corroboration multipliers — partially in place, not unified. |
| Synthesis | `LLMSynthesizer` + `CTXContextBuilder` + `validate_citations` + `verify_narrative_numbers` | Strong groundedness primitives; gap is **per-sentence** citation discipline (we cite at section/snippet level). Brief-composer that templates by KBQ doesn't exist. |

The `CTXQueryPipeline` ContextGuard (SPEC-011) is the right hallucination prevention primitive for the Signal narrative synthesis step — we just need to wire it as default for CI outputs.

### 2.6 Agent architecture

CI calls for an **orchestrator + 10 specialist agents** (Clinical Trials, Regulatory, Financial, Deal, Exec, Product&Label, Patent, Strategic Theme, Conference, Pricing, Synthesis).

What we have:
- `services/unified_handler.py` — single entry handler (opt-in, via `MZ_UNIFIED_HANDLER`).
- `services/agent/graphs/query_graph.py`, `team_eval_graph.py` — LangGraph-style graphs.
- `services/agent/tools/` — 4 tools (graph, metrics, RAG, SQL).
- `services/entity_agents.py` — orchestrator pattern for entity-type agents.
- `services/research_agent.py` — autonomous gap filler (built, 27 tests, not wired to scheduler).
- `services/data_steward.py` — curation loop.

**This is the right shape.** What's missing for CI:
- KBQ-named specialist agents — currently agents are entity-typed (drug, company, etc.), not question-typed. Easy refactor: register new personas in the agent registry, route by KBQ tag.
- Agent-specific tool sets (e.g. `edgar.item_5_02`, `dailymed.diff`, `transcript.extract`). Existing tool framework (`services/agent/tools/base.py`) supports adding new tools.
- An orchestrator with KBQ-aware routing — closer to a planner than the current intent classifier in `chat_handlers/intent.py`.

### 2.7 What we have that the CI doc doesn't ask for (bonus)

These are real assets we get for free:
- **Embeddings + pgvector** across drugs/companies/trials/protocols. CI doc is silent on semantic retrieval; we already have hybrid search, similar-entity, vector-by-MoA.
- **Materialized views** for KPIs (`mv_drug_pipeline_strength`, `mv_competitive_landscape`, `mv_safety_signals`).
- **Telemetry** (`services/telemetry.py`, migration 014) — CTX usage, query patterns, gap detection. Per-connector freshness telemetry exists.
- **CTX evidence packing** — token-budget-aware compression for LLM context, already production.
- **Test coverage** — 543+ tests, fixture-based, mock-DB. Ratchet stays.
- **Deployment** — Railway with CI, healthcheck, restart policy.
- **Conversation memory + research-job workspace** — ad-hoc Q&A workflow (CI Workflow D) is partly already built via `ChatWorkspaceService`.

---

## 3. Gap matrix — what we still have to build

Sized as S (≤1 sprint), M (1–2 sprints), L (2–4 sprints).

### 3.1 Backend extension (Phase 1 — MVP for KBQs 1, 2, 4, 5, 9, 10)

| # | Item | Size | Why now |
|---|---|---|---|
| B1 | `signals` table + Signal service (clustering, scoring, supersedence) | M | The unit-of-output gap. Blocks every CI workflow. |
| B2 | 8-K item-code parser (Items 1.01, 2.02, 5.02 minimum) | M | Unlocks 3 KBQs (Deal, Financial guidance, Exec). Highest single-source leverage. |
| B3 | Trial diff service (CT.gov status_history → `trial_status_change` events) | S | Already half-there in `clinical_trials.py`. Fill the gap. |
| B4 | DailyMed SPL XML connector + diff (`label_change` events) | M | Required for KBQ #5. |
| B5 | KBQ tagging on signals + KBQ rule engine (YAML-defined ignore/confirm rules per HR1.1, HR1.2, HR2.1…) | M | Embeds the CI doc's "hard rules" instead of paraphrasing. |
| B6 | Confidence tier enum + derivation lookup (per §5.4 of CI doc) | S | Replaces ad-hoc `trust_score` for downstream language gating. |
| B7 | Impact rule registry (YAML, hot-reload) | S | So analysts can tune without deploys. |
| B8 | Watchlist + alert subscription engine | M | CI Workflow E. New tables: `watchlists`, `watchlist_entities`, `alert_rules`, `alert_deliveries`. |
| B9 | Reviewer queue (state machine on signals: candidate → reviewed → shipped → superseded) | S | CI principle P5. |
| B10 | Brief composer service (templates per KBQ + per-sentence citations + versioned artifact) | M | CI Workflow C. Reuses `LLMSynthesizer`. |
| B11 | Per-connector freshness dashboard endpoint | S | Already partly there; expose. |
| B12 | Schema extensions: `companies.aliases/external_ids`, `drugs.modality/atc/ndc/unii`, `trials.status_history`, `persons.roles_history`, new `patents`, `deals` tables | M | One migration per. Backfill from existing data where possible. |
| B13 | Per-company IR scraper framework (template + 5 priority-co implementations to start) | L | Defer to Phase 2 if MVP scope pressure. |
| B14 | CTX ContextGuard as default for CI outputs (`MZ_UNIFIED_HANDLER=true` for /ci routes) | S | Land SPEC-011 first; it's in flight. |

**Phase 1 backend total: ~10–12 weeks for one backend engineer + part-time NLP support.** Matches CI doc's own 12-week MVP estimate, which was sized assuming a 2-engineer team without our existing assets.

### 3.2 Frontend (new from scratch)

The current frontend (Fraunces serif, chat-and-canvas, single-question Q&A) is **wrong shape** for the analyst's day. The mockup (`comp_intel.tsx`) is closer in spirit but is a MCP-direct demo without backend integration, signals, watchlists, briefs, or reviewer queue.

What to build (React 19 + TypeScript + Tailwind v4, sharing the design system tokens but a new layout):

| # | Surface | CI workflow | Notes |
|---|---|---|---|
| F1 | **Daily Digest** (home) | A | Watchlist-filtered, KBQ-sectioned, impact-sorted Signals. One-click promote / dismiss / tag. |
| F2 | **Signal Detail** | B | Event metadata, evidence stack ordered by confidence tier, side-by-side conflict view, historical context strip, cross-entity strip ("competitors in same indication"), inline ask-the-agent. |
| F3 | **Watchlist Manager** | A, E | Companies / products / KBQs / impact-tier subscriptions. |
| F4 | **Quarterly Brief Composer** | C | Pick company + date range + KBQs → orchestrator runs → reviewer queue → versioned artifact. |
| F5 | **Ad-hoc Q&A** | D | Chat surface, can reuse existing chat semantics; new prompt scaffold + Signal-citation rendering. |
| F6 | **Alert Center** | E | Push channels (email, Slack, Teams), rule editor, delivery history. |
| F7 | **Reviewer Queue** | All high-impact | List of `signals.status='candidate'`, side-by-side evidence, approve/reject/edit narrative. |
| F8 | **Connector Health** (admin) | NFR | Per-source freshness, error rate, doc count. |
| F9 | **Tracker views** (Trial, PDUFA, LOE heatmap, Deal, Exec feed, Earnings watch) | I4–I9 | Tabular and calendar projections of Signals filtered by event type. |

**Design language (proposal):**
- Density-first dark theme (à la `comp_intel.tsx`) for analyst-facing dashboards; switchable.
- DM Mono for IDs/codes/citations, DM Sans for body, Syne (or Fraunces) for display headings.
- Signal cards as the atomic UI primitive — same shape across digest, detail, brief.
- Evidence "stack" component: ordered by confidence tier, expandable, source-color-coded.
- Citation pills `[edgar:0]` style from the mockup, but resolving to Signals not raw results.
- Conflict badge component for cross-source disagreement.

**Frontend total: ~8–10 weeks for one FE engineer + part-time design.**

### 3.3 What to deliberately not do at MVP

- **Phase 2/3 connectors** (HTA, payer PDFs, conference scraping, transcripts) — defer until Phase 1 is shipping signals analysts actually read.
- **Rewriting entity resolution** — what we have is good; expand alias seeds, don't redesign.
- **Replacing `services/insight_engine.py`** — keep it, repurpose its outputs as Signals.
- **Custom property-graph DB** — Postgres + materialized edges has carried us to 600K links; CI doc Q6 default agrees.

---

## 4. Architecture sketch — extension shape

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                             FRONTEND (NEW)                                   │
│  /ci  → Digest · Signal Detail · Brief · Watchlist · Alerts · Reviewer Queue │
│  /research (existing) → chat + canvas, untouched                             │
└──────────────────────────────────────────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────────┐
│                          API LAYER (FastAPI, existing)                       │
│   New routes: /ci/digest, /ci/signals, /ci/briefs, /ci/watchlists,           │
│               /ci/alerts, /ci/review-queue                                   │
│   Existing:   /chat, /search, /entities, /metrics, /catalog                  │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────────┐
│                         AGENT / ORCHESTRATION                                │
│   Orchestrator (KBQ-routed)                                                  │
│   ├── Clinical Trials Agent  (existing CT.gov + PubMed tools)                │
│   ├── Regulatory Affairs Agent (openFDA + EMA + DailyMed-diff [NEW])         │
│   ├── Financial Agent (XBRL + 8-K Item 2.02 [NEW] + guidance diff [NEW])     │
│   ├── Deal Agent (8-K Item 1.01 [NEW] + PR matcher)                          │
│   ├── Exec Tracker Agent (8-K Item 5.02 [NEW] + IR leadership diff [P2])     │
│   ├── Product & Label Agent (DailyMed [NEW] + Orange Book + Purple Book [P2])│
│   ├── Patent & IP Agent (PatentsView [NEW])                                  │
│   ├── Strategic Theme Agent  (Phase 2)                                       │
│   ├── Conference Agent       (Phase 2)                                       │
│   ├── Pricing & Access Agent (Phase 2)                                       │
│   └── Synthesis Agent (existing LLMSynthesizer + Signal-aware brief composer)│
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────────┐
│                       INTELLIGENCE LAYER                                     │
│   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  ┌──────────┐   │
│   │Extraction│→ │Resolution│→ │ Linking  │→ │Dedup/Cluster │→ │Score+Syn │   │
│   │(connector│  │(EntityRes│  │(CrossLink│  │  [NEW: event │  │(Signal-  │   │
│   │ + LLM)   │  │ olver, 6 │  │  er, rule│  │   clustering │  │ aware    │   │
│   │          │  │ strategy)│  │  driven) │  │   + anchor)  │  │ brief)   │   │
│   └──────────┘  └──────────┘  └──────────┘  └──────────────┘  └──────────┘   │
└──────────────────────────────────┬───────────────────────────────────────────┘
                                   │
┌──────────────────────────────────▼───────────────────────────────────────────┐
│                          DATA PLANE                                          │
│  Postgres + pgvector                                                         │
│  ├── source_records  (Document layer — exists)                               │
│  ├── companies / drugs / trials / persons / patents [NEW] / deals [NEW]      │
│  ├── entity_links  (typed edges, confidence — exists, calibrated SPEC-013)   │
│  ├── market_events (Event spine — exists, extended in 026)                   │
│  ├── impact_assessments (per-affected-entity impact — exists)                │
│  ├── signals [NEW] (the unit of output: dedup'd, scored, KBQ-tagged)         │
│  ├── watchlists / alert_rules / alert_deliveries [NEW]                       │
│  ├── briefs / brief_versions [NEW]                                           │
│  ├── company_financials (XBRL — exists)                                      │
│  └── telemetry / steward_actions / ctx_events (governance — exists)          │
└──────────────────────────────────────────────────────────────────────────────┘
```

**Key insight:** the green columns in this diagram (existing) outnumber the blue (new) by roughly 3:1. This is a *spine extension*, not a parallel system.

---

## 5. KBQ feasibility, restated against our backend

This is the CI doc's table 4.x, recolored against what we actually have:

| KBQ | CI doc verdict | With Market-Zero today | Phase 1 doable? |
|---|---|---|---|
| 1. Financial | ✅ MVP | XBRL ingested; need 8-K Item 2.02 + guidance diff. ⚠️ partial | ✅ |
| 2. Exec movement | ✅ MVP | Need 8-K Item 5.02 parser + Person.roles_history. ❌ | ✅ (after B2, B12) |
| 3. Strategic shifts | ⚠️ Phase 1.5 | Need transcripts + theme classifier. ❌ | ❌ defer |
| 4. Clinical | ✅ MVP | CT.gov + PubMed have it; need diff→event emission. ⚠️ partial | ✅ (after B3) |
| 5. Product | ✅ MVP | Orange Book + drug records have it; need DailyMed SPL diff. ⚠️ partial | ✅ (after B4) |
| 6. AI / Digital | ⚠️ Phase 2 | Same as KBQ #3. | ❌ defer |
| 7. Conferences | ⚠️ Phase 2 | Need conference scrapers + transcript ingest. ❌ | ❌ defer |
| 8. Pricing & Access | ⚠️ Phase 2 | NADAC partial; need HTA + IRA + payer PDF. ❌ | ❌ defer |
| 9. Regulatory & Policy | ✅ MVP | openFDA + EMA partial; need designations, CHMP scraper. ⚠️ | ✅ |
| 10. M&A / Partnerships | ✅ MVP | Need 8-K Item 1.01 parser + Deal table. ❌ | ✅ (after B2, B12) |
| 11. ESG / Mfg / Supply | ⚠️ Phase 2 | Shortages have it; need warning letters + ESG report ingest. ⚠️ partial | ⚠️ partial |

**Phase 1 ships KBQs 1, 2, 4, 5, 9, 10 — exactly the CI doc's MVP cut.** None of those are blocked by missing platform primitives; all are blocked only by specific connectors and event-emission code.

---

## 6. Insight catalogue mapped to backend

CI's 14 insight types, against what serves them:

| # | Insight | Phase | Backend prerequisites |
|---|---|---|---|
| I1 Daily Digest | 1 | Signal table + watchlist + frontend F1 |
| I2 Company One-Pager | 1 | Signal filter by entity + frontend |
| I3 Quarterly Briefing | 2 | Brief composer (B10) + reviewer queue (B9) |
| I4 Trial Tracker | 1 | Trial diff (B3) + frontend table |
| I5 Approval/PDUFA Tracker | 1 (read) / 2 (forward calendar) | openFDA history + AdCom calendar (P2) |
| I6 LOE Heatmap | 1.5 | Patent table (B12) + Orange Book exclusivity computation |
| I7 Deal Tracker | 1 | 8-K Item 1.01 (B2) + Deal table (B12) |
| I8 Exec Movement Feed | 1 | 8-K Item 5.02 (B2) + roles_history (B12) |
| I9 Earnings Watch | 1 | XBRL (have) + 8-K Item 2.02 (B2) + guidance diff (part of B2) |
| I10 Strategic Theme Map | 2 | Theme classifier + transcript ingest |
| I11 Conference Coverage | 2 | Conference connectors |
| I12 Pricing & Access | 2 | HTA + formulary PDF |
| I13 Custom Q&A | 1 | Existing chat infra + Signal-aware retrieval |
| I14 Side-by-side Comparison | 1 | Signal filter + frontend |

**Phase 1 ships 8 of 14 insights** at MVP quality. That's a credible product.

---

## 7. Risks and how we contain them

| Risk | Probability | Impact | Containment |
|---|---|---|---|
| 8-K item-code parsing complexity (regex + LLM hybrid; PR↔filing date-window matching) | Medium | High | Start with rule-based parser on item-code headers, fall back to LLM extraction on body. Use existing `validate_citations` + `verify_narrative_numbers` to gate. ~1.5 sprint. |
| Signal dedup false positives (collapsing distinct events into one) | Medium | High | Conservative window thresholds; conflict detection surfaces to review queue rather than auto-merging mixed-tier clusters. Per CI principle P4 + Conflicting rule from Notes sheet. |
| Hallucinated citations in narrative synthesis | Medium | Critical | Wire `CTXContextBuilder` ContextGuard as default for /ci routes (SPEC-011 work). Per-sentence citation discipline in synthesis prompt. Reviewer queue gates impact_tier=high before external delivery. |
| Schema drift recurrence (the April 2026 DB crash mode) | Medium | Critical | SPEC-010 schema-drift cleanup must land before /ci ships. Migration test in CI for every PR touching schema. |
| Watchlist + alert blast radius (false-high-impact alerts at 3 AM) | Low | Medium | Reviewer-gated channel for impact_tier=high (CI principle P5). Throttle defaults. |
| Tier 3 vendor blockers (Cortellis, AlphaSense) gating Phase 2 KBQs | Medium | Medium | Phase 1 deliberately scoped to Tier 1; vendor procurement runs in parallel as separate decision track per Q3. |
| Frontend overreach (trying to ship 9 surfaces in 8 weeks) | High | High | Sequence: F1 → F2 → F7 → F3 → F6 → F4 → F8 → F9 → F5. Ship F1-F2 to a small group at week 4; iterate. |
| Two products competing for backend attention (existing /research vs new /ci) | Medium | Medium | Shared API layer. /research keeps current behavior; /ci is additive. No data-plane forking. |
| Performance: 50k docs/day target (NFR §11) vs current ingestion patterns | Low | Medium | Existing pipeline + Railway can handle this with WAL tuning per April postmortem. Re-measure after B2/B3 land. |
| Provenance integrity end-to-end (every Signal → ≥1 Document) | High importance | Existing `entity_links.provenance_source` gives us the substrate; enforce at write time on signals table via NOT NULL + check constraint on evidence array length ≥ 1. |

---

## 8. Phasing & effort estimate

### Phase 1 — CI MVP (~14 weeks)

**Backend (10–12 weeks, 1 engineer + part-time NLP):**
1. Weeks 1–2: schema extensions (B12), confidence tier (B6), impact rule registry (B7), CTX guard default (B14).
2. Weeks 2–4: Signals table + service (B1) + reviewer queue (B9).
3. Weeks 4–6: 8-K item-code parser (B2) — Items 1.01, 2.02, 5.02.
4. Weeks 6–7: Trial diff service (B3).
5. Weeks 7–9: DailyMed SPL connector + diff (B4).
6. Weeks 9–10: KBQ rule engine (B5).
7. Weeks 10–11: Watchlist + alert engine (B8).
8. Weeks 11–12: Brief composer (B10), freshness dashboard (B11).

**Frontend (8–10 weeks, 1 engineer, runs weeks 5–14):**
1. Week 1: design system + layout shell.
2. Weeks 2–3: F1 Daily Digest + F2 Signal Detail (the 80% of analyst time).
3. Week 4: F7 Reviewer Queue.
4. Week 5: F3 Watchlist Manager.
5. Week 6: F6 Alert Center.
6. Week 7: F4 Brief Composer (frontend half).
7. Week 8: F9 Trackers (Trial / PDUFA / Deal / Exec / Earnings).
8. Weeks 9–10: F5 Ad-hoc Q&A + F8 Connector Health, polish.

**KBQs delivered at MVP quality:** 1, 2, 4, 5, 9, 10. Insights I1, I2, I4, I5 (read), I7, I8, I9, I13.

### Phase 2 — Coverage depth (~10 weeks)

Per-company IR scrapers, conference connectors, AdCom calendar, HTA, IRA, payer formulary PDF, EU CTR, USPTO PTAB, designations, transcripts (Tier 2 path), strategic theme classifier. Adds KBQs 3, 6, 7, 8, 11. Adds Insights I3, I6, I10, I11, I12, I14.

### Phase 3 — Tier 3 + scale (~ongoing)

Cortellis (Reg + Deals + Pipeline), Citeline, AlphaSense, Bloomberg/Refinitiv, Evaluate, Medi-Span, Lex Machina, CB Insights, 50-state Medicaid. Procurement-gated. Backend-light, contract-heavy.

---

## 9. Decision recommendation

**Build it. Extend the backend, build the frontend new, run side-by-side at `/ci`.**

The CI design lines up with the platform's bone structure. The biggest single shift is conceptual — making the Signal a first-class persisted object rather than an ephemeral thing — and that work is bounded.

The frontend has to be new because the analyst's day (digest, watchlist, alert, brief) is structurally different from the current chat-and-canvas single-question UX. Reusing the design tokens but not the layout is the right level of reuse.

The biggest leverage point in Phase 1 is the **8-K item-code parser**: one connector extension unlocks three KBQs (Deal, Financial guidance, Exec movement). Build that first after the schema and Signal table are in place.

The biggest risk is **Signal dedup correctness** — collapsing distinct events into one would be invisible to the analyst until they catch it manually. The mitigation is conservative windows + a conflict review queue, not better auto-merging.

The Phase 1 scope (~14 weeks) is realistic with one backend engineer + one frontend engineer + part-time NLP and design support. It ships the analyst's daily workflow. Phase 2 fills coverage; Phase 3 adds Tier 3 vendors and scale.

---

## 10. Open questions to resolve before kickoff

These echo the CI doc's §12 but are reframed against the codebase decisions we'd be making:

1. **Watchlist / priority entities**: confirm the "20 clients" list. Drives priority-tag column on companies/drugs (used in impact scoring multipliers).
2. **Therapeutic area scope**: Onc, Immuno, CV/Met, Neuro? Drives connector targeting (CT.gov queries, conference picks for Phase 2).
3. **Reviewer SLA**: CI doc default is 2 business hours for impact=high. Confirm staffing implication.
4. **Output formats**: Web-first for digest/alerts, DOCX for briefs (CI doc default). Confirm — affects F4 implementation.
5. **Tier 3 procurement track**: which vendors get budgeted, by when? Doesn't block Phase 1 but blocks Phase 2 sequencing.
6. **LLM provider strategy**: CI doc default = Claude Opus for synthesis, Haiku/Sonnet for triage. Matches our current choices. Confirm cost ceiling per workflow.
7. **Existing `/research` surface**: keep, deprecate, or merge into `/ci` over time? Recommendation: keep — it serves a different audience (researchers, not CI analysts).
8. **Schema drift cleanup (SPEC-010) priority**: must land before B2 to avoid 8-K parser writing into half-broken tables. Confirm sequencing.
9. **Auth model**: existing `users_and_auth` (migration 034). Reviewer-queue role + watchlist ownership are new permission concepts — extend or new layer?

Once 1, 2, 7, and 8 have answers, Phase 1 sprint planning can start.

---

*End of assessment. Recommended next step: review with stakeholder, lock answers to questions 1/2/7/8, then break Phase 1 into a sprint plan starting with schema extensions (B12) and the Signals table (B1).*
