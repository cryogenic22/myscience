# CI Agent — Reimagined Specification

> Source: CI_Agent_Reimagined_Spec.docx (user-supplied 2026-05-09).
> Both agents (Claude + Antigravity) treat this as the canonical product
> vision. Cross-cutting work derived from this doc is tracked in
> docs/AGENT_BACKLOG.md and per-feature SPEC_NNN files.

---

Next-Generation Competitive Intelligence
Agentic Decision Flywheel Platform
Reimagined Process & Solution Design Specification
Audience: Solution Architects · Product Managers · Engineering Leads
Domain: Pharmaceutical / Life Sciences Competitive Intelligence
Document Version: 1.0

1. Executive Summary
Today's competitive intelligence (CI) workflows in pharma are built as linear, periodic, retrospective reporting cycles. By the time a SWOT or pricing comparison reaches the strategy team, the underlying signals are 4–12 weeks stale, the analysis is shaped by whichever sources happened to be queried, and the resulting recommendations rarely loop back to validate whether the read on the market was actually correct.
This document specifies a next-generation CI platform organized around a Decision Flywheel — a closed-loop system that continuously senses market signals, frames them as decisions, runs robust simulations and war-games, drives action, and learns from outcomes. The eight Key Business Questions (KBQs) from the prior workflow are preserved as foundational evidence layers but are subordinated to the flywheel — they become inputs to decisions, not the deliverable itself.
The platform is multi-agent, event-driven, and built on a shared knowledge graph. It is designed for three primary user modes: Always-On Sensing (passive monitoring with proactive alerts), Decision Mode (structured framing, simulation, and recommendation for a specific question), and War-Room Mode (real-time collaborative response to a market event). This document defines the process, the agent architecture, the data and knowledge layer, the frontend and backend boundaries, the data contracts between layers, and a phased delivery plan.
Core thesis
Competitive intelligence is not a report. It is a continuous decision-support capability. The agentic platform exists to compress the loop from signal → decision → action → learning, and to make every cycle measurably better than the last.

2. Document Map
This document is organized into ten sections covering vision, the flywheel model, agent architecture, data and knowledge layer, frontend and backend specifications, governance, the phased roadmap, and success metrics.
#
Section
What's inside
1
Executive Summary
Why this matters and what we are building
2
Document Map
This section
3
Vision & Strategic Goals
Outcomes the platform must deliver
4
Limitations of Current State
What today's KBQ workflow gets wrong
5
The Decision Flywheel — Conceptual Model
Five-stage closed-loop framework
6
Reimagined Process — End-to-End Flow
Stage-by-stage process specification
7
Agent Architecture
Agents, responsibilities, orchestration patterns
8
Data & Knowledge Layer
Sources, knowledge graph, evidence ledger
9
Frontend Design Specification
User modes, key surfaces, UX patterns
10
Backend Design Specification
Services, data contracts, APIs, infra
11
Governance, Trust & Compliance
Hallucination control, audit, IP, regulatory
12
Phased Delivery Roadmap
MVP through full flywheel
13
Success Metrics & KPIs
How we know it works
14
Open Questions & Risks
Where the architect and PM must align

3. Vision & Strategic Goals
3.1 Vision Statement
Build the operating system for competitive strategy in life sciences — a platform where every meaningful market signal is sensed within hours, every consequential decision is stress-tested through simulation before commitment, every action is tracked against its predicted outcome, and every cycle compounds the organization's ability to read and shape its competitive environment.
3.2 Strategic Goals
Compress signal-to-decision latency. Reduce the median time from a competitor signal appearing in any monitored source to a framed decision recommendation reaching the relevant strategy owner — target: under 24 hours for high-priority signals, down from current 4–12 weeks.
Replace point-in-time reports with living intelligence. Every KBQ output is a continuously updated artifact backed by a versioned knowledge graph, not a deck refreshed quarterly.
Make decisions stress-tested by default. No major strategic recommendation leaves the platform without simulation and war-game pressure-testing across at least three plausible futures.
Build institutional learning into the system. Every prediction the platform makes is tracked against actual outcomes. The model, prompts, source weights, and agent strategies adapt based on what was right and what was wrong.
Preserve human judgment as the decision authority. Agents draft, simulate, recommend, and explain. Humans frame, interrogate, decide, and own. The platform is built to elevate strategist judgment, not replace it.
Earn trust through traceability. Every claim is evidence-linked to source, timestamp, retrieval method, and confidence. Every recommendation exposes its reasoning chain. Nothing is a black box to the user.
3.3 Non-Goals
Replacing the strategy team or the medical/commercial expert. The platform augments judgment; it does not issue decisions.
Becoming a primary regulatory or medical-affairs system of record. Outputs may inform those workflows but are not the source of truth for filings or label claims.
Reproducing every paid-database feature natively. Where licensed data is needed (Citeline, MMIT, AlphaSense, etc.), the platform integrates rather than re-implements.
Real-time trading or immediate-execution use cases. The cadence is operational decision-making (hours to weeks), not algorithmic trading (sub-second).

4. Limitations of the Current KBQ Workflow
The eight-KBQ workflow described in the prior specification is a strong foundation for evidence collection but, viewed as a decision-support system, has structural gaps. The reimagined process retains the KBQ outputs as evidence layers and addresses each gap explicitly.
Gap
What current workflow does
Reimagined approach
Linear and one-shot
KBQs run sequentially with handoffs. There is no continuous re-evaluation when new signals arrive mid-cycle.
Replace with event-driven re-execution: any new signal that materially changes a KBQ output triggers downstream invalidation and refresh.
Output-centric, not decision-centric
The deliverable is a SWOT matrix or competitor table — an artifact, not a recommendation. The user is left to translate evidence into a call.
Wrap KBQ outputs inside Decision Briefs that frame a specific question, surface options, and quantify trade-offs.
No simulation or war-gaming
Comparisons are static (e.g., 'their MOA is checkpoint inhibitor, our MOA is bispecific'). There is no projection of how the market evolves under different scenarios.
Add a Simulation & War-Game layer that models competitor responses, payer behavior, launch sequencing, and pricing dynamics.
Sources are a fixed list
Each KBQ has hard-coded sources (FDA Orange Book, ClinicalTrials.gov, etc.). New sources require manual integration.
Treat sources as a registry with quality scoring; a Source Discovery Agent proposes new sources, and source weights are learned from prediction accuracy.
No feedback loop
Once a KBQ output is delivered, the platform does not learn whether it was correct, useful, or acted upon.
Every output is tagged with a prediction or recommendation, tracked against ground truth, and used to update agent behavior.
Confidence is implicit
Outputs are presented as fact. Cross-trial limitations are flagged in prose but not quantified.
Every claim carries an explicit confidence score, evidence chain, and uncertainty band; UI makes uncertainty first-class.
Database-dependence is fragile
KBQ 7 (Pricing) and KBQ 8 (Access) explicitly note 'output completeness depends on subscription access.' If a license lapses, the KBQ silently degrades.
Source health monitoring with explicit graceful degradation: the platform tells users what it cannot see and why.
Single-product framing
The workflow is built to analyze one focal product against competitors. Cross-portfolio and cross-indication patterns are not first-class.
Knowledge graph allows portfolio-level queries: 'across our oncology pipeline, where are the most contested MOA classes?'

5. The Decision Flywheel — Conceptual Model
The flywheel is the organizing metaphor for the platform. Five stages run continuously and concurrently across many decision threads. Each stage feeds the next, and the final stage feeds back into the first — making the whole system compound over time.
5.1 The Five Stages
1. SENSE: Continuous, multi-source signal ingestion and triage
Always-on monitoring of regulatory databases, trial registries, conference abstracts, earnings, news, social, patents, payer publications, and licensed CI databases. Signals are deduplicated, classified, scored for materiality, and routed.
2. FRAME: Convert signals into decision questions
A signal is not a decision. The Framing Agent converts material signals into structured Decision Briefs: 'Competitor X disclosed Phase III readout in 2L NSCLC — should we accelerate our own readout, reposition to 1L, or hold?' Each brief specifies stakeholders, time horizon, and the options under consideration.
3. SIMULATE: Stress-test options through modeling and war-gaming
For each framed decision, the Simulation Engine projects outcomes under multiple scenarios. War-Game Mode adds adversarial agents (competitor, payer, regulator, KOL) that respond to each option. Outputs are quantified ranges, not point estimates.
4. DECIDE & ACT: Human-authored decision with full audit trail
The platform presents a recommendation with reasoning chain, evidence, simulation results, and dissenting analyses. The human decision-maker selects, modifies, or rejects. The decision, rationale, and committed actions are logged as first-class objects.
5. LEARN: Track outcomes, attribute, and update
Every decision carries a prediction (e.g., 'We expect competitor share to grow 8–12% over 18 months in this segment'). The Learning Layer tracks the actual outcome, attributes accuracy to source, agent, and prompt versions, and updates source weights, agent strategies, and recommendation calibration.
5.2 Why a Flywheel and Not a Pipeline
A pipeline runs once and stops. A flywheel runs continuously, with the output of each rotation becoming the input to the next, and every rotation easier than the last because past learning is encoded into source weights, agent prompts, and decision templates. Three properties make the flywheel mode essential:
Compounding accuracy. Source quality scores, agent strategies, and confidence calibration improve with every prediction-outcome pair the system observes.
Compounding speed. Reusable decision templates, cached evidence chains, and pre-warmed simulations mean the second decision of a given type is faster than the first.
Compounding coverage. Every framed decision adds entities, relationships, and edges to the knowledge graph, making future framing richer.
5.3 The Eight KBQs in the Flywheel
The original eight KBQs are not discarded. They are repositioned as the SENSE-layer evidence backbone — the structured way the platform organizes what is known about the market. Each KBQ becomes a continuously maintained view in the knowledge graph, refreshed on signal arrival rather than on a workflow trigger.
KBQ
Becomes (in flywheel)
Refresh trigger
KBQ 1: Indications
Indication landscape view
Approval-status changes, new pipeline entries
KBQ 2: Competitors
Competitor entity registry
New competitor entries, MOA reclassifications
KBQ 3: Clinical
Clinical evidence layer
New trial readouts, conference data, publications
KBQ 4: Positioning
Messaging & promotion view
Label changes, DTC spend shifts, new claims
KBQ 5: Sales & Sentiment
Commercial performance view
Earnings releases, analyst rating changes
KBQ 6: SWOT
Synthesized strategic view
Recomputed when any of KBQ 1–5 materially changes
KBQ 7: Pricing
Pricing & cost-effectiveness view
WAC changes, HTA decisions, IRA actions
KBQ 8: Access
Coverage & formulary view
Formulary changes, PA additions, payer actions

6. Reimagined Process — End-to-End Flow
This section walks through the platform's operational flow stage by stage, specifying the actors, inputs, outputs, decision points, and instrumentation at each step. It is the canonical reference for how a signal becomes a decision becomes a learning.
6.1 Stage 1 — SENSE
6.1.1 Source Tiers
Sources are organized into four tiers based on access type, latency, and signal density. The platform queries each tier on its own cadence.
Tier
Polling cadence
Representative sources
Tier 1 — Authoritative public
Every 1–6 hours
FDA DailyMed, Drugs@FDA, FDA Orange/Purple Book, EMA EPAR, ClinicalTrials.gov, EU CTR, CMS coverage docs, USPTO, EPO
Tier 2 — Disclosure & news
Every 15–60 min during market hours
SEC EDGAR (8-K, 10-Q, 10-K), company IR pages, earnings transcripts, press releases, regulated news wires
Tier 3 — Scientific & conference
Daily; real-time during conference windows
PubMed, bioRxiv/medRxiv, ASCO/ESMO/ASH/AHA/ACC abstracts, late-breaking announcements
Tier 4 — Licensed CI
Per-source contract; typically daily
Citeline / Trialtrove, Evaluate Pharma, AlphaSense, IQVIA, MMIT, Fingertip Formulary, iSpot.tv, Kantar, Bloomberg
6.1.2 Signal Triage
Raw items from sources are not signals. They become signals only after triage. The Triage Agent applies four filters in order:
Relevance — does this item touch any entity (product, indication, competitor, payer, geography) the user's portfolio cares about? If no, archive.
Novelty — is the underlying claim already known in the knowledge graph at the same or higher confidence? If yes, log as confirming evidence and stop.
Materiality — would this item change at least one KBQ view, decision recommendation, or simulation parameter? Score on a 0–100 scale.
Routing — based on materiality and entity, route to the appropriate KBQ view-maintainer agent and (if score above threshold) to the Framing Agent.
Materiality scoring
A learned model trained on historical signals labeled by whether they ultimately changed a strategic decision. Inputs include source tier, entity criticality (focal product = highest), claim type (clinical readout > formulary tier change > earnings color commentary), and recency. Calibration is reviewed quarterly.
6.2 Stage 2 — FRAME
6.2.1 From Signal to Decision Brief
Most material signals do not, on their own, demand a decision. But clusters of signals do. The Framing Agent runs continuously, looking for one of three triggers:
Threshold trigger — a single signal scoring above 80 on materiality (e.g., competitor Phase III readout, FDA Complete Response Letter, IRA negotiation selection).
Cluster trigger — three or more related signals within a rolling window (e.g., two analyst downgrades plus a formulary tier-down within 14 days).
Calendar trigger — pre-scheduled decision points (quarterly portfolio review, pre-conference prep, annual planning).
6.2.2 Decision Brief Anatomy
A Decision Brief is the canonical handoff from sensing to simulation. It is a structured object with the following required fields:
Field
Description
brief_id
Unique identifier; immutable
question
The decision being asked, in plain language ('Should we accelerate our Phase III readout in 2L NSCLC?')
trigger
The signal(s) or calendar event that generated the brief, with timestamps and source links
stakeholders
Roles that must weigh in: e.g., Commercial Lead, Medical Affairs, Pricing & Access, R&D
time_horizon
When the decision must be made; when its consequences play out
options
The discrete choices under consideration; minimum 2, target 3–5
evidence_refs
Pointers to relevant KBQ views and underlying source records
constraints
Hard constraints: regulatory, contractual, ethical, resource
success_criteria
How we will know, after the fact, whether the decision was right
confidence_to_proceed
Framing Agent's self-assessment of whether the brief is decision-ready or needs more evidence
6.2.3 Human-in-the-Loop on Framing
Framing is the highest-leverage stage and the one most prone to subtle error (asking the wrong question is worse than answering it imperfectly). Every Decision Brief generated by the agent is reviewed by the assigned strategist before simulation. The reviewer can edit the question, add or remove options, expand stakeholders, or send back for more evidence.
6.3 Stage 3 — SIMULATE & WAR-GAME
6.3.1 Three Modes of Simulation
Different decisions need different kinds of stress-testing. The platform supports three simulation modes, selectable per brief:
Mode
What it does
Best fit
Scenario projection
Forecasts under defined futures (base / bull / bear)
Forward sales projections, share-of-voice trajectories, market sizing
Monte Carlo simulation
Probabilistic outcome distributions across hundreds of trials with parameter uncertainty
Pricing decisions, launch-timing decisions, R&D portfolio prioritization
Adversarial war-game
Multi-agent role-play: competitor, payer, regulator, KOL, patient advocacy each respond to each option
Launch sequencing, defensive responses to competitor moves, pricing under IRA negotiation
6.3.2 War-Game Mechanics
The war-game mode is the most distinctive capability and warrants explicit specification. For each Decision Brief option, the Orchestrator instantiates a panel of adversary agents:
Competitor agents — one per top-3 competitor, each prompted with that competitor's known strategy, recent moves, financial position, and pipeline state from the knowledge graph.
Payer agent — represents payer-side incentives, formulary economics, IRA pressure, and recent decision patterns.
Regulator agent — models likely FDA / EMA posture given recent guidance, advisory committee patterns, and approval precedents.
KOL / advocacy agent — represents clinical opinion-leader and patient-advocacy reactions, weighted by historical influence.
Each adversary agent reacts to each option across a defined number of rounds (default: 3). The Orchestrator records every move, computes the resulting market state, and produces a war-game transcript that becomes part of the Decision Brief.
War-game discipline
Adversary agents must be grounded in real evidence about how that adversary has actually behaved. A war-game where the competitor agent does whatever the prompt suggests is theater, not analysis. Every adversary action is tagged with the historical precedent or stated strategy that justifies it.
6.3.3 Simulation Outputs
Every simulation produces three artifacts: a quantified outcome distribution per option (NPV, share, time-to-event), a sensitivity analysis identifying which assumptions most drive the result, and a risk register flagging tail scenarios that warrant explicit mitigation planning.
6.4 Stage 4 — DECIDE & ACT
6.4.1 Recommendation Synthesis
After simulation, the Recommendation Agent synthesizes a final brief view: ranked options, expected value with confidence interval, key dependencies, dissenting reads, and a suggested decision. Crucially, the platform always presents at least one well-argued counter-recommendation. A unanimous AI is a suspicious AI.
6.4.2 The Decision Object
Once the human decision-maker commits, a Decision object is created with these fields, all immutable post-commit:
Field
Description
decision_id
Unique, immutable
brief_id
The Decision Brief this decision answers
chosen_option
The selected option from the brief
decision_maker
Human who committed; signed via authentication
committed_at
Timestamp
rationale
Decision-maker's own reasoning, captured verbatim
predicted_outcome
Quantified prediction the decision-maker is making (e.g., 'expect competitor share growth of 8–12% over 18 months')
actions
Concrete steps with owners and deadlines
review_at
When the platform will re-examine this decision against actual outcomes
evidence_snapshot
Frozen pointer to the evidence and simulation state at decision time
6.4.3 Action Tracking
Each action attached to a decision is a first-class trackable object: assignee, due date, status, and link back to the parent decision. The platform monitors completion and surfaces stale actions in the user's queue. Actions are not just reminders — they are the bridge from decision to learning.
6.5 Stage 5 — LEARN
6.5.1 Outcome Tracking
At the review_at timestamp on every Decision, the Learning Agent retrieves the actual market state and compares it against the predicted_outcome. The comparison produces an attribution record:
Was the prediction directionally correct? Magnitude correct?
Which sources contributed evidence that supported the correct view? Which supported a wrong view?
Which simulation assumptions held? Which broke?
Which adversary agent responses played out? Which were off?
6.5.2 What Gets Updated
Learning is not a one-line metric. It updates four distinct things:
What is updated
How
Source weights
Sources whose signals consistently support correct predictions earn higher weight in materiality scoring and evidence ranking
Agent strategies
Prompt templates, retrieval strategies, and reasoning patterns of agents whose outputs were accepted and proved correct are reinforced; those proved wrong are flagged for review
Recommendation calibration
If the platform's 'high confidence' recommendations are right 60% of the time when they should be right 85%, the calibration model is retrained
War-game adversary models
Adversary behaviors that matched real competitor moves are reinforced; behaviors that didn't are corrected or removed
6.5.3 Closing the Loop
The output of the Learning stage feeds directly back into Stage 1 (SENSE) — updated source weights change which signals score as material. It also feeds Stage 3 (SIMULATE) by updating war-game adversary models, and Stage 4 (DECIDE) by recalibrating recommendation confidence. This is the flywheel rotating.

7. Agent Architecture
The platform is built as a society of specialized agents coordinated by an Orchestrator. This section enumerates the agent roster, defines responsibilities, and specifies the orchestration patterns.
7.1 Agent Roster
Agent
Cardinality
Responsibility
Source Connector Agents
One per source (Drugs@FDA, ClinicalTrials.gov, MMIT, etc.)
Authenticate, fetch, normalize, deduplicate, emit raw items into the signal bus
Triage Agent
Single instance; horizontally scaled by topic shard
Apply relevance / novelty / materiality / routing filters to incoming items
KBQ View Maintainer Agents
One per KBQ (×8)
Keep each KBQ view current as new signals arrive; flag downstream invalidations
Source Discovery Agent
Single instance
Continuously propose new candidate sources based on emerging entity coverage gaps
Framing Agent
Single instance with per-portfolio context
Convert clusters of material signals into Decision Briefs; apply trigger logic
Simulation Agents (Scenario / Monte Carlo / War-Game)
One orchestrator + N worker agents per simulation run
Execute the requested simulation mode; produce outcome distributions and transcripts
Adversary Agents (Competitor / Payer / Regulator / KOL)
Instantiated per war-game
Role-play the relevant adversary in war-game mode, grounded in evidence
Recommendation Agent
Single instance
Synthesize simulation outputs into ranked options with reasoning and dissent
Decision Steward Agent
Single instance
Manage the Decision object lifecycle: capture rationale, track actions, schedule reviews
Learning Agent
Single instance, runs nightly + on-review-trigger
Compare predictions to outcomes, update source weights, agent strategies, calibration
Explainer Agent
Single instance, on-demand
On user request, produce a plain-language explanation of any claim, recommendation, or simulation result, traversing the evidence graph
Guardrail Agent
Single instance, runs on every external-facing output
Check outputs against compliance, hallucination, and safety policies before user delivery
7.2 Orchestration Patterns
Three patterns govern how agents interact. Choosing the right pattern per task is critical for both correctness and cost control.
7.2.1 Event-driven (default for SENSE)
Source connectors emit events to a message bus. Triage Agent and KBQ View Maintainers subscribe and react. No central coordinator. Scales horizontally; resilient to individual agent failure.
7.2.2 Orchestrated workflow (default for FRAME → SIMULATE → DECIDE)
A Decision Brief triggers a defined workflow: Framing Agent → human review → Simulation Orchestrator → Recommendation Agent → human decision. State is persisted at each step; resumable on failure. Each step has explicit timeout and fallback.
7.2.3 Hierarchical with debate (war-game and high-stakes recommendations)
The Recommendation Agent acts as a chair. Two or more sub-agents are tasked to argue opposing positions ('argue for accelerating the readout', 'argue for holding'). Their arguments and evidence are surfaced to the human, not collapsed into a single answer. This pattern is the antidote to false consensus.
7.3 Agent Memory & State
Three layers of memory, each with a distinct retention and access pattern:
Layer
Scope
Storage
Short-term working memory
Per-agent, per-task; flushed on task completion
In-process or Redis; sized for single reasoning chain
Long-term entity memory
Per-entity (product, competitor, indication); persistent
Knowledge graph + vector index
Institutional memory
Cross-agent, cross-decision; persistent and versioned
Decision archive + outcome ledger; queryable for 'have we faced this before?'
7.4 Cost & Latency Discipline
A multi-agent system without cost discipline becomes prohibitively expensive. Three rules govern resource use:
Tiered model selection. Triage and routine extraction use small/fast models. Reasoning, framing, and recommendation use frontier models. War-game adversaries default to mid-tier with optional frontier upgrade per turn.
Caching by claim, not by query. The same factual claim retrieved from the same source within a freshness window is served from cache; different framings of the same question reuse the same evidence.
Budget per Decision Brief. Each brief carries a configurable token and dollar budget. The Orchestrator declines to escalate past it without explicit human approval.

8. Data & Knowledge Layer
The flywheel is only as good as what it knows. This section specifies the data infrastructure that makes continuous, evidence-grounded reasoning possible.
8.1 Knowledge Graph
A graph database (Neo4j or equivalent) holds the canonical model of the market. Core node types and edge types:
Node type
Key edges (and properties)
Product
isMadeBy → Company; treats → Indication; hasMOA → Mechanism; competesWith → Product
Indication
subTypeOf → Indication; affects → Population; hasLineOfTherapy → LineOfTherapy
Company
owns → Product; reportedIn → Filing; analyzedBy → Analyst
Trial
studies → Product; inIndication → Indication; sponsoredBy → Company; hasReadout → Readout
Readout
fromTrial → Trial; reportsEndpoint → Endpoint; publishedAt → Source
Source
publishedClaim → Claim; ofType → SourceType; lastCheckedAt (property)
Claim
evidencedBy → Source; supports / contradicts → Claim; confidence (property)
DecisionBrief
framedFrom → Signal; references → Claim; producedDecision → Decision
Decision
answers → DecisionBrief; predicted → Outcome; observedAs → Outcome (post-review)
Signal
from → Source; touches → Product/Company/Indication; materialityScore (property)
Why a graph and not just a warehouse
Competitive intelligence questions are inherently relational ('which competitors share an MOA class with our pipeline AND have a Phase III readout in the next 6 months AND have a payer-favorable HTA precedent'). These traversals are awkward in SQL and natural in Cypher. The graph also makes evidence chains explicit: every Claim node connects to the Sources that support it.
8.2 Evidence Ledger
Every Claim in the graph is backed by an evidence record in the ledger. The ledger is append-only and content-addressed (hash of the source document), so every claim is reproducible to its origin. Ledger record fields:
source_id and source_url (and archived snapshot for sources prone to change)
retrieved_at timestamp and retrieval method (API, scrape, manual upload)
extraction_method (which agent, which model version, which prompt version)
extracted_text (the exact passage backing the claim)
confidence (0–1, with calibration)
contradicting_evidence_ids (other ledger records that disagree)
8.3 Source Registry & Quality Scoring
Every source is itself an entity in the platform with a tracked quality score. Quality is a learned, multi-dimensional measure:
Dimension
Definition
Coverage
What fraction of relevant entities does this source actually cover?
Latency
How fresh is the data on average? How often does it lag?
Predictive accuracy
Of claims sourced primarily from this source, what fraction proved correct over the last N decisions?
Stability
How often does the source restructure (URL changes, format changes, schema breaks)?
License health
For paid sources: is the license active, what is the rate-limit headroom, when does it renew?
8.4 Storage & Retrieval Topology
Different access patterns demand different stores. The platform uses a polyglot persistence model:
Store
Technology choice
Use
Knowledge graph
Neo4j or Amazon Neptune
Entity & relationship traversal
Document store
S3 + parquet for snapshots, JSON for ledger records
Append-only evidence archive
Vector index
pgvector or a dedicated vector DB
Semantic retrieval over claims and source passages
Time-series store
TimescaleDB or InfluxDB
Pricing curves, share trajectories, signal volumes over time
Operational DB
PostgreSQL
Decision Briefs, Decisions, Actions, user state
Cache & message bus
Redis + Kafka (or equivalent)
Inter-agent coordination, signal fan-out, cached claims

9. Frontend Design Specification
The user interface is where trust is earned or lost. Three principles govern frontend design: surface uncertainty as first-class, make the evidence chain always one click away, and design for three distinct user modes rather than a single dashboard.
9.1 The Three User Modes
9.1.1 Always-On Sensing Mode
This is the default landing experience. The user sees a personalized feed of material signals affecting their portfolio, organized by entity (focal product, top competitors, key indications) and ranked by materiality score. Each signal card shows: source, timestamp, materiality score with the factors driving it, the KBQ view(s) it changed, and a one-click 'frame as decision' action.
The sensing surface answers the implicit question: 'What changed since I last looked, and what should I care about?' It is not a generic news feed; it is a curated, scored, evidence-linked stream tied directly to the user's strategic context.
9.1.2 Decision Mode
Triggered by a Decision Brief — either auto-generated by the Framing Agent or manually opened by the user. The Decision workspace is a single-page, multi-panel interface:
Brief panel (top): question, options, time horizon, stakeholders. Editable until simulation is run.
Evidence panel (left): the relevant KBQ views, deep-linkable to underlying source records.
Simulation panel (center): scenario / Monte Carlo / war-game outputs with interactive sensitivity controls.
Recommendation panel (right): ranked options, dissent view, and the commit-decision action.
Reasoning trace (collapsible drawer): the full chain of agent calls, prompts, and intermediate outputs that produced the recommendation.
9.1.3 War-Room Mode
A real-time collaborative mode for high-stakes events (competitor surprise readout, FDA action, IRA selection). Multiple users join the same Decision Brief, see live-updating evidence and simulations, run new war-game rounds with custom adversary prompts, and chat alongside the workspace. The platform preserves the full session as a Decision Brief artifact when the war-room closes.
9.2 Cross-Cutting UX Patterns
9.2.1 Confidence as a First-Class Visual
Every claim, recommendation, and forecast carries a visible confidence indicator. The platform never shows a number without its uncertainty, never shows a recommendation without its supporting confidence, and never collapses a range into a point estimate without an explicit user click.
9.2.2 Evidence Chain Always One Click Away
Every claim in every view has an 'evidence' affordance that opens a panel showing the source, retrieval timestamp, exact passage, contradicting evidence (if any), and the agent reasoning that produced the claim. No claim is ever orphaned from its provenance.
9.2.3 Disagreement-Surface Design
When agents disagree (e.g., one source says formulary tier 2, another says tier 3), the UI surfaces both, ranks by source quality, and lets the user designate which to accept or escalate to manual review. Disagreements are signals, not bugs.
9.2.4 The Ask-Anything Panel
A persistent natural-language input lets the user ask any question across the knowledge graph: 'show me every product in my therapeutic area whose payer access has degraded in the last 90 days.' Results are graph traversals, not search results, and link directly into the relevant entity views.
9.3 Key Surfaces
Surface
When it appears
What it shows
Sensing Feed
Default home
Materiality-ranked signal stream
Entity Pages
Per product, competitor, indication
Living KBQ-1-through-8 views with change history
Decision Workspace
Per Decision Brief
Evidence + Simulation + Recommendation + Reasoning
War-Room
Real-time collab on a brief
Live evidence, ad-hoc simulation, multi-user chat
Decision Archive
All committed decisions
Searchable by entity, decision-maker, outcome
Outcome Dashboard
Learning surface
Predictions vs. outcomes, source-quality trends, agent-strategy performance
Source Health
Admin / power user
Per-source freshness, error rates, license status, quality scores
Ask-Anything
Persistent overlay
Natural-language graph queries
9.4 Frontend Tech Stack (recommended)
The frontend is a TypeScript single-page application. React with server components is appropriate. Recommended building blocks: a component library with strong data-density support (e.g., Radix + Tailwind, or AG Grid for tables), a charting library suited to time-series and probability distributions (Plotly or Vega-Lite), a graph visualization for entity exploration (sigma.js or react-force-graph), and a real-time channel (WebSockets or Server-Sent Events) for sensing-feed and war-room updates.

10. Backend Design Specification
The backend is a set of services organized around the flywheel stages and a shared platform layer. Service boundaries follow the 'one team can own and deploy independently' rule.
10.1 Service Map
Service
Responsibility
Implementation hint
Ingestion Service
Per-source connectors, scheduling, retry, snapshot archival
Source-specific (HTTP, S3, JDBC, vendor SDKs)
Signal Bus
High-throughput pub/sub for raw items and triaged signals
Kafka / equivalent
Triage Service
Hosts Triage Agent + materiality scoring model
Python / Ray for model serving
Knowledge Graph Service
Read/write API to graph + ledger; enforces evidence-link discipline
Neo4j + custom service in Go or Python
Vector Search Service
Semantic retrieval over claims and source passages
pgvector or dedicated vector DB
KBQ View Service
Maintains the eight KBQ views; serves them to frontend
Read-optimized projections from graph
Framing Service
Hosts Framing Agent; manages Decision Brief lifecycle
Python; integrates with LLM gateway
Simulation Service
Scenario, Monte Carlo, war-game execution; queues, workers, results
Python + workflow engine (Temporal / Airflow)
Decision Service
Decision objects, action tracking, review scheduling
PostgreSQL + REST API
Learning Service
Outcome attribution, source-weight updates, calibration
Scheduled batch + on-trigger jobs
LLM Gateway
Centralized model access, prompt-version registry, cost tracking, guardrails
Custom service over multiple model providers
Auth & Authz Service
User identity, role-based access, audit log
Standard (OAuth/OIDC + custom RBAC)
API Gateway
Single ingress for the frontend; rate limiting, request shaping
Standard
10.2 Critical Data Contracts
These are the contracts the architect should specify in detail before any service is built. Drift on these contracts is the most common failure mode in multi-team agent systems.
10.2.1 Signal Contract (Ingestion → Triage)
Fields: signal_id (UUID), source_id, retrieved_at (ISO-8601), payload (raw, source-specific), entities_mentioned[] (NER pre-pass), claim_candidates[] (extraction pre-pass), provenance (URL, archived_snapshot_ref, fetch_method).
10.2.2 Triaged Signal Contract (Triage → KBQ View / Framing)
Adds: materiality_score (0–100), routing_targets[] (which KBQ views and/or Framing Agent), novelty_class (new / confirming / contradicting), entity_links[] (resolved knowledge-graph node IDs).
10.2.3 Decision Brief Contract (Framing → Simulation / Frontend)
Per the Brief Anatomy in Section 6.2.2, plus state machine: draft → human_review → simulation_pending → simulation_complete → decision_pending → committed → in_review → closed.
10.2.4 Simulation Result Contract
Fields: simulation_id, brief_id, mode (scenario / monte_carlo / war_game), per-option outcome distribution, sensitivity ranking, war-game transcript (if applicable), assumptions log (frozen at run time), reproducibility seed, model versions used.
10.2.5 Decision Contract
Per Section 6.4.2, with cryptographic signing of the immutable fields by the decision-maker's authenticated session token, so the audit trail is tamper-evident.
10.3 LLM Gateway: Why It Is Non-Negotiable
Every agent in the system calls one or more language models. Centralizing this through a single gateway is essential for four reasons:
Cost visibility and control. Without a gateway, model spend is invisible until the bill arrives.
Prompt versioning. Every prompt used in production is registered, versioned, and tied to outcomes — so the Learning Service can attribute prediction accuracy to specific prompt versions.
Provider portability. The gateway abstracts the provider so the platform can route to different models per task and switch providers without rewriting agents.
Safety and PII filtering. A single chokepoint where every prompt and response is scanned for prohibited content, leaked credentials, or PII.
10.4 Observability
A multi-agent system is uninterpretable without first-class observability. Required from day one:
Distributed tracing across agent calls, with the trace ID surfaced in the Reasoning Trace UI panel.
Structured logging of every prompt, response, model version, token count, and latency.
Metrics per agent: throughput, error rate, mean and tail latency, token cost.
A 'replay' capability: given a Decision Brief ID, replay the full chain of agent calls in a sandbox for debugging.
10.5 Deployment & Scaling Posture
Stateless services run in a managed container platform (Kubernetes or equivalent). Stateful services (graph, vector store, time-series) use managed offerings where available. The signal bus and message queue are managed (e.g., MSK or Confluent for Kafka). Simulation workers are autoscaled based on queue depth. War-room mode requires sticky sessions and edge-cached real-time channels. Multi-region read replicas of the graph for global users; writes consolidated to a primary region.

11. Governance, Trust & Compliance
In life sciences, an unreliable competitive intelligence platform is worse than no platform — it can drive regulatory missteps, off-label implications, or commercial bets predicated on phantom data. Governance is built in from day one, not bolted on.
11.1 Hallucination Control
Three layers of defense:
Retrieval grounding. Every claim that appears in any user-facing artifact must be linkable to one or more evidence ledger records. Claims without ledger backing are rejected by the Guardrail Agent.
Cross-source corroboration thresholds. High-stakes claims (pricing, regulatory status, payer coverage) require at least two independent sources, or are flagged with explicit single-source warnings.
Self-consistency checks. The Recommendation Agent's output is re-checked against its own cited evidence by an independent verification pass; contradictions trigger regeneration or human escalation.
11.2 Audit & Reproducibility
Every Decision is reproducible. Given a decision_id, the platform can recreate: the exact evidence available at decision time, the exact agent versions and prompts that ran, the exact simulation outputs, and the exact recommendation presented. This is enforced via the evidence_snapshot, model version registry, and prompt registry being immutable post-decision.
11.3 Access Control & Information Boundaries
Role-based access at the entity level: a user assigned to one therapeutic area does not see Decision Briefs in another. Sensitive Decisions (M&A, undisclosed pipeline) are walled off in restricted compartments with separate audit logs. All access is logged for compliance review.
11.4 IP, Licensing & Terms-of-Use
Each licensed source has an explicit usage profile encoded in the Source Registry: is bulk extraction allowed, can claims derived from it be persisted in the graph, can it be combined with other sources in derived analytics, what attribution is required. The Ingestion Service enforces these at fetch time. The Knowledge Graph Service enforces them at retrieval time. The frontend enforces them at display time (e.g., source attribution alongside any quoted passage).
11.5 Regulatory Posture
The platform is not a regulated medical device; it produces strategic intelligence, not clinical decisions. Outputs are explicitly labeled as decision-support, not as approved medical or regulatory guidance. Where outputs are used to inform regulated workflows (label strategy, payer submissions), they must pass through the user's existing review processes — the platform does not substitute for them.

12. Phased Delivery Roadmap
Building the full flywheel in one release is not realistic. The roadmap delivers a usable product at each phase while preserving architectural integrity for the full vision.
12.1 Phase 1 — Foundation (Quarters 1–2)
Goal: stand up the SENSE layer with the eight KBQ views as living artifacts on a small set of tier-1 public sources. No simulation, no decision objects yet.
Deliverables: Knowledge graph schema, Evidence Ledger, Source Connectors for FDA / EMA / ClinicalTrials.gov / SEC EDGAR / PubMed, Triage Agent v1, KBQ Views 1, 2, 3 (Indications, Competitors, Clinical), Sensing Feed UI, Entity Pages.
Success criterion: a strategist can replace one manual KBQ refresh per week with the platform's living view, with full evidence chains.
12.2 Phase 2 — Decision Mode (Quarters 3–4)
Goal: introduce Decision Briefs, scenario simulation, and the Decision Workspace. KBQs 4, 5, 6, 7, 8 added.
Deliverables: Framing Agent, Decision Brief lifecycle, Scenario Simulation Service, Recommendation Agent, Decision Workspace UI, Decision Archive, all eight KBQ views in production.
Success criterion: at least 20 Decision Briefs framed and committed through the platform per quarter, with strategist NPS > 40.
12.3 Phase 3 — War-Game & Learning (Quarters 5–6)
Goal: introduce adversarial war-game simulation, Monte Carlo, and the closed feedback loop.
Deliverables: Adversary Agents, War-Game Mode, Monte Carlo Simulation Service, Learning Agent, Outcome Dashboard, source-quality scoring.
Success criterion: prediction-vs-outcome attribution running on at least 3 months of decisions; measurable improvement in materiality-scoring precision.
12.4 Phase 4 — War-Room & Compounding (Quarter 7+)
Goal: real-time collaboration, full source coverage including licensed CI databases, advanced learning.
Deliverables: War-Room Mode, real-time channels, Citeline / Evaluate / MMIT / AlphaSense integrations, Source Discovery Agent, automated source-weight updating, calibration retraining.
Success criterion: signal-to-decision median latency below 24 hours for high-materiality signals; documented year-over-year improvement in recommendation calibration.
12.5 What to NOT Build in Phase 1
Discipline about scope is the difference between shipping and not. Specifically defer: war-game adversaries (compelling demo, high engineering and prompt-engineering cost; defer to Phase 3), licensed-source integration (license negotiation alone can consume a quarter; defer non-essential ones to Phase 4), and the Source Discovery Agent (impressive but unnecessary while the curated source list is small; defer to Phase 4).

13. Success Metrics & KPIs
Metrics fall into four categories. The platform must instrument all four from Phase 1, even where the metric will not move meaningfully until later phases.
13.1 Decision-Quality Metrics
Metric
Definition
Target
Prediction accuracy
Of decisions with measurable predicted outcomes, fraction directionally correct at review_at
65% by end of Phase 3, 75% by end of Phase 4
Calibration
Of decisions tagged 'high confidence', fraction actually correct (target: matches the stated confidence)
Within 5 points of stated confidence by Phase 4
Decision velocity
Median time from brief creation to decision commit
< 5 business days for routine, < 24 hours for high-materiality
Coverage
Fraction of strategic decisions in the user's portfolio that pass through the platform
> 60% by end of Phase 3
13.2 Sensing & Evidence Metrics
Metric
Definition
Target
Signal latency
P50 / P95 from event in source to signal in user feed
< 1 hour P50, < 6 hours P95
Materiality precision
Of signals flagged high-materiality, fraction the user marks relevant
> 70%
Evidence-chain integrity
Fraction of user-facing claims with complete ledger backing
100% (enforced)
Source health
Fraction of registered sources fetching successfully in the last 24h
> 98%
13.3 Adoption & Trust Metrics
Metric
Definition
Target
Weekly active strategists
Users running at least one substantive query per week
Track and grow
Recommendation acceptance rate
Fraction of platform recommendations the human decision-maker selects unmodified
Target a healthy 40–60% — 100% suggests blind trust; under 20% suggests low value
Override-with-rationale rate
When users override a recommendation, fraction where they capture rationale
> 90% (instrumented as required field)
Strategist NPS
Quarterly survey
> 40 by end of Phase 2, > 50 by Phase 4
13.4 Platform Health Metrics
Metric
Definition
Target
Cost per Decision Brief
All-in token, infra, and licensed-data cost
Track and reduce; benchmark vs. comparable consultant spend
Mean tokens per recommendation
Token spend per Recommendation Agent run
Trend down via caching and tiered models
Agent error rate
Fraction of agent runs that fail or produce guardrail-rejected output
< 2%
Replay success rate
Fraction of decisions reproducible from audit data
100% (enforced)

14. Open Questions & Risks
The architect and product manager should treat this final section as the working agenda for the first sprint. Each item is unresolved at the level of this specification and requires explicit decisions before build.
14.1 Open Architectural Questions
Single tenant or multi-tenant from day one? Multi-tenant adds complexity but is essential if the platform serves multiple business units or external customers.
Which graph database — Neo4j (mature, query language well-known) or Neptune (managed, AWS-native)? Decide based on existing cloud commitments and team familiarity.
Workflow engine choice — Temporal, Airflow, Prefect, custom? Temporal is best fit for long-running, resumable agent workflows but adds a new platform dependency.
Real-time channel — WebSockets vs SSE vs a managed service (Pusher, Ably, or AWS AppSync)? Affects War-Room mode latency and operational burden.
Where do simulations run — same cluster as agents, or a dedicated compute pool with GPU access? Monte Carlo at scale and Bayesian models can be expensive.
14.2 Open Product Questions
Who owns the Framing Agent's output before human review — does it go to the relevant strategist's queue automatically, or to a triage role first?
How aggressive should the materiality threshold be by default? Too low and users drown; too high and material signals are missed.
Are war-game adversary agents a feature exposed to all users, or only to a designated 'red-team' role with elevated permissions?
What is the policy when paid-source license expires or rate-limit is hit mid-decision? Block the decision, degrade gracefully with a warning, or allow override?
Should the Decision Archive be searchable across the entire organization, or compartmentalized by therapeutic area / business unit?
14.3 Top Risks
Risk
Likelihood × Impact
Mitigation
Hallucination in user-facing recommendations
High
Guardrail Agent + retrieval grounding + cross-source corroboration; explicit confidence bands; never display a claim without evidence link
License violation on paid sources
High
Source Registry enforces usage profile at fetch, retrieval, and display; legal review before each new licensed source integration
Strategist over-trust ('the AI said so')
Medium-High
UI patterns that always surface dissent and uncertainty; mandatory rationale capture on commit; calibration metrics shared with users
Cost overrun from agent recursion / loops
Medium
Per-brief budget caps, tiered model selection, max-step circuit breakers in Orchestrator
Source schema drift breaking ingestion silently
Medium
Schema validation at fetch; alerting when extraction confidence drops; canary checks per source
Knowledge graph quality decay over time
Medium
Periodic graph audits; entity-resolution refresh; orphan-claim sweeps
Slow decision adoption (built but unused)
High
Phase 1 ships with one strong workflow integration, not eight weak ones; embed with one strategist team for first 90 days

— End of Specification —
