# Pharma Competitive Intelligence Agent — Design Document

**Status:** Draft v1.0 — Engineering Input Specification
**Audience:** Data Engineering, Backend, ML/NLP, Agent Orchestration, Product
**Source artifact:** `Pharma_News_Alert_Agent_Data_Source_Inventory.xlsx` (4 sheets: Data Mapping, Notes, Appendix, Data Source Inventory)

---

## 0. How to read this document

This document synthesises the team's existing CI source inventory and KBQ framework into a buildable specification. It is structured so that each section can be lifted directly into a sprint:

1. **Executive summary & guiding principles** — the "why" and the non-negotiables.
2. **Source landscape & feasibility** — every source rated for build effort, signal value, and phase.
3. **KBQ-by-KBQ feasibility analysis** — the 11 business questions, each mapped to sources, an extraction approach, hard/soft rules, and an MVP cut.
4. **Canonical data model** — entities, relationships, identifiers, and the event spine.
5. **Intelligence layer** — enrichment, linking, scoring, deduplication, and insight generation.
6. **Agent architecture** — orchestrator, specialist agents, tools, memory, and guardrails.
7. **CI user workflows** — what the analyst actually does, end to end.
8. **Insight catalogue** — the concrete outputs the system must produce.
9. **Build phasing & open questions** — sequencing and decisions that block development.

---

## 1. Executive summary

The team has catalogued **42 data sources across 8 alert categories** and defined **11 Key Business Questions (KBQs)** that a CI analyst covering large pharma must answer continuously. The current state is a manual workflow: analysts read, triangulate, and synthesise into newsletters and ad-hoc briefs. The proposed system replaces the *collection and first-pass synthesis* with an agentic pipeline, while keeping analysts in the loop for judgement-heavy tasks (impact sizing, narrative shaping, competitive implications).

**The design rests on four convictions:**

1. **The hard problem is not collection — it is canonicalisation and linking.** The same event (e.g. an FDA approval) shows up in 8-K filings, the FDA's openFDA API, DailyMed, company press releases, three news outlets, and an analyst note, each with different identifiers, timestamps, and framing. Without a canonical entity graph (Company → Product → Indication → Trial → Filing → Event), the agent cannot deduplicate, cannot triangulate, and cannot answer "what changed."
2. **Tiering must be enforced at the rule level, not the source level.** The Appendix's Tier 1/2/3 framework is correct for build prioritisation, but the *credibility* and *use* of a piece of information depends on the KBQ. For example, financial guidance is only valid from official disclosures (rule from Sheet "Data Mapping" KBQ #1: *"ignore analyst estimates in other non-credible sources"*); exec movement can be triggered by LinkedIn but must be *confirmed* by 8-K or company website. These rules belong in the intelligence layer, not in the connectors.
3. **The unit of output is the *Signal*, not the *Article*.** Analysts do not want "5 articles about Pfizer" — they want "Pfizer raised FY guidance by 3%, confirmed in Q3 10-Q, consistent with earnings call commentary, contradicting an earlier analyst note." The system's job is to collapse N raw documents into 1 signal with provenance.
4. **Build the MVP on Tier 1 free, structured sources.** Drugs@FDA, ClinicalTrials.gov, SEC EDGAR, PubMed, USPTO PatentsView, FDA MedWatch, EMA, CMS, and DailyMed cover roughly 70% of the high-value signals at zero licensing cost. Tier 2 (scraping + NLP of company IR, news, conferences) and Tier 3 (Cortellis, AlphaSense, Bloomberg) are additive, not foundational.

**MVP scope (Phase 1, ~12 weeks):** Tier 1 connectors + canonical entity graph + 4 KBQs (Clinical, Product, Regulatory, M&A) + daily digest workflow.
**Phase 2 (~8 weeks):** Tier 2 scrapers, news API, full 11 KBQs, alerting, impact scoring.
**Phase 3 (~ongoing):** Tier 3 vendor integration, multi-agent deep-dive workflows, custom briefs.

---

## 2. Guiding principles

| # | Principle | Implication |
|---|-----------|-------------|
| P1 | **Provenance is mandatory.** Every assertion in every output traces to ≥1 source URL, source timestamp, and ingestion timestamp. | Schema must carry `source_id`, `source_url`, `source_published_at`, `ingested_at`, `extracted_by` on every fact. |
| P2 | **Source tier governs trust, not inclusion.** A Tier 2 signal can *trigger* an alert; a Tier 1 source must *confirm* it before it ships in a deliverable. | Two-stage publishing pipeline: `candidate_signal` → `confirmed_signal`. |
| P3 | **Officially disclosed beats reported beats inferred.** | Hard rule encoded into the scoring layer (see §5.4). |
| P4 | **Deduplicate at the event level, not the article level.** | Event clustering is a first-class step, not an afterthought. |
| P5 | **Humans validate before high-stakes outputs ship.** Newsletters, client briefs, and any output that names individuals or makes financial claims pass through a reviewer queue. | Workflow must support a review/approve UI. |
| P6 | **Every KBQ has an "ignore" rule.** The Data Mapping sheet's "Functional rules" column is full of these. They must be encoded, not paraphrased. | Rule engine is part of the intelligence layer. |

---

## 3. Source landscape & feasibility analysis

### 3.1 Source inventory at a glance

The 42 sources cluster into **eight alert categories** and **three tiers**:

- **Tier 1 (govt / structured / free):** ~17 sources. Build first. APIs are stable, schemas documented, low maintenance.
- **Tier 2 (semi-structured / scraping / freemium):** ~18 sources. Build second. Higher signal richness for narrative context but fragile (websites change).
- **Tier 3 (licensed / pre-curated):** ~7 sources (Cortellis, Citeline, GlobalData, AlphaSense, Bloomberg, Refinitiv, Evaluate Pharma, IPD Analytics, Lex Machina, Medi-Span/RED BOOK). Build last. Saves NLP effort but adds material licensing cost and contractual constraints on downstream use.

### 3.2 Connector feasibility — by source

The table below converts each row of the source inventory into a build estimate. *Effort* is sized as S (≤1 sprint), M (1–2 sprints), L (2–4 sprints). *Signal value* reflects how many KBQs the source feeds and how unique the signal is.

| Source | Category | Tier | Access | Format | Effort | Signal value | Notes for engineering |
|---|---|---|---|---|---|---|---|
| ClinicalTrials.gov v2 API | Clinical | 1 | REST + RSS | Structured | S | High | Stable v2 API; AACT mirror available for SQL access; key entity = NCT ID. |
| ClinicalTrials.gov Results DB | Clinical | 1 | REST | Structured | S | High | Subset of above; results lag readouts by weeks — flag this in UX. |
| PubMed / MEDLINE | Clinical | 1 | E-utilities | Structured | S | High | Use ESearch + EFetch; cross-walk PMID ↔ NCT ↔ DOI. |
| EU CTR (CTIS) | Clinical | 1 | Scraping / bulk | Semi | M | Medium | No clean API; bulk dumps are best route. Mandatory for EU trials since Jan 2023 — coverage will grow. |
| Cortellis / Citeline / GlobalData | Clinical | 3 | Licensed API | Structured | M | High | Pre-curated pipeline; replaces large NLP investment but contractual redistribution limits apply. |
| Drugs@FDA (openFDA) | Product | 1 | REST | Structured | S | High | Approval actions, NDA/BLA/sNDA. Primary key = application number. |
| FDA NDC Directory | Product | 1 | REST + bulk | Structured | S | Medium | Product/package identification; foundational for product entity resolution. |
| DailyMed (NLM) | Product | 1 | REST + RSS | SPL/XML | M | High | Structured Product Labelling — best machine-readable label source. SPL parsing is non-trivial. |
| FDA MedWatch | Product | 1 | RSS | Semi | S | High | Real-time safety signal; immediate alert trigger. |
| FDA Orange Book | Product | 1 | REST + bulk | Structured | S | High | TE codes, patents, exclusivity → key for LOE timing. |
| FDA Purple Book | Product | 1 | Web + API | Structured | S | High | Biosimilar reference product tracking. |
| Drugs.com RSS | Product | 2 | RSS (6 feeds) | Semi | S | Medium | Useful aggregator; lower priority once Tier 1 is in place. |
| SEC EDGAR (8-K, S-1) | Competitor Moves | 1 | Full-text search API | Structured + unstructured | M | Very high | 8-K filings are the gold standard for material events; needs item-code parsing (Item 1.01, 2.01, 5.02 etc.). |
| Company IR pages | Competitor Moves | 2 | Per-company scraper | Unstructured | L | High | 50–100 scrapers; high maintenance burden. Use a scraper framework with per-site templates. |
| LinkedIn + IR pages | Competitor Moves | 2 | API limited / scraping | Unstructured | L | Medium | LinkedIn ToS is restrictive; use only as a *trigger* signal, confirm via SEC DEF 14A or company site. |
| Cortellis Deals / GlobalData | Competitor Moves | 3 | Licensed | Structured | M | High | Pre-curated deal terms — saves weeks of NLP work on press releases. |
| BioPharma Dive / FiercePharma / Endpoints | Competitor Moves + News | 2 | RSS + scraping | Unstructured | S | High | Curated trade press; high signal-to-noise; primary narrative source. |
| SEC EDGAR (10-K, 10-Q) | Financial | 1 | Full-text search API | Structured + unstructured | L | Very high | Product-level revenue extraction requires NLP on tables (XBRL helps but is incomplete for pharma segment data). |
| Earnings call transcripts (Seeking Alpha / AlphaSense) | Financial | 2/3 | Scraping / Licensed | Unstructured | M | Very high | AlphaSense is the licensed path; Seeking Alpha is fragile. Transcript-level NLP is high-value for forward guidance. |
| Elsevier Gold Standard / Medi-Span / RED BOOK | Financial | 3 | Licensed | Structured | M | High | Industry standard for WAC/AWP/ASP. No good free substitute. |
| Yahoo / Bloomberg / Refinitiv | Financial | 2/3 | API / Licensed | Structured | S–M | Medium | Sentiment & analyst signals; treat as supplementary per Functional Rule on KBQ #1. |
| 10-K (sales force size) | Financial | 1/2 | EDGAR + manual | Unstructured | M | Low–Medium | SG&A disclosures rarely break out field force; flag as low-confidence extraction. |
| FDA CDER Calendar + Guidance | Regulatory | 1 | RSS + scraping | Semi | S | High | PDUFA date tracker is critical; structured calendar pull is feasible. |
| EMA | Regulatory | 1 | RSS + scraping | Semi | M | High | CHMP opinions ~2 months ahead of EC approval — high lead-indicator value. |
| CMS.gov | Regulatory | 1 | RSS + scraping | Semi | M | High | NCD/LCD changes; IRA implementation page. The connected `CMS Coverage` MCP can substitute for parts of this. |
| CMS IRA Implementation | Regulatory | 1 | Scraping + manual | Semi | M | Very high | Selected drugs list is small (~10–20/yr) but each is a major event for the named manufacturer. |
| Medicaid.gov + state sites | Regulatory | 2 | Scraping | Semi | L | Medium | 50-state coverage is expensive; prioritise top 10 by enrollment as the inventory suggests. |
| Payer websites (UHC, Aetna, Cigna, CVS, ESI) | Regulatory | 2 | Scraping (PDF) | Unstructured | L | High | Formulary PDFs are quarterly and structured-but-not-machine-readable. PDF parsing + diff = the technical core. |
| Conference websites (ASCO, ESMO, etc.) | Conferences | 2 | Seasonal scraping | Unstructured | M | Very high | Abstract DBs open 1–4 weeks pre-conference; build seasonal jobs, not always-on scrapers. |
| JPM Conference / IR pages | Conferences | 2 | Scraping + manual | Unstructured | M | Very high | One annual event; outsized signal value. Worth manual curation supplementing automation. |
| FDA AdCom calendar | Conferences | 1 | RSS + scraping | Semi | S | High | AdCom votes are leading indicators of approvals. |
| Investor / R&D days | Conferences | 2 | IR scraping + manual | Unstructured | M | High | Same scraper infrastructure as IR pages. |
| Pharma event calendars | Conferences | 2 | Scraping | Semi | S | Low (operational) | Used to schedule the *other* conference scrapers. Operational, not analytical. |
| News API (Bing / NewsAPI) | News | 1/2 | API | Unstructured | S | Medium | High volume; relevance filtering and dedup are the work. |
| STAT / Reuters Health / BioPharma Dive | News | 2 | RSS + scraping | Unstructured | S | High | Same connector as Competitor Moves entry above. |
| PR Newswire / Business Wire / GlobeNewswire | News | 2 | RSS + API | Semi | S | High | Aggregated press releases; filter by ticker/company. |
| X / LinkedIn (social) | News | 2 | API limited / tools | Unstructured | M | Low–Medium | Use only for KOL signal detection; treat as soft signal. |
| USPTO PatentsView | Patent & IP | 1 | REST + bulk | Structured | M | High | Search by assignee + CPC class; key cross-walk = assignee ↔ company entity. |
| WIPO PATENTSCOPE / Espacenet | Patent & IP | 1 | Web search + API | Structured | M | Medium | Global view; PCT signals geographic intent. |
| USPTO PTAB | Patent & IP | 1 | Scraping + bulk | Structured | M | High | IPR proceedings — early Para IV signal; cross-ref Orange Book. |
| PACER / Docket Alarm / Lex Machina | Patent & IP | 2/3 | Licensed / scraping | Semi | L | Medium-High | PACER is free but operationally painful; Lex Machina is the productionised path. |
| Cortellis / Evaluate Pharma / IPD Analytics | Patent & IP | 3 | Licensed | Structured | M | High | Pre-calculated LOE with PTE / pediatric exclusivity adjustments. |

### 3.3 Feasibility headlines

- **~17 Tier 1 sources covering 8 categories can be built in roughly 8–10 weeks** by a 2-engineer team (1 backend, 1 NLP). They unlock 6 of 11 KBQs at MVP quality.
- **The two largest engineering risks are (a) per-company IR page scraping at scale and (b) payer formulary PDF parsing**, both of which are Tier 2 and required for KBQs around exec movement, deals, and pricing/access.
- **SEC EDGAR is the single highest-leverage source**: 8-K covers M&A, exec changes, material events; 10-K/10-Q cover financials; DEF 14A covers governance. Invest disproportionately here.
- **Tier 3 vendors are not "nice-to-have."** They are the *only* practical path to (i) pre-curated deal terms, (ii) structured pipeline analytics, (iii) reliable WAC/AWP/ASP pricing. Plan for licensing decisions in parallel with build.

---

## 4. KBQ-by-KBQ feasibility analysis

The Data Mapping sheet defines **11 KBQs**. Each is analysed below using a consistent template:
- **What the analyst is asking**
- **Required signals** (the atomic facts to capture)
- **Sources, in priority order** (per the sheet's "Sources" column, reconciled against the Source Inventory)
- **Extraction approach**
- **Hard rules** (must enforce — from the "Functional rules" column)
- **Soft rules** (heuristics)
- **Feasibility verdict + MVP cut**

### KBQ 1 — Financial & Market Performance

**What the analyst is asking:** Has the company's financial trajectory or guidance changed? Specifically: revenue, sales, EPS guidance, growth projections, R&D spend, SG&A spend, GAAP vs non-GAAP differences.

**Required signals:**
- Reported revenue (period, segment, product if disclosed)
- Reported EPS (GAAP and non-GAAP)
- Forward guidance (FY revenue, EPS, growth %)
- R&D and SG&A absolute values + YoY change
- Guidance *changes* vs prior quarter

**Sources, priority order:**
1. SEC EDGAR 10-K / 10-Q (Tier 1)
2. SEC EDGAR 8-K (for guidance updates between filings)
3. Earnings call transcripts (Tier 2/3 via AlphaSense)
4. Company press releases / IR pages
5. News sources (FirstWord Pharma, Business Wire, FiercePharma, Reuters, STAT+) — *for context only*
6. AlphaSense — for impact / cross-company comparison

**Extraction approach:**
- XBRL parsing of 10-K/10-Q for top-level financials. XBRL gives clean structured numbers for revenue, EPS, R&D, SG&A at company level.
- Pharma *segment* revenue (per-product) is usually outside XBRL. Use NLP table extraction on the filing's MD&A and Financial Statements sections. This is hard and should be flagged low-confidence until validated.
- 8-K Item 2.02 (Results of Operations) for early earnings disclosure ahead of full 10-Q.
- Earnings transcripts: extract guidance sentences with a fine-tuned classifier (or LLM with structured output) — fields: metric, value, period, direction (raise/lower/reaffirm).

**Hard rules (from sheet):**
- HR1.1: *Capture only officially disclosed financials or guidance.* → Reject any number whose source is not in {SEC, company press release, earnings transcript}.
- HR1.2: *Flag changes vs prior quarter or guidance as updates.* → Diff engine required: compare to last known value per metric per company.
- HR1.3: *Ignore analyst estimates from non-credible sources.* → Whitelist of credible analyst sources (AlphaSense, Bloomberg, Refinitiv); drop the rest.
- HR1.4: *All fields look for GAAP vs Non-GAAP updates.* → Both flavours stored as separate facts, never merged.

**Soft rules:**
- Forward guidance changes are higher-impact than reported results matching consensus.
- A guidance *raise* coincident with positive product news = high-confidence positive signal.

**Feasibility verdict:** **High** for top-line financials and guidance changes (Tier 1 is sufficient). **Medium** for product-level revenue (requires NLP + manual validation). **In MVP:** company-level revenue, EPS, guidance, R&D, SG&A from XBRL. **Phase 2:** product-level extraction.

---

### KBQ 2 — Corporate Governance & Leadership Changes

**What the analyst is asking:** Who has joined, left, been promoted, or had their role changed? Focus on Director-level and above, plus key R&D / Commercial leadership.

**Required signals:**
- Person (name, prior role, new role)
- Company
- Event type (join / exit / promotion / role change / board appointment)
- Effective date
- Successor named (in exit cases)
- Confirmation source

**Sources, priority order:**
1. Company press releases
2. Company website (Leadership / Governance pages)
3. SEC 8-K Item 5.02 (Departure/Election of Directors or Principal Officers)
4. SEC DEF 14A (proxy statement — annual)
5. LinkedIn (for confirmation only — NOT a primary trigger)
6. BioPharma Dive, Reuters, FiercePharma — for impact commentary

**Extraction approach:**
- 8-K Item 5.02 is the canonical, structured trigger. It is filed within 4 business days. NLP on the 8-K body extracts: person name, role before, role after, effective date, reason if disclosed.
- Daily scraper of ~50–100 priority companies' Leadership pages — diff against last snapshot to detect changes.
- LinkedIn is *not* an MVP source. Even if a profile changes, ToS and reliability concerns make it confirmatory only.
- Press releases provide the framing (mission, strategic intent) that 8-Ks lack.

**Hard rules (from sheet):**
- HR2.1: *Track Directors and above (or equivalent R&D/Commercial leadership).* → Title taxonomy + threshold filter required.
- HR2.2: *Include new joiners, exits, promotions, role expansions.* → Event-type enum.
- HR2.3: *Flag C-suite and key leadership changes as high impact.* → Impact tier based on title.
- HR2.4: *Provide successor in case of exit movement if available.* → Two-event linking: exit + arrival or exit + interim assignment.

**Soft rules:**
- Multiple senior departures within a quarter = strategic shift signal, even without a press release.
- A CMO/CSO change is a leading indicator for pipeline reprioritisation.

**Feasibility verdict:** **High** for SEC-confirmed changes. **Medium** for non-SEC-filer subsidiaries and private companies (require IR scraping + news triangulation). **In MVP:** 8-K Item 5.02 ingestion + company leadership page scraper for top 20 priority companies.

---

### KBQ 3 — Strategic shifts

**What the analyst is asking:** Has the company changed *how* it operates? Examples from the sheet: SG&A reduction / R&D increase, becoming "AI-first," changing therapy area focus, specialty vs generic emphasis, portfolio rationalisation.

**Required signals:**
- Strategic theme (e.g., "AI-first", "TA exit: cardiovascular", "pivot to specialty")
- Direction (entering / exiting / increasing / decreasing)
- Supporting evidence (which document, which sentence)
- Speaker / signer (CEO, CFO, board)

**Sources, priority order:**
1. Earnings call transcripts (CEO/CFO commentary)
2. Investor presentations / R&D day disclosures
3. Company strategy announcements / press releases
4. FirstWord Pharma, STAT, FiercePharma
5. AlphaSense — for consolidated cross-company strategy reports

**Extraction approach:**
- This KBQ is **inherently NLP-heavy**. Strategy is rarely stated as a structured fact; it emerges from prose.
- Use an LLM-based classifier with a strategic-theme taxonomy (TA focus, modality focus, geographic focus, capability/AI, capital allocation, M&A posture, ESG).
- Quote-level extraction: capture the sentence + surrounding context + speaker + venue.
- Cluster repeated assertions across earnings → R&D day → press release as evidence of a *committed* shift rather than a one-off comment.

**Hard rules:** The sheet does not specify formal rules for KBQ #3. Apply principle P3 (officially disclosed beats reported beats inferred): a strategic shift signal must be backed by ≥1 quote from CEO/CFO/CSO or an investor-facing document.

**Soft rules:**
- A theme repeated across ≥2 venues by ≥2 executives within 90 days = "committed shift."
- A theme appearing only in trade press without exec attribution = "rumour / not confirmed."
- 10-K Risk Factor *additions* are a quiet but reliable strategic signal (e.g., new AI-related risk language).

**Feasibility verdict:** **Medium.** Detection is feasible with current LLMs; *attribution and confirmation* are the harder parts. **In MVP:** keyword + LLM classification of earnings transcripts and press releases for the priority companies; manual review queue. **Phase 2:** cross-document theme aggregation.

---

### KBQ 4 — Clinical information

**What the analyst is asking:** What is happening in the clinical pipeline of every priority company — trial starts, status changes, phase transitions, endpoint changes, results, safety, RWE, post-market surveillance.

**Required signals:**
- Trial identifier (NCT, EudraCT, JPRN, etc.)
- Sponsor company
- Drug / intervention
- Indication
- Phase + status + status-change date
- Primary / secondary endpoints
- Results (efficacy values, p-values, AEs)
- Publications (PMID / DOI)
- Conference presentations (venue, date, abstract ID)

**Sources, priority order:**
1. Company press releases
2. ClinicalTrials.gov + EU CTR
3. Scientific conferences (ASCO, ESMO, ASH, etc.)
4. Peer-reviewed journals (PubMed)
5. Regulatory agency communications (FDA, EMA)
6. Citeline / Trialtrove (Tier 3 database)

**Extraction approach:**
- ClinicalTrials.gov v2 API is the spine. Daily delta pull on `LastUpdatePostDate`. Capture: NCT, sponsor, condition, phase, status, primary completion date, primary outcome measures, results module if posted.
- Status-change detection: maintain previous snapshot per NCT; emit a Signal when phase, status, or primary completion date changes.
- PubMed E-utilities: search by NCT ID (PubMed has a `[si]` tag for trial registry IDs), pull abstract and metadata.
- Conference scraping: seasonal jobs around major congresses; abstract IDs become the cross-walk.
- Press releases: NLP extraction of efficacy/safety claims; cross-reference back to NCT IDs.

**Hard rules:** No formal rules listed for this KBQ. Implicit rules:
- Press release claims must be linkable to an NCT or a credible scientific venue before they ship as "results." Otherwise tag as "company-stated, unverified."

**Soft rules:**
- A status change to "Terminated" or "Withdrawn" is high-impact regardless of phase.
- "Met primary endpoint" + p-value + effect size = high-confidence positive readout.
- Discrepancy between press release claim and CT.gov status = flag for analyst.

**Feasibility verdict:** **High.** This is the best-served KBQ by free Tier 1 sources. **In MVP:** full CT.gov + PubMed pipeline with cross-walk; press release linking. **Phase 2:** EU CTR, conference abstract pipelines, Tier 3 (Citeline) for pre-curated competitive landscape views.

---

### KBQ 5 — Product information

**What the analyst is asking:** For every product (in-market and pipeline), what is changing — sales, projections, launch dates, patent expiry, formulation, label/packaging?

**Required signals:**
- Product identifier (brand name, generic name, NDC, NDA/BLA #)
- Sales data (period, value, source)
- Launch milestones (planned / actual)
- Patent expiry date (and any LOE adjustments)
- Label changes (new indication, new dosage, new warning)
- Formulation / packaging updates

**Sources, priority order:**
1. Company press releases & earnings commentary
2. Product-level company websites
3. Regulatory labels (FDA via DailyMed, EMA)
4. News sources (BioPharma Dive, Reuters, FiercePharma, FirstWord)
5. Bloomberg, AlphaSense for sales projections

**Extraction approach:**
- DailyMed SPL is the canonical label source. Diff SPL versions per product to detect indication / dosage / boxed warning changes.
- Drugs@FDA approval actions feed launch / approval milestones.
- Orange Book + Purple Book: patent listings, exclusivities, biosimilar references — the LOE base layer.
- Earnings transcripts and 10-Q product-level callouts: for product revenue (low-confidence without segment disclosure).

**Hard rules:** No explicit rules; apply P3 (officially disclosed beats reported).

**Soft rules:**
- A label change adding a new indication is commercially equivalent to a new approval — same tier of impact.
- LOE within 24 months for a product >$1B in sales = pipeline-defining event for the company.

**Feasibility verdict:** **High** for label, approval, patent expiry. **Medium** for product-level sales without licensed data. **In MVP:** DailyMed SPL diff + Orange Book + Drugs@FDA. **Phase 2:** product-level revenue NLP. **Phase 3:** Evaluate Pharma / IPD Analytics for projections.

---

### KBQ 6 — AI / Digital updates

**What the analyst is asking:** How is each company adopting AI / digital across R&D, clinical, commercial, manufacturing?

**Required signals:**
- Company
- Function (R&D / clinical / commercial / manufacturing / G&A)
- AI/digital theme (drug discovery AI, trial design, RWE, sales analytics, factory automation)
- Initiative (named platform, partnership, hire)
- Source quote + venue

**Sources, priority order:**
1. Earnings call transcripts
2. Investor presentations / transcripts
3. Company strategy announcements / press releases
4. FirstWord Pharma, STAT, FiercePharma
5. CB Insights (Tier 3)

**Extraction approach:**
- Same NLP infrastructure as KBQ #3 (strategic shifts) — this is essentially a sub-theme.
- Custom keyword + classifier targeting AI-specific vocabulary (LLM, foundation model, generative, ML platform, in-silico, real-world data platform, digital therapeutics, etc.).
- Tag function (R&D vs commercial vs manufacturing) using context.

**Hard rules:** None explicit. Apply P3.

**Soft rules:**
- Named platform + named external partner (e.g., Big Tech, foundation model provider) = high-confidence committed initiative.
- Generic "we are leveraging AI" language without specifics = noise; suppress.

**Feasibility verdict:** **Medium.** Same as KBQ #3. **In MVP:** ride on the strategic-shift classifier with an AI sub-tag. **Phase 3:** CB Insights integration for funded-startup landscape.

---

### KBQ 7 — Conference & events information

**What the analyst is asking:** Which key events are each priority company participating in, and what did they say/show?

**Required signals:**
- Event (name, date, venue, type — investor / industry conf / TA conf)
- Company participation (presentation slot, abstract, poster)
- Document (deck, transcript, abstract)
- Key claims / data shown

**Sources, priority order:**
1. Company press releases
2. Investor decks shared on company website + dedicated conference websites
3. Conference coverage by FiercePharma, BioPharma Dive, STAT+, Endpoints, Reuters
4. Bloomberg, AlphaSense — for transcripts of:
   - Quarterly / annual presentations, R&D days, ESG events
   - Investor conferences (JPM, BofA, Goldman, Jefferies, Barclays)
   - TA conferences (ASCO, ASH, AACR, ESMO, AHA, ACC, EHA, EULAR, AAOS, World Vaccine Congress, AAN)

**Extraction approach:**
- Maintain a master event calendar (the inventory's "conference calendar tracking" source feeds this).
- Per event, schedule scraping jobs for the conference site (abstracts), and synchronise with company IR scrapers (deck/replay).
- NLP on transcripts/decks to extract: products mentioned, data shown (efficacy, safety), strategic claims, milestone commitments.
- Cross-link claims to the trial / product entities they reference.

**Hard rules:** None explicit.

**Soft rules:**
- An R&D day announcement carries higher commitment weight than a single earnings call mention.
- AdCom briefing documents and votes are leading indicators of approval — separate impact tier.

**Feasibility verdict:** **Medium.** Calendar + scraping is operational; transcript access is gated by AlphaSense / Bloomberg licensing. **In MVP:** AdCom calendar + ASCO/ESMO abstract scraping for priority products + IR deck downloads. **Phase 2:** transcript ingestion via licensed source.

---

### KBQ 8 — Pricing & Access information

**What the analyst is asking:** What product-specific pricing changes, payer changes (tiering), new access (country/indication), and reimbursement decisions have occurred?

**Required signals:**
- Product
- Geography / payer
- Change type (price change, tier change, PA criteria, step therapy, reimbursement decision)
- Effective date
- Magnitude (% price change, tier from/to)

**Sources, priority order:**
1. Company press releases
2. HTA agencies (NICE, IQWiG, HAS)
3. Payer / provider published reports
4. BioPharma Dive, Reuters, FiercePharma, FirstWord, Scrip
5. *(Implicit Tier 3:)* Medi-Span / Gold Standard / RED BOOK for WAC

**Extraction approach:**
- HTA agencies publish structured-ish decision documents. Build per-agency parsers (NICE, IQWiG, HAS, CADTH, PBAC).
- Payer formulary documents are quarterly PDFs. Build a PDF-diff pipeline: parse to structured table (drug, tier, restrictions), diff against last quarter, emit changes.
- WAC changes require licensed pricing data in practice; trade press coverage is a fallback signal.
- IRA selected drug list (CMS) — annual event but very high impact for named manufacturers.

**Hard rules:** None explicit.

**Soft rules:**
- An HTA negative recommendation in EU5 is materially worse for global revenue than US payer step-therapy addition, all else equal.
- Tier change up (lower tier number = more preferred) outperforms a price reduction in most payer dynamics.

**Feasibility verdict:** **Medium-Low without Tier 3.** WAC tracking is the gap. **In MVP:** HTA scraping + IRA list + trade press coverage. **Phase 2:** payer formulary PDF pipeline. **Phase 3:** licensed pricing data.

---

### KBQ 9 — Regulatory & Policy information

**What the analyst is asking:** What's happening across regulatory filings, approvals, rejections, special statuses (fast track, breakthrough, accelerated, priority, orphan, pediatric), label changes, Rx-to-OTC switches?

**Required signals:**
- Drug / application number
- Agency (FDA / EMA / MHRA / PMDA / Health Canada / TGA / CDSCO / ANVISA / NMPA)
- Action type (submission / approval / CRL / withdrawal / label change / designation grant)
- Date
- Indication

**Sources, priority order:**
1. Company press releases
2. Regulator announcements: FDA, EMA, MHRA, PMDA
3. Drugs@FDA, EMA websites
4. BioPharma Dive, Reuters, FiercePharma, FirstWord, Scrip

**Extraction approach:**
- Drugs@FDA + openFDA: structured approval actions.
- FDA designation databases (Breakthrough, Fast Track, Priority Review, Orphan, Rare Pediatric Disease) — partly structured, partly press-release-driven.
- DailyMed for label changes (cross-ref KBQ #5).
- EMA: EPAR + CHMP opinions — semi-structured PDFs / pages, scrape weekly.
- Other regulators: lower automation maturity; consider Tier 3 (Cortellis Regulatory Intelligence) for global coverage. The connected Cortellis MCP can substitute.

**Hard rules:** None explicit.

**Soft rules:**
- CHMP positive opinion → EC approval ~60 days later (used as predictive lead indicator).
- A CRL (Complete Response Letter) is rarely disclosed by the FDA directly; expect it via 8-K and press release.

**Feasibility verdict:** **High** for FDA, EMA. **Medium** for global. **In MVP:** FDA + EMA. **Phase 2/3:** Cortellis Regulatory for ROW.

---

### KBQ 10 — M&A and Partnerships

**What the analyst is asking:** What M&A, licensing, collaboration, or partnership deals have been announced?

**Required signals:**
- Parties (acquirer, target / partner A, partner B)
- Deal type (M&A / asset deal / license-in / license-out / co-promotion / R&D collaboration)
- Subject (asset, indication, geography)
- Financial terms (upfront, milestones, royalties, total potential value)
- Closing date / status

**Sources, priority order:**
1. Company press releases
2. SEC filings (8-K Item 1.01 for material agreements; S-1, 10-K Item 1)
3. Quarterly transcripts, annual reports
4. BioPharma Dive, Reuters, FiercePharma, FirstWord, Scrip
5. BioMedTracker, Evaluate Pharma, Pitchbook (Tier 3)

**Extraction approach:**
- 8-K Item 1.01 ("Entry into a Material Definitive Agreement") is the structured anchor.
- Press release NLP for deal terms (parties, upfronts, milestones, royalties, asset/indication). LLMs with structured output are well-suited here.
- Cross-check against Tier 3 deal databases for confirmation and structured terms.

**Hard rules:** None explicit; apply P3.

**Soft rules:**
- Undisclosed terms ≠ small deal. Flag explicitly rather than infer.
- Multiple deals from the same acquirer in a TA within 12 months = consolidation pattern.

**Feasibility verdict:** **High** at "deal happened" level. **Medium** at "deal terms" level without Tier 3. **In MVP:** 8-K Item 1.01 + press release NLP. **Phase 3:** Cortellis Deals / Pitchbook.

---

### KBQ 11 — Others (ESG, Manufacturing & Supply Chain)

**What the analyst is asking:** Sustainability / ESG disclosures, manufacturing changes, supply chain disruptions.

**Required signals:**
- ESG metric updates (emissions, diversity, governance scores)
- Manufacturing facility events (new facility, expansion, closure, FDA Form 483, warning letter)
- Supply chain events (drug shortage, CMO change)

**Sources, priority order:**
1. Company press releases
2. Company ESG / sustainability reports
3. BioPharma Dive, Reuters, FiercePharma, FirstWord, Scrip
4. *(Implicit Tier 1:)* FDA Drug Shortages database, FDA Warning Letters / 483s

**Extraction approach:**
- ESG reports are annual PDFs — schedule annual ingestion + structured extraction.
- FDA Drug Shortages list — daily delta pull (free, structured).
- FDA Warning Letters and Form 483 data — scraping FDA's site (already partly in the inventory's regulatory section).

**Feasibility verdict:** **Medium** as a packaged KBQ; individually most sub-signals are tractable. **In MVP:** drug shortages + warning letters. **Phase 2:** ESG diff. Lowest priority of the 11.

---

### 4.x KBQ feasibility summary

| KBQ | Tier 1 coverage | NLP load | Tier 3 dependency | MVP-ready? | Highest-leverage source |
|---|---|---|---|---|---|
| 1. Financial | High (XBRL) | Medium | Low for company-level, High for product-level | ✅ | SEC EDGAR 10-K/10-Q + 8-K |
| 2. Exec movement | High (8-K Item 5.02) | Low | Low | ✅ | SEC 8-K |
| 3. Strategic shifts | Medium | High | Medium (AlphaSense) | ⚠️ Phase 1.5 | Earnings transcripts |
| 4. Clinical | Very High | Medium | Low | ✅ | ClinicalTrials.gov + PubMed |
| 5. Product | High | Medium | Medium (Evaluate) | ✅ | DailyMed + Orange Book |
| 6. AI / Digital | Medium | High | Medium (CB Insights) | ⚠️ Phase 2 | Earnings transcripts |
| 7. Conferences | Medium | High | High (AlphaSense for transcripts) | ⚠️ Phase 2 | Conference websites + IR |
| 8. Pricing & Access | Medium-Low | Medium | High (Medi-Span) | ⚠️ Phase 2 | HTA + IRA + payer PDFs |
| 9. Regulatory & Policy | High | Medium | Medium (Cortellis Reg) | ✅ | Drugs@FDA + EMA |
| 10. M&A / Partnerships | High | High | Medium (Cortellis Deals) | ✅ | SEC 8-K Item 1.01 |
| 11. ESG / Mfg / Supply | Medium | Medium | Low | ⚠️ Phase 2 | FDA Shortages + Warning Letters |

**MVP cut: KBQs 1, 2, 4, 5, 9, 10** — six KBQs, fully buildable on Tier 1 sources, covering the core analyst workflow.

---

## 5. Canonical data model

The data model is the spine of the system. Every connector writes into it; every agent reads from it; every output cites it. The model has four layers:

1. **Raw layer** — exact-as-fetched documents with provenance.
2. **Entity layer** — canonical Company, Product, Trial, Person, Patent, Deal, Event, Document.
3. **Fact / Signal layer** — atomic, typed assertions extracted from documents.
4. **Insight layer** — clusters, narratives, scores, briefs.

### 5.1 Raw layer

```
Document
├── document_id (UUID)
├── source_id (FK → Source)
├── source_url
├── source_published_at
├── ingested_at
├── content_type (api_json | rss_item | html | pdf | xbrl | spl_xml | sec_filing)
├── raw_payload (blob)
├── normalised_text (string — extracted plain text for NLP)
├── document_hash (SHA-256 of raw_payload — dedup key)
└── language
```

Every connector produces `Document` rows. Nothing is deleted; entities and facts are derived.

### 5.2 Entity layer — canonical entities

#### Company
```
company_id (UUID)
legal_name
common_name
ticker
cik (SEC Central Index Key)         -- the master cross-walk for filings
lei (Legal Entity Identifier)
duns
country_hq
parent_company_id (self-FK for subs)
status (active | acquired | dissolved)
aliases [list]                       -- "GSK" / "GlaxoSmithKline plc"
external_ids {                       -- adapter-friendly bag
  openfda_labeler_codes: [...]
  cortellis_id: "..."
  pitchbook_id: "..."
}
```

#### Product
```
product_id (UUID)
brand_name
inn / generic_name                  -- WHO INN where available
company_id (current rights holder)
licensor_history [list]              -- M&A creates rights transfers
modality (small_molecule | mab | adc | bispecific | gene_therapy | cell_therapy | rna | vaccine | device)
mechanism_of_action
atc_codes [list]
ndc_codes [list]                    -- from FDA NDC Directory
fda_application_numbers [list]      -- NDA / BLA / ANDA / sNDA
ema_emea_numbers [list]
unii_codes [list]                   -- FDA's substance ID
chembl_id
drugbank_id
status (preclinical | phase_1..3 | filed | approved | withdrawn | discontinued)
first_approval_date
indications [list of Indication FK]
```

#### Indication
```
indication_id
mesh_term
icd10_codes [list]
snomed_id
description
```

#### Trial
```
trial_id (UUID)
nct_id                              -- ClinicalTrials.gov
eudract_id                          -- EU CTR
other_registry_ids {jprn, ctri, ...}
sponsor_company_id
collaborator_company_ids [list]
products [list of Product FK]
indications [list of Indication FK]
phase
status (not_yet_recruiting | recruiting | active | completed | terminated | withdrawn | suspended)
status_history [list of {status, date, source_document_id}]
primary_completion_date_planned
primary_completion_date_actual
primary_endpoints [list]
secondary_endpoints [list]
results_posted (bool)
publication_pmids [list]
last_observed_at
```

#### Person
```
person_id
full_name
canonical_name (lowercased, normalised)
linkedin_url
roles_history [list of Role]
```
```
Role
├── company_id
├── title
├── functional_area (CEO | CFO | CSO | CMO | CCO | head_of_RD | board | other)
├── seniority_tier (C-suite | EVP/SVP | VP | Director | Other)
├── start_date
├── end_date
├── source_document_id
└── confirmed (bool — true only when confirmed by 8-K or company website)
```

#### Patent
```
patent_id
patent_number (US/EP/PCT)
type (grant | application | design | PTE)
assignee_company_id
filing_date
grant_date
expiration_date
priority_date
cpc_codes [list]
linked_products [list of Product FK]   -- via Orange Book / Purple Book listing
status (granted | abandoned | expired | challenged)
```

#### Deal
```
deal_id
deal_type (M&A | asset | license_in | license_out | collaboration | co_promote | option)
parties [list of Company FK]
acquirer_id
target_id
subject_products [list]
subject_indications [list]
geography
upfront_value
milestone_potential
royalty_terms (text)
total_potential_value
announced_date
closing_date
status (announced | closed | terminated)
```

#### Event (a polymorphic anchor — see §5.3)
```
event_id
event_type                            -- enum: see §5.3
primary_entity_type                   -- which entity is the "subject"
primary_entity_id
event_date                            -- when it actually happened (not when reported)
disclosed_date                        -- when it became publicly known
embargoed (bool)
documents [list of Document FK]       -- all docs that evidence this event
related_events [list]                 -- e.g. press release + 8-K + news article
```

#### Document-to-Entity link table
```
document_entity_link
├── document_id
├── entity_type
├── entity_id
├── extraction_method (rule | ner | llm | manual)
├── confidence (0.0–1.0)
└── span (char offsets)
```

### 5.3 The Event spine

The `Event` entity is what makes "deduplicate at the event level" (P4) operationally possible. Every signal that matters is, structurally, an event. The event taxonomy maps directly to the KBQs:

| Event type | Maps to KBQ | Primary entity |
|---|---|---|
| `trial_status_change` | 4 | Trial |
| `trial_results_posted` | 4 | Trial |
| `trial_publication` | 4 | Trial + Document |
| `regulatory_submission` | 9 | Product |
| `regulatory_approval` | 9 | Product |
| `regulatory_crl` | 9 | Product |
| `regulatory_designation` (BTD, Fast Track, …) | 9 | Product |
| `label_change` | 5 / 9 | Product |
| `safety_alert` | 5 | Product |
| `loe_event` (patent expiry, exclusivity loss) | 5 | Product |
| `deal_announced` | 10 | Deal |
| `deal_closed` | 10 | Deal |
| `exec_change` | 2 | Person + Company |
| `financial_disclosure` | 1 | Company |
| `guidance_change` | 1 | Company |
| `strategic_signal` | 3 / 6 | Company |
| `event_participation` | 7 | Company + Event venue |
| `pricing_change` | 8 | Product |
| `formulary_change` | 8 | Product + Payer |
| `mfg_event` (483, warning letter, shortage) | 11 | Company / Product |
| `esg_disclosure` | 11 | Company |

### 5.4 Fact / Signal layer

A `Signal` is what the agent ships — to a digest, a brief, or a downstream system. It is the unit of intelligence.

```
Signal
├── signal_id
├── event_id (FK)
├── kbq_tags [list]                     -- which KBQs this serves
├── headline (string, ≤120 chars)
├── summary (string, ≤500 chars)        -- agent-written, paraphrased only
├── direction (positive | negative | neutral | mixed)
├── confidence_tier (confirmed | reported | inferred)
│                                       -- per principle P3
├── impact_tier (high | medium | low)   -- per scoring rules below
├── evidence [list of Document FK]
├── primary_entity_id (Company/Product/Person/Trial/Deal)
├── related_entity_ids [list]
├── created_at
├── superseded_by_signal_id (nullable)  -- when newer info supersedes
├── reviewed_by (user_id, nullable)
└── shipped_to (digest_id / brief_id list)
```

#### Confidence tier — derivation rule (HARD)

| Source class | confidence_tier |
|---|---|
| SEC filing, regulator (FDA/EMA/CMS), CT.gov, Orange Book, DailyMed, peer-reviewed PubMed | **confirmed** |
| Company press release, IR page, official transcript | **confirmed** *for company-attributable claims*; **reported** for forward-looking claims |
| Trade press (FiercePharma, BioPharma Dive, STAT, Endpoints, Reuters Health, FirstWord) | **reported** |
| LinkedIn, X/Twitter, general news API, blog | **inferred** |
| Tier 3 vendor (Cortellis, Citeline, AlphaSense) | **confirmed** for facts; **reported** for vendor analysis |

#### Impact tier — derivation rule (heuristic, tunable)

Impact is computed per event type. Examples:

- `regulatory_approval` for a product with projected peak sales >$1B → **high**
- `trial_status_change` to "terminated" in Phase 3 → **high**
- `exec_change` at C-suite → **high**; at Director level → **low**
- `deal_announced` with disclosed total >$1B → **high**
- `guidance_change` with magnitude >5% → **high**
- `label_change` adding new indication → **high**; minor warning addition → **medium**

Impact rules live in a YAML registry, not in code, so analysts can tune them.

---

## 6. Intelligence layer

The intelligence layer sits between raw documents and the analyst-facing surface. It performs five jobs in sequence:

```
   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
   │  Extraction  │ → │   Resolution │ → │   Linking    │ → │ Deduplication│ → │   Scoring &  │
   │              │   │              │   │              │   │  & Clustering│   │   Synthesis  │
   └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘
```

### 6.1 Extraction

Per source type, the extraction strategy differs:

| Source class | Extraction strategy |
|---|---|
| Structured APIs (CT.gov, openFDA, PatentsView, EDGAR XBRL) | Direct mapping — schema → entity fields |
| SEC filings (8-K, 10-K, 10-Q, DEF 14A, S-1) | Item-code parser + section parser + LLM extraction per item type. Item 1.01 → Deal; Item 5.02 → exec_change; Item 2.02 → financial_disclosure |
| DailyMed SPL XML | XSLT → structured label fields; diff against prior version |
| HTML / press releases | LLM extraction with structured output schema per event type |
| PDFs (formularies, ESG, EMA EPARs) | OCR if scanned + layout-aware parser + LLM extraction |
| Transcripts | Sentence-level segmentation + speaker attribution + LLM classification by KBQ |
| RSS / news APIs | Title + summary triage by relevance classifier; full fetch only if relevant |

Each extraction emits one or more `Fact` candidates with: extraction method, confidence, span pointer, model/version. Nothing is committed to the entity layer until resolution succeeds.

### 6.2 Entity resolution

The hardest engineering problem after collection is canonicalisation. Specifically:

- **Companies:** "Pfizer," "Pfizer Inc.," "Pfizer (NYSE: PFE)," CIK 0000078003, openFDA labeler 0069 — all the same. Resolution priority: ticker → CIK → LEI → exact name match → fuzzy + alias table.
- **Products:** brand vs INN vs ATC vs NDC. Maintain a `product_alias` table and an LLM-assisted disambiguator for ambiguous mentions ("Keytruda" easy; "MK-3475" or "pembrolizumab" requires alias resolution).
- **Trials:** NCT and EudraCT IDs are the canonical keys. Press releases often refer to trials by acronym (KEYNOTE-189, CHECKMATE-067) — maintain an acronym → registry-ID mapping table.
- **People:** name + company + role context. Avoid creating duplicate persons across companies (career moves are exactly the events we want to capture).
- **Indications:** MeSH terms as canonical, ICD-10 / SNOMED as cross-references.

Resolution is a service. Every fact-extraction step calls it. Unresolved entities go to a review queue, not to the entity layer.

### 6.3 Cross-source linking

Once entities are resolved, link facts across sources:

- **Trial ↔ Publication:** PubMed `[si]` tag with NCT ID; if missing, link by matching sponsor + drug + indication + completion date.
- **Trial ↔ Press release:** match by NCT ID mention, or by the trial-acronym alias table.
- **Approval ↔ Filing ↔ Label:** Drugs@FDA application number is the bridge between approval action, the underlying NDA/BLA submission, and the SPL on DailyMed.
- **Deal ↔ Filing ↔ Press release:** 8-K Item 1.01 + dated press release within ±1 day window.
- **Patent ↔ Product:** Orange Book listings and Purple Book listings provide the link directly. For non-listed patents, NLP on patent claims + assignee + drug-name mention.

Linking outputs are explicit edges in the graph (typed: `evidence_for`, `references`, `supersedes`, `acquired_in`, etc.).

### 6.4 Event clustering & deduplication

For every newly extracted fact, find the canonical Event:

1. **Same-event detection:** group facts that share (event_type, primary_entity, event_date ± window). Window is event-type-specific: ±1 day for approvals, ±7 days for deals, ±30 days for strategic signals.
2. **Anchor selection:** within a cluster, the highest-confidence-tier source becomes the anchor. All other documents in the cluster become evidence on the same Event.
3. **Conflict detection:** if facts within a cluster contradict (e.g. approval date varies across sources), surface to a review queue. Do not auto-resolve with majority voting on confidence-tier-mixed clusters.

The Notes sheet's "Conflicting rule" line is a placeholder — this is where it gets implemented.

### 6.5 Scoring & impact synthesis

Two scores per signal, both stored, both surfaceable to the user:

**Confidence score** — derived from the rule in §5.4.

**Impact score** — composite of:
- Event type base weight (from YAML)
- Entity weights (priority companies / priority products score higher; the Data Mapping sheet refers to "20 clients" — these become priority tags)
- Magnitude (% guidance change, deal value, peak sales projection)
- Recency
- Cross-source corroboration count (within the cluster)
- KBQ-specific multipliers (e.g. C-suite multiplier on exec_change)

The output is a single 0–100 score plus a human-readable rationale string ("High: C-suite change at priority company, confirmed in 8-K + press release + 2 news outlets").

### 6.6 Narrative synthesis (LLM)

The final step turns a Signal into a paragraph an analyst will actually read. Constraints:

- **Paraphrase only.** No verbatim copying from source documents (copyright + provenance).
- **Cite at the sentence level.** Each sentence carries the document IDs that support it.
- **No speculation.** If the source did not say it, the agent does not say it. Forward-looking inferences must be explicitly tagged.
- **Length-bounded.** Headline ≤120 chars; summary ≤500 chars; long-form briefs are a separate output type.

---

## 7. Agent architecture

The system is agentic in the sense that an orchestrator decomposes user goals into tasks and dispatches them to specialist agents that read and write the entity / signal layer. The agents do not invent data — they query the data model, call extraction tools, and synthesise.

### 7.1 Agent roster

```
                            ┌────────────────────────┐
                            │      Orchestrator      │
                            │  (planner + router)    │
                            └─────────┬──────────────┘
                                      │
   ┌──────────┬──────────────┬────────┼───────────┬─────────────┬─────────────┐
   ▼          ▼              ▼        ▼           ▼             ▼             ▼
┌──────┐ ┌─────────┐ ┌──────────────┐ ┌────────┐ ┌─────────┐ ┌──────────┐ ┌──────────┐
│Clini-│ │Regulator│ │   Financial  │ │  Deal  │ │  Exec   │ │Strategic │ │ Synthesis│
│ cal  │ │  Affair │ │              │ │        │ │ Tracker │ │  Theme   │ │ (Brief)  │
│Trial │ │         │ │              │ │        │ │         │ │          │ │          │
└──────┘ └─────────┘ └──────────────┘ └────────┘ └─────────┘ └──────────┘ └──────────┘
```

Each specialist agent owns a slice of KBQs and the corresponding sources:

| Agent | Owns KBQs | Primary sources | Tools |
|---|---|---|---|
| Clinical Trials | 4 | CT.gov, EU CTR, PubMed, Citeline | `cttrials.search`, `cttrials.diff`, `pubmed.lookup`, `pubmed.search`, `pubmed.related` |
| Regulatory Affairs | 9, 11 (regulatory part) | Drugs@FDA, EMA, CMS, DailyMed, FDA designations | `openfda.query`, `dailymed.diff`, `cms_coverage.search`, `cortellis_reg.search` |
| Financial | 1 | EDGAR XBRL, transcripts, 8-K Item 2.02 | `edgar.filings`, `edgar.xbrl`, `transcript.extract`, `guidance.diff` |
| Deal | 10 | 8-K Item 1.01, press releases, Cortellis Deals | `edgar.item_1_01`, `pr.search`, `cortellis_deals.search` |
| Exec Tracker | 2 | 8-K Item 5.02, IR leadership pages, DEF 14A | `edgar.item_5_02`, `ir.leadership_diff`, `linkedin.confirm` (read-only confirmation) |
| Product & Label | 5 | DailyMed, Orange Book, Purple Book, NDC | `dailymed.diff`, `orangebook.lookup`, `purplebook.lookup`, `loe.compute` |
| Patent & IP | (within KBQ 5/10) | PatentsView, PTAB, Orange Book, Lex Machina | `uspto.search`, `ptab.search`, `pacer.dockets` |
| Strategic Theme | 3, 6 | Transcripts, R&D days, press releases | `theme.classify`, `theme.aggregate`, `quote.extract` |
| Conference | 7 | Conference websites, IR decks, AdCom calendar | `conference.scrape`, `adcom.calendar`, `transcript.extract` |
| Pricing & Access | 8 | HTA agencies, IRA list, formulary PDFs | `hta.search`, `cms_ira.list`, `formulary.diff`, `medispan.lookup` |
| Synthesis | (cross-cutting) | All Signals | `signal.search`, `signal.cluster`, `brief.compose`, `digest.compose` |

### 7.2 Tool layer

Tools are deterministic functions over the data model. Agents call tools; they do not call sources directly. This keeps provenance, rate-limiting, and caching centralised.

Key tool categories:

- **Source-specific search/fetch tools** — one per connector. Return `Document` rows.
- **Extraction tools** — turn a `Document` into candidate `Fact`s.
- **Resolution tools** — entity resolver service.
- **Diff tools** — compare current snapshot to previous (CT.gov status, SPL label, leadership page, formulary).
- **Search tools over the entity/signal store** — `signal.search(filters)`, `entity.lookup(id)`.
- **Composition tools** — `brief.compose(signal_ids, format)`, `digest.compose(filters, period)`.

### 7.3 Memory & state

Three kinds of memory:

1. **Long-term: the entity/signal store.** This *is* memory.
2. **Per-analyst: preferences, watchlists, saved searches, prior briefs.** Used by the orchestrator to personalise.
3. **Per-task: scratchpad.** Plan, intermediate findings, retries. Discarded after task closure.

### 7.4 Guardrails

- **No fabrication:** the synthesis agent's prompt enforces "every claim must point to a Signal in the store; if no Signal supports it, say 'no signal found.'"
- **Tier-aware claims:** when emitting a claim that depends on `inferred` or `reported` confidence, the language is hedged ("press reports indicate…"). Hard claims are reserved for `confirmed` only.
- **Copyright:** synthesis paraphrases; verbatim quotes are limited to short attributable lines from official disclosures (CEO statement, press release headline).
- **Reviewer-in-the-loop:** any output ranked impact_tier=high is queued for human approval before external delivery.

---

## 8. CI user workflows

This section translates the architecture into the analyst's day. We define five workflows, each with the data and intelligence layer affordances they require.

### 8.1 Workflow A — Daily morning digest

**Persona:** CI analyst covering 20 priority companies.
**Goal:** know everything material that happened in the last 24 hours before 9 AM.

**Flow:**
1. Analyst opens the dashboard. The Synthesis agent has already pre-built a digest for them based on their watchlist (companies, products, KBQs of interest).
2. Digest is structured by KBQ section, then by company, then by signal.
3. Each signal shows: headline, impact tier, confidence tier, 1-paragraph summary, "why this matters" sentence, links to evidence documents.
4. Analyst skims; for any high-impact signal, they click through to the Signal detail page (see 8.2).
5. One-click "promote to client brief" or "dismiss as noise" or "tag for follow-up."

**Data/intelligence layer enables:**
- Watchlist-aware filtering (entity_id ∈ watchlist).
- Time-bounded filtering on `created_at`.
- Pre-computed impact / confidence scores.
- Pre-built narrative summaries.
- Reviewer queue for items shipped >medium impact.

### 8.2 Workflow B — Signal deep-dive

**Persona:** CI analyst, mid-morning.
**Goal:** understand a single signal in full — what happened, what's the supporting evidence, what's the historical context, what are the implications.

**Flow:**
1. Analyst clicks into a Signal.
2. Signal detail page shows:
   - Event metadata (type, date, primary entity)
   - All evidence documents, ordered by confidence tier
   - Side-by-side view: company press release vs SEC filing vs trade press
   - Historical context strip: prior related events for this entity (e.g. for a guidance change, the last 4 quarters of guidance; for a trial status change, the trial's full history)
   - Cross-entity strip: related signals for competitors (e.g. for an approval, competitor approvals in the same indication)
3. Analyst can ask the agent free-form: "what does this mean for [competitor product]?" → routed to Synthesis agent, which queries the store and answers with cited Signals.

**Data/intelligence layer enables:**
- The Event spine (8.1) with all evidence linked.
- Entity-keyed historical querying.
- Cross-entity querying via the indication / TA links.
- Conversational query routing.

### 8.3 Workflow C — Quarterly briefing on a company

**Persona:** Senior CI lead.
**Goal:** generate a 5-page briefing on a target company covering all 11 KBQs over the last 90 days.

**Flow:**
1. User enters: company + date range + KBQs to include.
2. Orchestrator dispatches to all relevant specialist agents in parallel.
3. Each agent returns its top-N signals for that company in scope.
4. Synthesis agent composes the brief with section per KBQ, evidence appendix, and a generated executive summary.
5. Reviewer queue: every brief is human-reviewed before shipping.
6. Output is a versioned artifact (PDF / DOCX / web page) with full citation map.

**Data/intelligence layer enables:**
- Multi-agent orchestration.
- Templated brief composition with provenance preserved end to end.
- Versioning + reviewer queue + audit trail.

### 8.4 Workflow D — Ad-hoc question ("what is X doing in Y?")

**Persona:** Any internal stakeholder, including non-CI users.
**Goal:** ask a natural-language question and get a sourced answer.

**Flow:**
1. User types: "What is Lilly's strategy in obesity outside the US?"
2. Orchestrator parses: entity=Lilly, theme=obesity, geography=ex-US.
3. Routes to Strategic Theme + Regulatory + Clinical agents.
4. Synthesis agent assembles an answer of ~500 words with citations.
5. If any sub-question hits a low-confidence area, the answer says so explicitly ("limited public disclosure on ex-US commercial plans; available signals are…").

**Data/intelligence layer enables:**
- Entity / theme / geo filters across the entire signal store.
- "Honest about gaps" — explicit handling of unknowns.
- Conversational routing with structured output.

### 8.5 Workflow E — Alerting (push, not pull)

**Persona:** CI analyst with multiple watchlists.
**Goal:** get pushed an alert the moment a high-impact event happens.

**Flow:**
1. Analyst configures alert rules: entity / KBQ / minimum impact_tier / channel (email, Slack, Teams).
2. As Signals are written into the store, the alerting service evaluates rules against new Signals.
3. Matching signals trigger alerts: short headline + 1-line summary + link to Signal detail.
4. For impact_tier=high, alert is gated by reviewer queue (1-tap approve in a Slack/Teams card).

**Data/intelligence layer enables:**
- Streaming signal store (events emitted on insert/update).
- Rule engine evaluating new Signals against subscriptions.
- Reviewer-gated channels for high-impact pushes.

---

## 9. Insight catalogue

The insight catalogue is the "menu" of outputs the system must generate. These are the deliverables; everything in the architecture exists to produce these. Each insight type maps cleanly back to one or more KBQs and uses defined data-model fields.

| # | Insight | KBQs | Data model fields used | Format |
|---|---|---|---|---|
| I1 | Daily Pharma Digest (per analyst, watchlist-filtered) | All | Signals (24h, priority entities) | Web + email |
| I2 | Company One-Pager (snapshot) | All | Company + last-30d Signals | Web + PDF |
| I3 | Quarterly Company Briefing | All | Signals (90d) by KBQ | DOCX / PDF |
| I4 | Trial Tracker (per indication or per company) | 4 | Trial entities + status_history + linked publications | Web table + alerts |
| I5 | Approval & PDUFA Tracker | 9 | Regulatory events (forward calendar) | Web calendar + alerts |
| I6 | LOE Heatmap | 5 | Patent + Product + ExclusivityFacts | Web grid |
| I7 | Deal Tracker (M&A + licensing) | 10 | Deal entities | Web table + alerts |
| I8 | Executive Movement Feed | 2 | Person + Role events | Web feed + alerts |
| I9 | Earnings Watch (guidance changes) | 1 | Financial / guidance_change events | Web + alerts |
| I10 | Strategic Theme Map | 3, 6 | Strategic_signal events clustered by theme | Visualisation |
| I11 | Conference Coverage Brief (event-driven) | 7 | Event_participation + linked Signals | DOCX / PDF |
| I12 | Pricing & Access Update (per priority product) | 8 | Pricing + formulary events | Web + alerts |
| I13 | Custom Q&A | All | Free-form over Signals | Conversational |
| I14 | Side-by-side Comparison (2–4 companies, 1 KBQ) | Any one | Signals filtered + structured | Web table |

---

## 10. Build phasing

### Phase 1 — MVP (~12 weeks, 2 backend + 1 NLP/ML + 1 product/PM)

**Connectors:**
- SEC EDGAR (8-K Items 1.01, 2.02, 5.02; 10-K, 10-Q via XBRL)
- Drugs@FDA (openFDA)
- ClinicalTrials.gov v2 + AACT
- PubMed E-utilities
- DailyMed SPL
- Orange Book + Purple Book
- FDA MedWatch RSS
- USPTO PatentsView
- 1 news connector (RSS aggregator: BioPharma Dive + FiercePharma + Endpoints + Reuters Health)

**KBQs covered at MVP quality:** 1 (company-level), 2, 4, 5, 9, 10.

**Data model:** entity layer + event spine + signal layer fully implemented.
**Intelligence layer:** extraction + resolution + linking + dedup + scoring (rule-based; LLM synthesis for narrative only).
**Agents:** Clinical, Regulatory, Financial, Deal, Exec, Product&Label, Synthesis. Orchestrator with simple routing.
**Workflows live:** A (digest), B (signal detail), E (alerting basic).
**Insights live:** I1, I2, I4, I5, I7, I8, I9.

### Phase 2 — Depth & coverage (~8 weeks)

**Connectors added:**
- Per-company IR scrapers (top 20 priority cos)
- Conference websites (ASCO, ESMO, AACR, ASH, AHA, ACC, EHA, EULAR, AAOS, World Vaccine Congress, AAN)
- AdCom calendar
- HTA agencies (NICE, IQWiG, HAS)
- CMS IRA implementation page
- Payer formulary PDFs (top 5 commercial payers)
- EU CTR
- USPTO PTAB
- WIPO / Espacenet
- PR Newswire / Business Wire / GlobeNewswire

**KBQs added at quality:** 3, 6, 7 (partial), 8 (partial), 11.
**Intelligence layer:** strategic theme classifier; product-level revenue extraction; LLM-based deal-term extraction.
**Workflows live:** C (quarterly briefing), D (ad-hoc Q&A), E full.
**Insights live:** I3, I6, I10, I11, I12, I13, I14.

### Phase 3 — Tier 3 integration & scale

**Connectors added:**
- Cortellis (Regulatory + Deals + Pipeline) — already partly available via the Cortellis Regulatory MCP
- Citeline / GlobalData
- AlphaSense (transcripts + analyst notes)
- Bloomberg / Refinitiv
- Evaluate Pharma / IPD Analytics
- Medi-Span / RED BOOK / Gold Standard
- Lex Machina / Docket Alarm
- CB Insights
- 50-state Medicaid + state PDLs

**Capability added:** product-level revenue with sales projections; deep transcript NLP; pre-curated competitive landscapes; full pricing tracking.

---

## 11. Non-functional requirements

- **Latency:** ingestion → Signal availability ≤15 min for real-time sources (RSS, 8-K), ≤24h for daily/weekly sources.
- **Throughput:** target 50k documents/day at steady state across all connectors.
- **Provenance:** every Signal MUST cite ≥1 Document; every assertion in a brief MUST cite ≥1 Signal.
- **Observability:** per-connector freshness dashboard (last successful pull, error rate, doc count); per-agent latency + token-usage metrics; Signal review queue depth.
- **Audit:** every state change on a Signal (created, scored, reviewed, shipped, superseded) is event-logged with user/agent, timestamp, before/after.
- **Security:** licensed-source content (Tier 3) is access-controlled and never redistributed in raw form. Output flagging if a brief includes Tier 3-derived content.
- **Cost controls:** LLM calls metered per agent; budget caps per workflow; cheap models for triage, premium models only for synthesis.

---

## 12. Open questions for the team

These need answers before development can proceed cleanly. Each has a stated default if no decision is made.

| # | Question | Default |
|---|---|---|
| Q1 | Final priority company list (the sheet refers to "20 clients") | Top 20 by FY revenue, plus any explicitly named |
| Q2 | Priority TAs (the KBQs are TA-agnostic; some signals only matter in scope) | Onc, Immuno, CV/Met, Neuro — confirm with stakeholders |
| Q3 | Tier 3 licensing budget — Cortellis, AlphaSense, Bloomberg are on the inventory; which will be procured for Phase 3? | Procure Cortellis (Regulatory + Deals + Pipeline) and AlphaSense first |
| Q4 | Reviewer SLA — how fast must high-impact signals clear the review queue? | 2 business hours for impact=high |
| Q5 | Output formats — DOCX-first, PDF-first, web-first? | Web-first for digest/alerts; DOCX for briefs (the Notes sheet refers to a "newsletter" pattern) |
| Q6 | Where does the entity store live? Postgres + a graph layer, or a property graph DB outright? | Postgres for entities + Signals; lightweight graph view via materialised edges. Re-evaluate at Phase 2 |
| Q7 | LLM provider strategy and model tiering | Claude Opus for synthesis and brief composition; Haiku/Sonnet for extraction and triage |
| Q8 | Newsletter cadence(s) — daily, weekly, on-event? | Daily digest + on-event alerts; weekly TA-specific roll-ups in Phase 2 |
| Q9 | Conflict-resolution UX — when sources disagree, what does the analyst see? | Side-by-side evidence view with explicit "conflict" badge; never auto-resolve |
| Q10 | Data retention | Raw documents 24 months; entity/signal layer indefinitely; LLM scratchpad 30 days |

---

## 13. Glossary

- **KBQ** — Key Business Question. The 11 questions in the Data Mapping sheet.
- **Signal** — atomic, scored, deduplicated unit of intelligence. The system's output unit.
- **Event** — canonical anchor for things that happened in the world. Multiple Documents → 1 Event → ≥1 Signal.
- **Confidence tier** — confirmed / reported / inferred. Determined by source class.
- **Impact tier** — high / medium / low. Determined by event type, entity priority, and magnitude.
- **Tier 1/2/3** — source classification per the Appendix sheet (free govt / scraped trade / licensed vendor).
- **LOE** — Loss of Exclusivity.
- **PDUFA** — Prescription Drug User Fee Act date — the FDA action target date.
- **CRL** — Complete Response Letter (FDA non-approval).
- **CHMP** — EMA's Committee for Medicinal Products for Human Use.
- **WAC / AWP / ASP** — wholesale acquisition cost / average wholesale price / average sales price.
- **NCT / EudraCT** — trial registry IDs (US / EU).
- **NCD / LCD** — National / Local Coverage Determinations (CMS).
- **PTE** — Patent Term Extension.

---

*End of design document. This document is a starting input for engineering; data-model details (PK/FK constraints, indexes, partitioning strategy) and concrete API contracts per connector are scoped to follow-on technical specs per Phase 1 sprint.*