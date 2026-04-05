# SPEC-003: Proactive Intelligence — Event-Driven Impact Analysis

> **Status**: Draft
> **Priority**: P1
> **Dependencies**: InsightEngine, ScenarioEngine, scheduler pipeline, SPEC-002 (workspace UX)
> **Date**: 2026-03-28

---

## Problem Statement

Market Zero is **reactive by design**: users must ask questions to receive intelligence. The system has the building blocks for proactive behaviour — InsightEngine detects safety signals, pipeline milestones, and competitive shifts; ScenarioEngine runs deterministic what-if simulations — but these capabilities are disconnected and invisible to users. No external market events flow in, no auto-simulation triggers exist, and no notification surface presents time-sensitive intelligence without being asked.

The result: a user logging in on Monday morning has no idea that over the weekend (a) a Phase 3 trial for a competitor drug was halted by FDA, (b) a new entrant filed an IND in their therapeutic area, or (c) a safety signal crossed the PRR > 5.0 critical threshold. They would need to know exactly which questions to ask.

---

## Solution: Event-Driven Proactive Intelligence Loop

### Core Loop

```
┌────────────────────────────────────────────────────────────────────┐
│  STAGE 1: Event Detection (continuous, multi-source)               │
│                                                                    │
│  Authoritative APIs ──┐                                            │
│  Press releases ──────┤──► EventCollector ──► market_events table  │
│  News feeds ──────────┤    (classify, dedupe, trust-score)         │
│  State-change diffs ──┘                                            │
│                                                                    │
│  Quality gate: trust_score ≥ threshold per tier                    │
└────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────────────┐
│  STAGE 2: Impact Routing (per-event, deterministic)                │
│                                                                    │
│  market_events ──► ImpactRouter                                    │
│                     │                                              │
│                     ├─► Entity graph traversal (who is affected?)  │
│                     ├─► Scenario auto-simulation (what changes?)   │
│                     └─► Insight generation (so what?)              │
│                                                                    │
│  Output: ImpactAssessment (affected entities, simulations, brief)  │
│  Quality gate: at least 1 affected entity resolved in graph        │
└────────────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌────────────────────────────────────────────────────────────────────┐
│  STAGE 3: Intelligence Delivery (push to user)                     │
│                                                                    │
│  ImpactAssessment ──► IntelligenceFeed                             │
│                        │                                           │
│                        ├─► Workspace feed panel (new tab)          │
│                        ├─► Notification badges + bell              │
│                        ├─► Chat proactive injection                │
│                        └─► Email digest (optional, future)         │
│                                                                    │
│  Quality gate: user can dismiss, snooze, or drill into any item    │
└────────────────────────────────────────────────────────────────────┘
```

---

## Stage 1: Event Detection

### 1.1 Event Taxonomy

Events are classified into a controlled taxonomy that maps directly to entity types and scenario operations already in the system.

| Category | Sub-type | Example | Auto-simulation |
|----------|----------|---------|-----------------|
| **Regulatory** | approval | FDA approves new drug X | `landscape_single_mechanism` |
| | rejection | CRL issued for drug Y | `pipeline_without_entity` |
| | clinical_hold | Phase 2 trial suspended | `pipeline_excluding_inactive` |
| | label_change | Black box warning added | Safety signal escalation |
| **Clinical** | phase_advance | Drug Z enters Phase 3 | `drug_pipeline_strength` |
| | trial_halt | Interim futility stop | `pipeline_without_entity` |
| | primary_endpoint | Met/missed primary EP | `competitive_landscape` update |
| | enrollment_complete | Recruitment closed | Milestone tracking |
| **Commercial** | launch | Drug X launched in EU | `competitive_landscape` |
| | withdrawal | Voluntary market withdrawal | `landscape_without_entity` |
| | pricing_action | WAC increase >10% | Pricing alert |
| | access_change | Formulary addition/removal | Access landscape update |
| **Corporate** | acquisition | Company A acquires B | `landscape_without_company` |
| | partnership | Licensing deal signed | SPONSORS/OWNS link creation |
| | patent_expiry | Key patent expires | Generic entry simulation |
| | restructuring | R&D site closure | Portfolio impact |
| **Safety** | signal_escalation | PRR crosses 5.0 threshold | Already in InsightEngine |
| | recall | Voluntary recall issued | Supply impact |
| | rems | REMS programme required | Access restriction |

### 1.2 Four-Tier Trust Model

Not all event sources are equally reliable. The system classifies sources into trust tiers that determine processing behaviour.

| Tier | Source Type | Trust Score | Processing | Verification |
|------|------------|-------------|------------|--------------|
| **T1 — Authoritative** | ClinicalTrials.gov status changes, FDA approval letters, SEC 8-K filings, Orange Book updates | 0.95–1.0 | Auto-process immediately | None required — these are the ground truth |
| **T2 — Official Press** | Company press releases (PR Newswire, BusinessWire, GlobeNewswire), WHO announcements | 0.70–0.90 | Auto-process with verification queue | Cross-reference against T1 within 48h |
| **T3 — News & Analysis** | Reuters Health, STAT News, Endpoints News, FiercePharma | 0.40–0.65 | Process but flag as unverified | Require T1/T2 confirmation before auto-simulation |
| **T4 — Social & Informal** | Twitter/X, conference abstracts, analyst reports, blog posts | 0.10–0.35 | Ingest for awareness only | Human review before any system action |

**Trust score formula**:

```
trust_score = source_tier_base × recency_factor × corroboration_bonus

where:
  source_tier_base = {T1: 0.95, T2: 0.80, T3: 0.50, T4: 0.20}
  recency_factor   = max(0.5, 1.0 - (hours_since_event / 168))  # decays over 7 days
  corroboration_bonus = 0.1 × min(3, corroborating_source_count)  # up to +0.3
```

### 1.3 Event Source Connectors (new)

These extend the existing `BaseConnector` pattern in `connectors/base.py`.

| Connector | Source | Tier | Frequency | What it detects |
|-----------|--------|------|-----------|-----------------|
| `ClinicalTrialsDiffConnector` | ClinicalTrials.gov | T1 | Every 6h | Status changes (recruiting → completed, phase advances), new registrations |
| `FDAActionsConnector` | FDA.gov (Drugs@FDA, approval letters, CRLs) | T1 | Daily | New approvals, rejections, label changes, REMS, safety communications |
| `SECEventConnector` | SEC EDGAR 8-K filings | T1 | Daily | Material events: acquisitions, licensing deals, financial restatements |
| `PressReleaseConnector` | PR Newswire / BusinessWire RSS | T2 | Every 2h | Drug launches, partnership announcements, clinical data readouts |
| `PharmaNewsFeedConnector` | Reuters Health, STAT, Endpoints RSS/API | T3 | Every 4h | Industry news, analyst reactions, conference coverage |

**State-change detection** (the most reliable pattern): Rather than classifying free-text news, the T1 connectors compare the current state of authoritative records against the last-known state stored in Market Zero. For example, the `ClinicalTrialsDiffConnector` compares `clinical_trials.status` in the database with the latest API response. A change from `RECRUITING` to `COMPLETED` is an unambiguous event. This is far more trustworthy than NLP extraction from news articles.

### 1.4 Database Schema: `market_events`

```sql
-- Migration 015: market_events and impact_assessments
CREATE TABLE market_events (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type      TEXT NOT NULL,          -- taxonomy category.sub_type
    title           TEXT NOT NULL,          -- human-readable headline
    description     TEXT,                   -- detail paragraph
    source_url      TEXT,                   -- canonical source link
    source_name     TEXT NOT NULL,          -- connector name
    source_tier     SMALLINT NOT NULL CHECK (source_tier BETWEEN 1 AND 4),
    trust_score     REAL NOT NULL DEFAULT 0.5,

    -- Entity linkage
    primary_entity_id   UUID REFERENCES drugs(id),
    primary_entity_type TEXT,               -- 'drug', 'company', 'trial', etc.
    primary_entity_name TEXT,               -- denormalised for display

    -- Temporal
    event_date      TIMESTAMPTZ,           -- when the event occurred (if known)
    detected_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Processing state
    status          TEXT NOT NULL DEFAULT 'detected'
                    CHECK (status IN ('detected', 'verified', 'simulated', 'delivered', 'dismissed', 'expired')),
    verified_at     TIMESTAMPTZ,
    corroborating_sources JSONB DEFAULT '[]'::jsonb,

    -- Deduplication
    event_hash      TEXT UNIQUE,           -- SHA-256 of (event_type + primary_entity_name + event_date)

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_market_events_status ON market_events(status);
CREATE INDEX idx_market_events_type ON market_events(event_type);
CREATE INDEX idx_market_events_entity ON market_events(primary_entity_id);
CREATE INDEX idx_market_events_detected ON market_events(detected_at DESC);
CREATE INDEX idx_market_events_trust ON market_events(trust_score);

CREATE TABLE impact_assessments (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id        UUID NOT NULL REFERENCES market_events(id),

    -- What was affected
    affected_entities JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- [{"entity_id": "...", "entity_type": "drug", "name": "...", "impact_type": "direct|indirect"}]

    -- Scenario results
    simulations     JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- [{"scenario_type": "landscape_without_entity", "summary": "...", "delta": {...}}]

    -- Synthesised brief
    impact_brief    TEXT,                  -- LLM-generated 2-3 paragraph analysis
    severity        TEXT NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low')),
    confidence      REAL NOT NULL DEFAULT 0.5,

    -- Delivery tracking
    delivered_at    TIMESTAMPTZ,
    dismissed_at    TIMESTAMPTZ,
    snoozed_until   TIMESTAMPTZ,
    user_feedback   TEXT,                  -- thumbs up/down + optional note

    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_impact_event ON impact_assessments(event_id);
CREATE INDEX idx_impact_severity ON impact_assessments(severity);
CREATE INDEX idx_impact_delivered ON impact_assessments(delivered_at);
```

---

## Stage 2: Impact Routing

### 2.1 `EventCollector` Service

New service at `services/event_collector.py`. Responsible for ingesting raw events, deduplicating, entity-resolving, and trust-scoring.

```python
# Pseudocode — key methods

class EventCollector:
    def __init__(self, db: Database, entity_resolver: EntityResolver):
        ...

    def ingest(self, raw_event: RawEvent) -> MarketEvent | None:
        """Ingest a raw event from any connector.

        1. Compute event_hash for deduplication
        2. Resolve primary entity via EntityResolver
        3. Compute trust_score from source tier + recency + corroboration
        4. Insert into market_events (skip if duplicate hash)
        5. Return MarketEvent or None if duplicate
        """

    def verify(self, event_id: UUID) -> bool:
        """Check if a lower-tier event has been corroborated.

        Queries market_events for events with overlapping entity + type
        from higher-tier sources within the corroboration window.
        """

    def expire_stale(self, max_age_days: int = 30) -> int:
        """Mark old unverified events as 'expired'."""
```

### 2.2 `ImpactRouter` Service

New service at `services/impact_router.py`. The core intelligence: given an event, determine what it affects and run the appropriate simulations.

```python
class ImpactRouter:
    def __init__(self, db: Database, graph: GraphTraversal,
                 scenario: ScenarioEngine, metrics: PharmaMetrics,
                 llm: LLMSynthesizer):
        ...

    def assess(self, event: MarketEvent) -> ImpactAssessment:
        """Full impact assessment pipeline for a single event.

        1. Identify affected entities via graph neighbourhood traversal
        2. Select applicable scenario simulations from EVENT_SCENARIO_MAP
        3. Run simulations via ScenarioEngine
        4. Synthesise impact brief via LLMSynthesizer
        5. Compute severity from simulation deltas + event trust
        6. Persist ImpactAssessment
        """

    def _identify_affected(self, event: MarketEvent) -> list[AffectedEntity]:
        """Graph traversal from the primary entity outward.

        Uses GraphTraversal.neighborhood(depth=2) to find:
        - Direct: same drug, same company, same trial
        - Indirect: competing drugs (COMPETES_WITH), same mechanism,
                     same therapeutic area, trial sponsors
        """

    def _select_simulations(self, event: MarketEvent) -> list[SimulationSpec]:
        """Map event type to scenario operations.

        Uses EVENT_SCENARIO_MAP (see taxonomy table above).
        A single event may trigger multiple simulations.
        """

    def _synthesise_brief(self, event: MarketEvent,
                          affected: list[AffectedEntity],
                          sim_results: list[ScenarioResult]) -> str:
        """LLM-generated impact analysis grounded in simulation data.

        Uses LLMSynthesizer with CTX context from affected entities.
        Prompt enforces: cite scenario results, state confidence level,
        identify what to watch next.
        """
```

### 2.3 Event-to-Scenario Mapping

The `EVENT_SCENARIO_MAP` is a declarative mapping from event types to scenario operations, analogous to how `LinkRule` maps entity types to cross-link patterns.

```python
EVENT_SCENARIO_MAP: dict[str, list[SimulationSpec]] = {
    "regulatory.approval": [
        SimulationSpec("competitive_landscape", scope="mechanism"),
        SimulationSpec("drug_pipeline_strength", scope="therapeutic_area"),
    ],
    "regulatory.rejection": [
        SimulationSpec("pipeline_without_entity", target="primary_entity"),
        SimulationSpec("competitive_landscape", scope="mechanism"),
    ],
    "regulatory.clinical_hold": [
        SimulationSpec("pipeline_excluding_inactive", scope="therapeutic_area"),
    ],
    "clinical.phase_advance": [
        SimulationSpec("drug_pipeline_strength", target="primary_entity"),
        SimulationSpec("competitive_landscape", scope="mechanism"),
    ],
    "clinical.trial_halt": [
        SimulationSpec("pipeline_without_entity", target="primary_entity"),
    ],
    "commercial.withdrawal": [
        SimulationSpec("landscape_without_entity", target="primary_entity"),
        SimulationSpec("competitive_landscape", scope="mechanism"),
    ],
    "corporate.acquisition": [
        SimulationSpec("landscape_without_company", target="acquiring_company"),
        SimulationSpec("company_portfolio", target="merged_entity"),
    ],
    "safety.signal_escalation": [
        SimulationSpec("threshold_alert", metric="prr", threshold=5.0),
    ],
}
```

### 2.4 Integration with Existing Services

The ImpactRouter reuses existing services — it does not duplicate them:

| Existing Service | How ImpactRouter Uses It |
|-----------------|--------------------------|
| `GraphTraversal.neighborhood()` | Find affected entities within 2 hops |
| `ScenarioEngine.landscape_without_entity()` | Simulate market impact of drug withdrawal |
| `ScenarioEngine.pipeline_without_entity()` | Simulate pipeline impact of trial failure |
| `ScenarioEngine.pipeline_excluding_inactive()` | Simulate clinical hold impact |
| `PharmaMetrics.competitive_landscape()` | Before/after competitive position |
| `PharmaMetrics.drug_pipeline_strength()` | Before/after pipeline strength |
| `LLMSynthesizer.synthesize()` | Generate impact brief narrative |
| `InsightEngine.scan()` | Supplement with existing insight detection |
| `EntityResolver.resolve()` | Link event mentions to graph entities |

### 2.5 Scheduler Integration

The event detection runs as a new scheduler task, slotting into the existing `DataPipelineScheduler` post-pipeline sequence.

```python
# In scheduler/runner.py → _run_post_tasks()

# 8. Event detection and impact assessment
try:
    t0 = time.time()
    from services.event_collector import EventCollector
    from services.impact_router import ImpactRouter

    collector = EventCollector(db, entity_resolver)
    router = ImpactRouter(db, graph, scenario, metrics, llm)

    # Run event connectors
    new_events = collector.collect_from_all_sources()

    # Assess impacts for events above trust threshold
    assessments = []
    for event in new_events:
        if event.trust_score >= 0.6:  # T1 and verified T2 only
            assessment = router.assess(event)
            assessments.append(assessment)

    results["event_intelligence"] = (
        f"OK: {len(new_events)} events, {len(assessments)} assessed "
        f"({time.time()-t0:.1f}s)"
    )
except Exception as e:
    logger.exception("Post-task event_intelligence failed")
    results["event_intelligence"] = f"ERROR: {e}"
```

Additionally, high-frequency event sources (T1 state-change detection) run on their own cron schedule independent of the full ETL pipeline:

```python
# In scheduler/config.py
CONNECTOR_SCHEDULES[SourceType.CT_DIFF] = {
    "cron": {"hour": "*/6"},           # every 6 hours
    "label": "ClinicalTrials.gov state diffs",
}
CONNECTOR_SCHEDULES[SourceType.FDA_ACTIONS] = {
    "cron": {"hour": "6,18"},          # twice daily
    "label": "FDA regulatory actions",
}
CONNECTOR_SCHEDULES[SourceType.PRESS_RELEASES] = {
    "cron": {"hour": "*/2"},           # every 2 hours
    "label": "Press release monitoring",
}
```

---

## Stage 3: Intelligence Delivery — UX/UI Design

### 3.1 Workspace Layout Evolution

The existing workspace (SPEC-002) is a chat-left / canvas-right split panel. Proactive intelligence adds a third surface: the **Intelligence Feed**, accessible via a new top-bar tab and an ambient notification layer.

```
┌──────────────────────────────────────────────────────────────────┐
│  TopBar:  [Chat]  [Intelligence ●3]  [Graph]  [Catalog]         │
│           ──────   ─────────────      ─────    ───────           │
└──────────────────────────────────────────────────────────────────┘
│                         │                                        │
│   Intelligence Feed     │         Impact Detail (Canvas)         │
│                         │                                        │
│   ┌──────────────────┐  │  ┌──────────────────────────────────┐  │
│   │ ● CRITICAL        │  │  │  Impact Brief                    │  │
│   │ FDA halts trial   │  │  │                                  │  │
│   │ for Semaglutide   │  │  │  "The clinical hold on Trial     │  │
│   │ analog XYZ-401    │  │  │   NCT0589... removes one of      │  │
│   │                   │  │  │   three Phase 2 candidates..."   │  │
│   │ 2h ago · T1 ✓     │  │  │                                  │  │
│   ├───────────────────┤  │  ├──────────────────────────────────┤  │
│   │ ▲ HIGH            │  │  │  Affected Entities               │  │
│   │ Phase 3 complete: │  │  │  ┌────┐ ┌────┐ ┌────┐ ┌────┐   │  │
│   │ Entresto generic  │  │  │  │Drug│ │Drug│ │Co. │ │Trial│   │  │
│   │ bioequiv study    │  │  │  └────┘ └────┘ └────┘ └────┘   │  │
│   │                   │  │  ├──────────────────────────────────┤  │
│   │ 6h ago · T1 ✓     │  │  │  Simulation Results              │  │
│   ├───────────────────┤  │  │                                  │  │
│   │ ■ MEDIUM          │  │  │  Pipeline Strength: 8.2 → 6.4   │  │
│   │ New SGLT2 entrant │  │  │  HHI Delta: -340 points          │  │
│   │ files IND in T2D  │  │  │  Competitors affected: 4         │  │
│   │                   │  │  │                                  │  │
│   │ 1d ago · T2 ◐     │  │  │  [Chart: before/after bar]      │  │
│   ├───────────────────┤  │  ├──────────────────────────────────┤  │
│   │ ○ LOW             │  │  │  What to Watch                   │  │
│   │ Pricing: WAC +12% │  │  │  • FDA response within 30 days  │  │
│   │ for Brand Z       │  │  │  • Competitor pipeline readouts  │  │
│   │                   │  │  │  • Sponsor financial filings     │  │
│   │ 2d ago · T3 ◌     │  │  │                                  │  │
│   └──────────────────┘  │  └──────────────────────────────────┘  │
│                         │                                        │
│   [Filter ▾] [Mark all  │  │  [Dismiss] [Snooze] [Ask about…]  │
│    read]                │  │                                     │
└─────────────────────────┴──────────────────────────────────────┘
```

### 3.2 TopBar: Intelligence Tab with Badge

The existing `TopBar.tsx` segmented navigation gains an "Intelligence" tab. When unread high-severity items exist, a notification badge appears.

```
Tabs:  Chat    Intelligence ●3    Graph    Catalog
                ↑ red dot with count of unread critical+high items
```

**Design tokens** (using existing CSS custom properties):

| Element | Token | Value |
|---------|-------|-------|
| Badge background | `var(--color-accent)` | Warm accent colour |
| Badge text | `var(--color-surface)` | White on accent |
| Active tab underline | `var(--color-ink)` | Standard ink |
| Unread indicator dot | `var(--color-severity-critical)` | New token — `#DC2626` |

**New CSS tokens** added to `frontend/src/index.css`:

```css
:root {
    --color-severity-critical: #DC2626;
    --color-severity-high: #D97706;
    --color-severity-medium: #2563EB;
    --color-severity-low: #6B7280;
    --color-trust-verified: #059669;
    --color-trust-pending: #D97706;
    --color-trust-unverified: #9CA3AF;
}
```

### 3.3 Intelligence Feed Panel (Left Side)

The feed panel replaces the chat panel when the Intelligence tab is active. It is a **chronological, filterable list of event cards** sorted by severity within time windows.

#### Event Card Component

Each event is rendered as an `EventCard` — a compact, scannable tile.

```
┌─────────────────────────────────────────┐
│ ● CRITICAL · Regulatory · Clinical Hold │  ← severity dot + category + sub-type
│                                         │
│ FDA places clinical hold on XYZ-401     │  ← title (Fraunces, 16px)
│ Phase 2 trial in NASH suspended after   │  ← description excerpt (DM Sans, 14px)
│ serious hepatic events reported in...   │
│                                         │
│ XYZ-401 · Novartis · NASH              │  ← entity pills (existing Pill component)
│                                         │
│ 2h ago · ClinicalTrials.gov · T1 ✓     │  ← timestamp · source · trust indicator
│                                         │
│ Pipeline impact: -1.8 pts              │  ← key metric delta (if simulated)
│                                         │
└─────────────────────────────────────────┘
```

**Visual design rules:**

- Left border colour encodes severity: `4px solid var(--color-severity-{level})`
- Background: `var(--color-surface)` with subtle hover state
- Trust indicator: `✓` (verified, green), `◐` (pending verification, amber), `◌` (unverified, grey)
- Entity mentions use the existing `Pill` component from `frontend/src/components/ui/Pill.tsx`
- Fonts: Title in **Fraunces** (serif, 16px), body in **DM Sans** (14px), metadata in DM Sans (12px, muted)
- Unread items have `border-left-width: 4px`; read items fade to `2px` and `opacity: 0.85`

#### Feed Filters

A compact filter bar at the top of the feed:

```
[All] [Critical] [High] [Medium] [Low]    [Regulatory ▾] [Last 7d ▾]
```

- Severity pills toggle independently (multi-select)
- Category dropdown filters by event taxonomy top-level
- Time window: Last 24h, Last 7d, Last 30d, All
- State: a "Show dismissed" toggle (off by default)

### 3.4 Impact Detail Panel (Right Side / Canvas)

When a user clicks an event card, the right-side canvas panel displays the full `ImpactAssessment`. This reuses the existing `CanvasPanel` architecture with new tab content.

#### Impact Detail Tabs

| Tab | Content | Component |
|-----|---------|-----------|
| **Brief** | LLM-generated impact analysis (2-3 paragraphs) with inline citations | `ImpactBriefTab` |
| **Entities** | Grid of affected entities with impact type (direct/indirect) badges | Reuses existing `EntityGrid` from `CanvasPanel.tsx` |
| **Simulations** | Before/after comparison charts for each simulation run | `SimulationTab` |
| **Source** | Original event source, corroborating sources, trust breakdown | `SourceTab` |

#### Brief Tab

The primary view. Renders the `impact_brief` narrative using the same `NarrativeMessage` component from chat, ensuring consistent citation rendering, Markdown formatting, and entity linking.

Below the narrative, a **"What to Watch"** section lists 2-4 forward-looking items the user should monitor, generated by the LLM with time horizons.

#### Simulations Tab

Renders each simulation result as a **before/after comparison card**:

```
┌─────────────────────────────────────────────────────┐
│  Pipeline Strength: GLP-1 Agonists (T2D)            │
│                                                     │
│  Before event          After event                  │
│  ████████████ 8.2      ██████████ 6.4               │
│                                                     │
│  Δ -1.8 points (−22%)                               │
│                                                     │
│  Drugs removed from active pipeline: 1              │
│  Remaining candidates: 6 → 5                        │
└─────────────────────────────────────────────────────┘
```

Uses Recharts `BarChart` (already in the project dependencies) for visual comparison. The `VizCard` component from `CanvasPanel.tsx` is extended with a `comparison` variant.

### 3.5 Notification Layer

A lightweight, ambient notification system that works across all workspace tabs.

#### Bell Icon

Added to the top-right of `TopBar`, next to the theme toggle:

```
[Chat] [Intelligence ●3] [Graph] [Catalog]                    🔔●  ◐
                                                               ↑     ↑
                                                          bell+badge  theme
```

- Badge shows count of critical + high severity unread items
- Clicking opens a **notification drawer** (using the existing `Drawer` component from `frontend/src/components/ui/Drawer.tsx`)
- Drawer shows a compact list of recent events with one-tap "View" or "Dismiss"

#### Chat Proactive Injection

When a user is in the Chat tab and asks a question about an entity that has recent unread intelligence, the system prepends a contextual alert:

```
┌──────────────────────────────────────────────────┐
│  ⚡ Recent intelligence about Semaglutide          │
│                                                    │
│  2 events detected in the last 24h:               │
│  • Phase 3 trial NCT0612… completed (6h ago)      │
│  • New competitor IND filed in GLP-1 space (18h)  │
│                                                    │
│  [View in Intelligence Feed →]                     │
└──────────────────────────────────────────────────┘
```

This is injected by the `CTXContextBuilder` during the `retrieve` stage — it queries `market_events` for the entities detected in the user's question and includes relevant recent events in the LLM context.

### 3.6 Landing Page: Intelligence Strip

The existing `LandingPage.tsx` has a metrics strip showing Total Records, Graph Links, etc. Below this, add a new **"Latest Intelligence"** section showing the 3 most recent high-severity events as compact cards.

```
┌────────────────────────────────────────────────────────────────┐
│                    Latest Intelligence                          │
│                                                                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐        │
│  │ ● Clinical    │  │ ▲ Regulatory │  │ ■ Commercial │        │
│  │   hold:       │  │   Phase 3    │  │   New SGLT2  │        │
│  │   XYZ-401     │  │   complete:  │  │   entrant    │        │
│  │               │  │   Entresto   │  │   in T2D     │        │
│  │   2h ago      │  │   6h ago     │  │   1d ago     │        │
│  └──────────────┘  └──────────────┘  └──────────────┘        │
│                                                                │
│                    [View all intelligence →]                    │
└────────────────────────────────────────────────────────────────┘
```

These cards use the same `EventCard` component in a compact/mini variant, laid out in a 3-column grid.

---

## New Components (Frontend)

| Component | File | Purpose |
|-----------|------|---------|
| `IntelligenceFeed` | `components/intelligence/IntelligenceFeed.tsx` | Feed panel orchestrator: data fetching, filtering, pagination |
| `EventCard` | `components/intelligence/EventCard.tsx` | Individual event tile with severity, trust, entity pills |
| `EventCardMini` | `components/intelligence/EventCardMini.tsx` | Compact variant for landing page and notification drawer |
| `ImpactBriefTab` | `components/intelligence/ImpactBriefTab.tsx` | Narrative impact analysis rendering |
| `SimulationTab` | `components/intelligence/SimulationTab.tsx` | Before/after comparison charts |
| `SourceTab` | `components/intelligence/SourceTab.tsx` | Event provenance and trust breakdown |
| `FeedFilters` | `components/intelligence/FeedFilters.tsx` | Severity, category, time range filter bar |
| `NotificationBell` | `components/intelligence/NotificationBell.tsx` | Bell icon with badge count |
| `NotificationDrawer` | `components/intelligence/NotificationDrawer.tsx` | Slide-out compact event list (wraps existing `Drawer`) |
| `IntelligenceStrip` | `components/intelligence/IntelligenceStrip.tsx` | Landing page latest intelligence section |

---

## New Services (Backend)

| Service | File | Purpose |
|---------|------|---------|
| `EventCollector` | `services/event_collector.py` | Ingest, deduplicate, trust-score, entity-resolve events |
| `ImpactRouter` | `services/impact_router.py` | Graph traversal → scenario simulation → brief synthesis |
| `IntelligenceFeedService` | `services/intelligence_feed.py` | Query/filter/paginate events + assessments for frontend |

---

## New API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET` | `/api/intelligence/feed` | Paginated feed of events with assessments. Params: `severity`, `category`, `since`, `limit`, `offset` |
| `GET` | `/api/intelligence/events/{id}` | Single event detail with full assessment |
| `POST` | `/api/intelligence/events/{id}/dismiss` | Mark event as dismissed |
| `POST` | `/api/intelligence/events/{id}/snooze` | Snooze event until specified time |
| `POST` | `/api/intelligence/events/{id}/feedback` | User feedback (thumbs up/down + note) |
| `GET` | `/api/intelligence/unread-count` | Badge count: `{critical: N, high: N, total: N}` |
| `GET` | `/api/intelligence/entity/{entity_id}/recent` | Recent events for a specific entity (for chat injection) |

All routes go in `api/routes/intelligence.py`, registered in `api/app.py` via the standard router pattern.

---

## New Connectors

| Connector | File | Base Class |
|-----------|------|-----------|
| `ClinicalTrialsDiffConnector` | `connectors/clinical_trials_diff.py` | `BaseConnector` |
| `FDAActionsConnector` | `connectors/fda_actions.py` | `BaseConnector` |
| `SECEventConnector` | `connectors/sec_events.py` | `BaseConnector` |
| `PressReleaseConnector` | `connectors/press_releases.py` | `BaseConnector` |
| `PharmaNewsFeedConnector` | `connectors/pharma_news.py` | `BaseConnector` |

Each connector extends `BaseConnector` from `connectors/base.py`, implementing `fetch()`, `source_type`, and `health_check()`. They emit `RawRecord` objects with `record_type = RecordType.EVENT` (new enum value).

---

## Implementation Plan

### Phase 1: Foundation (Weeks 1-2)

**Goal**: Event detection from authoritative sources, stored in database.

| Task | Files | Tests |
|------|-------|-------|
| Migration 015: `market_events` + `impact_assessments` tables | `schema/migrations/015_market_events.sql` | Migration smoke test |
| Add `RecordType.EVENT` to enum | `connectors/base.py` | Existing enum tests |
| `EventCollector` service | `services/event_collector.py` | `tests/test_event_collector.py` |
| `ClinicalTrialsDiffConnector` | `connectors/clinical_trials_diff.py` | `tests/test_ct_diff_connector.py` |
| `FDAActionsConnector` | `connectors/fda_actions.py` | `tests/test_fda_actions.py` |
| Scheduler integration for T1 connectors | `scheduler/config.py`, `scheduler/runner.py` | Scheduler config test |
| Intelligence feed API (read-only) | `api/routes/intelligence.py` | `tests/test_intelligence_api.py` |

**Exit criteria**: T1 events detected from ClinicalTrials.gov and FDA, persisted with trust scores, queryable via API.

### Phase 2: Impact Analysis (Weeks 3-4)

**Goal**: Automatic impact assessment with scenario simulations.

| Task | Files | Tests |
|------|-------|-------|
| `ImpactRouter` service | `services/impact_router.py` | `tests/test_impact_router.py` |
| `EVENT_SCENARIO_MAP` configuration | `services/impact_router.py` | Map coverage tests |
| Impact brief generation via `LLMSynthesizer` | `services/impact_router.py` | Mock LLM brief tests |
| Severity computation from simulation deltas | `services/impact_router.py` | Severity threshold tests |
| Connect InsightEngine outputs as events | `services/event_collector.py` | Integration test |
| Dismiss/snooze/feedback API endpoints | `api/routes/intelligence.py` | `tests/test_intelligence_api.py` |

**Exit criteria**: Events auto-trigger simulations, produce impact briefs, persist assessments with severity.

### Phase 3: Frontend — Intelligence Feed (Weeks 5-6)

**Goal**: Users can view, filter, and interact with proactive intelligence.

| Task | Files | Tests |
|------|-------|-------|
| CSS severity + trust tokens | `frontend/src/index.css` | Visual regression |
| `EventCard` component | `components/intelligence/EventCard.tsx` | Vitest render test |
| `IntelligenceFeed` panel | `components/intelligence/IntelligenceFeed.tsx` | Vitest render test |
| `FeedFilters` component | `components/intelligence/FeedFilters.tsx` | Vitest render test |
| TopBar: Intelligence tab + badge | `components/layout/TopBar.tsx` | Vitest render test |
| WorkspacePage: Intelligence tab routing | `pages/WorkspacePage.tsx` | Integration test |

**Exit criteria**: Intelligence tab visible in workspace, shows feed of events with severity colours and trust indicators, filterable by severity/category/time.

### Phase 4: Impact Detail + Notifications (Weeks 7-8)

**Goal**: Full drill-down experience and ambient notifications.

| Task | Files | Tests |
|------|-------|-------|
| `ImpactBriefTab` (narrative rendering) | `components/intelligence/ImpactBriefTab.tsx` | Vitest render test |
| `SimulationTab` (before/after charts) | `components/intelligence/SimulationTab.tsx` | Vitest render test |
| `SourceTab` (provenance display) | `components/intelligence/SourceTab.tsx` | Vitest render test |
| `NotificationBell` + `NotificationDrawer` | `components/intelligence/NotificationBell.tsx` | Vitest render test |
| Chat proactive injection in CTXContextBuilder | `services/ctx_context.py` | `tests/test_ctx_pipeline.py` |
| Landing page `IntelligenceStrip` | `components/intelligence/IntelligenceStrip.tsx` | Vitest render test |

**Exit criteria**: Click-through from event card to full impact brief with simulations. Bell icon with badge. Chat mentions relevant recent events.

### Phase 5: Extended Sources + Verification (Weeks 9-10)

**Goal**: T2/T3 sources, cross-tier verification, corroboration.

| Task | Files | Tests |
|------|-------|-------|
| `PressReleaseConnector` | `connectors/press_releases.py` | `tests/test_press_releases.py` |
| `SECEventConnector` (8-K material events) | `connectors/sec_events.py` | `tests/test_sec_events.py` |
| `PharmaNewsFeedConnector` | `connectors/pharma_news.py` | `tests/test_pharma_news.py` |
| Cross-tier verification logic | `services/event_collector.py` | `tests/test_event_verification.py` |
| Corroboration bonus scoring | `services/event_collector.py` | Trust score unit tests |
| Feed: trust indicator hover with source breakdown | `components/intelligence/EventCard.tsx` | Visual test |

**Exit criteria**: T2/T3 events flowing in, lower-tier events auto-verified when T1 confirmation arrives, trust scores adjust with corroboration.

### Phase 6: Polish + Email Digest (Weeks 11-12)

**Goal**: Refinement, email delivery, user preferences.

| Task | Files | Tests |
|------|-------|-------|
| Email digest service (daily/weekly) | `services/email_digest.py` | `tests/test_email_digest.py` |
| User preference API (severity threshold, categories, digest frequency) | `api/routes/preferences.py` | `tests/test_preferences.py` |
| Feed performance optimisation (materialised view for feed queries) | `schema/migrations/016_mv_intelligence_feed.sql` | Query perf benchmark |
| Keyboard shortcuts: `I` to open Intelligence tab, `J/K` to navigate feed | `components/intelligence/IntelligenceFeed.tsx` | Interaction test |
| Accessibility: ARIA roles, focus management, screen reader labels | All intelligence components | a11y audit |

**Exit criteria**: Email digests working, user preferences respected, feed loads < 200ms, keyboard-navigable.

---

## Metrics and Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Event detection latency (T1) | < 6h from source update | `detected_at - event_date` |
| Event detection latency (T2) | < 4h from press release | `detected_at - event_date` |
| Impact assessment coverage | ≥ 80% of events have ≥1 affected entity | `affected_entities` non-empty |
| Simulation relevance | ≥ 70% of assessments produce meaningful delta | `sim_delta != 0` |
| Trust score accuracy | ≥ 90% of T1 events verified as accurate | Manual audit sample |
| User engagement | ≥ 40% of feed items viewed (not just listed) | `delivered_at` set |
| Dismissal rate | < 50% of delivered items dismissed without viewing detail | `dismissed_at` tracking |
| Feed load time | < 200ms for 50-item page | API response timing |

---

## Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| **Event flood**: too many low-value events overwhelm users | Severity-based filtering defaults to critical+high only. Feed caps at 50 items per page. Stale unverified events auto-expire after 30 days. |
| **False events**: T3/T4 sources produce inaccurate intelligence | Trust model prevents auto-simulation below T2 verified. All T3/T4 items display prominent "Unverified" badge. User feedback loop trains future filtering. |
| **Simulation noise**: scenario simulations produce trivial deltas | Minimum delta threshold required for display (configurable). Simulations with zero-impact are logged but not surfaced. |
| **LLM hallucination in briefs**: impact narrative cites facts not in data | Brief generation uses same `ContextGuard` and citation validation from CTX pipeline. Briefs are grounded in simulation outputs, not general knowledge. |
| **Performance**: event processing slows the ETL pipeline | Event detection runs on separate cron schedule (not blocking main ETL). Impact assessment is async per-event. Feed queries use materialised view (Phase 6). |

---

## Relationship to Existing Specs

- **SPEC-001 (Autonomous Research Engine)**: The research agent fills knowledge gaps; the event system detects external changes. They are complementary — events may trigger research targets (e.g., new drug detected → research agent enriches its profile).
- **SPEC-002 (Frontend UX Revamp)**: The Intelligence Feed is a new workspace tab within the SPEC-002 layout architecture. It reuses the split-panel, canvas tabs, and design system established there.

---

## Open Questions

1. **Real-time vs batch**: Should T1 state-change detection eventually move to a streaming/webhook model (e.g., ClinicalTrials.gov API polling vs webhook)? For now, polling every 6h is pragmatic.
2. **User-scoped feeds**: Should users be able to set watchlists (specific drugs, companies, TAs) to filter their feed? Deferred to Phase 6 preferences.
3. **Multi-user**: Current design assumes a single-user system. If multi-user is added, events and assessments become shared, but delivery/read state becomes per-user.
4. **Cost**: Each impact assessment involves LLM synthesis. At 20 events/day × ~2K tokens/brief, this is roughly $0.12/day on GPT-4o-mini — negligible. Scale concern begins at 500+ events/day.
