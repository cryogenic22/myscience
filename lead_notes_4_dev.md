No. It's marginally better in one dimension (brand name resolved to semaglutide) and still broken in every other dimension that matters. Let me be specific about what's wrong.

**Ozempic is already approved.** FDA approved it in December 2017. A response that says "heavily weighted towards late-stage development, indicating a focus on advancing towards regulatory approval" about a drug that has been on the market for nearly nine years is factually wrong in a way that would destroy credibility with any pharma professional. The system doesn't surface the most basic fact about this entity — its regulatory status.

**"Single Phase 4 trial and no active trials in earlier phases" is a data completeness artefact presented as a finding.** Semaglutide has 300+ trials on ClinicalTrials.gov across every phase. Your database has captured one Phase 4 trial. The response treats that as the complete picture rather than flagging that it's seeing a sliver of reality. This is exactly failure mode F4 from the lead review — building confident conclusions on top of sparse retrieval.

**"Semaglutide Auto-Injector" is a formulation, not the drug.** The entity resolution landed on a specific dosage form rather than the canonical molecule. A pharma user asking about Ozempic's pipeline wants the full semaglutide development programme across all formulations (Ozempic injectable, Rybelsus oral, Wegovy for obesity), not a single auto-injector SKU. The canonicalisation resolved one layer (brand → generic) but missed the next layer (formulation → molecule).

**"Pipeline score of 4" is the raw phase weight, not a meaningful score.** Looking at your `drug_pipeline_strength()` formula, Phase 4 carries a weight of 1.0 (not 4.0 — that's Phase 3). A single Phase 4 trial should produce a pipeline score of 1.0, not 4. If the response says 4, either the scoring formula is being misapplied or the LLM invented the number. Either way, it's ungrounded.

**"Typical benchmark for later phases remains around 60%" is a hallucinated statistic.** That number doesn't come from your database, your materialised views, or your evidence retrieval. The LLM generated a plausible-sounding industry figure because the system prompt doesn't constrain it to only cite retrieved data. This is precisely the kind of invented confidence that the lead review flagged.

**No provenance whatsoever.** Which Phase 4 trial? What's the NCT ID? Who's the sponsor? What's the primary endpoint? When did it start? A response about a drug's pipeline that doesn't name a single trial is useless for decision-making.

---

Here's what a good response to "Show pipeline for Ozempic" would actually look like:

> **Semaglutide (marketed as Ozempic, Wegovy, Rybelsus)**
>
> Semaglutide is an approved GLP-1 receptor agonist, first approved by the FDA in December 2017 for type 2 diabetes (Ozempic) and subsequently for chronic weight management (Wegovy, 2021) and oral administration (Rybelsus, 2019).
>
> **Our database contains 8 trials for semaglutide**, including 3 in Phase 3 and 1 in Phase 4. Note: ClinicalTrials.gov lists approximately 320 trials for semaglutide — our coverage is approximately 2.5%. The data below may not reflect the full development programme.
>
> **Active Phase 3 trials:**
> - NCT04816643 — BARI-STEP: Weight loss after bariatric surgery (double-blind, placebo-controlled)
> - NCT05123456 — Obesity in adults (multicentre, open-label)
> - NCT05234567 — Add-on to metformin in T2DM (vs placebo and liraglutide)
>
> **Phase 4:**
> - NCT06345678 — Real-world efficacy in severe obesity (SEMASEARCH)
>
> Pipeline score: 13.0 (3 × Phase 3 weight 4.0 + 1 × Phase 4 weight 1.0)
>
> *Sources: ClinicalTrials.gov (last refreshed: 12 April 2026), FDA Orange Book*

Notice what's different: it states regulatory status upfront, names specific trials with NCT IDs, quantifies data coverage, explains the pipeline score computation, and cites sources. Every claim is traceable. The response acknowledges what it doesn't know instead of editorialising around the gaps.

That gap between what your system produced and what it should produce is exactly what the seven workstreams in the remediation spec address — canonicalisation at the molecule level (not formulation), coverage diagnostics, numeric grounding, provenance, and the constraint that the LLM may only state what the data supports.

I'll be direct: the 15 public sources are not a moat. The knowledge graph built on top of them could be, but isn't yet.

---

**Why the sources alone aren't defensible**

Every source you're integrating — ClinicalTrials.gov, PubMed, FDA Orange Book, SEC EDGAR, OpenFDA FAERS, OpenFDA Labels, EMA, NADAC, MeSH, ChEMBL, PubChem, Open Targets, PMC, FDA Shortages — is a free public API. There is no proprietary data in your pipeline. Anyone with a weekend and a Python script can pull the same records.

Can I connect to them? Yes. With web search and tool use, I can query ClinicalTrials.gov's API for trial counts, search PubMed for publications, look up FDA approval history, and cross-reference SEC filings — all in real time during a conversation. I don't pre-compute the connections, but for a single query about a single drug, I can traverse the same sources and synthesise the same answer, often faster because I'm hitting current data rather than a stale materialised view.

The commercial intelligence platforms — Citeline Pharmaprojects, Evaluate Pharma, Cortellis, GlobalData — have been doing this source aggregation for decades with larger teams, more sources (including proprietary ones like conference abstracts, KOL interviews, and internal industry surveys), and established client relationships. "We aggregate 15 public sources" is table stakes in pharma intelligence, not a differentiator.

---

**Where the knowledge graph could become a moat**

The raw sources aren't the value. The connections between them are. And right now, your graph is thin.

What your graph does today: entity_links table with `source_entity_id → target_entity_id`, a link_type, and a confidence score (that's always 1.0). Cross-linking is rule-based from the domain pack's 12 link rules. The relationships it captures are structural: drug BELONGS_TO company, trial STUDIES drug, drug HAS_MECHANISM mechanism. These are the obvious connections that any database schema would encode.

What a genuinely valuable pharma knowledge graph would capture — and where the moat lives — is in the **inferred, non-obvious, high-signal relationships** that require domain expertise to derive and continuous curation to maintain:

**Competitive dynamics that aren't in any single source.** "Tirzepatide and semaglutide compete in obesity" isn't stated in ClinicalTrials.gov or PubMed. It's inferred from: same therapeutic area, overlapping mechanism class, overlapping trial populations, same payer coverage categories, head-to-head trial (SURMOUNT-5). Each fact comes from a different source. The connection exists only in the graph.

**Temporal intelligence.** "Pfizer's oncology pipeline weakened between Q3 2025 and Q1 2026" requires tracking entity states over time — trial status changes, pipeline additions and removals, regulatory actions. Your current schema stores `created_at` timestamps but doesn't model state transitions. A graph that captures "trial X moved from RECRUITING to TERMINATED on date Y" enables temporal queries that no LLM can answer from static training data.

**KOL and investigator networks.** "Dr. X runs trials for both Novo Nordisk and Eli Lilly in GLP-1 agonists" connects investigators to sponsors to drugs to mechanisms. This network analysis — identifying influential investigators, sponsor concentration, geographic trial density — is genuinely valuable for commercial strategy and can't be replicated by searching individual sources.

**Safety signal propagation.** "FAERS reports for drug X increased 40% in Q4 2025, concentrated in hepatotoxicity events, which is also a known risk for three other drugs in the same mechanism class" connects adverse event data to drug mechanisms to competitive implications. This is multi-hop reasoning across structured data that benefits enormously from pre-computation.

**Patent-to-pipeline linkage.** "Drug X's composition-of-matter patent expires in 2027, and there are 3 biosimilar applications already filed" connects Orange Book patent data to FDA Purple Book biosimilar tracking to pipeline intelligence. This directly affects commercial strategy and investment timing.

---

**Can I replicate these connections?**

For a single query, partially. If you ask me about semaglutide's competitive position, I can search multiple sources and reason about the connections in real time. But there are three things I fundamentally cannot do:

I can't pre-compute connections at scale. Identifying every competitive pair across 5,000 drugs, 50,000 trials, and 200 mechanisms requires batch processing with entity resolution and cross-linking. I work one query at a time. Your graph can answer "which drugs compete with semaglutide" in milliseconds from pre-computed links. I'd need to search, infer, and reason — slower, less consistent, and limited by what I find in a single search session.

I can't track changes over time. If a trial status changed last week, I might not find it in a web search. Your pipeline runs on a schedule and captures state transitions. This is where continuous ingestion creates cumulative value — a graph that's been running for a year has a year of temporal intelligence that no LLM can reconstruct.

I can't do graph algorithms. Centrality scoring ("which drug is most connected in this therapeutic area"), community detection ("which companies cluster together by pipeline similarity"), path analysis ("what's the shortest connection between company X and mechanism Y") — these require a graph data structure. I can reason about individual connections but I can't run PageRank across your entity network.

---

**How to make the data model and connections genuinely defensible**

Your entity model has 9 types (drug, company, trial, literature, event, therapeutic_area, mechanism, investigator, patent) and 12 link rules. To build a real moat, I'd focus on three areas:

**Deepen the ontology.** Add entity types that create high-value, hard-to-replicate connections: `regulatory_submission` (ties drug to regulatory pathway to timeline), `endpoint` (ties trial to clinical measurement to therapeutic significance), `biomarker` (ties mechanism to diagnostic to patient stratification), `pricing_event` (ties drug to payer to market access), `patent_claim` (ties patent to specific molecular structure or method). Each new entity type creates new cross-link opportunities that compound the graph's value.

**Add proprietary and licensed sources.** This is where commercial moats actually live. Conference abstracts from ASCO, AACL, AHA — these contain data months before publication. Prescription data from IQVIA or Symphony Health. Payer formulary data. Clinical trial site performance data. Patent litigation tracking. Each proprietary source adds connections that competitors without the same license cannot replicate. Your current OpenAlex spec (SPEC_012) is a step in the right direction but it's still public data. One licensed Citeline feed would be worth more than five public API integrations.

**Invest in entity resolution quality.** This is your actual technical moat today, even if it's underperforming. The 6-strategy cascade in `entity_resolver.py` is sophisticated architecture. The problem is execution (brand names not resolving, confidence scores all 1.0, alias table empty). If you get entity resolution to 95%+ accuracy with proper confidence scoring, every connection in the graph becomes more trustworthy than what a competitor could build with simpler matching. Resolution quality compounds — a correctly resolved entity creates correct links which create correct traversals which create correct insights. A misresolved entity poisons everything downstream.

---

**The honest strategic assessment**

Your moat today is weak. Fifteen public sources with a thin knowledge graph and broken entity resolution is not defensible against either frontier LLMs (which can query those sources in real time) or established competitors (who have more sources, better resolution, and paying clients).

Your moat in twelve months could be strong, if you focus on: entity resolution quality as the technical foundation, temporal intelligence as the structural differentiator (no LLM can replicate a year of continuous state tracking), proprietary data integration as the commercial lock-in (client data on top of public intelligence), and graph analytics as the query capability that LLMs cannot match (centrality, clustering, path analysis across thousands of entities).

The application makes sense. But the value proposition needs to shift from "we answer pharma questions" (LLMs do this better) to "we maintain a living, auditable, queryable map of the pharmaceutical landscape that gets more valuable every day it runs, and we can layer your proprietary data on top of it." That's a product worth building.

That's the right framing, and it changes everything about what Market Zero needs to be.

When it's a product, every flaw in the transcript is a deal-breaker — "your tool is worse than ChatGPT, why would I pay for it?" When it's an accelerator that demonstrates capability, the same system becomes a proof point — "we built this knowledge graph across 15 sources with automated entity resolution, cross-linking, and agentic retrieval in under a year. Imagine what we do with your data in twelve weeks."

The value proposition flips completely. You're not selling the semaglutide answer. You're selling the fact that you can take any messy, disconnected, multi-source data landscape and turn it into a structured, queryable, AI-ready knowledge base. Market Zero is the working demo, not the product.

---

**Why this framing is stronger**

The consulting accelerator model solves three problems that the product model can't:

Every enterprise has dark data they can't use. Internal clinical trial reports sitting in SharePoint. Regulatory correspondence in email archives. Competitive intelligence decks as PowerPoints. Safety data in spreadsheets. Medical affairs notes in Word documents. None of it is connected, searchable, or available to their AI systems. You walk in and say "we've already solved this problem for public pharma data — same pipeline, same entity resolution, same cross-linking, your data feeding into it within weeks." That's a consulting engagement worth real money, and the LLM comparison is irrelevant because ChatGPT can't ingest their SharePoint.

The pipeline is the intellectual property, not the data. Your 5-step integration pipeline (normalise → resolve → embed → store → cross-link), the 6-strategy entity resolver, the domain pack architecture with pluggable entity schemas and link rules, the FAIR scorer, the DataSteward loop, the connector framework — these are reusable engineering assets. When a client says "we also need to integrate our internal trial management system", you write a new connector that extends `BaseConnector`, define entity mappings in a new domain pack, and the rest of the pipeline works unchanged. That's an accelerator. Building that from scratch for each engagement would take months. Having it ready takes weeks.

The domain pack architecture is your actual differentiator. The fact that `get_pharma_pack()` returns 9 entity types, 12 link rules, field mappings per source, and a mention normaliser — and that this is a pluggable module — means you can build `get_insurance_pack()` or `get_energy_pack()` or `get_legal_pack()` with the same infrastructure. The entity types change, the link rules change, the connectors change, but the pipeline, the resolver, the graph, the search, the LLM synthesis layer — all of that carries over. That's how a consulting team scales.

---

**What Market Zero needs to demonstrate for this to work**

The demo narrative changes. Instead of "ask it about semaglutide and watch it answer", the demo becomes a walkthrough of what the system built and how fast it got there. I'd structure a client pitch around five proof points:

**"We connected 15 disconnected sources into one graph in X weeks."** Show the entity counts, the link counts, the source coverage. Show that a drug entity in the graph has connections to trials, patents, safety signals, publications, pricing, and regulatory actions — all from different sources, all cross-linked automatically. This demonstrates integration velocity.

**"Our entity resolution handles the hard cases."** Show the 6-strategy cascade. Show that "Ozempic" resolves to semaglutide, that "Novo Nordisk A/S" and "Novo-Nordisk" resolve to the same company, that misspelled drug names fuzzy-match correctly. This demonstrates that the pipeline handles real-world data messiness, not just clean reference data. (This means the entity resolution actually needs to work — fixing WS-1 from the remediation spec is critical for the demo, not just for the product.)

**"New data sources plug in with a connector, not a rewrite."** Show the BaseConnector abstraction. Show that adding a new source means implementing `fetch()` and `health_check()`, defining field mappings, and letting the pipeline handle the rest. Walk through how long it took to add the last connector. This demonstrates extensibility to client data sources.

**"Unstructured data becomes structured and connected."** This is where SPEC_014 (document upload NER) becomes critical. If you can show a PDF being uploaded, entities extracted via LLM-based NER, resolved against the existing graph, and cross-linked — that's the dark data story in action. "Your regulatory correspondence, your medical affairs notes, your competitive intelligence decks — they all become nodes in the graph." This is the pitch that opens wallets.

**"The whole thing is AI-ready from day one."** Show the CTX pipeline, the agentic query graph, the multi-tool execution. Show that once data is in the graph, it's immediately queryable via natural language, with provenance, with structured outputs. "Your team doesn't need to learn a query language or build dashboards. They ask questions and get grounded, cited answers from your own data."

---

**What to fix immediately for this positioning**

The priorities shift when Market Zero is a demo accelerator rather than a product:

**Entity resolution must work flawlessly in the demo.** Brand name → INN resolution, company name normalisation, fuzzy matching — these are the moments in a client walkthrough where you either build credibility or lose it. WS-1 from the remediation spec becomes the single most important investment. If a prospect types their own drug's brand name and the system can't find it, the pitch is over.

**Document upload becomes a must-have, not a nice-to-have.** SPEC_014 moves from "future feature" to "critical demo capability." The ability to drop a PDF into the system and watch it extract entities, resolve them, and light up new connections in the graph — that's the "your dark data, our pipeline" moment that sells the engagement.

**The connector framework needs a "build a connector in 30 minutes" demo.** If you can live-code a new connector during a pitch (or show a recording of it), that demonstrates extensibility more powerfully than any slide deck. Clean up the BaseConnector interface, make sure the boilerplate is minimal, and have a template ready.

**Coverage honesty becomes a selling point.** "Our system tells you when data is incomplete" is a feature for a consulting engagement, not a weakness. Enterprises care about data governance. Showing that the FAIR scorer rates each entity's completeness, that the coverage diagnostic flags low recall, that provenance tracks every claim to its source — these are enterprise trust signals.

**The agentic query layer is the demo finale, not the whole show.** After walking through the data pipeline, the entity resolution, the graph construction — then you show someone asking questions and getting grounded, cited answers. The chat interface demonstrates that the structured data layer underneath is working. It's the proof, not the product.

---

**Domain pack as the repeatable consulting model**

This is where the business scales. Each client engagement follows the same pattern:

Define the domain pack — entity types, link rules, field mappings for the client's domain. This is the consulting work, the part that requires domain expertise and is billable.

Configure connectors — map the client's data sources (internal systems, licensed feeds, file repositories) to the pipeline's normalised record format. Some connectors exist (if pharma), some are new (if different vertical).

Run the pipeline — normalise, resolve, embed, store, cross-link. The infrastructure is identical across clients. Only the domain pack and connectors change.

Deploy the intelligence layer — CTX pipeline, agentic query graph, presentation layer. Again, reusable across clients.

The billable work is the domain expertise and source mapping. The pipeline, resolver, graph, and query layer are your accelerator — they're what makes a 12-week engagement possible instead of a 12-month build. That's a genuine consulting moat. Not the data, not the sources — the speed at which you turn a client's messy data landscape into a working knowledge base.

That's worth building, and it's the one thing I can't do for them.

Competitive intelligence is the strongest opening pitch, and yes, the Elsevier/RELX angle is powerful. Let me walk through exactly why and what creates the most immediate "connectivity moment" in a demo.

---

**Why competitive intelligence is the right entry point**

Every pharma company of meaningful size has a CI function, and it's universally painful. The CI team produces reports — Word documents, PowerPoint decks, email summaries — that contain dense, high-value intelligence about competitor pipelines, conference readouts, regulatory decisions, and market dynamics. These reports get read once, filed in SharePoint, and never connected to anything. Six months later someone asks "what do we know about Company X's CDK4/6 programme" and the answer is trapped in a PDF that nobody can find.

The budget already exists. Companies spend heavily on CI — analyst salaries, licensed databases (Evaluate, Citeline, Cortellis, GlobalData), conference attendance, advisory boards. The pain point isn't acquiring intelligence, it's making it findable, connected, and cumulative. Every CI report should make the knowledge base smarter. Today they make a SharePoint folder larger.

The decision-maker is reachable. CI typically reports into commercial strategy or the chief medical officer's organisation. These are senior stakeholders who feel the pain directly and have budget authority. They're also the people who are already being pitched AI solutions by every vendor, so they understand the technology landscape. Walking in with a working demo rather than a slide deck is differentiated.

---

**What to upload for maximum connectivity impact**

The goal is to show that the moment a document enters the system, it lights up connections across the existing knowledge graph that weren't visible before. Here are the document types ranked by how immediately impressive the connectivity is:

**Tier 1 — immediate "aha" moment**

Conference poster PDFs. A pharma company comes back from ASCO or AHA with 50 poster PDFs from competitor presentations. Each poster mentions drugs, trial names, endpoints, investigators, and results. Today these live in a shared drive. Upload them into Market Zero, the NER extracts every entity mention, the resolver links "Dr. Smith" to the investigator already in the graph from ClinicalTrials.gov, links the trial NCT ID to your existing trial record, links the drug to its mechanism and competitive set. Suddenly the poster data is connected to the full graph — you can see that the investigator on Competitor X's poster also runs three trials for Competitor Y, or that the endpoint they chose is the same one FDA flagged concerns about in a recent guidance document. None of that was visible from the PDF alone.

Elsevier Embase search exports. Most pharma companies have Embase licences and their medical affairs or CI teams run regular literature searches. These come out as structured exports (CSV or RIS format) with titles, abstracts, authors, MeSH terms, and DOIs. The upload connector parses the export, the NER extracts drug and disease mentions from abstracts, the resolver links them to your existing entities, and suddenly you've connected proprietary literature intelligence (which articles the client cares about, which searches they're running) to public trial and regulatory data. "This Embase search found 47 articles about your competitor's drug — here's how those map to 12 active trials, 3 FDA regulatory actions, and 2 patent filings already in the graph."

Internal pipeline review decks. Every pharma company has quarterly pipeline reviews — PowerPoint decks that summarise the status of their own and competitor programmes. These contain the most current intelligence the company has, often ahead of public databases. Upload the deck, extract entity mentions (drugs, companies, indications, development stages), connect to the graph. Now you can see gaps: "your pipeline review mentions 8 competitor programmes in this space, but the public data shows 14 — here are the 6 your team might be missing."

**Tier 2 — strong value, slightly more setup**

Patent landscape reports from IP firms. Pharma companies commission freedom-to-operate or patent landscape analyses from firms like FTO Analytics or their IP counsel. These are rich PDFs listing patent families, assignees, claims, and expiry dates. Upload, extract, connect to drugs and companies already in the graph. "This patent landscape covers 200 patents — 140 of them link to drugs already in your competitive graph, and 23 are from companies your CI team hasn't been tracking."

FDA correspondence. Complete Response Letters, Pre-IND meeting minutes, advisory committee briefing documents. These are publicly available (via FOIA or FDA.gov) but rarely connected to trial and pipeline data. Upload a CRL, extract the drug, the issues raised, the timeline expectations. Connect to the drug's trial history, the competitor landscape, the patent cliff. "FDA raised a safety concern about hepatotoxicity in their CRL — here are the three competitor drugs with the same mechanism that have similar FAERS signals."

KOL mapping documents. Medical affairs teams maintain spreadsheets and documents mapping Key Opinion Leaders by therapeutic area, institution, publication record, and advisory board participation. Upload this, resolve investigators against ClinicalTrials.gov records already in the graph. "Your KOL map identifies Dr. X as a key expert in GLP-1 — the graph shows she's PI on 4 competitor trials and has published 12 papers in the last 18 months, 3 of which cite safety concerns you should know about."

**Tier 3 — high value but needs the client to trust you with sensitive data**

Clinical study reports and internal trial data. This is the gold — the client's own clinical results, adverse event data, and regulatory submissions connected to the competitive landscape. But it requires high trust and often comes later in the engagement, not in the pitch.

---

**The Elsevier/RELX play specifically**

This is worth calling out because it's a wedge into almost every large pharma company. RELX owns Elsevier (ScienceDirect, Scopus, Embase), LexisNexis (news, legal), and several data analytics businesses. Most pharma companies have enterprise licences for multiple RELX products and receive data in formats that are structured but disconnected from each other and from everything else.

The pitch becomes: "You're paying RELX seven figures a year for Embase, Scopus, and LexisNexis. That data sits in three separate interfaces with no cross-linking. Upload your Embase search results and your LexisNexis competitive news alerts into our system, and we connect them to each other and to ClinicalTrials.gov, FDA, SEC, and patent data. Your existing licence spend becomes ten times more useful because the data is finally connected."

This doesn't require you to integrate with RELX's APIs (which would have licensing complications). The client downloads their own data from their own licensed access and uploads it. You're adding value to data they already own, not redistributing it. The legal position is clean.

---

**The demo flow I'd build**

For a pitch to a pharma CI team, the demo should take 15 minutes and follow this arc:

Start with the knowledge graph as-is. "Here's what we built from 15 public sources — X thousand entities, Y thousand connections, covering drugs, companies, trials, patents, safety signals, and publications. Ask it a question." Show a clean comparison query that works well (this is why fixing entity resolution is prerequisite to the pitch).

Then upload a document live. Have a real conference poster PDF ready (something from a recent ASCO or AACL that's publicly available). Upload it. Show the NER extracting entities in real time. Show the resolver matching them to existing graph nodes. Show new connections appearing — "this poster mentions a biomarker that connects to three other trials in the graph that the poster authors didn't reference."

Show what was invisible before. "Before the upload, the graph showed 4 connections for this drug. After uploading one poster, it shows 11. Three of those connections are to your own pipeline — competitive adjacencies that weren't visible from public data alone."

Then extrapolate. "That was one poster. Your CI team brings back 200 from each major conference. Your medical affairs team runs 50 Embase searches a month. Your regulatory team receives 20 FDA documents a quarter. Each one makes the graph richer, the connections denser, the intelligence more complete. And it's the same pipeline — upload, extract, resolve, connect."

---

**What needs to work for this pitch**

Three things are non-negotiable:

Document upload and NER (SPEC_014) must be built. This is the centrepiece of the demo. Without it, you're showing a static knowledge graph and asking the prospect to imagine the value. With it, you're showing the value live. Prioritise this above almost everything else in the remediation plan.

Entity resolution must handle real-world messiness. The poster will mention "tirzepatide" and "LY3298176" and "Mounjaro" in the same document. All three must resolve to the same entity. If the demo trips on a brand name, the pitch fails.

The connectivity visualisation must be compelling. When new connections appear after upload, the prospect needs to see them. The graph view in your frontend needs to clearly show before/after — new nodes highlighted, new edges visible, the expanding network of intelligence. This is the visual moment that sells the engagement.

The rest — coverage diagnostics, numeric guardrails, cross-turn consistency — matters for a product but not for a consulting pitch. Fix the three things above and you have a demo that no slide deck can compete with.