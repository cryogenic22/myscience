MarketZero · Helix
Data Strategy & Semantic Layer Specification
Document type: Pre-build architecture specification
Audience: Data architects, ML engineering, backend engineering, product
Anchored against: Lilly 10-K 2025, Lilly Q1 2026 PR, Novo 2025 FY, Novo Q1 2026, ZS KBQ Framework
Version: 0.1

0. TL;DR
The platform's defensibility is not in the frontend or the agents — it is in the semantic layer that turns heterogeneous source data into a coherent, queryable, evidence-linked model of the pharmaceutical competitive landscape.
This document specifies three things:

The canonical entity model — what objects exist in the world the platform reasons about
The hybrid storage architecture — graph for relationships, facts table for time-stamped claims, vector index for semantic similarity
The extraction and synthesis pipeline — how source documents become semantic-layer state

Every surface in the MarketZero · Helix frontend is, ultimately, a query against this layer. If this layer is wrong, the platform is broken in ways no UI work can fix. If it is right, the platform becomes straightforward to build.

1. Three layers — clear separation of concerns
┌────────────────────────────────────────────────────────────────┐
│ LAYER 3 — INTELLIGENCE                                          │
│ Twin · Synthesizer · KBQ workers · Strategist · Coach          │
│ Materiality scoring · Moment generation · Game theory          │
│                                                                 │
│ Never touches raw data. Only queries the semantic layer.       │
└──────────────────────────────┬─────────────────────────────────┘
                               │ structured queries
┌──────────────────────────────▼─────────────────────────────────┐
│ LAYER 2 — SEMANTIC                                              │
│ Canonical entities (Products, Companies, Indications, Trials…)  │
│ Typed facts with provenance & validity periods                  │
│ Knowledge graph (nodes + edges)                                 │
│ Vector embeddings for semantic search                           │
│                                                                 │
│ Single source of truth. Versioned. Evidence-linked.            │
└──────────────────────────────┬─────────────────────────────────┘
                               │ extraction pipelines
┌──────────────────────────────▼─────────────────────────────────┐
│ LAYER 1 — DATA PLANE                                            │
│ Raw documents (S3) · Connector outputs · Internal uploads      │
│ Public: ClinicalTrials.gov, PubMed, FDA, EMA, CMS, SEC EDGAR   │
│ Paid: Citeline, Evaluate Pharma, AlphaSense, MMIT (stubbed v1) │
│ Internal: Knowledge Library uploads                            │
└────────────────────────────────────────────────────────────────┘
Inviolable boundary: Layer 3 never reads Layer 1. Agents, the twin, KBQ workers — none of them open a raw PDF, none of them call a connector directly. Everything goes through the semantic layer. This is non-negotiable. It is what makes the platform auditable, what makes provenance work, and what allows us to swap a data source without rewriting agents.

2. The canonical entity model
The vocabulary the entire platform speaks. Every entity type below is a first-class object with a canonical ID, a stable schema, and an identity resolution rule.
2.1 Core entity types
EntityPurposeCanonical ID formatExampleCompanyPharma sponsor, payer, regulator, KOL employerco:{slug}co:novo_nordisk, co:eli_lillyProductA drug, device, or therapy with regulatory identityprod:{slug}prod:wegovy, prod:zepboundActiveIngredientThe molecular entity (INN/USAN)mol:{slug}mol:semaglutide, mol:tirzepatideFormulationSpecific form of a productform:{prod}:{slug}form:wegovy:injectable_2_4mg, form:wegovy:oral_25mgIndicationDisease/condition for treatmentind:{slug}ind:obesity, ind:t2d, ind:hfpef, ind:mashTrialA clinical trialtrial:NCT{8}trial:NCT04788511PublicationPeer-reviewed article or preprintpub:PMID{n} or pub:DOI:{doi}pub:PMID38291842RegulatoryEventApproval, label change, NCD, advisoryreg:{authority}:{id}reg:fda:nda:215256:approval_2021_06PayerPolicyFormulary listing, coverage decisionpol:{payer}:{prod}:{year}pol:esi:wegovy:2026PriceObservationA price at a point in time, with typeprice:{prod}:{type}:{date}price:wegovy:wac:2027_01_01EndpointTrial endpoint with definitionep:{slug}ep:mace_3pt, ep:percent_weight_lossTrialResultReported outcome on an endpoint in a trialtr:{trial}:{endpoint}:{arm}tr:NCT05822830:mace:tirz_armKOLKey opinion leaderkol:{slug}kol:louis_aronneConferenceScientific or business conferenceconf:{slug}:{year}conf:aace:2026PatentIP claim with expirypat:{authority}:{number}pat:uspto:11123456DocumentSource document (10-K, PR, label, paper)doc:{hash}doc:a8f3c2...FactA typed claim with provenancefact:{hash}fact:b91d4e...TenantCustomer organizationtenant:{slug}tenant:novo_us_ci_teamWatchlistUser-defined saved filterwl:{tenant}:{slug}wl:novo_us_ci_team:lilly_pipelineDecisionFrameUser-initiated decision shelldf:{tenant}:{id}df:novo_us_ci_team:00427MomentSystem-surfaced decisionmom:{tenant}:{id}mom:novo_us_ci_team:00891CommitCommitted decision (ledger entry)cmt:{tenant}:{id}cmt:novo_us_ci_team:00038
2.2 Identity resolution rules
The hardest problem in the semantic layer is deciding when two surface mentions refer to the same canonical entity. Rules per entity type:
Company. Match on: (a) ticker symbol if present, (b) SEC CIK if available, (c) normalized legal name with corporate suffix removal ("Eli Lilly and Company" → "eli lilly"), (d) known alias dictionary. Maintain a Company.aliases[] array updated by ingestion. Disambiguate parent/subsidiary explicitly with parent_of edges.
Product. Match on: (a) FDA application number (NDA/BLA) if known, (b) brand name normalized, (c) generic name plus formulation plus strength. Critical: "Wegovy injectable 2.4mg" and "Wegovy pill 25mg" are different Formulations of the same Product family. Resolved as Product = wegovy, with Formulation = injectable_2_4mg | injectable_7_2mg | oral_25mg. This matters because pricing and access policies often differ by formulation.
ActiveIngredient. Match on INN/USAN. Maintain mapping to all brand Products containing this molecule. Semaglutide → Wegovy + Ozempic + Rybelsus + (different formulations).
Indication. Match against a curated ontology (MeSH for disease, ICD-10 for billing, with internal merge rules). "Obesity," "chronic weight management," "overweight with weight-related medical problems" all canonicalize to ind:obesity with sub-types for population specifics.
Trial. NCT ID is canonical; cross-references to EudraCT, JRCT, CTRI maintained as aliases.
Publication. PMID canonical for PubMed; DOI canonical otherwise; cross-reference both.
Document. Content hash (SHA-256 of canonicalized text). Identical documents collapse.
2.3 Relationship edges in the knowledge graph
The graph topology. Every edge is typed and most carry properties.
Company ─── develops ─→ Product
Company ─── manufactures ─→ Product
Company ─── parent_of ─→ Company
Product ─── contains ─→ ActiveIngredient
Product ─── has_formulation ─→ Formulation
Product ─── approved_for ─→ Indication    [props: status, geography, date, authority, lot, mono_combo]
Product ─── pipeline_for ─→ Indication    [props: phase, geography, expected_date, trial_ref]
Product ─── competes_with ─→ Product      [props: in_indication, mechanism_basis, intensity_score]
Product ─── prior_art_for ─→ Patent
Product ─── data_protection ─→ {jurisdiction, expiry}
ActiveIngredient ─── mechanism ─→ MechanismOfAction
Trial ─── sponsored_by ─→ Company
Trial ─── studies ─→ Product
Trial ─── for_indication ─→ Indication
Trial ─── primary_endpoint ─→ Endpoint
Trial ─── result ─→ TrialResult           [props: arm, value, ci, p_value, n]
Publication ─── reports ─→ Trial
Publication ─── authored_by ─→ KOL
Publication ─── published_in ─→ Journal
KOL ─── presented_at ─→ Conference
RegulatoryEvent ─── concerns ─→ Product
RegulatoryEvent ─── authority ─→ Company   (FDA, EMA, CMS, NICE, etc. as Company)
PayerPolicy ─── covers ─→ Product          [props: tier, pa, st, ql, percent_lives]
PriceObservation ─── of ─→ Product
PriceObservation ─── of_formulation ─→ Formulation
Fact ─── extracted_from ─→ Document        [props: page, paragraph, char_span]
Fact ─── asserts_about ─→ {any Entity}
Fact ─── supersedes ─→ Fact                (when newer data overrides)
2.4 Temporal model
Every fact has validity. Three possible patterns:
Point-in-time facts. "Wegovy approved June 2021." valid_from: 2021-06-04, valid_to: null (still valid).
Interval facts. "Wegovy WAC was $1,349 from 2024-01 to 2026-12." valid_from: 2024-01-01, valid_to: 2026-12-31.
Anticipatory facts. "Wegovy WAC will be $675 effective 2027-01-01." Stored with valid_from: 2027-01-01, asserted_at: 2026-Q1, source: nvo_q1_2026_pr. Critical for war gaming.
Facts can be superseded but never deleted. The fact ledger is append-only. When Lilly's Q2 2026 report changes a guidance number from Q1, the Q1 fact remains in the store with superseded_by: <new fact id>. This preserves audit trail and enables replay.

3. Storage architecture — the hybrid model
Three stores, one logical semantic layer.
3.1 Property graph (Neo4j)
Holds: entity nodes, relationship edges, ontology hierarchy.
What goes here: anything where the structure of relationships matters. Product → Indication mappings, Company hierarchies, Trial → Endpoint → Result chains, competitive landscape edges, mechanism classifications.
What does not go here: time-series facts, raw text, large unstructured content.
Query language: Cypher. Most KBQ queries are graph traversals: "all Products with Approved or P3 status for ind:obesity, group by Company, return MOA class" → ~12 line Cypher.
Properties on nodes: minimal — canonical ID, type, name, aliases array, created/updated timestamps. Heavy data lives in the facts table.
3.2 Relational facts table (Postgres)
Holds: typed, time-stamped, evidence-linked facts.
Schema:
sqlCREATE TABLE facts (
  id              UUID PRIMARY KEY,
  subject_id      TEXT NOT NULL,       -- canonical entity ID
  predicate       TEXT NOT NULL,       -- typed relation (e.g., "revenue", "wac_price")
  object_value    JSONB,                -- typed payload
  object_entity   TEXT,                 -- if object is itself an entity
  period_type     TEXT,                 -- point | interval | anticipatory
  valid_from      TIMESTAMPTZ,
  valid_to        TIMESTAMPTZ,
  asserted_at     TIMESTAMPTZ NOT NULL, -- when this fact was extracted
  source_doc_id   TEXT NOT NULL,        -- doc:{hash}
  source_locator  JSONB,                -- {page, paragraph, char_span}
  extractor       TEXT NOT NULL,        -- parser name or LLM prompt hash
  confidence      NUMERIC(3,2),         -- 0.00 to 1.00
  superseded_by   UUID,                 -- if this fact has been superseded
  tenant_scope    TEXT,                 -- null = global, otherwise tenant ID
  created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_facts_subject ON facts (subject_id, predicate, valid_from DESC);
CREATE INDEX idx_facts_predicate ON facts (predicate, valid_from DESC);
CREATE INDEX idx_facts_source ON facts (source_doc_id);
CREATE INDEX idx_facts_period ON facts USING GIST (tstzrange(valid_from, valid_to));
Why relational not graph for facts: facts are inherently tabular, time-indexed, and queried analytically (give me the latest WAC for prod:wegovy as of date X). Graph databases do this badly. Postgres with proper indexes does it well.
Row-level security: every row has tenant_scope. Most facts are global; some (internal MSL insights) are tenant-private.
3.3 Vector index (Qdrant)
Holds: embeddings for semantic search across documents and extracted facts.
Three collections:

doc_chunks — text chunks from source documents, embedded for retrieval-augmented agent queries
fact_summaries — short natural-language summaries of facts, for similarity search ("find facts similar to: 'Lilly accelerated oral GLP-1 filing'")
entity_descriptions — embedded entity summaries for fuzzy matching during entity resolution

Vector store enables:

Coach agent learning ("what did we say about similar moments in the past?")
Sentinel deduplication ("is this signal substantively new vs. yesterday's?")
KBQ supplementation ("find narrative context for this fact")

Never used as the source of truth. Always supplementary to the graph + facts table.
3.4 Event log (Redpanda or Kafka)
Holds: every change to the semantic layer as an immutable event stream.
Events:

FactAsserted — new fact added
FactSuperseded — older fact marked superseded
EntityResolved — alias mapped to canonical
RelationshipUpserted — new or updated graph edge
TwinBeliefUpdated — posterior shifted
MomentGenerated — new moment created
DecisionCommitted — ledger entry created

Consumers: Twin agent (Bayesian update), Synthesizer (cross-stream correlation), Audit log, Replay subsystem.
Event log enables the Replay surface — scrub to any point in time and reconstruct semantic state.

4. Source-to-semantic mapping
The contract between Layer 1 (data plane) and Layer 2 (semantic). For each source: what entities and facts it produces, and how.
4.1 Source registry — extraction approach
SourceTierUpdateExtractionEntities producedKey fact predicatesClinicalTrials.govPublicDailyParser (REST API)Trial, Product (asset), Indication, Endpoint, Company (sponsor)trial_phase, trial_status, trial_sponsor, trial_indication, trial_endpoint, trial_enrollment, trial_completion_dateEU CTR / CTISPublicDailyParser (HTML)Trial (with EudraCT ID), Companytrial_phase, trial_status (EU), trial_sponsorPubMed E-utilitiesPublicDailyParser (XML) + LLMPublication, KOL (author), Trial (referenced)pub_year, pub_journal, pub_authors, pub_topic, pub_summaryFDA DailyMedPublicWeeklyParser (XML SPL) + LLM for indication wordingProduct, Indication, Formulation, RegulatoryEventapproved_indication, label_section, label_warning, dosingDrugs@FDAPublicWeeklyParser (REST)Product, RegulatoryEvent, ActiveIngredientnda_number, approval_date, application_typeFDA Orange BookPublicMonthlyParser (CSV)Product, Patentexclusivity_expiry, patent_listingFDA Purple BookPublicMonthlyParser (CSV)Product (biologic), Companybla_number, biosimilar_statusEMA EPAR/SmPCPublicWeeklyParser (HTML) + LLMProduct, Indication, RegulatoryEvent (EU)eu_approved_indication, eu_authorisation_dateCMS ASP filesPublicQuarterlyParser (CSV)Product, PriceObservationasp_price, hcpcs_code, billing_unitNADACPublicWeeklyParser (CSV)Product, PriceObservationnadac_price, ndcMedicare Part D FormularyPublicQuarterlyParser (CSV)Product, PayerPolicytier, pa_required, st_required, qlSEC EDGAR (10-K, 10-Q, 8-K)PublicFiling-drivenParser (tables) + LLM (narrative)Company, Product, Trial, PriceObservation, RegulatoryEventrevenue, ebitda, guidance, pipeline_commentary, patent_expiryCompany press releasesPublicHourly pollLLM extractionVariousevent_announcement, financial_update, regulatory_updateEarnings transcriptsPublicQuarterlyLLM extractionCompany, Product, MarketObservationguidance, qualitative_commentary, analyst_questionNICE / IQWiG / HASPublicWeeklyParser (HTML) + LLMProduct, PayerPolicy, RegulatoryEventhta_decision, hta_rationale, ex_us_pricingConference abstractsMixedConference cycleLLM extractionPublication, Trial, KOLconference_data, late_breaking, subgroup_analysisCiteline / TrialtrovePaid (v2)DailyAPI + parserTrial, Product (pipeline)curated_phase, analyst_view, transition_eventEvaluate PharmaPaid (v2)DailyAPIProduct, MarketObservationconsensus_forecast, peak_sales_estimateAlphaSensePaid (v2)DailyAPI + LLMVariousanalyst_sentiment, transcript_excerptMMIT / FingertipPaid (v2)WeeklyAPIProduct, PayerPolicydetailed_coverage, payer_specificNavelinPaid (v2)WeeklyAPIProduct, PriceObservationnet_price_estimate, contracted_priceInternal: Knowledge Library uploadsInternalOn uploadLLM extraction with tenant-scoped schemaVarious + InternalInsightmsl_observation, payer_rejection, sales_intel
4.2 Extraction approach decision tree
For any incoming document, decide approach by structure:
Is the source a structured API (JSON/XML/CSV)?
├─ YES → Direct parser. Output: Facts with confidence 1.0. No LLM.
└─ NO → Is the structure consistent (e.g., FDA SPL XML)?
   ├─ YES → Parser-first. Use LLM only for narrative segments (indication wording).
   └─ NO → Is it narrative prose (10-K, PR, transcript)?
      ├─ YES → LLM extraction with strict JSON schema and post-validation.
      └─ NO → Is it a mixed table-and-prose document (10-K with embedded tables)?
         └─ Hybrid: extract tables with parsers, extract narrative claims with LLM, link both to the same Document.
4.3 Worked example — Lilly Q1 2026 press release
This is a real document in your repo. Tracing it end-to-end.
Input: PDF press release dated April 30, 2026.
Step 1 — Document ingestion.

Compute hash → doc:a8f3c2e9d4b1... (canonical Document ID)
Store raw PDF in S3 under tenant_global/sources/
Store extracted text in Postgres documents table
Emit DocumentIngested event

Step 2 — Extraction (hybrid).
The document has both structured and narrative content. Two extractors run in parallel:
Table extractor (parser-first): Identifies the bullet-point financial summary. Output facts (confidence 1.0):
yaml- subject: co:eli_lilly
  predicate: revenue
  object_value: { amount: 19_800_000_000, currency: USD }
  period_type: interval
  valid_from: 2026-01-01
  valid_to: 2026-03-31
  asserted_at: 2026-04-30
  source_doc_id: doc:a8f3c2e9d4b1...
  source_locator: { page: 1, paragraph: 1, bullet: 0 }
  extractor: lly_pr_table_parser_v1
  confidence: 1.00

- subject: co:eli_lilly
  predicate: revenue_growth_yoy
  object_value: { pct: 0.56 }
  period_type: interval
  valid_from: 2026-01-01
  valid_to: 2026-03-31
  ...

- subject: co:eli_lilly
  predicate: eps_diluted
  object_value: { gaap: 8.26, non_gaap: 8.55 }
  ...

- subject: co:eli_lilly
  predicate: guidance_revenue_fy
  object_value: { fy: 2026, low: 82_000_000_000, high: 85_000_000_000, currency: USD }
  period_type: anticipatory
  valid_from: 2026-04-30
  ...
Narrative extractor (LLM with schema): Processes the prose bullets and CEO quote. System prompt instructs: "Extract events of regulatory, pipeline, and BD&L significance. Use the provided schema. Cite paragraph numbers."
Output facts (confidence 0.85-0.95 based on language directness):
yaml- subject: prod:foundayo
  predicate: regulatory_approval
  object_value: { authority: fda, indication: ind:obesity, population: "adults with overweight + weight-related comorbidity", date: 2026-Q1 }
  asserted_at: 2026-04-30
  source_doc_id: doc:a8f3c2e9d4b1...
  source_locator: { page: 1, paragraph: 4 }
  extractor: lly_pr_narrative_llm_v3
  confidence: 0.95

- subject: prod:foundayo
  predicate: phase3_readout
  object_value: { trial: trial:t2d_obesity_cv_risk, outcome: positive, indication: ind:t2d }
  asserted_at: 2026-04-30
  confidence: 0.90

- subject: co:eli_lilly
  predicate: acquisition_announcement
  object_value: { target: co:orna_therapeutics, status: agreement }
  asserted_at: 2026-04-30
  confidence: 0.95

- subject: co:eli_lilly  
  predicate: acquisition_announcement
  object_value: { target: co:centessa_pharmaceuticals, status: agreement }
  ...

- subject: co:eli_lilly
  predicate: investor_event
  object_value: { type: investment_community_meeting, date: 2026-12-07 }
  ...
Step 3 — Entity resolution.
For each entity referenced, resolve to canonical or create new:

"Eli Lilly and Company" + ticker LLY → co:eli_lilly (existing)
"Foundayo (orforglipron)" → new Product entity? No — prod:orforglipron already exists as Pipeline; promote to prod:foundayo brand with Product.brand_name = "Foundayo", Product.generic_name = "orforglipron", Product.contains = mol:orforglipron. Create alias mapping Foundayo → prod:foundayo.
"Orna Therapeutics" → new co:orna_therapeutics
"Centessa Pharmaceuticals" → new co:centessa_pharmaceuticals

Step 4 — Graph updates.
cypher// Promote orforglipron from pipeline to approved
MATCH (p:Product {id: 'prod:foundayo'})
MATCH (i:Indication {id: 'ind:obesity'})
MERGE (p)-[r:approved_for]->(i)
SET r.status = 'Approved',
    r.geography = 'US',
    r.date = '2026-Q1',
    r.authority = 'FDA',
    r.population = 'adults with overweight + weight-related comorbidity',
    r.evidence_fact_id = 'fact:...'

// Add acquisitions
MERGE (parent:Company {id: 'co:eli_lilly'})
MERGE (target:Company {id: 'co:orna_therapeutics'})
MERGE (parent)-[r:acquiring]->(target)
SET r.announced_date = '2026-04-30',
    r.status = 'agreement',
    r.evidence_fact_id = 'fact:...'
Step 5 — Vector embedding.
For each fact and each document chunk: generate embedding, store in Qdrant.
Critical: the embedding model is versioned. Re-embedding the corpus when model changes is a backfill job, not an inline operation.
Step 6 — Event emission.
For each new fact: emit FactAsserted event.
For each graph mutation: emit RelationshipUpserted.
For superseded prior facts (e.g., if previous fact said "orforglipron is Phase 3 pending FDA decision"): emit FactSuperseded with the new fact ID as supersedor.
The Twin agent subscribes to these events. When FactSuperseded arrives for predicate "approval_status" of prod:foundayo, the Twin updates P(orforglipron approved by Q2 2026) from a beta(α=4, β=2) prior to a point mass at 1.0. Posterior shift triggers Moment evaluation by the Synthesizer.
4.4 The same trace for Novo Q1 2026
Demonstrating the same approach on a different shape of document — Novo's Q1 release is more table-heavy than Lilly's.
Key facts extracted:
yaml- subject: co:novo_nordisk
  predicate: revenue
  object_value: { amount: 96_823_000_000, currency: DKK }
  period_type: interval
  valid_from: 2026-01-01
  valid_to: 2026-03-31
  asserted_at: 2026-05-06
  confidence: 1.00

- subject: prod:wegovy
  predicate: prescription_volume
  object_value: { weekly_trx: 475_000, geography: US, week_ending: 2026-04-17 }
  asserted_at: 2026-05-06
  confidence: 1.00

- subject: form:wegovy:oral_25mg
  predicate: launch_event
  object_value: { date: 2026-01-05, geography: US }
  asserted_at: 2026-05-06
  confidence: 1.00

- subject: form:wegovy:oral_25mg
  predicate: prescription_volume
  object_value: { cumulative_trx: 2_000_000, since: 2026-01-05, weekly_trx: 200_000, as_of: 2026-04-17 }
  ...

- subject: form:wegovy:injectable_7_2mg
  predicate: regulatory_approval
  object_value: { authority: fda, indication: ind:obesity, date: 2026-03 }
  asserted_at: 2026-05-06
  confidence: 1.00

- subject: form:wegovy:injectable_7_2mg
  predicate: trial_result
  object_value: { trial: trial:step_up, endpoint: ep:percent_weight_loss, value: 0.207, n: ... }

# Critical anticipatory fact
- subject: prod:wegovy
  predicate: wac_price_change
  object_value: { new_wac: 675, currency: USD, applies_to: [form:wegovy:injectable_2_4mg, form:wegovy:injectable_7_2mg, form:wegovy:oral_25mg], reduction_pct: 0.50 }
  period_type: anticipatory
  valid_from: 2027-01-01
  asserted_at: 2026-05-06
  source_doc_id: doc:novo_q1_2026
  confidence: 0.98  # Announced but not yet effective

- subject: prod:ozempic
  predicate: wac_price_change
  object_value: { new_wac: 675, currency: USD, reduction_pct: 0.35 }
  period_type: anticipatory
  valid_from: 2027-01-01
  asserted_at: 2026-05-06
  confidence: 0.98

# Distribution channel facts
- subject: prod:wegovy
  predicate: distribution_partnership
  object_value: { partner: co:ro, channel: telehealth_subscription }
  asserted_at: 2026-05-06
  
- subject: prod:wegovy
  predicate: distribution_partnership
  object_value: { partner: co:weightwatchers, channel: telehealth_subscription }
  ...
The WAC price change fact is highly significant. Anticipatory facts like this are exactly what should trigger Moment generation — a $675 list price across all formulations effective January 2027 has dominant implications for competitor pricing, payer dynamics, and Lilly's Foundayo launch strategy.

5. KBQ-to-semantic queries
Proof that the semantic layer is sufficient to power the KBQs. For each of the eight KBQs, specifying the actual queries.
5.1 KBQ-1 — Identify Indications
Question: What indications (in-market + pipeline) does Product X have?
Query:
cypherMATCH (p:Product {id: $productId})
OPTIONAL MATCH (p)-[a:approved_for]->(i_appr:Indication)
OPTIONAL MATCH (p)-[r:pipeline_for]->(i_pipe:Indication)
RETURN 
  p.brand_name AS product,
  collect(DISTINCT {
    indication: i_appr.name,
    status: 'Approved',
    geography: a.geography,
    date: a.date,
    authority: a.authority,
    lot: a.lot,
    evidence: a.evidence_fact_id
  }) AS approved_indications,
  collect(DISTINCT {
    indication: i_pipe.name,
    status: 'Pipeline',
    phase: r.phase,
    geography: r.geography,
    expected: r.expected_date,
    trial: r.trial_ref,
    evidence: r.evidence_fact_id
  }) AS pipeline_indications
Provenance: Every row carries an evidence_fact_id. The KBQ output for Wegovy would include rows linking back to facts extracted from the Novo Q1 PR (e.g., HFpEF Phase 3 status from STEP-HFpEF) and from FDA DailyMed (approved indications).
Decision gate: Comprehensiveness check is a query against indication ontology coverage:
sql-- Are there indications that match this product's mechanism class but aren't connected?
SELECT i.id, i.name
FROM indications i
WHERE i.mechanism_class = (SELECT mechanism_class FROM products WHERE id = $productId)
  AND i.id NOT IN (
    SELECT object_entity FROM facts
    WHERE subject_id = $productId AND predicate IN ('approved_for', 'pipeline_for')
  );
Above zero → analyst review prompt.
5.2 KBQ-2 — Identify Competitors
Question: Who competes with Product X in its indications?
Query:
cypherMATCH (p:Product {id: $productId})-[r1:approved_for|pipeline_for]->(i:Indication)
MATCH (other:Product)-[r2:approved_for|pipeline_for]->(i)
WHERE other.id <> p.id
OPTIONAL MATCH (other)-[:contains]->(mol:ActiveIngredient)-[:mechanism]->(moa:MechanismOfAction)
OPTIONAL MATCH (other)<-[:develops]-(co:Company)
RETURN 
  i.name AS indication,
  collect({
    product: other.brand_name,
    company: co.name,
    moa: moa.name,
    moa_class: moa.class,
    status: r2.status,
    phase: r2.phase,
    geography: r2.geography,
    competitive_basis: CASE 
      WHEN moa.class = p.moa_class THEN 'same_mechanism'
      ELSE 'cross_mechanism'
    END
  }) AS competitors,
  count(DISTINCT other) AS intensity_score
Output: Per-indication competitive landscape with MOA classification. For Wegovy in obesity, this returns Zepbound (tirzepatide, same MOA class GLP-1 incretin), Foundayo (orforglipron, same MOA class but oral), MariTide (different MOA: GLP-1 / GIPR antagonist combination), pipeline danuglipron (Pfizer).
5.3 KBQ-3 — Clinical Results Comparison
Query: Find pivotal trials for product and competitors, return endpoint comparison.
cypherMATCH (p:Product)-[:approved_for|pipeline_for]->(i:Indication {id: $indicationId})
WHERE p.id IN $productList
MATCH (t:Trial)-[:studies]->(p)
WHERE t.phase IN ['3', 'Pivotal']
MATCH (t)-[r:result]->(tr:TrialResult)-[:on_endpoint]->(e:Endpoint)
RETURN 
  p.brand_name AS product,
  t.nct_id AS trial,
  e.name AS endpoint,
  tr.value AS value,
  tr.confidence_interval AS ci,
  tr.p_value AS p_value,
  tr.population_n AS n,
  t.comparator AS comparator
ORDER BY p.brand_name, e.name;
For obesity, this returns a comparison matrix:

Wegovy injectable 2.4mg (STEP 1 results)
Wegovy injectable 7.2mg (STEP UP — 20.7% weight loss)
Wegovy oral 25mg (OASIS results)
Zepbound (SURMOUNT-1 results)
Foundayo (Foundayo-1 obesity results)
MariTide (MARITIME results when reported)

Cross-trial caveats added programmatically: different N, different populations, different comparator arms → automated limitation flag.
5.4 KBQ-4 — Market Positioning
Requires sources beyond what's in the current repo, but the query shape:
cypherMATCH (p:Product {id: $productId})
OPTIONAL MATCH (p)-[:has_messaging]->(m:Messaging)
OPTIONAL MATCH (p)-[:targets_segment]->(s:Segment)
OPTIONAL MATCH (p)-[:dtc_spend]->(d:DTCObservation)
RETURN 
  p.brand_name,
  collect(DISTINCT m.theme) AS messaging_themes,
  collect(DISTINCT s.descriptor) AS target_segments,
  sum(d.spend) AS dtc_spend_lly
For full implementation, this requires Kantar / iSpot.tv ingestion (paid v2).
5.5 KBQ-5 — Sales Performance & Sentiment
Query:
sqlWITH revenue_facts AS (
  SELECT 
    subject_id AS company,
    (object_value->>'amount')::NUMERIC AS revenue,
    object_value->>'currency' AS currency,
    valid_from AS period_start,
    valid_to AS period_end,
    source_doc_id
  FROM facts
  WHERE predicate = 'revenue'
    AND subject_id IN ('co:novo_nordisk', 'co:eli_lilly', 'co:amgen', 'co:pfizer')
    AND valid_from >= '2024-01-01'
    AND superseded_by IS NULL
)
SELECT 
  company,
  period_start,
  period_end,
  revenue,
  currency,
  LAG(revenue) OVER (PARTITION BY company ORDER BY period_start) AS prior_revenue,
  (revenue / LAG(revenue) OVER (PARTITION BY company ORDER BY period_start) - 1) AS growth_qoq
FROM revenue_facts
ORDER BY company, period_start;
For product-level sales (Wegovy, Zepbound, etc.), the query is at predicate product_revenue. Both Novo and Lilly disclose Wegovy and Zepbound product revenue in their filings; the extraction pipeline captures both.
Analyst sentiment: separate predicate analyst_rating extracted from AlphaSense feeds (paid, stubbed v1) or from public sell-side notes.
5.6 KBQ-6 — SWOT Analysis
SWOT is a synthesis over KBQs 1-5, not a direct query. The KBQ-6 worker:

Calls KBQ-1 through KBQ-5 queries for the product
Passes the structured output to an LLM with prompt: "Generate SWOT items. Each item MUST cite the KBQ output that supports it."
Validates that every output item has a cites: [kbq_id] field
Stores SWOT items as facts with predicate swot_item

Example output for Wegovy:
yaml- swot: strength
  claim: "Only oral peptide GLP-1 approved for obesity; first-mover in tablet form factor"
  cites: [kbq-1-wegovy-indications, kbq-2-obesity-competitors]
  evidence_facts: [fact:wegovy_oral_25mg_fda_approval_dec_2025, fact:wegovy_pill_launch_jan_2026]

- swot: strength
  claim: "Q1 2026 prescription volume 475K weekly, with oral driving 200K of that — strongest GLP-1 launch ever"
  cites: [kbq-5-wegovy-sales]
  evidence_facts: [fact:wegovy_q1_2026_trx, fact:wegovy_pill_cumulative_trx]

- swot: weakness  
  claim: "Announced 50% WAC reduction effective Jan 2027 — material margin compression"
  cites: [kbq-7-wegovy-pricing]
  evidence_facts: [fact:wegovy_wac_change_675]

- swot: threat
  claim: "Foundayo (orforglipron) approved by FDA Q1 2026 — Lilly's first-mover advantage in oral GLP-1 erodes Wegovy oral differentiation"
  cites: [kbq-2-obesity-competitors, kbq-3-obesity-clinical]
  evidence_facts: [fact:foundayo_fda_approval_q1_2026]

- swot: opportunity
  claim: "MASH submission filed with EMA (Q1 2026) and China priority review granted — TAM expansion beyond obesity"
  cites: [kbq-1-wegovy-indications]
  evidence_facts: [fact:wegovy_mash_ema_submission]
Every SWOT element has working provenance back to source documents through the fact ledger.
5.7 KBQ-7 — Pricing Comparison
Query:
sqlSELECT 
  p.brand_name,
  f.subject_id,
  f.object_value->>'price_type' AS price_type,
  (f.object_value->>'amount')::NUMERIC AS price,
  f.object_value->>'currency' AS currency,
  f.valid_from,
  f.valid_to,
  f.period_type
FROM facts f
JOIN products p ON p.id = f.subject_id
WHERE f.predicate IN ('wac_price', 'net_price_estimate', 'asp_price', 'nadac_price')
  AND f.subject_id IN ($productList)
  AND f.superseded_by IS NULL
ORDER BY p.brand_name, f.valid_from DESC;
Critical: for Wegovy, this returns both the current WAC and the announced future WAC ($675 effective Jan 2027) because the latter is an anticipatory fact still valid.
Strategist agents and the Twin both see the anticipatory price as a future state with high confidence — they can simulate post-Jan-2027 dynamics.
5.8 KBQ-8 — Access Comparison
Requires MMIT/Fingertip data (paid, stubbed v1). In MVP, partial coverage from CMS Part D files:
cypherMATCH (pol:PayerPolicy)-[:covers]->(p:Product {id: $productId})
RETURN 
  pol.payer_name,
  pol.tier,
  pol.pa_required,
  pol.st_required,
  pol.percent_lives,
  pol.effective_date,
  pol.source_doc_id

6. Materiality scoring — how it actually computes
The materiality score (0-10) is a derived fact computed when a signal arrives. The computation uses the semantic layer.
For each signal:
pythondef compute_materiality(signal, tenant_priorities, twin_state):
    
    # 1. Strategic relevance (0.30)
    # LLM classifier: does this signal touch a strategic priority?
    relevance = classify_relevance(
        signal.title + " " + signal.detail,
        tenant_priorities  # e.g., ["GLP-1 obesity", "T2D", "CV outcomes"]
    )  # → 0.0 to 1.0

    # 2. Posterior shift (0.25)
    # What twin beliefs does this signal touch, and how much would they move?
    affected_beliefs = identify_affected_beliefs(signal, twin_state)
    shift_magnitude = max(
        bayesian_update_magnitude(b, signal) 
        for b in affected_beliefs
    ) if affected_beliefs else 0.0  # → 0.0 to 1.0

    # 3. Novelty (0.15)
    # Vector similarity to recent signals on same subject
    similar = qdrant.search(
        collection="signals_30d",
        embedding=signal.embedding,
        filter={"subject": signal.subject_id}
    )
    novelty = 1.0 - max([s.score for s in similar] or [0.0])  # → 0.0 to 1.0

    # 4. Recency × decay (0.10)
    age_days = (now() - signal.published_at).days
    recency = math.exp(-age_days / 14)  # 14-day half-life

    # 5. Source reliability (0.10)
    # Sentinel agent's track record on this source
    reliability = source_track_record(signal.source_id)  # → 0.0 to 1.0

    # 6. Cross-stream confluence (0.10)
    # Are other recent signals from different streams pointing at the same subject?
    confluence = count_confluent_signals(
        subject=signal.subject_id,
        within=timedelta(days=7),
        exclude_stream=signal.stream
    ) / 5.0  # capped at 5

    raw_score = (
        0.30 * relevance +
        0.25 * shift_magnitude +
        0.15 * novelty +
        0.10 * recency +
        0.10 * reliability +
        0.10 * min(1.0, confluence)
    ) * 10.0

    # 7. Watchlist bonus (per-user, additive +0.5 cap)
    user_bonus = watchlist_match_bonus(signal, user.watchlists)
    
    return min(10.0, raw_score + user_bonus)
This is deterministic given the same inputs and the same twin state. Reproducibility is a property of the design, not luck.
The reason Market Zero's prototype showed 1% materiality on every signal: probably the classifier wasn't trained, the twin wasn't connected, or the inputs weren't weighted. Fixed by spec above.

7. Twin update — how facts become beliefs
When FactAsserted event arrives, Twin agent:

Identify affected twin variables. A fact about Foundayo approval touches variables like P(orforglipron US obesity approval by Q2 2026), Lilly oral GLP-1 launch timeline, Foundayo market share 2026, etc.
Compute Bayesian update. For each affected variable, apply update rule based on fact type:

Categorical fact (approval yes/no): point mass at certainty if confidence ≥ 0.95
Continuous fact (revenue, price): Gaussian posterior given evidence likelihood
Probability fact (analyst estimate): Beta-Binomial update


Compute posterior shift. Measure KL divergence or Wasserstein distance between prior and posterior.
Persist new twin snapshot. Twin state versioned; snapshot at each material change.
Emit TwinBeliefUpdated event with magnitude. Synthesizer subscribes — if magnitude × downstream EV-at-stake × novelty crosses moment threshold, generate Moment.

Example with Foundayo:
Prior (from Lilly Q4 2025 commentary):
  P(orforglipron US obesity approval by Q2 2026) ~ Beta(α=4, β=2) → mean 0.67

Fact arrives:
  prod:foundayo approved_for ind:obesity by FDA, date 2026-Q1

Posterior:
  P(orforglipron US obesity approval by Q2 2026) = 1.0 (point mass)

Shift magnitude: KL(prior || posterior) = ∞ → cap at 10.0 (max signal)

Affected downstream beliefs:
  - P(Lilly captures 30%+ obesity oral share by EOY 2026) prior 0.35 → posterior 0.62 (Bayesian update via twin graph)
  - P(Novo Wegovy oral maintains 50%+ obesity oral share) prior 0.80 → posterior 0.55
  - Expected Wegovy oral 2027 revenue: prior $4.2B → posterior $3.1B

EV-at-stake for Novo: |3.1 - 4.2|B = $1.1B → MOMENT GENERATED
This is exactly the kind of inference the platform should support, and it requires the semantic layer to be correct.

8. Shallow trace across all four GLP-1 players
The worked example above was deep on Wegovy. Confirming the model works across the field by tracing what facts get extracted for each player from the documents in your repo.
8.1 Novo Nordisk (from FY 2025 and Q1 2026 docs)
Company-level: revenue (2025 DKK 309B, Q1 2026 DKK 96.8B), operating profit, guidance, share buyback.
Product Wegovy facts: indications (obesity, CV risk reduction, MASH submission EU+CN), formulations (injectable 2.4, injectable 7.2 HD, oral 25mg), pricing (current WAC, announced $675 reduction effective Jan 2027), prescription volume (475K weekly TRx, 2M+ cumulative oral), launches (oral US Jan 2026, HD US April 2026), distribution partnerships (Ro, WeightWatchers, LifeMD, Hims, Sesame), trial results (STEP UP 20.7% weight loss).
Product Ozempic facts: indications (T2D, CV reduction), formulations (injectable, oral pill), pricing (announced $675 ≈35% reduction Jan 2027), trial (SOUL CV outcomes Japan submission).
Product Awiqli (insulin icodec): indication (T2D), US FDA approval Q1 2026, formulation (once-weekly), launch (US 2H 2026 planned).
Pipeline assets: CagriSema (Phase 3 obesity REIMAGINE-2 completed, FDA submission), zenagamtide AMAZE program initiated, ACSL5i Phase 1 initiated, UBT251 Phase 2 China completed, etavopivat HIBISCUS Phase 3 met co-primary endpoints (sickle cell).
8.2 Eli Lilly (from 10-K 2025 and Q1 2026 PR)
Company-level: revenue (2025 $65.2B, Q1 2026 $19.8B +56%), EPS (Q1 $8.26), guidance raise (FY 2026 $82-85B), net income, R&D split (early-stage $4.9B, late-stage $8.5B in 2025).
Product Foundayo (orforglipron): approved Q1 2026 (FDA, obesity), Phase 3 positive readout T2D + CV risk, Commissioner's National Priority Voucher granted, pre-launch inventory $1.5B → indicates imminent launch, EU regulatory filing submitted.
Product Mounjaro / Zepbound (tirzepatide): indications (T2D, obesity, OSA US 2024, HFpEF US 2025 SUMMIT), patent (compound US 2036, EU 2037, JP 2040; data protection US 2027, EU 2033, JP 2030), pipeline (MASH SYNERGY-NASH, CKD SURPASS-CKD).
Product retatrutide: Phase 3 positive readout in T2D (Q1 2026 PR), continued pipeline development.
Product insulin efsitora: regulatory submission US/EU/Japan for T2D.
BD&L activity: four acquisitions in Q1 2026 (Orna Therapeutics, Centessa Pharmaceuticals, Kelonia Therapeutics, Ajax Therapeutics).
Pipeline products: Jaypirca (BTK inhibitor) positive Phase 3 combo data, Taltz + Zepbound combo positive data, Verzenio, Olumiant, Omvoh, Ebglyss (immunology), Kisunla (Alzheimer's), Inluriyo, Cyramza, Retevmo, Emgality.
8.3 Amgen (inferable from competitive context only — no Amgen filings in repo)
Mention in Novo doc: "competition" — no direct facts about MariTide or AMG 133 in your repo.
Recommended fact source: Amgen 10-K, earnings transcripts, ClinicalTrials.gov for MariTide (NCT06640335 MARITIME trial), patent filings.
Fact extraction from those sources would produce: MariTide Phase 3 enrollment status, monthly dosing differentiation, GLP-1 / GIPR-antagonist mechanism, expected readout timing.
8.4 Pfizer (inferable from competitive context only)
Mention in Novo doc: "competition."
Recommended fact source: Pfizer 10-K, earnings transcripts, ClinicalTrials.gov, recent press releases on danuglipron program status.
Critical recent context not in repo but knowable: danuglipron development suspended (Q4 2024 announcement), now in reformulation; oral GLP-1 program is open question.
8.5 What the trace reveals
Doing this exercise on real data exposes the gaps in our v1 demo:

The "P(Lilly oral GLP-1 by Q1 2027)" framing in our previous demo is obsolete. Foundayo is already approved. The strategic question is now "how do Novo's Wegovy oral and Lilly's Foundayo split the oral GLP-1 market in 2026-2027?"
The dominant strategic event in the market is Novo's $675 WAC announcement. This is the largest pricing move in branded pharma in recent memory and should be the headline Moment.
Distribution / channel strategy is a real signal stream that our demo missed. Subscription telehealth (Ro, Hims, WeightWatchers) is materially different from traditional pharmacy distribution.
The 340B provision reversal is a $4.2B accounting fact that's important context for understanding reported vs. adjusted Novo numbers — and any KBQ-5 sales analysis must distinguish reported from adjusted.
CagriSema readout (REIMAGINE-2) is recent news that the previous demo had as future event. Timeline corrected.

The semantic layer makes these corrections cheap. Without it, every demo would need manual data refresh.

9. Build plan for the data + semantic layer
Phase 0 — Foundation (4 weeks)

Stand up Postgres (facts), Neo4j (graph), Qdrant (vectors), Redpanda (event log)
Implement canonical entity model and identity resolution rules
Build first three parsers: ClinicalTrials.gov, PubMed, SEC EDGAR (10-K + press releases)
Build LLM extraction harness with schema validation and confidence scoring
Set up event log subscribers (audit, telemetry only at this stage)

Acceptance: Ingest all four GLP-1 player 10-Ks and Q1 PRs from your repo. Produce a fact store containing every fact in this document. Run a Cypher query that returns Wegovy's full indication landscape.
Phase 1 — Coverage (8 weeks)

Add parsers: FDA DailyMed, Orange Book, Purple Book, CMS ASP, NADAC, EMA, EU CTR, NICE/IQWiG/HAS
Add LLM extractors: earnings transcripts, conference abstracts
Build entity resolution at scale (alias dictionaries, fuzzy matching, human-in-loop for ambiguous cases)
Implement temporal model with valid_from/valid_to and supersession logic
Implement materiality scoring (deterministic, deployable)
Internal Knowledge Library ingestion pipeline

Acceptance: All 8 KBQs produce defensible output for Wegovy, Zepbound, Foundayo, MariTide. Materiality scores discriminate between Tier 1, 2, 3 signals correctly on a curated eval set.
Phase 2 — Intelligence layer (8 weeks)

Twin schema implementation with Bayesian update pipeline
Synthesizer agent for cross-stream causal fusion
Moment generation with EV calibration
KBQ orchestrator running full chain on demand
Strategist agents (three personas) with structured Play output
War Game engine with manual mode wired to KBQ Profiles
Decision Ledger with append-only immutability and hash chain

Acceptance: Synthesizer correctly generates a Moment for the Foundayo approval event, citing the underlying fact, with three plays from three Strategist personas, all with valid evidence_basis arrays.
Phase 3 — Paid integrations and game theory (Phase 3 of product roadmap)

Paid connector integrations (Citeline, Evaluate Pharma, AlphaSense, MMIT, Navelin)
Twin-derived payoff matrices for game theory
Mixed-strategy Nash and Bayesian games
Coach agent decision pattern learning
Replay subsystem reading from event log


10. Why this approach wins
Three things this architecture does that single-layer or LLM-first approaches don't:
Provenance is structural, not bolt-on. Every fact in the system carries its source. Every KBQ output cites the facts it uses. Every Moment cites the KBQ outputs. Click any number in the UI and walk the chain to the original PDF page. This is what makes the platform defensible to regulators and skeptics.
Reproducibility is a property of the design. Given the same data state, the same query produces the same answer. Materiality scoring is deterministic. KBQ outputs are deterministic. Same prompt, same fact base, same output. LLM-first approaches lose this; structured + LLM-where-needed approaches keep it.
Source agnosticism. Swap ClinicalTrials.gov for an internal trial DB? Just write a new connector — the rest of the platform doesn't know or care. Swap LLM provider? Re-version the extraction prompts and backfill where it matters. The semantic layer is the contract; sources fulfill it.

11. Open questions

Ontology source for indications. MeSH? SNOMED? ICD-10? Custom curation? Recommend hybrid: ICD-10 for billing-relevant indications, custom for novel categories (e.g., "obesity with CV risk" isn't an ICD code but is a real commercial segment).
Multi-tenancy vs. global facts. Most facts (FDA approvals, trial results) are global. Some (internal MSL observations) are tenant-private. How does an analyst at Novo see Novo-only internal facts but global facts about Lilly? Row-level security on facts table; tenant_scope nullable, tenant-private rows filtered by RLS policy.
Fact-level conflict resolution. Two sources disagree on Wegovy revenue for a quarter. Which wins? Recommendation: store both, mark with conflict, surface to analyst as a flag. Do not silently pick one.
Embedding model choice and versioning. OpenAI ada-3? Cohere? Local model? Pick one and version it; re-embed on upgrade.
Entity resolution edge cases. Mounjaro and Zepbound are the same molecule (tirzepatide) but different Products with different indications and pricing. The model handles this via Product.contains = ActiveIngredient. But this is a recurring pattern — mol:semaglutide → 3 brand Products. Worth documenting as a pattern.
Real-time vs. batch. Most extractors run on schedule. Some signals (8-K filings, press releases) demand near-real-time. Which sources warrant real-time? Cost vs. value trade-off.
Confidence calibration. LLM-assigned confidence scores tend to be overconfident. Need a calibration step that compares predicted confidence to historical correctness and adjusts.
Backfill vs. forward extraction. Should we backfill 5 years of filings on day one, or only forward-extract from now? Recommend: 2 years backfill for context; forward extraction is primary.


End of document. The frontend rebuild can proceed once Phase 0 + Phase 1 of this layer are in place. The frontend is then a thin presentation of semantic-layer queries.Project contentmarket_zero_helixCreated by youMarketZero · Helix — Data Strategy & Semantic Layer.md1,014 linesmdLilly_2025 Annual Report on Form 10-K.pdf4,910 linespdfNovo Nordisk Q12026financialworkbook.xlsxxlsxContentimport { useState, useRef } from "react";

const SOURCES = [
  { id: "pubmed", label: "PubMed", icon: "🧬", color: "#1a7abf", desc: "Peer-reviewed literature" },
  { id: "biorxiv", label: "bioRxiv", icon: "📄", color: "#c0392b", desc: "Preprints" },
  { id: "chembl", label: "ChEMBL", icon: "⚗️"pastedProduct_CI_Agent_All_KBQ_Workflows_V2.0.docx491 linesdocx