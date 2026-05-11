# MarketZero · Helix
## Surface Mapping & Merge Decisions

**Purpose:** Resolve every IA conflict between the two products. One artifact per surface. One decision per artifact. No ambiguity left for the build team.

**Merge rule:** Helix IA is primary. MarketZero verbs, taxonomy, and tactical UX patterns are adopted into the Helix shape where they improve it. Where they conflict, Helix wins on architecture; MarketZero wins on language and analyst-facing interactions.

---

## 1. Top-level navigation — final shape

The unified left nav. Six primary surfaces plus a persistent Decision Ledger pin.

| # | Surface | Source | Notes |
|---|---------|--------|-------|
| 1 | **Bridge** | Helix | Home. Pulse + Twin + Moments. MarketZero's Sensing Feed folds in as the Pulse zone. |
| 2 | **Watchlist** | MarketZero | NEW top-level. Saved-search-as-product. Filters into Bridge views. |
| 3 | **KBQ Workspace** | Helix | Eight-station structured intelligence pipeline. |
| 4 | **War Game** | Helix + MarketZero | "War Rooms" naming retained for individual sessions; "War Game" is the surface. |
| 5 | **Knowledge** | Helix | Internal docs upload + indexing. |
| 6 | **Replay** | Helix | Twin belief history + decision outcomes (MarketZero's Insights folds in). |
| — | **Decision Ledger** | NEW (from MarketZero's Decisions) | Persistent pin in nav, always one click away. Append-only commit record. |
| — | **Reviewer** | MarketZero | NEW top-level, alongside Agents. Coach surface. |
| — | **Agents** | Helix | Roster and autonomy controls. |

What got dropped or merged:
- MarketZero's **Sensing Feed** → becomes Pulse zone in Bridge (was already there in Helix)
- MarketZero's **Daily Digest** → becomes a scheduled view *mode* of the Bridge (toggle in the header)
- MarketZero's **Signals DB** → becomes a power-user filter view accessible from Bridge ("Browse all signals →")
- MarketZero's **War Rooms** → individual war-game sessions inside the War Game surface; the term "War Room" is kept for a session
- MarketZero's **Decisions** → Decision Ledger (pinned, not a top-level)
- MarketZero's **Insights** → folds into Replay (rationale: same job, Helix's belief-curve treatment is stronger)

---

## 2. Surface-by-surface merge decisions

### 2.1 Sensing Feed (MZ) → Bridge / Pulse zone (Helix)

| Aspect | MarketZero | Helix | Decision |
|--------|------------|-------|----------|
| Layout | Full-page vertical list | Vertical column inside Bridge | **Helix.** Bridge keeps three zones (Pulse · Twin · Moments). Full-page Signals view available as "Browse all" drilldown. |
| Signal classification | Impact category (Financial / Strategic / Clinical / etc.) | Source stream (Trials / Regulatory / Publications / etc.) | **MarketZero taxonomy primary** for the *user-facing filter*. Source stream retained as a secondary tag visible on each signal. Both indexed. |
| Priority indication | Materiality dial + tier_1/2/3 | Impact score (1–10) | **MarketZero.** Tier classification is more analyst-comprehensible. Numeric impact score retained as detail-on-hover. |
| "FRAME AS DECISION" verb | Yes, on every signal | No equivalent | **Adopted from MarketZero**, but with constraint: button visibility gated by tier (tier_1 always, tier_2 on hover, tier_3 hidden by default with reveal). Decision fatigue mitigation. |
| Empty state | Raw 401 JSON (observed bug) | Informative empty state | **Helix.** Empty states must explain. No raw errors. |
| Always-on monitoring banner | "MONITORING · 3 AGENTS ACTIVE" | "11 agents · live" in header | **Helix.** Global agent status in header, not per-surface. |

### 2.2 Daily Digest (MZ) → Bridge / scheduled view mode (Helix)

| Aspect | Decision |
|--------|----------|
| Concept | Adopted from MarketZero. Daily/weekly scheduled rollup is genuinely useful. |
| Placement | Mode toggle in Bridge header: *Live* (default) / *Today's Digest* / *This Week*. |
| Content | Top 5 moments + 10 signals from the period, with morning-brief framing. |
| Delivery | Also available as email/Slack push at user-configured time. |

### 2.3 Signals DB (MZ) → Browse-all-signals view (folded)

| Aspect | Decision |
|--------|----------|
| Concept | Adopted from MarketZero. Power users need queryable signal history. |
| Placement | Accessed from Bridge via "Browse all signals →" link in the Pulse zone footer. Not a top-level nav item. |
| Features | Full filtering by category, tier, date, source, company. Save filter as Watchlist (creates a new Watchlist entry). |

### 2.4 Watchlist (MZ) → Watchlist (new top-level)

| Aspect | Decision |
|--------|----------|
| Concept | Adopted from MarketZero as a top-level surface. This is what Helix was missing. |
| Definition | A Watchlist is a saved-search-plus-subscription. It binds a filter expression (category + companies + keywords + tier threshold) to alerting preferences. |
| Examples | "Lilly + Pricing & Access + tier_1 only" / "Any company + Regulatory + AI & Digital + daily digest" |
| Surface | List view of all Watchlists in the tenant + new-Watchlist creator. Click a Watchlist to see its current matching signals (essentially a pre-filtered Bridge). |
| Relationship to KBQ | A Watchlist can be promoted to a KBQ Profile target. "Watch Lilly pricing" can trigger KBQ-7 refresh automatically. |

### 2.5 War Rooms (MZ) → War Game / sessions (Helix)

| Aspect | Decision |
|--------|----------|
| Surface name | **War Game** (Helix) for the platform-level capability. Individual sessions called **War Rooms** (MarketZero language retained). |
| Modes | Helix's three modes preserved: Manual / Auto-Simulate / Game-Theoretic. |
| Session list | War Game landing shows list of active and past War Rooms (sessions). Click into a session to enter the room. |
| Entry points | Three: (1) directly from War Game surface, (2) "Run War Game on this Play" from a Moment, (3) "Frame as Decision → Open War Room" from a tier_1 signal. |

### 2.6 Decisions (MZ) → Decision Ledger (pinned)

| Aspect | Decision |
|--------|----------|
| Concept | Adopted from MarketZero, repositioned as a persistent pinned element rather than a top-level nav item. |
| Placement | Pin in the header next to agent status. Click opens a slide-over panel showing recent decisions + jump to full ledger. |
| Content | Append-only record of every commit. Each entry: title, decision date, who committed, play chosen, outcome (if known), evidence chain. |
| Why pinned, not nav | Decisions are the *output* of the platform — they should be glanceable and accessible from anywhere, not buried in a tab the user navigates to. |

### 2.7 Insights (MZ) → Replay (Helix)

| Aspect | Decision |
|--------|----------|
| Surface | **Replay** (Helix). MarketZero's Insights folds in. |
| Rationale | Same job (review past state and outcomes); Helix's belief-curve treatment with scrubber is stronger than a static insights view. |
| Inherited from MZ | The "insights extracted per period" framing. Replay's top bar shows count of decisions, moments, outcomes, accuracy delta for the selected period. |

### 2.8 Reviewer (MZ) → Reviewer (new top-level)

| Aspect | Decision |
|--------|----------|
| Concept | Adopted from MarketZero as a top-level surface. Better than burying Coach in Agents. |
| Definition | The surface where the Coach agent surfaces observations about the user's decision patterns — biases flagged, predictions that didn't pan out, decisions that have outperformed others. |
| Content | Personalized feed of Coach observations + accuracy summary per decision category + "lessons learned" structured prompts. |
| Tone | Advisory, never authoritative. The Coach surfaces patterns; the human decides whether they're real. |

### 2.9 KBQ Workspace, Knowledge Library, Agents

These three come straight from Helix without substantive change, because MarketZero doesn't have direct counterparts. Naming retained.

---

## 3. Verb and language adoption

| MarketZero language | Adopted? | Where |
|---------------------|----------|-------|
| **"Frame as Decision"** | Yes | Action button on signals (tier-gated) and on Bridge Twin nodes |
| **"Sensing"** | Partial | Used as the *category* for the Sentinel agent class. Not used as a surface name (Helix's "Pulse" is more concrete). |
| **"Materiality"** | Yes | Replaces Helix's "impact score" terminology. The number remains 1–10 but is *called* materiality. |
| **"Tier 1/2/3"** | Yes | Replaces Helix's "high/medium/low impact" labels. Tier 1 = decision-grade, Tier 2 = noteworthy, Tier 3 = monitoring. |
| **"War Room"** | Yes | For an individual war game session. The platform-level capability is "War Game." |
| **"Watchlist"** | Yes | First-class concept and top-level surface. |
| **"Daily Digest"** | Yes | As a Bridge view mode. |
| **"Reviewer"** | Yes | As a top-level surface. |
| **"Signals DB"** | Adopted in concept, renamed | Becomes "Browse signals" inside the Bridge. The acronym "DB" is jargon. |
| **"Connectors"** | Yes | Footer link in MarketZero retained. Goes to a connector management view (existed only in the engineering brief in Helix). |

### Helix language preserved

| Helix language | Why kept |
|----------------|----------|
| **"Bridge"** | Strong metaphor (calm landing surface, the place the user starts the day). MarketZero "Cockpit" had less semantic weight. |
| **"AI Moments"** | The cinematic decision concept is unique to Helix. Worth preserving the name. |
| **"Digital Twin"** | Industry-standard term, accurately describes the underlying model. |
| **"KBQ" / "KBQ Profile" / "KBQ Workspace"** | Anchors the platform to the eight-question framework the CI community already knows. |
| **"Play"** | Better than "decision option" or "action." Sharp, strategic. |
| **"Posterior shift" / "Belief delta"** | Precise. Bayesian framing matters for the analyst community. |

---

## 4. Taxonomy adoption

The MarketZero impact category taxonomy is adopted as the primary user-facing classification. Helix's source-stream taxonomy is retained as a secondary tag.

### Primary classification — Impact Category (from MarketZero)

1. **Financial** — earnings, guidance, revenue, sell-side notes, M&A finance
2. **Governance** — leadership changes, board, ethics, regulatory enforcement
3. **Strategic** — partnerships, divestitures, market entry/exit
4. **Clinical** — trial readouts, safety signals, label changes, clinical hold
5. **Product** — launches, supply, formulation, manufacturing
6. **Regulatory** — FDA / EMA / regulatory body actions, advisories, NCDs
7. **M&A** — acquisitions, in-license, JV, asset swap
8. **Pricing & Access** — formulary, payer policy, IRA, HTA, list/net price
9. **AI & Digital** — digital therapeutics, AI/ML clearance, data partnerships
10. **ESG & Supply** — supply chain, sustainability, manufacturing geography

### Secondary classification — Source Stream (from Helix)

Retained as a per-signal tag, used for source attribution and provenance, not as the primary filter:

Trials · Regulatory · Publications · Payer · KOL · Financial · Patent · Internal

(Note: "Financial" appears in both taxonomies. That's fine — it's the same concept, captured both as a source-of-truth tag and as a user-facing filter category.)

### Tier classification (from MarketZero)

- **Tier 1** — decision-grade. Materiality ≥ 7. Triggers Moment generation. Shows FRAME AS DECISION prominently.
- **Tier 2** — noteworthy. Materiality 4–6. Surfaces in Daily Digest. FRAME AS DECISION on hover.
- **Tier 3** — monitoring. Materiality < 4. Available in Signals DB / Browse, not prominent in Pulse.

Tier is computed automatically by the Sentinel and Synthesizer agents. Users can manually re-tier a signal (logged for Coach learning).

---

## 5. Materiality scoring — the fix

The screenshots showed everything scoring 1%, which is a model failure. The merged product cannot ship with this. Specifying the fix:

### What materiality scores

A 0–10 numeric score (displayed as 0–100% on the dial) representing the signal's expected impact on the tenant's strategic priorities.

### Inputs to the score

| Input | Weight | Source |
|-------|--------|--------|
| Strategic relevance | 0.30 | LLM classifier against tenant's stated priorities (e.g., "GLP-1 obesity," "oncology pipeline," etc.) |
| Posterior shift magnitude | 0.25 | How much does this signal move the Twin's beliefs? Larger shift = higher materiality. |
| Novelty | 0.15 | Is this signal new information or restated context? Embedding-distance to recent signals on same topic. |
| Recency × decay | 0.10 | Fresh signals score higher; decay over time. |
| Source reliability | 0.10 | Sentinel agent's track record on this source. |
| Cross-stream confluence | 0.10 | Bonus if multiple streams independently surface the same event. |

### Threshold for tiers

- Tier 1: materiality ≥ 7.0
- Tier 2: 4.0 ≤ materiality < 7.0
- Tier 3: materiality < 4.0

### Validation

Materiality scoring model evaluated nightly against:
- Historical signals with known outcomes (did this signal actually matter?)
- Analyst overrides (when a user re-tiers a signal, that's training data)
- Decision-correlation (signals that fed Tier 1 Moments that resulted in committed decisions are validated)

Target accuracy at GA: Tier 1 precision ≥ 0.75, Tier 2 ≥ 0.60.

---

## 6. Action: "FRAME AS DECISION" — full spec

Adopted from MarketZero. Tightened into a typed workflow.

### Trigger surface

- Tier 1 signal cards in Bridge / Pulse: button visible
- Tier 2 signal cards: button on hover
- Tier 3 signal cards: button accessible from signal detail view only
- Bridge / Twin nodes: button available on right-click or hover-action

### What it does

Clicking "Frame as Decision" launches a structured **Decision Frame** modal:

```
┌─────────────────────────────────────────────────────────┐
│ FRAME AS DECISION                                  ✕    │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  Triggering signal:                                      │
│  "Lilly SURMOUNT-MMO interim hit CV endpoint"          │
│  [tier 1] [Clinical · Regulatory]                       │
│                                                          │
│  Decision frame:                                         │
│  ┌────────────────────────────────────────────────┐    │
│  │ Question to resolve                             │    │
│  │ [text input — analyst writes the decision Q]   │    │
│  └────────────────────────────────────────────────┘    │
│                                                          │
│  Decision class:                                         │
│  ◯ Pricing       ◯ Indication launch     ◉ Other       │
│  ◯ Trial design  ◯ M&A / partnership                    │
│                                                          │
│  Time horizon:    [< 30 days ▾]                         │
│  EV at stake:     [auto-estimated: $340M ✎]            │
│  Stakeholders:    [+ add team members]                  │
│                                                          │
│  Suggested next steps:                                   │
│  □ Open as Moment (with auto-generated plays)           │
│  □ Open War Room (manual move builder)                  │
│  □ Run KBQ-3 refresh on Lilly                           │
│                                                          │
│              [Cancel]      [Create Frame →]              │
└─────────────────────────────────────────────────────────┘
```

### Output

Creates a new **Decision Frame** object that becomes a first-class artifact:
- Visible in the Decision Ledger as "in-frame" (not yet committed)
- Promoted to a Moment if Strategist agents generate plays
- Convertible to a War Room
- Trackable to outcome

Decision Frames are how analysts seed the system, vs. Moments which are how the system seeds the analyst.

---

## 7. Watchlist — full spec

New first-class surface. Three things a Watchlist binds together:

1. **Filter expression** — categorical, company-based, keyword-based, tier-threshold-based
2. **Subscription preferences** — delivery channel (in-app / email / Slack), cadence (real-time / digest / weekly)
3. **Automation** — optionally trigger KBQ refresh on relevant signals, optionally auto-tag signals into a topic stream

### Surface layout

```
┌─────────────────────────────────────────────────────────┐
│  Watchlists                              [+ New]         │
├─────────────────────────────────────────────────────────┤
│  ▸ Lilly GLP-1 pipeline      8 active  · last hit 2h    │
│  ▸ ESI rebate enforcement   3 active  · last hit 1d    │
│  ▸ CMS NCD developments    12 active  · last hit 4h    │
│  ▸ My internal MSL feed     4 active  · last hit 6h    │
└─────────────────────────────────────────────────────────┘
```

Click any Watchlist to see a pre-filtered Bridge with the matching signals + a header summarizing the filter.

### Watchlist as a contract

A Watchlist also acts as a contract with the system: "I care about this; alert me." This drives:
- Personalized materiality (a signal matching a Watchlist gets a +0.5 materiality bonus for this user)
- Personalized Daily Digest (Digest leads with Watchlist hits)
- Coach learning (Watchlist patterns inform what this user prioritizes)

---

## 8. Decision Ledger — full spec

The append-only commit record, pinned in the header.

### Header pin

```
[≡ nav]  HELIX · MarketZero    [● 11 agents]  [📋 Decisions: 47]  [theme]
```

Click "Decisions" opens a slide-over panel showing:
- Last 5 committed decisions
- 3 most recent outcomes
- Pending: 2 frames awaiting commit
- "Open full ledger →"

### Full ledger view

Table view with columns:

| Decided | Title | Class | EV at stake | Committed by | Outcome | Evidence |
|---------|-------|-------|-------------|--------------|---------|----------|
| 2026-04-12 | "Match ESI floor with carve-out negotiation" | Pricing | $95M | J. Singh | Pending | [chain] |
| 2026-04-08 | "File coalition NCD comment with cardiology societies" | Regulatory | $740M | Committee | In progress | [chain] |
| 2026-03-29 | "Hold semaglutide oral acceleration" | R&D | $180M | M. Chen | Confirmed (Lilly delayed) | [chain] |

Every row is clickable → full decision detail with the original Moment, the plays considered, the play chosen, the signal chain, the outcome update history.

### Immutability

Decisions, once committed, are not editable. Outcomes can be appended (a decision can be amended with new outcome information, but the original commit is preserved). This is the audit trail.

---

## 9. Reviewer surface — full spec

Where the Coach agent surfaces observations to the user.

### Layout

Three sections, top to bottom:

**1. Pattern observations** (this week)
> *"Your last 3 commits in Pricing & Access category were Cautious-tier plays. The Moments offered Balanced or Aggressive options with higher EV. Consider whether risk tolerance calibration warrants attention."*
> [View decisions] [Mark as noted]

**2. Prediction track record** (rolling 30 days)
- Your decisions outperformed alternatives: 7/12 (58%)
- System recommendations you accepted: 9/15 (60% — accuracy 0.78)
- System recommendations you rejected: 6 (jury still out on 4)

**3. Suggested lessons**
- Structured "lesson capture" prompts every Friday — 2 minutes
- Past lessons tagged and surfaced at relevant future Moments

### Tone constraints

The Reviewer is advisory. It uses observational language ("the system noticed," "consider whether"), never directive language ("you should," "you must"). Every observation is dismissible. Every observation cites evidence.

The Coach learning model is per-user, not cross-tenant. Bias patterns from one user do not affect another user's experience.

---

## 10. Connectors — surfaced

MarketZero's footer link "Connectors → ENTERPRISE" makes connector management visible. Helix had this only in the engineering brief. Adopting MarketZero's choice to surface it.

### Connectors view (accessed from footer)

Two columns:

| Public sources | Status | Last sync | Tenant scope |
|----------------|--------|-----------|--------------|
| ClinicalTrials.gov | ● Live | 4 min ago | Default |
| PubMed | ● Live | 12 min ago | Default |
| FDA DailyMed | ● Live | 1 hour ago | Default |
| EMA | ● Live | 2 hours ago | Default |
| CMS ASP / NADAC | ● Live | Daily | Default |
| FDA Orange Book | ● Live | Daily | Default |
| Company SEC filings | ● Live | 30 min ago | Configurable |
| Press release feeds | ● Partial | 15 min ago | Configurable |

| Paid sources | Status | Contract | Setup |
|--------------|--------|----------|-------|
| Citeline / Trialtrove | ◯ Stub | Required | [Configure] |
| Evaluate Pharma | ◯ Stub | Required | [Configure] |
| AlphaSense | ◯ Stub | Required | [Configure] |
| MMIT / Fingertip | ◯ Stub | Required | [Configure] |
| Navelin | ◯ Stub | Required | [Configure] |
| IQVIA | ◯ Stub | Required | [Configure] |

### Internal sources

| Internal | Status | Volume | Configure |
|----------|--------|--------|-----------|
| Knowledge Library uploads | ● Live | 47 docs | [Manage] |
| Salesforce CRM | ◯ Available | — | [Connect] |
| SharePoint | ◯ Available | — | [Connect] |
| Slack channels | ◯ Available | — | [Connect] |
| Veeva | ◯ Available | — | [Connect] |
| Internal forecast API | ◯ Available | — | [Connect] |

---

## 11. Brand and product identity

### Name

**MarketZero · Helix**

Long form: "MarketZero · Helix — Pharma Decision Intelligence"

Short form: "Helix" acceptable in internal documentation. "MarketZero" acceptable in commercial contexts. The full form is used on logo, login screen, and external collateral.

### Visual identity

- Typography: Instrument Serif (editorial) + Inter (UI) + JetBrains Mono (numeric) — Helix system retained
- Color: Helix palette retained (restrained, accent-reserved)
- Themes: Dark / Hybrid / Light — Helix system retained
- Logo: TBD — should evoke both market-sensing (concentric / radial form) and intelligence helix (twisted / paired form)

### Tagline candidates

1. "The state of your market, continuously."
2. "Decisions, framed."
3. "Sense. Model. Decide."

(Decision deferred to brand workshop.)

---

## 12. What gets cut, what stays — quick reference

### Cut from MarketZero (or substantively repositioned)

- Standalone "Sensing Feed" surface → folded into Bridge / Pulse
- Standalone "Daily Digest" surface → folded into Bridge as view mode
- Standalone "Signals DB" surface → folded into Bridge as drilldown
- Standalone "Decisions" surface → repositioned as pinned ledger
- Standalone "Insights" surface → folded into Replay
- "Cockpit" subtitle → dropped (Bridge metaphor wins)
- "Materiality 1%" displays → fixed (see §5)

### Cut from Helix

- "Pulse" as a top-level surface name → kept as a zone name within Bridge
- Stream-based primary taxonomy → demoted to secondary tag
- Impact score 1–10 displayed as such → relabeled "materiality" with tier classification
- "Empty state with no information" anti-pattern (was already noted in brief)

### New things, not in either product

- Decision Frame as a typed object (formalization of MZ's FRAME AS DECISION)
- Tier-gated visibility of action verbs (prevents decision fatigue)
- Per-user materiality calibration via Watchlists
- Connector management surface (was only in engineering brief)

---

## 13. Open questions for the build team

These are not resolved by this mapping and need product decisions.

1. **Decision Frame vs. Moment** — both are "decisions in flight." Are they the same object with different origins (user-framed vs. system-generated) or two distinct objects? The cleaner model is one object with a `provenance` field; the more flexible model is two. Decide before data model is finalized.

2. **Watchlist → Materiality bonus magnitude** — the +0.5 bonus suggested in §5 is a guess. Needs A/B testing in design partners. Could be 0.3, could be 1.0.

3. **Daily Digest delivery channels** — email and Slack are obvious. What about Teams? Mobile push? Voice brief (read-aloud)? Scope for v1.

4. **Reviewer scope** — Coach observations per individual, per team, or per tenant? Probably per individual with team-level aggregation as a separate view. Confirm.

5. **War Room session sharing** — can two users be in the same War Room concurrently (multiplayer) or sequentially (handoff)? Multiplayer is more powerful but harder. Defer to Phase 2.

6. **Decision Ledger export format** — JSON is obvious. PDF report for audit? CSV for analysis? Verifiable signature for 21 CFR Part 11 compliance? Confirm regulatory needs.

---

*End of mapping document. The prototype artifact and revised engineering brief implement these decisions.*

# MarketZero · Helix
## Engineering Brief — v0.2 (Unified Product)

**Status:** Pre-PRD. Supersedes the original Helix v0.1 brief.
**Audience:** Product, design, engineering, ML, and data partnership leads.
**Anchored against:** the surface mapping document and the unified prototype.

---

## 0. TL;DR

MarketZero · Helix is a continuously-running decision intelligence platform for pharmaceutical competitive intelligence and strategy teams. It merges MarketZero's analyst-facing IA and signal-handling workflow with Helix's intelligence depth (digital twin, KBQ Profiles, game-theoretic war gaming, AI Moments).

The unified product preserves Helix's architectural backbone — two clocks (continuous Flywheel + on-demand KBQ chain), evidence-linked state, cinematic moments — while adopting MarketZero's vocabulary and tactical UX patterns (FRAME AS DECISION verb, impact category taxonomy, tier classification, Watchlists, Daily Digest, Reviewer surface).

This is not a dashboard. It is the operating system for pharma strategy.

---

## 1. Why merge

Both products are solving the same problem from different angles. Combining preserves the strengths of each:

**MarketZero brings:** the verb (FRAME AS DECISION), the taxonomy (10 impact categories), the tier system (1/2/3), the analyst workflow (Sensing → Watchlist → War Room → Decision → Insight → Reviewer), the surfacing of agent personas, the connector management surface.

**Helix brings:** the architecture (two-clock Flywheel + KBQ), the digital twin (probabilistic posterior state), the KBQ chain (eight structured workflows), the cinematic Moment, the game theory module (Nash + Stackelberg), the Replay belief curves, the autonomy-graduating agent model.

Neither alone is sufficient. MarketZero without Helix is a fast inbox. Helix without MarketZero is a vision document. Together they ship a product real CI teams will adopt.

---

## 2. Philosophy

Seven principles. The original six from Helix v0.1 plus one new principle that emerged from the merge.

### 2.1 Calm by default, cinematic when it matters
Main view near-empty most of the time. Three numbers, one sentence. System earns the right to interrupt by demonstrating leverage.

### 2.2 State, not documents
Canonical artifact is the versioned, evidence-linked state. Decks render on demand.

### 2.3 Evidence-linked or it didn't happen
Every claim traces back through synthesis agent → signals → source documents. No black box.

### 2.4 Humans decide, agents prepare
Agents do sensing, synthesis, dossier-building, simulation, option-generation. Human picks among comparable options. Autonomy graduates with track record.

### 2.5 Structure beats freedom
Free-text agent interactions are seductive demos and terrible products. Structured moves, typed schemas, fixed enums, bounded scoring. Reproducible.

### 2.6 Two clocks, one platform
Continuous time (Flywheel) and discrete time (Moment). Both, always.

### 2.7 The verb matters
**NEW.** Adopted from MarketZero's FRAME AS DECISION. The product's value is in the *transitions* between observation and action. Every transition needs an explicit verb the user can grasp and the system can log. The verbs:

- **SENSE** (sentinel agents → signals)
- **FRAME** (signal → decision frame; user-initiated)
- **SURFACE** (synthesizer → moment; system-initiated)
- **PLAY** (strategist → option generation)
- **SIMULATE** (war room → reaction analysis)
- **COMMIT** (human → decision ledger)
- **REVIEW** (coach → pattern observation)
- **RECALIBRATE** (coach → model update)

Every interaction in the product is expressible as one of these verbs. If a feature doesn't map to a verb, it doesn't belong.

---

## 3. Architecture

### 3.1 The two-layer system

```
                    ┌────────────────────────────────────┐
                    │           FLYWHEEL                  │
                    │  (continuous, agent-driven)        │
                    │                                     │
                    │  SENSE → SURFACE → SIMULATE        │
                    │     ↑                  ↓           │
                    │     │     COMMIT       │           │
                    │     └──── RECALIBRATE ─┘           │
                    └─────────────┬──────────────────────┘
                                  │ trigger
                                  ▼
                    ┌────────────────────────────────────┐
                    │           KBQ CHAIN                 │
                    │  (on-demand, structured workflows) │
                    │                                     │
                    │  1 → 2 → 3 → 4 → 5 → 6 → 7,8       │
                    └─────────────┬──────────────────────┘
                                  │ outputs ground
                                  ▼
                          [back to Flywheel]
```

### 3.2 Surfaces (final IA)

Six primary navigation items plus two oversight items plus a pinned ledger. See the mapping document for full rationale; this is the canonical list.

**Primary (workflow):**
1. **Bridge** — home. Pulse + Twin + Moments. Mode toggle: Live / Today's Digest / This Week.
2. **Watchlist** — saved filters as first-class objects.
3. **KBQ Workspace** — eight-station structured intelligence pipeline.
4. **War Game** — three modes (Manual / Auto-Simulate / Game-Theoretic). Sessions called War Rooms.
5. **Knowledge** — internal document library, indexed and citable.
6. **Replay** — twin belief history + outcome learning.

**Oversight:**
7. **Reviewer** — Coach agent observations.
8. **Agents** — roster with autonomy, accuracy.

**Pinned in header:**
- **Decision Ledger** — slide-over panel showing recent commits + jump to full ledger.

**Footer accessible:**
- **Connectors** — data source registry.

### 3.3 Object model

Every entity in the platform is one of these types. Names final.

| Object | Purpose | Origin | Lifecycle |
|--------|---------|--------|-----------|
| **Signal** | Atomic unit of intelligence. One event from one source. | Sentinel agent | Materialized, scored, retained 18mo |
| **Watchlist** | Saved filter + subscription | User-created | Persistent until deleted |
| **KBQ Profile** | Versioned, evidence-linked product/competitor dossier | KBQ chain | Persistent, versioned |
| **KBQ Output** | Specific output of one KBQ run | KBQ worker | Immutable, addressable |
| **Decision Frame** | Pre-commit decision shell | User (FRAME AS DECISION) | Mutable until committed |
| **Moment** | System-surfaced decision opportunity | Synthesizer + Strategist | Resolved by Commit / Defer / Expire |
| **Play** | Typed strategic option | Strategist persona | Tied to Moment or Frame |
| **War Room** | War game session | User / Moment trigger | Active or archived |
| **Move** | Player move within War Room | User | Logged |
| **Reaction** | Competitor response to Move | Strategist agent | Logged |
| **Commit** | Decision Ledger entry | User commit action | Immutable, append-only |
| **Outcome** | Result of a committed decision | Coach + signals | Appended over time |
| **Twin Snapshot** | Versioned state of the digital twin | Twin agent | Retained for Replay |
| **Coach Observation** | Pattern flagged by Coach agent | Coach agent | Persistent, dismissible |

### 3.4 The Decision Frame ↔ Moment distinction

Two paths into a decision; both produce a Commit.

- **User-framed:** analyst sees a signal, clicks FRAME AS DECISION, fills the modal, creates a Decision Frame. Strategist agents may then generate plays for the frame, escalating it to a Moment-equivalent.
- **System-surfaced:** synthesizer detects posterior shift × EV-at-stake × time-decay above threshold; auto-generates a Moment with plays.

Both converge into the same downstream flow: review plays → optionally Run War Room → Commit or Defer.

Open question: should these be one object with `provenance: "user-framed" | "system-surfaced"` or two distinct objects? Recommendation: one object with provenance field. Simpler data model, cleaner queries, same UX.

---

## 4. Experience design

### 4.1 Visual language

- **Typography:** *Instrument Serif* (editorial titles), *Inter* (UI), *JetBrains Mono* (numbers, IDs, technical labels)
- **Themes:** Dark (default), Hybrid (dark Bridge + light Moments), Light. Toggleable globally.
- **Color discipline:** restrained. Each company has a fixed color. Each impact category has a fixed color. Status colors limited to ok/warn/danger/neutral.
- **Motion:** minimal. Pulses for live state. Fade-up for new content. Slide-right for slide-overs. No decorative animation.
- **Density:** Sidebar always-visible (220px). Bridge medium density. Moments spacious. KBQ Workspace dense. Agents tabular.

### 4.2 The Bridge — definitive layout

Top: mode toggle (Live / Today's Digest / This Week) + status hint.

Hero strip: most-urgent moment with title, EV at stake, "Open Moment" button.

Three zones:

- **Pulse (left, ~1fr)** — Sensing feed. Category filter chips at top (10 impact categories + All). Signal cards sorted by materiality. Each card shows materiality dial (0-10 scaled to 0-100% visual), category tag, tier badge, source stream, company, title, source ID, FRAME AS DECISION button (tier-gated).
- **Twin (center, ~1.4fr)** — Living network. Your assets, rival assets, patients, payers, regulators. Edges weighted, future-flows ghost-dashed, pulsing on active state changes. Hover for detail.
- **Moments (right, ~1fr)** — Stacked moment cards ranked by EV × time-decay. Category tag, EV at stake, belief delta bar, three play indicators (color-coded by kind), expiry countdown.

### 4.3 The Moment view — cinematic

Triggered from clicking a Moment card. Full-screen overlay.

Hybrid theme: dark Bridge stays behind; Moment renders in light editorial register.

Layout:
- Top bar: back button + Moment ID + expiry countdown
- Title block: large serif title, two-line summary
- Left column: three Play cards (Aggressive / Balanced / Cautious), selected one drives Monte Carlo outcome distribution chart below
- Right column: signal chain (each signal that fed the moment, with source attribution) + belief shift visualization (prior → posterior with bar)
- Bottom: three actions — Open as War Room / Defer / Commit Decision

### 4.4 FRAME AS DECISION — interaction spec

Trigger: button on signal cards (tier 1: always visible; tier 2: on hover; tier 3: in detail view only). Also accessible from Twin node right-click.

Modal contains:
- Source signal echo (read-only)
- Question textarea (analyst writes the decision question)
- Decision class dropdown (Pricing, Indication, Trial, M&A, Other)
- Time horizon dropdown (<7d, <30d, <90d, <1y)
- EV-at-stake auto-estimated (editable)
- Suggested next steps checkboxes (Open as Moment, Open War Room, Trigger KBQ refresh)
- Cancel / Create Frame buttons

Output: new Decision Frame appears in Decision Ledger as "in-frame" status.

### 4.5 Watchlist — first-class surface

Top: "+ New Watchlist" button.

List: each Watchlist shows name, filter expression, active signal count, last-hit timestamp.

Clicking a Watchlist opens a pre-filtered Bridge with the matching signals.

A Watchlist binds three things: filter expression, subscription preferences (channel/cadence), automation (KBQ triggers).

Personalized materiality bonus: signals matching a Watchlist get +0.5 materiality for this user. Magnitude tunable; A/B test in Phase 2.

### 4.6 Decision Ledger — pinned slide-over

Header pin: "◆ Decisions · 47"

Click opens slide-over (480px wide, right-anchored):
- Stats row: total commits, pending frames, outcomes tracked
- Recent decisions list (last 5 visible)
- "Open full ledger →" link

Full ledger: table view, columns = date, title, class, EV at stake, committed-by, outcome, evidence chain.

Decisions immutable once committed. Outcomes append over time.

### 4.7 Reviewer surface

Top stats: decisions this quarter, outperformed-system rate, coach observations count.

Body: list of Coach observations. Each card: kind tag (PATTERN / TRACK-RECORD / LESSON), week, observation text, action buttons (View decisions / Mark as noted / Dismiss).

Tone constraint enforced in prompts: observational language, never directive.

### 4.8 Connectors — accessible from footer

Two columns: Public (live status, last sync) and Paid (stub status, configure button).

Internal sources section: Knowledge Library, Salesforce, SharePoint, Slack, Veeva, internal forecast APIs.

---

## 5. Key features (build-ready)

### 5.1 Sensing
- 8 sentinel agent classes (Trials, Regulatory, Publications, Payer, KOL, Financial, Patent, Internal)
- Materiality scoring with 6 weighted inputs (see §6)
- Tier classification (1/2/3) with threshold tuning per tenant
- Impact category taxonomy (10 categories) as primary user-facing classification
- Source stream taxonomy (8 streams) as secondary tag

### 5.2 Watchlist
- Filter expression builder (category × company × tier × keyword × stream)
- Subscription preferences (in-app / email / Slack; real-time / digest)
- Automation hooks (trigger KBQ refresh, push to channel)
- Materiality calibration (matched signals get bonus)

### 5.3 Decision Frame
- FRAME AS DECISION modal from signals and Twin nodes
- Typed fields with auto-estimated EV
- Frames listed in Decision Ledger as "in-frame"
- Promotable to Moment with strategist-generated plays

### 5.4 Digital Twin
- Graph schema with probabilistic state per node
- Bayesian updates on signal arrival
- Twin Snapshots versioned for Replay
- Network visualization in Bridge center zone

### 5.5 Moments
- Synthesizer-triggered moment generation
- Three Strategist personas generating three plays
- Monte Carlo outcome distribution per play
- Signal chain provenance
- Belief shift visualization
- Cinematic single-decision view

### 5.6 KBQ Workspace
- All 8 KBQs as first-class workflow entities
- Pipeline visualization with dependency graph
- Per-product KBQ Profiles with versioned outputs
- Decision gates surfaced at KBQ-1, KBQ-3, KBQ-7
- Source registry with public/paid tagging

### 5.7 War Game
- Three modes: Manual / Auto-Simulate / Game-Theoretic
- Manual: structured move builder, deterministic competitor reactions
- Auto-Simulate: N-round autonomous play with policy
- Game-Theoretic: Nash (pure-strategy on payoff matrix) + Stackelberg (game tree with backward induction)
- Sessions called War Rooms; listable, replayable

### 5.8 Knowledge Library
- Drag-drop upload (PDF, DOCX, PPTX, XLSX, CSV, TXT)
- Auto-indexing pipeline (entity extraction, embeddings, tag inference)
- Internal-source citation (INTERNAL:doc-id) across platform
- Knowledge surfaces as internal-stream signals in Pulse

### 5.9 Decision Ledger
- Append-only commit record
- Pinned slide-over in header
- Full ledger view with filtering and export
- Outcome tracking for committed decisions
- 21 CFR Part 11 alignment for audit trail

### 5.10 Replay
- Twin belief curves with scrubber
- Signal / moment / decision markers on timeline
- Per-week context cards (twin state, event, learning)
- Outcome correlation visible per decision

### 5.11 Reviewer
- Coach agent observations surfaced as cards
- Pattern detection (recent decision patterns)
- Track record (rolling accuracy)
- Lesson capture prompts
- Per-user, never cross-tenant

### 5.12 Agents
- Roster view with role, status, accuracy, autonomy
- Autonomy graduation (1-5 ladder) based on track record
- Per-agent activity log
- Promotion/demotion controls

### 5.13 Connectors
- Source registry with public/paid tier
- Per-tenant credential management for paid sources
- Health monitoring and sync status
- Configurable poll cadences

### 5.14 Platform
- Three themes (Dark / Hybrid / Light)
- Multi-tenant with row-level security
- Audit log for every agent and human action
- Tenant data isolation
- Export (JSON / CSV / PDF) for any artifact

---

## 6. Materiality scoring — the fix

The original MarketZero screenshots showed signals scoring at 1% materiality across the board. Unified product cannot ship with this. Specification:

### Formula

```
materiality = 
  0.30 × strategic_relevance     (LLM classifier vs tenant priorities)
  + 0.25 × posterior_shift       (twin belief delta magnitude)
  + 0.15 × novelty               (embedding distance to recent signals)
  + 0.10 × recency_decay         (fresh > old)
  + 0.10 × source_reliability    (sentinel track record)
  + 0.10 × cross_stream_confluence (bonus for multi-stream confirmation)

  + Watchlist match bonus (per-user, additive +0.5 cap)
```

Output: 0.0 to 10.0. Displayed in UI as both raw number (in dial) and tier (1/2/3).

### Tier thresholds

- Tier 1: materiality ≥ 7.0 (decision-grade)
- Tier 2: 4.0 ≤ materiality < 7.0 (noteworthy)
- Tier 3: materiality < 4.0 (monitoring)

### Validation

Nightly eval against:
- Historical signals with known outcomes
- Analyst overrides (re-tier actions are training data)
- Decision correlation (signals feeding Tier 1 Moments that resulted in commits validate as correctly-tiered)

Target at GA: Tier 1 precision ≥ 0.75, Tier 2 ≥ 0.60.

---

## 7. Build instructions

### 7.1 Stack

- **Frontend:** Next.js 14+ (App Router), React 18, TypeScript strict, Tailwind, tRPC, TanStack Query, Framer Motion (sparingly), Recharts / visx, D3 for Twin graph, react-pdf
- **Backend:** Node.js (TypeScript) for API; Python workers for ML and scoring
- **LLM gateway:** Anthropic primary, multi-provider routing supported
- **Data:** Postgres (state, RLS), S3 (raw docs, exports), Qdrant (vector DB), Redis (cache, rate limits, queues), Redpanda or Kafka (event log)
- **Infra:** Kubernetes, Terraform, GitHub Actions, OpenTelemetry

### 7.2 Frontend principles

- Sidebar always-visible (220px). Collapsible only at < 768px breakpoint.
- Header sticky, low-density. Three things only: agent status, Decision Ledger pin, theme toggle.
- Every surface follows the same pattern: sub-title (caps, letter-spaced), serif title, dim description paragraph, then content.
- Bridge mode toggle in body (not header) so it stays contextual to the surface.
- Theme tokens via CSS variables; Hybrid mode overrides token set within Moment route layout.
- No scrolljacking. No skeleton screens unless data takes > 800ms. Pulse-soft loading state instead.
- Maintain prototype fidelity. Prototype is the design source of truth; deviations require design review.

Performance budgets:
- Bridge initial paint: < 1.5s on broadband
- Moment view open: < 300ms after click
- Twin graph: 60fps with up to 80 nodes / 200 edges
- KBQ pipeline render: client-side, no API call

### 7.3 KBQ workflow engine

Each KBQ is a typed workflow:

```typescript
interface KBQ {
  id: number;
  code: string;                          // "KBQ-1"
  question: string;
  inputSchema: ZodSchema;
  outputSchema: ZodSchema;
  dependencies: number[];                // KBQ IDs upstream
  steps: KBQStep[];
  decisionGates: KBQGate[];
  sources: SourceRef[];
  freshness: FreshnessPolicy;
  paidDependent: boolean;
}

interface KBQStep {
  id: string;
  description: string;
  agentClass: string;
  sourceRefs: string[];
  promptTemplate: string;                // versioned, hashed
  outputKey: string;
  retryPolicy: RetryPolicy;
}

interface KBQGate {
  afterStep: string;
  question: string;
  evaluator: (state: KBQState) => "yes" | "no" | "needs-human";
  yesBranch: "proceed" | "skip-to-output";
  noBranch: "loop-back" | "request-additional-sources";
}
```

KBQ runs: idempotent, cached by `(productId, kbqId, sourceVersionHash)`. Outputs immutable; re-runs create new versions.

### 7.4 Agent runtime

LLM gateway is single chokepoint:
- Provider routing
- Per-tenant per-agent token accounting
- Prompt versioning (hashed; outputs reference hash)
- Schema validation (Zod)
- Retry with backoff
- Hard timeouts

Tool registry:
- Sentinels: read-only (search, fetch, parse)
- Synthesizers: read + classify
- Twin: read + bayesian update
- Strategists: read + game theory solvers + Monte Carlo
- Executors: write, gated by autonomy and approval workflow
- Coach: read decision history + emit observations

Memory: stateless agents by default. Persistent state in data layer. Multi-turn conversations via short-lived Redis sessions.

Sandboxing: game theory and Monte Carlo run in isolated workers with limits.

### 7.5 Digital twin

Schema: graph + probabilistic state per node.

```typescript
interface TwinNode {
  id: string;
  type: "asset" | "segment" | "payer" | "regulator" | "kol";
  ownerCompanyId?: string;
  attributes: Record<string, any>;
  beliefs: Record<string, Distribution>;
  lastUpdated: ISO8601;
  confidence: number;
}

type Distribution =
  | { kind: "beta"; alpha: number; beta: number }
  | { kind: "gaussian"; mu: number; sigma: number }
  | { kind: "categorical"; probs: Record<string, number> }
  | { kind: "point"; value: any };
```

Bayesian update on signal arrival. Deterministic given same signal + prior. Reproducibility critical.

Visualization: D3 force-directed with pinned anchor groups. Real-time updates animate via D3 transitions.

### 7.6 Moment generation

Synthesizer runs every 15 min + on-demand after high-impact signal:

```
moment_score = posterior_shift × ev_at_stake × time_urgency × novelty
```

Above threshold (tunable per tenant), draft Moment with title, summary, signal chain, belief delta, three plays from Strategist personas.

Plays = typed objects, never free-form prose.

Outcome distribution: Monte Carlo 10,000 runs, client-side or worker-based.

Commit writes to Decision Ledger (immutable Postgres). Triggers downstream Executor actions per play's execution kind.

### 7.7 Game theory module

Nash solver (pure-strategy, discrete 2-player payoff matrix): O(n²m), client-side. Mixed-strategy: Python worker, scipy.optimize or nashpy.

Stackelberg: backward induction. Pure logic, client-side.

Payoff derivation: from twin posterior. Hand-tuned for demo scenarios; twin-derived for v2. **This is the hard work.** Most of the engineering effort in game theory is constructing the payoff matrix, not solving it.

Bayesian games and continuous-strategy Nash: deferred to v2.

### 7.8 Knowledge ingestion

Upload pipeline:
1. Client → S3 (presigned URL)
2. Ingest worker pulls
3. Document parser (Unstructured.io or custom)
4. Entity extraction (LLM with schema)
5. Chunk + embed (configurable embedding model)
6. Store: entities → Postgres, embeddings → Qdrant, raw → S3
7. Tag inference (LLM classifier)
8. Surface as Internal-stream signals if time-bound

Target indexing latency: < 90s for docs up to 50 pages.

Citation: INTERNAL:doc-{uuid}, matches public source citation format.

### 7.9 Connectors

Common interface:

```typescript
interface Connector {
  id: string;
  tier: "public" | "paid";
  poll(): Promise<RawSignal[]>;
  fetch(query: Query): Promise<RawDocument[]>;
  parse(raw: RawDocument): Promise<ParsedEntity[]>;
  health(): Promise<ConnectorHealth>;
}
```

Public MVP connectors: ClinicalTrials.gov, EU CTR, PubMed, FDA DailyMed, Orange Book, Purple Book, EMA, CMS ASP/NADAC, SEC EDGAR, NICE/IQWiG/HAS.

Paid (v2): Citeline, Evaluate Pharma, AlphaSense, IQVIA, iSpot, MMIT, Navelin, SSR Health.

### 7.10 Data model

```
Tenants ──┬── Users
          ├── KBQProfiles ──┬── KBQOutputs (versioned, immutable)
          │                 └── Sources
          ├── Watchlists
          ├── TwinSnapshots
          ├── Signals
          ├── DecisionFrames ──── (promoted to Moments)
          ├── Moments ──── Plays
          ├── Commits (append-only Decision Ledger)
          ├── Outcomes (append-only per Commit)
          ├── WarRooms ──── Moves ──── Reactions
          ├── KnowledgeDocs ──── Chunks ──── Embeddings
          ├── CoachObservations
          └── AgentRuns ──── AgentEvents
```

Every row: tenantId, createdBy, createdAt, version, evidenceLinks[]. Row-level security via Postgres RLS.

### 7.11 Observability

Log every: agent call, tool invocation, KBQ run, twin update, moment generation, human action.

Dashboards: Grafana. Tracing: OpenTelemetry. Cost: per-tenant billing pipeline.

Agent accuracy: computed from prediction vs outcome where observable, surfaced in Agents view.

### 7.12 Testing

- Unit tests for pure functions (Nash, Stackelberg, materiality scoring, Bayesian update math)
- Integration tests for KBQ workflows (golden inputs → expected outputs)
- Agent eval suite (curated historical scenarios, nightly run)
- Replay tests (record a week of signals, replay in CI to detect regressions)
- No mocking of LLM calls in eval

---

## 8. Security, compliance, regulatory

### 8.1 Data residency and isolation

Multi-tenant by default with RLS. Single-tenant VPC available on request. US and EU residency at GA; other regions on request.

### 8.2 Compliance posture

- SOC 2 Type II within 12 months of GA
- HIPAA-compliant opt-in (BAA, encrypted at rest, audit log)
- 21 CFR Part 11 alignment for Decision Ledger (immutable, hash-chained)
- GxP-friendly design for adjacent use cases

### 8.3 Data handling

- Customer data never used to train shared models
- Per-tenant fine-tuning on isolated infra
- LLM and connector API calls routed through tenant-aware gateways
- Retention configurable per data class (default: signals 18mo, KBQ outputs indefinite, decisions indefinite)

### 8.4 Audit and explainability

- Provenance to source documents for every artifact
- Decision Ledger append-only, hash-chained
- Executor actions logged and reversible within configurable window
- Customer-on-demand audit log export

### 8.5 Human-AI accountability

- AI-generated artifacts labeled as such
- No autonomous Executor action without human-readable rationale and reversibility commitment
- Coach observations advisory, never authoritative

---

## 9. Phasing

### Phase 1 — Foundation (months 1-6)

Goal: functional MVP for one design partner.

**Scope:**
- Single-tenant deployment
- 3 sentinel classes live (Trials, Publications, Internal)
- KBQ-1, KBQ-2, KBQ-3 functional
- Knowledge Library upload + indexing
- Bridge with Pulse + simplified Twin
- Moments with manual review
- Watchlists v1 (filter expression, in-app only)
- War Game manual mode only
- Decision Ledger v1
- Hybrid theme

**Acceptance:** design partner CI team uses MarketZero · Helix for quarterly competitive review; reports replacing 40%+ of current workflow.

### Phase 2 — Flywheel (months 6-12)

Goal: continuous operation, multi-tenant, full IA.

**Scope:**
- All 8 sentinel classes live
- All 8 KBQs functional (paid sources still stubbed)
- Twin with full Bayesian update
- War Game Auto-Simulate mode
- Game-Theoretic mode with Nash (discrete) + Stackelberg
- Replay with belief curves
- Reviewer surface with Coach
- Agents view with autonomy controls
- Watchlists v2 (subscriptions, automation hooks)
- Multi-tenant, SOC 2 Type I

**Acceptance:** three design partners running continuously; ≥ 4 moments/week/tenant; commit-rate ≥ 30%.

### Phase 3 — Intelligence (months 12-18)

Goal: game theory, autonomy, learning, paid sources.

**Scope:**
- Twin-derived payoff matrices
- Mixed-strategy Nash + Bayesian games
- Stackelberg with continuous strategies (LP solver)
- Executor autonomy graduation
- Coach with decision-pattern feedback into Reviewer
- SOC 2 Type II, HIPAA for opt-in
- Paid source integrations live (contracts permitting)

**Acceptance:** at least one tenant grants Executor autonomy level 4 on ≥ 3 action types; human time saved per decision > 60% vs Phase 1 baseline.

---

## 10. Open questions

1. **Decision Frame vs Moment object model.** One object with provenance field, or two? Recommendation: one.
2. **Watchlist materiality bonus magnitude.** +0.5 is a guess. A/B test.
3. **Daily Digest delivery channels.** Email + Slack obvious. Teams, mobile push, voice brief? Scope.
4. **Reviewer scope.** Per-individual confirmed. Team-aggregation view in Phase 2?
5. **War Room multiplayer.** Concurrent users in one War Room, or sequential handoff? Defer to Phase 2.
6. **Decision Ledger export.** JSON, CSV, PDF audit report, signed for Part 11? Confirm regulatory needs.
7. **Materiality model.** Hand-tuned weights in Phase 1; learn weights per-tenant in Phase 2. How?
8. **Connector contracts.** Paid source terms vary; legal review per source before integration.
9. **Pricing model.** Per-seat is industry-standard but product value is in decisions. Hybrid?
10. **Internationalization.** GLP-1 is global. Twin needs per-geography state. Defer to Phase 3.

---

## 11. Definition of Done (v1 GA)

Ship when all true:

- CI analyst can stand up a new product profile and run full KBQ chain in < 10 min
- Bridge surfaces moments without false-positive noise above 1/analyst/day
- Every artifact has working provenance — click any number, get to the source
- All three War Game modes demoable on real scenarios
- Decision Ledger queryable, exportable, hash-chain verifiable
- Multi-tenant deployment with RLS passes external penetration test
- FRAME AS DECISION is the most-used action in the platform after WATCH (proving the verb landed)
- Materiality scoring evaluated at Tier 1 precision ≥ 0.75
- Documentation supports new dev shipping a KBQ workflow in their first sprint

When those are all true, ship.

---

## Appendix A — Glossary

| Term | Definition |
|------|------------|
| **Bridge** | Home surface. Pulse + Twin + Moments. |
| **Pulse** | Live sensing-feed zone within Bridge. |
| **Twin** | Digital twin of the market. Graph + probabilistic state per node. |
| **Moment** | System-surfaced bounded decision. Carries title, summary, plays, EV-at-stake, expiry. |
| **Decision Frame** | User-initiated decision shell. Created via FRAME AS DECISION. |
| **Commit** | Immutable record in Decision Ledger. |
| **War Room** | One war-game session. |
| **War Game** | The platform surface containing modes (Manual/Auto/Game-Theory) and active War Rooms. |
| **KBQ** | Key Business Question. One of eight structured analyses. |
| **KBQ Profile** | Versioned, evidence-linked dossier per product. |
| **Watchlist** | Saved filter + subscription + automation hooks. |
| **Materiality** | Signal score 0–10. Drives tier classification. |
| **Tier** | 1 (decision-grade) / 2 (noteworthy) / 3 (monitoring). |
| **Sentinel** | Always-on agent class watching one source. |
| **Synthesizer** | Agent class doing cross-stream causal fusion. |
| **Strategist** | Agent class generating plays. Three personas. |
| **Coach** | Agent class watching human decision patterns. |
| **Executor** | Agent class executing low-stakes approved actions. |
| **Play** | Typed strategic option proposed by Strategist. |
| **Posterior shift** | Magnitude of Twin belief update after signal. |
| **Evidence-linked** | Property: every claim traces to source. |
| **Frame as Decision** | The verb that promotes a signal into a Decision Frame. |

---

*End of brief. The mapping document specifies surface-level decisions; the prototype implements them; this brief gives engineering the spine.*