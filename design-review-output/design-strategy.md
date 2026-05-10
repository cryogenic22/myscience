# Market Zero — Design Strategy

> **The pivot, the principles, the philosophy, the priorities.**
> What the design and engineering teams should align on before week 1 of the 24-week plan.

**Audience:** Design lead, engineering lead, PM, executive sponsor
**Purpose:** Replace ad-hoc product decisions with a shared stance. The themes that should run through every design choice in the next 24 weeks.
**Companion:** `enhancement-backlog.md` is the *what* and *when*. This is the *why* and *how-we-think*.

---

## 1. The headline take

**You have built a category-defining backend. The next 24 weeks ship the experience to match.**

The platform already runs 15 connectors ingesting 162,787 trials, 1,511 FDA Orange Book drugs, full PubMed/PMC, EMA, SEC EDGAR, OpenFDA FAERS + Labels, NADAC pricing, ChEMBL, PubChem, Open Targets and a Pharma News scraper. The CTX context-builder is in production. The materiality scoring service signed off on 9 May 2026. The agent framework, the prompt registry, the game-theory simulation engine — all there. The substrate is genuinely impressive.

The product is not yet doing it justice. Three of the eight Knowledge-Based Questions in the Reimagined Spec are critically thin (Positioning, Pricing, Access). Three of eight CI tabs return 401 errors visible to the user. The most differentiating asset of the platform — fifteen live connectors — is exposed as a raw JSON dump at `/connectors`. ConversationMemory exists in `services/conversation_memory.py` but isn't wired into chat. Multi-tenancy isn't enforced. The DecisionWorkspace looks like Jira on first contact. Materiality scores all show 1% on production because the scorer isn't running on new ingestion.

The fix is structural, not cosmetic. Stop adding specs. Start expressing the specs you have. The 24-week plan in `enhancement-backlog.md` does exactly this: 12 epics, ~36 stories, ~120 tasks, all referenced to existing code files and prototype demonstrations.

---

## 2. The strategic pivot

**From "ship the contract, defer the experience" to "every spec ships with a UI surface that demonstrates its value to Maya."**

The pattern visible across the audit is consistent: SPEC-030 (Decision Workspace v2) shipped on the day the review began with three placeholder panels. SPEC-031 (Materiality scoring) backend signed off the same day with no UI integration. SPEC-035 (Ask-graph) endpoint shipped with no frontend consumer. The team has a habit of writing the spec, building the contract, and deferring the experience layer to "a later iteration that never quite arrives."

This pattern is structurally faster but produces the perceived gap that prompted this review: "the design isn't delivering to the experience this product should have in future." A reorientation is warranted.

For the next 24 weeks: **every spec ships with a UI surface that demonstrates the spec's value to Maya, even if the UI ships behind a feature flag.** The goal is not 19 specs at 60% experiential completion. It is 12 epics at 95% experiential completion. The remaining work can wait or be cut.

This is not a slowdown. It is a re-allocation. The same engineers who would have written SPEC-040 in week 12 instead spend that week wiring SPEC-031's materiality drawer into the SensingFeed. The headline metric shifts from "specs shipped per quarter" to "Maya-felt experience uplift per quarter."

---

## 3. The substrate story · one platform, two products, room for more

The product is not Core Intelligence. The product is not CI + War Gaming. The product is the **shared substrate** on which both, and a third or fourth product, are built. This framing matters because it tells the buyer (and the team) what they're investing in.

```
                  ┌─ Core Intelligence (workspace, ask, dossier, brief)
   Substrate ────┤
                  └─ CI + War Gaming (sensing, decisions, war-rooms, learning)
```

The substrate has three layers:

**The data layer** — 15 live connectors today, 28 more in the roadmap, a BYOD upload pipeline, customer-connector framework. The 8-KBQ coverage matrix tells you exactly what the substrate can answer.

**The intelligence layer** — three named agents (Sentinel, Strategist, Curator), the CTX context pipeline, pgvector with HNSW indexes, the prompt registry, the game-theory simulation engine, the learning loop.

**The experience layer** — the surfaces that make all of this legible to humans. This is the layer that the next 24 weeks rebuilds.

A future third product (regulatory affairs, medical affairs, BD&L) can be built on the same substrate without rebuilding it. The shared engine is the moat. The product surfaces are the expressions.

**Practical consequence:** every design decision asks "does this make the substrate more legible, or does it bury it?" If the answer is "buries it" (e.g. `/connectors` raw JSON), redesign. If "makes it legible" (e.g. data catalog view, KBQ coverage strip, source registry surface), invest.

---

## 4. The four design principles

These run through every prototype, every epic, every story.

### Principle 1 · Trust is a primitive, not a feature

A pharma analyst's reputation rebuilds slowly after one bad call. Every recommendation, every signal, every claim must be traceable back to its evidence in one click. Confidence must be visible, multidimensional, and never collapsed to a single number without an explicit user click.

This translates to the **trust spine** that sits behind every assistant turn:

- **Citation chips** with tier-coloured backgrounds (T1 green / T2 blue / T3 violet) on every claim
- **Entity badges** colour-coded by type, opening a dossier preview on hover
- **Confidence pills** showing one composite + four dimension bars (evidence quality, source diversity, recency, calibration)
- **Source strip** under every answer showing what fed it
- **Reasoning trace** one click away on every assistant message
- **Why-this** button next to anything proactive

If trust is a primitive, the citation chip is the atom. Get the chip right and every surface inherits the discipline.

### Principle 2 · Agents are colleagues, not chatbots

The platform claims agentic intelligence on the landing page. Today this is felt only in `AgentStatusBar` showing "Monitoring · 3 agents" as a static label. Three named agents — Sentinel (Sense), Strategist (Frame + Simulate), Curator (Learn + Recalibrate) — must be visible across every surface, with current activity, last action, and addressable nudges.

This translates to the **agentic philosophy** of four words:

- **Continuous** — agents work whether or not you're watching. The simulation feed runs 47 scenarios a day; you tune in when something interesting happens.
- **Calibrated** — every agent's authority is earned per scenario type via Curator's calibration window. >0.70 calibration → eligible for L3 (recommend). Calibration drops → auto-demote.
- **Contestable** — every output is grounded in evidence; every counter-recommendation is enforced; every prompt is versioned and flaggable.
- **Bounded** — the 5-level authority spectrum (L1 watch / L2 suggest / L3 recommend / L4 act-with-notice / L5 auto-audit) maps decision rights between human and agent. Most decisions sit at L2 or L3 today. As trust accumulates, the spectrum shifts.

War-gaming is the most visible expression of this. War-gaming is not a meeting you schedule; it's the background state of the company. Six adversary digital twins (Pfizer, Lilly, AZN, FDA, Payer, KOL) are continuously modelled. Strategist runs scenarios continuously. The cockpit is where you tune in.

### Principle 3 · The substrate is the surface

Every catalog should have an "add to it" door. Every signal should be one click from its evidence. Every entity should be one click from its dossier. Every recommendation should be one click from the war-game it came from. The substrate is not behind the surface; it *is* the surface.

This translates to:

- **Ask-this-subgraph** affordance — the graph stops being a picture and becomes an interlocutor
- **Entity dossier** as a first-class route — Maya thinks in entities; the product is organised that way
- **Catalog as a real surface** — replaces /connectors raw JSON; persona-aware; supports request-a-connector flow
- **BYOD everywhere** — drop-zone in the catalog, in the workspace chat composer, in the dossier evidence panel

When users see the substrate, they understand the product. When the substrate is hidden, the product looks like one tool among many.

### Principle 4 · Progressive disclosure everywhere

Every metadata artefact follows the same four-level disclosure rhythm:

| Level | Latency | What | Example |
|---|---|---|---|
| **Glance** | < 0.5s | Always visible · scannable | Tier-coloured citation chip |
| **Hover** | 250ms | Brief preview without commitment | Source name + date + 1-line snippet |
| **Click** | < 200ms | Full detail in side panel | Evidence card · jumps + highlights |
| **Drawer** | < 500ms | Everything connected to it | Aggregate views by source/tier/recency |

This rhythm is the same for citation chips, entity badges, confidence pills, evidence stacks, reasoning traces, and the why-this pattern. One disclosure pattern · six artefacts · every surface. The user learns the rhythm once and trusts it everywhere.

---

## 5. The persona-led navigation

Three personas. Same product. Different defaults.

### Maya · the senior CI analyst

Lands on the **Pulse** with three ranked signals + the agent rail showing what's being worked on. Hero is the substrate diagram (so she understands what she owns). Then the war-game board (the strategic surface) and the dissent dashboard (what is the system genuinely torn about?). Search and Graph are accessible but folded behind ⌘K. The catalog and KBQ library are out of view by default — she's not here for that.

Her arc through the product is **Pulse → Dossier → Ask · KBQ → Strategist proposal → War-game → Brief → Commit**. Built for synthesis, not stitching. See `prototype/persona-analyst-mayas-tuesday.html` for the full hour-by-hour walk.

### Ravi · the data steward

Lands on the **Connector marketplace** with all 15 sources, tier, schedule, records, status. Then the auto-annotation flow showing how uploads land. The HITL review queue is a hero surface — these are the entities awaiting his judgement. Catalog table with quality scores comes next. Trigger feed and prompt registry — the meta-machinery — are visible because he needs to spot drift before it propagates.

His arc is **Health check → HITL queue → BYOD upload → Schema drift → Quality scorecard → Tenant audit → Prompt supervision**. Built for judgement, not babysitting. See `prototype/persona-steward-ravis-tuesday.html` for the full hour-by-hour walk.

### Executive sponsor

Lands on the **substrate diagram** (one platform, two products, room for more) + KPI strip (15 connectors, 162k entities, 0.74 FAIR, 14 HITL, 571 signals). Then the KBQ readiness strip (3 strong, 2 moderate, 3 thin). Then the licence health panel (cost transparency, what's free, what's paid, projected cost after Phase 2).

Her arc is **substrate diagram → KBQ readiness → calibration scoreboard → licence health → roadmap**. Built for governance, not authoring.

The persona toggle in the catalog (and elsewhere) **dims rather than hides** sections that aren't relevant to the chosen persona. This is more honest than a hard role-switcher because catalogs cross persona boundaries constantly. Dimming preserves discovery; hiding teaches the user to distrust their navigation.

---

## 6. The agentic layer philosophy · expanded

The four words from Principle 2 deserve more.

### Continuous

War-gaming today is a meeting you schedule. In the future state, war-gaming is the background state of the company. Strategist runs 47 scenarios a day proactively — when a signal arrives, when a posterior shifts, when a calendar trigger fires (pre-ASCO, pre-quarterly), when a counterfactual variant of an existing scenario hasn't been tested in 30 days. Most return "no material finding". A few cross your attention threshold and surface in your morning Pulse.

The user interaction shifts from "open the war-game tool, set up a scenario, run it, read it" to "scroll the morning Pulse, see what mattered overnight, click into the cockpit when something interesting needs your judgement". Agents work whether or not you're watching.

### Calibrated

Per spec §6.5.2, every prediction the platform makes is tracked against actual outcomes. The Learning Layer attributes accuracy to source, agent, and prompt versions, and updates source weights, agent strategies, and recommendation calibration.

Today this is post-hoc — `services/outcome_detector.py` matches outcomes but does not feed back into prompt selection. The active feedback loop (E12 in the backlog) closes this. Every agent has a calibration score per scenario type. Curator runs a windowed calibration job nightly. Authority is earned: an agent that calibrates well over 14 scenarios at 0.70+ is eligible for promotion to L3 (recommend) on that scenario type.

This is the discipline that prevents the "the AI said so" failure mode. Trust accumulates with evidence; doesn't get given.

### Contestable

Every output must be challenge-able by the user. This means:

- **Counter-recommendations enforced** per SPEC-033 — POST `/recommendations/synthesize` returns primary + counter, never just primary. A unanimous AI is a suspicious AI.
- **Reasoning trace** one click away — what the LLM call chain was, which prompt version, which evidence got chosen vs rejected
- **Override sliders** in the war-game cockpit — tune any assumption, watch the recommendation flip or hold
- **Stress tests** ran beside every baseline — "if Pfizer aggressive 80% instead of 61% → flips? holds?"
- **Dissent dashboard** surfacing the decisions where the system was genuinely torn (gap > 50%)
- **Why-this** button next to anything proactive — the question that prevents hallucination panic

The platform earns trust by making itself easy to disagree with.

### Bounded

The 5-level authority spectrum is not a feature — it's the constitutional structure of how human and agent share decision rights:

- **L1 Watch** — humans decide everything. Default for novel scenario types where calibration is unknown.
- **L2 Suggest** — agents propose, humans review every output. Default for high-stakes financial impact (>$50M).
- **L3 Recommend** — agents make the call, humans approve the diff. Default once calibration > 0.70 on a scenario type.
- **L4 Act with notice** — agents act within bounded authority, humans audit. Default for low-stakes reversible (parameter tuning, scenario re-runs).
- **L5 Auto · audit-only** — agents act fully, humans audit retrospectively. Default for housekeeping (rerunning stale scenarios, recomputing source weights).

Not every decision needs a human. And not every decision should be made by an agent. The spectrum tells you which is which, and the answer is per scenario type, per agent, per stake-size — not a global setting.

---

## 7. What to defer · the deliberate non-list

Discipline about scope is the difference between shipping and not. Some things are aspirational, important, and *not* the right thing to build in the next 24 weeks. The audit and the verification phase identified these explicitly. Defer them with intent.

- **Bayesian / Stackelberg / POMDP layer of the war-game board** (SPEC-025). The maths is "pending sign-off by Antigravity". Build the cockpit MVP on the existing stub-reactor; defer the deeper engine to v2.
- **Decision signing with cryptographic provenance** (SPEC-034). Premium feature; matters for enterprise/regulated buyers, not yet for the persona walk. Ships when a buyer demands it.
- **Source Discovery Agent** (spec §7.1). Impressive but unnecessary while curated source list is small. Defer to Phase 4 of the connector roadmap.
- **War-game adversary LLM reactor** (SPEC-028). Stub reactor ships first; LLM reactor is a follow-up after the cockpit MVP proves valuable.
- **Full Catalog deprecation**. Pivot to dossier proves itself for one entity type (drug) first; full deprecation in Q2 2027.
- **Phase 2 paid connectors before executive cost-benefit**. IQVIA, MMIT, AlphaSense, RedBook each turn one critically-thin KBQ comprehensive. Each is six-figure annual. Pick the order based on the one TA where you most need full-stack CI; do not commit four at once.
- **Multi-tenancy beyond E11's basic enforcement**. Per-tenant pricing, per-tenant feature flags, white-labelling — premium features, ship when needed.
- **Real-time war-room mode for high-stakes events** (spec §9.1.3). Phase 4 of the original roadmap; defer until cockpit single-user proves itself.

The product after week 24, with these deferrals, is a category-leading CI platform. The product after week 48, with the deferred items, is a category-defining one. Get the first 24 weeks right and the next 24 will be obvious.

---

## 8. What to commit to in the next 24 weeks · the deliberate list

Every commit decision in the next 24 weeks should ladder back to one of these:

1. **Trust foundation** — close the four critical heuristic findings in weeks 1–2 (E1)
2. **Agent presence felt, not just claimed** — three named agents across all surfaces (E2)
3. **Entity dossier as the spine** — the surface that makes brief composition fast (E3)
4. **Brief composer that reads like Notion, not Jira** — writing-first replaces 5-panel form (E4)
5. **War-game cockpit · the WOW surface** — payoff matrix + adversary twins + authority spectrum (E5)
6. **Chat surface that thinks with the user** — wire ConversationMemory; 6 metadata patterns (E6)
7. **Graph as interlocutor not picture** — ask-this-subgraph; saved subgraphs (E7)
8. **Catalog replaces JSON dump** — three personas served by one surface (E8)
9. **Phase 1 connectors · 8 free public sources** — close largest unfed KBQ gaps (E9)
10. **Source registry with FAIR scoring** — the steward's quality scaffolding (E10)
11. **Multi-tenancy enforcement** — the SaaS-blocker fix (E11)
12. **Prompt registry promotion + active feedback** — close the learning loop (E12)

These twelve, in this order, are the bridge from audit to action.

---

## 9. The trust spine · re-stated

Trust is not a feature. It is the spine of every surface. Six artefacts implement it:

| Artefact | Always visible | Hover | Click | Drawer |
|---|---|---|---|---|
| **Citation chip** | Tier colour | Source + date + snippet | Jumps to evidence card | Full source |
| **Entity badge** | Type colour + dashed underline | Entity card preview | Add to working set | Full dossier |
| **Confidence pill** | Composite + 4 bars | Dimension labels | Why-this-confidence | Calibration history |
| **Evidence stack** | Referenced items border-highlighted | Highlight the citation that uses it | Open source | Aggregate views |
| **Reasoning trace** | "trace" link under message | — | Inline expand | Raw prompts + LLM responses |
| **Why-this** | Tiny badge next to anything proactive | — | One-paragraph explanation | Materiality breakdown |

Implement these once, use them everywhere. The user learns the language; the language earns the product the right to be trusted.

See `prototype/chat-graph-metadata.html` for the full pattern library, with each artefact demoed in real prose.

---

## 10. The substrate diagram · re-stated as a discipline

```
┌────────────────────────────────────────────────────────────────────────┐
│  EXPERIENCE LAYER · the next 24 weeks                                  │
│                                                                        │
│  Pulse · Dossier · Workspace · Brief Composer · War-Game Cockpit       │
│  Catalog · Source Registry · Learning Loop · Ask-Anything (⌘K)         │
│                                                                        │
│  Persona-aware · trust-first · progressively disclosed                  │
└────────────────────────────────────────────────────────────────────────┘
                                  ▲
                                  │
┌────────────────────────────────────────────────────────────────────────┐
│  INTELLIGENCE LAYER · already built                                    │
│                                                                        │
│  Sentinel · Strategist · Curator · Adversary digital twins ×6          │
│  CTX context pipeline · pgvector + HNSW · Prompt registry              │
│  Game theory · Bayesian Monte Carlo · Counter-rec enforcement          │
└────────────────────────────────────────────────────────────────────────┘
                                  ▲
                                  │
┌────────────────────────────────────────────────────────────────────────┐
│  DATA LAYER · 15 live · 28 in roadmap                                  │
│                                                                        │
│  T1 Authoritative · T2 Disclosure · T3 Scientific · T4 Licensed CI     │
│  ClinicalTrials.gov · FDA OB · SEC EDGAR · OpenFDA · EMA · NADAC       │
│  PubMed · PMC · ChEMBL · PubChem · Open Targets · Pharma News · MeSH   │
│                                                                        │
│  + BYOD upload + customer connectors                                   │
└────────────────────────────────────────────────────────────────────────┘
```

**Discipline:** every design decision asks "which layer is this in?" If the answer is "experience layer", honour the four design principles. If "intelligence layer", honour the agentic philosophy. If "data layer", honour the FAIR scoring + source registry discipline. If a decision crosses layers, prefer the answer that makes the substrate more legible.

---

## 11. Success metrics · how we know it worked

Per `phase-reports/phase8-verification.docx` Agent D and the original `tech-specs/tech-specs.docx`, these are the metrics we instrument from week 1.

### Decision-quality metrics

| Metric | Target by week 24 |
|---|---|
| Prediction accuracy (directionally correct at review_at) | 65% |
| Calibration (high-confidence decisions correct) | within 5pts of stated confidence |
| Decision velocity · routine | < 5 business days |
| Decision velocity · high-materiality | < 24 hours |
| Coverage (decisions through platform) | > 60% |

### Sensing & evidence metrics

| Metric | Target |
|---|---|
| Signal latency P50 / P95 | < 1h / < 6h |
| Materiality precision (high-material flagged → user-relevant) | > 70% |
| Evidence-chain integrity | 100% (enforced) |
| Source health uptime (24h) | > 98% |

### Adoption & trust metrics

| Metric | Target |
|---|---|
| Weekly active analysts | track and grow |
| Recommendation acceptance rate | 40-60% (100% = blind trust; <20% = low value) |
| Override-with-rationale rate | > 90% (instrumented as required field) |
| Strategist NPS | > 40 by week 16, > 50 by week 24 |

### Platform health metrics

| Metric | Target |
|---|---|
| Cost per Decision Brief | track and reduce |
| Mean tokens per recommendation | trend down |
| Agent error rate | < 2% |
| Replay success rate | 100% (enforced) |

### The two metrics that matter most

If you only track two:

1. **Strategist NPS** — does Maya recommend the platform to a peer?
2. **Recommendation acceptance rate** — does the brand lead trust the platform's call enough to act on it?

Everything else is in service of those two.

---

## 12. The strategic question for the executive sponsor · before week 1

The next 24 weeks deliver a category-leading CI platform built on a substrate that already exists. The decision is not whether to ship this — it's how to fund the licensed-data conversation that turns Phase 2 of the connector roadmap from "thin" to "comprehensive."

The four Phase 2 sources are:

| Source | Closes | Annual cost (est) |
|---|---|---|
| IQVIA | KBQ 5 Sales (TRx, NRx by drug by month) | ~$280k |
| MMIT | KBQ 8 Access (formularies, PA, step therapy) | ~$180k |
| AlphaSense | KBQ 5 Sales (transcripts) + analyst reports | ~$120k |
| RedBook (or FDB) | KBQ 7 Pricing (WAC + AWP) | ~$90k |

Total Phase 2 is ~$670k/yr. Each of the four turns one critically-thin KBQ comprehensive.

**The recommendation is not to commit all four at once.** Pick the order based on the one TA where you most need full-stack CI. For diabetes/obesity (the current TA scope), MMIT + IQVIA in that order makes sense because access pressure is the binding constraint. For oncology, AlphaSense + IQVIA because conference + transcript intelligence drive more decisions than payer access.

The strategy doc cannot make this decision. The executive cost-benefit needs to.

---

## 13. The closing argument · in one paragraph

You have specified a category-leading product and built most of its mechanics. The remaining work is mostly about expression, not about building new things from scratch. The next 24 weeks ship eight new builds and refactor fifteen existing surfaces — every one referenced in the enhancement backlog to a specific code file and a specific prototype demonstration. The discipline that makes this work is editorial, not technical: every spec ships with a UI surface that demonstrates its value to Maya; every metadata artefact follows one disclosure pattern; every agent is named, calibrated, contestable and bounded; the substrate is the surface. Get these twelve epics shipped and the product the spec backlog already promises is the product Maya opens on a Tuesday morning.

---

> **Stop adding specs. Finish the experience of the specs you have. Then add two new ones.**
> — Closing line of `phase9-instruction-set.docx`

