# SPEC-016 — PulseAction.AI Platform: Layers, Modules, and Foundations

**Status:** Architectural Decision Document — supersedes SPEC-015 §Verdict on the architectural-shape question; absorbs `comp_intel_2.md` critique
**Decision:** Reposition PulseAction.AI as a **horizontal pharma intelligence platform** with a thin Mission Control landing surface and pluggable **module apps** on top. Initial modules: *Pharma Research Intelligence* (the existing chat+canvas, repositioned) and *Competitive Intelligence* (new). Future modules (Regulatory Affairs, Market Access, Medical Affairs, KOL Intelligence) plug into the same horizontal layers.
**Primary inputs:** `comp_intelligence.md`, `comp_intel.tsx`, `specs/SPEC_015_competitive_intelligence_assessment.md`, `specs/comp_intel_2.md`, the existing codebase.

---

## 0. The reframe

Two things stop being framed as competing surfaces and start being framed as *consumers of a common platform*:

- **Pharma Research Intelligence** — the analyst/researcher who wants to ask questions of the pharma graph and get cited, structured answers. Today's `/research`. Repositioned, not rebuilt.
- **Pharma Competitive Intelligence** — the CI analyst who triages signals against a watchlist, escalates high-impact events, composes briefs, and pushes alerts.

What they share is not a database — it's a **platform**. Three horizontal layers, both modules consume them.

This makes the previous "extend vs fresh build" question obsolete. The answer is: *neither, and both.* The horizontal layers are extended; the module apps on top are built fresh, with their own surfaces, schemas, and SLAs. The seam between platform and modules is the architecture.

```
╔══════════════════════════════════════════════════════════════════════════╗
║                      MARKET ZERO PLATFORM                                ║
║                                                                          ║
║  ┌────────────────────────────────────────────────────────────────────┐  ║
║  │                    MISSION CONTROL (landing)                       │  ║
║  │   Switch modules · platform health · cross-module search           │  ║
║  └─────────────┬──────────────────────────────────┬──────────────────┘   ║
║                │                                  │                      ║
║   ┌────────────▼─────────────┐    ┌───────────────▼─────────────┐        ║
║   │ MODULE: Pharma Research  │    │ MODULE: Competitive Intel    │ ←── future
║   │ Intelligence             │    │                              │     modules
║   │ (chat + canvas, existing)│    │ (digest + signals + briefs)  │
║   └────────────┬─────────────┘    └───────────────┬──────────────┘        ║
║                │                                  │                      ║
║   ═════════════▼══════════════════════════════════▼══════════════════    ║
║                    CONSUMPTION LAYER (per-module)                        ║
║   ─────────────────────────────────────────────────────────────────      ║
║                                                                          ║
║                    INTELLIGENCE LAYER (shared)                           ║
║   Signals · Events · Scoring · Synthesis · KBQ rule engine ·             ║
║   Entity graph · Embeddings · Citations · Hallucination guard            ║
║   ─────────────────────────────────────────────────────────────────      ║
║                                                                          ║
║                    DATA CATALOG LAYER (shared)                           ║
║   Connectors · Normalizer · Entity Resolver · Cross-Linker ·             ║
║   Domain Pack · Mention Normalizer · Document Store · Provenance         ║
║                                                                          ║
║   ─────────────────────────────────────────────────────────────────      ║
║                                                                          ║
║                    INFRA & FOUNDATIONS                                   ║
║   Auth · Multi-tenancy · Observability · Secrets · CI/CD ·               ║
║   Feature Flags · Cost metering · Data retention                         ║
╚══════════════════════════════════════════════════════════════════════════╝
```

The platform's value compounds as modules are added. Every new module inherits the catalog's connectors, the resolver's canonicalization, and the intelligence layer's signals + scoring + guardrails. **A new module is a frontend + a thin module-specific service + a contract against the platform**, not a from-scratch system.

---

## 1. The three horizontal layers, defined

Each layer has a stable contract, an owner, and a release cadence. Modules consume layers via versioned contracts; layers do not consume modules.

### 1.1 Data Catalog Layer

**What it owns.** Every piece of raw and resolved data that came from the world.

- **Connectors** — 17 today, growing. Each maps to a SourceType enum, has a stable `fetch()` contract, emits `RawRecord`s with provenance.
- **Normalizer** — converts raw records to canonical entity records.
- **Entity Resolver** — 6-strategy cascade (exact → alias → fuzzy → embedding → LLM → auto-create).
- **Cross-Linker** — declarative `LinkRule`s emit typed edges with confidence and provenance.
- **Mention Normalizer** — drug/company name cleaning.
- **Domain Pack** — pharma's `EntitySchema`s, `LinkRule`s, `OntologyConfig`s, `MentionNormalizer`s. Tomorrow we can register a med-device pack or a payer pack alongside it.
- **Document Store** — `source_records` table; raw payloads, hashes, provenance, timestamps.
- **Provenance** — every fact carries `source_id`, `source_url`, `source_published_at`, `ingested_at`, `extracted_by`.

**What it does not own.** Signals. Scoring. Briefs. Watchlists. Alerts. Anything an analyst sees.

**Contract surface.**
- `GET /catalog/entities/{type}/{id}` — canonical entity fetch with versioning.
- `GET /catalog/documents/{id}` — provenance-preserved document fetch.
- `GET /catalog/links/{entity_id}` — typed edges with confidence + provenance.
- `POST /catalog/resolve` — entity-resolution-as-a-service.
- Outbound CDC stream `catalog.events.entity_resolved` / `catalog.events.entity_updated` / `catalog.events.document_ingested` — what modules subscribe to.

**Module access pattern.** Modules **read** the catalog. They do not write to it. New connectors land in the catalog (so all modules benefit), not in modules.

### 1.2 Intelligence Layer

**What it owns.** Things derived from the catalog that *are not raw*. The "what should we believe / what matters" plane.

- **Event Spine** — `market_events` extended with `source_tier`, `trust_score`, `event_hash`, `corroborating_sources`, plus the typed taxonomy from CI design (~22 event types).
- **Signals** — *new* table. Deduplicated, KBQ-tagged, dual-tier-scored (confidence + impact), with `superseded_by_signal_id`, `supersedence_reason`. The unit-of-output that modules consume.
- **Clustering & Dedup Service** — per-event-type window + secondary-feature matching (entity overlap, document similarity); promotion path for late-arriving high-tier evidence; conflict detection routes to reviewer queue.
- **KBQ Rule Engine** — versioned, hot-reloadable YAML. Hard rules (HR1.1, HR2.1, …) executed at extraction time; impact rules tunable at runtime.
- **Scoring** — confidence tier (derived, not assigned, with corroboration + time-decay modifiers); impact tier (event-type base × entity priority × magnitude × recency × cross-source corroboration count).
- **Pattern Detector** — emits meta-signals when N events of type T fire on entity E within window W (e.g., 3 exec departures from one TA team in 90 days).
- **Negative-event detector** — `expected_event_missed` signals when calendar-projected events don't fire by their date (PDUFA passes without action; CHMP meeting deferred).
- **Synthesis Service** — schema-locked LLM output with per-sentence citations, hedging tied to confidence tier, validation pass against cited documents (semantic, not just presence).
- **Hallucination Guard** — `CTXContextBuilder` ContextGuard wired as default for all module-facing synthesis.
- **Entity Graph** — pgvector-powered hybrid search, graph traversal, materialized KPI views.
- **Provenance Audit** — periodic job: walk all signals, resolve all evidence document IDs, report orphans / retractions / broken citations. Pulls signals from active digests until reviewed.
- **Telemetry & Eval** — per-pipeline metrics, regression set against 50 hand-labeled historical events, weekly score report.

**Contract surface.**
- `GET /intel/signals?filters=…` — paginated, filter-by-watchlist / KBQ / confidence / impact / date.
- `GET /intel/signals/{id}` — full signal with evidence stack ordered by confidence tier.
- `GET /intel/events/{id}` — event with linked signals + evidence.
- `POST /intel/synthesize` — narrative synthesis over a Signal set.
- `POST /intel/ask` — Signal-aware Q&A (consumes the same store, returns cited answers).
- Outbound stream `intel.signal.created` / `intel.signal.updated` / `intel.signal.superseded` — what modules subscribe to for push UX.

**Module access pattern.** Modules **read** signals and **write** module-specific derivatives (briefs, digest snapshots, alert deliveries). The intelligence layer never reads from a module.

### 1.3 Consumption Layer (per-module)

**What it owns.** Everything an end user sees, plus the per-module state that doesn't generalize.

- The **frontend** — UI, design system instantiation, routes, state.
- **Module-specific tables** — for CI: `watchlists`, `alert_rules`, `alert_deliveries`, `digest_snapshots`, `digest_views`, `briefs`, `brief_versions`, `signal_shares`, `signal_tags`, `reviewer_actions`. For Research: existing chat sessions, research jobs, conversation memory.
- **Module-specific services** — orchestration, agent personas, brief composition templates, alert delivery channels, watchlist evaluation engine.
- **Module-specific APIs** — `/ci/digest`, `/ci/briefs`, `/ci/watchlists`, `/research/chat`, `/research/sessions`, etc.

**What it does not own.** Raw data. Entity resolution. Cross-source linking. Signal scoring. Hallucination guard. Domain pack. (All of those are inherited from the platform.)

**Contract direction.** Modules depend on layers below. Layers don't depend on modules. New module = frontend + thin service + table set + contract calls.

---

## 2. The module model

A *module* in this platform is a contract:

```
Module Contract
├── Identity
│   ├── module_id           (e.g., "pharma_ci", "pharma_research")
│   ├── display_name        ("Competitive Intelligence")
│   ├── tagline             ("Triage, brief, alert.")
│   └── icon
├── Entry point
│   ├── route               ("/ci")
│   └── permission_scope    ("ci.read", "ci.write", "ci.review")
├── Surface manifest
│   └── surfaces []         (Daily Digest, Signal Detail, Watchlist, …)
├── Data ownership
│   ├── owned_tables []     ("watchlists", "alert_rules", …)
│   └── consumed_contracts []  ("catalog.entity", "intel.signal", …)
├── Telemetry namespace     ("ci.*")
└── Cost budget             (LLM tokens / month, per-workflow caps)
```

Three modules are in scope:

| Module | Status | Initial surfaces |
|---|---|---|
| **Pharma Research Intelligence** | Existing, repositioned. Refactored to consume platform contracts cleanly. | Workspace (chat + canvas), Sessions, Saved Research |
| **Pharma Competitive Intelligence** | New. | Daily Digest, Signal Detail, Watchlist, Alerts, Reviewer Queue, Brief Composer (P1.5), Trackers (P1.5) |
| **(future) Pharma Regulatory** | Reserved. Will consume the same Regulatory Affairs agent + adds regulator-specific workflows. | TBD |

**Mission Control is not a module.** It's a thin shell that:
- Authenticates the user.
- Lists the modules they have access to (RBAC).
- Shows live platform health (connector freshness, signal volume, agent health).
- Exposes cross-module search (one query, results from every module's surfaces).
- Routes to the chosen module.

This keeps the landing surface honest about being a switcher, not a competitor to the modules themselves.

---

## 3. Mission Control — the first screen

The user lands on Mission Control. They see:

```
┌──────────────────────────────────────────────────────────────────────────┐
│  ◐ PulseAction.AI                                          kapil@…  ⚙  ⌘K  │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Good morning, Kapil.                                                    │
│  Tuesday, 28 April · 09:14                                               │
│                                                                          │
│  ┌─────────────────────────────────┐  ┌───────────────────────────────┐  │
│  │  Competitive Intelligence       │  │  Pharma Research Intelligence │  │
│  │  ─────────────────────          │  │  ────────────────────         │  │
│  │  12 new signals · 2 high-impact │  │  3 active research jobs       │  │
│  │  4 in reviewer queue            │  │  Last asked: GLP-1 cardio…    │  │
│  │  Watchlist healthy              │  │  Memory: 14 entities          │  │
│  │                                 │  │                               │  │
│  │  Open CI →                      │  │  Open Research →              │  │
│  └─────────────────────────────────┘  └───────────────────────────────┘  │
│                                                                          │
│  Platform                                                                │
│  ─────────                                                               │
│  Catalog freshness   ✓ all sources updated within 24h                    │
│  Intelligence        612 signals in last 7d · 89% pass guard             │
│  Cost (this month)   $1,847 / $5,000 LLM budget                          │
│                                                                          │
│  Recent across modules                                                   │
│  ─────────────────────                                                   │
│  • Pfizer 8-K Item 5.02: CMO transition       CI · 2h ago               │
│  • "Tirzepatide MACE outcomes" research run  Research · 4h ago         │
│  • Novo CHMP positive opinion                CI · 6h ago               │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Design tenets.**
- **Glanceable, not loud.** Two large module cards. Each carries one number that matters and one status descriptor. Click-through is one tap from anywhere.
- **No empty states.** If a user has no CI access, show a "Discover CI" card with a one-line pitch.
- **Cross-module timeline.** Recent activity from any module the user has access to, source-tagged. Powers "did I see X today?"
- **Platform health is a feature.** Catalog freshness + intel volume + cost surfaces — operations as user-visible. Trust comes from transparency.
- **⌘K command palette** — "Search Pfizer," "Open Watchlist," "New brief," "Switch to research." Keyboard-first; the analyst's reality.
- **No marketing fluff.** No "Welcome back!" balloons. The user knows where they are.

---

## 4. Design system — direction

### 4.1 North star

The right shape for this product is the place where **Apple Health's compositional restraint**, **Oura's score-led summarization**, **Linear's keyboard-first density**, **Stripe Dashboard's tabular fluency**, and **Spotify's library-as-collection** meet. Not the dark-monospace IDE-look of the current `comp_intel.tsx` mockup; not the warm-serif chat-style of the current `/research` UX. A third thing, which serves both.

What we take from each:

| Influence | Take |
|---|---|
| **Apple Health** | Card composition, glanceable summary tiles, drill-down for depth, time-bucket controls (D/W/M/Q/Y), color-coded indicators. |
| **Oura** | "Score of the day" pattern (signal volume / impact tier / freshness tier), warm soft-dark mode, contributing-factors strip below the score. |
| **Apple iOS / macOS** | Spatial hierarchy, restraint, precise typography, focus states, density-when-needed-and-airy-by-default. Mission Control as a UX primitive. |
| **Linear** | Keyboard-first navigation (j/k/e/f/x), command palette (⌘K), no decorative motion, fast list virtualization. |
| **Stripe Dashboard** | Data tables done well, filterable trackers, export, audit trail. |
| **Spotify** | Sidebar navigation, library-as-a-collection (watchlists), smart suggestions ("companies often watched together"). |
| **Mercury / Wealthfront** | Card-based dashboards with one-clear-number-per-card hierarchy. |
| **Notion** | Composition primitives — every surface is composed from a small set of blocks (signal card, evidence block, citation pill, score tile, time-range selector, conflict badge). |

What we explicitly reject:
- Emoji-heavy "fun" UI. This is a tool.
- Gradient-on-everything dashboards. Restraint signals quality.
- Skeuomorphism, drop shadows for decoration.
- Verbose copywriting in the UI. Headlines, not paragraphs.
- Dark mode that's pure `#000`. Use a warm graphite (`#0E0F11`–`#14161A`). Pure black destroys depth on OLED and produces eye strain.

### 4.2 Brand identity (proposed, open to revision)

- **Platform:** *PulseAction.AI* (existing). Wordmark in display type, lowercase, tight tracking. Internal codename: `mz`.
- **Modules:**
  - *PulseAction · Research* (pharma research intelligence)
  - *PulseAction · CI* (competitive intelligence)
  - *PulseAction · Regulatory* (future)
  - *PulseAction · Market Access* (future)

Module identifier always co-locates with platform mark. Modules carry one accent color (Research = warm amber; CI = analyst blue). All other UI uses neutral grays.

### 4.3 Tokens (to be implemented as `packages/design-tokens`)

**Color (light + soft-dark, both first-class):**

```
Neutrals (light)               Neutrals (soft-dark)
  bg/canvas       #FAFAF7        bg/canvas       #0E0F11
  bg/surface      #FFFFFF        bg/surface      #14161A
  bg/elevated    #F5F4F0         bg/elevated    #1A1D22
  border/subtle   #ECECE7        border/subtle   #21252B
  border/strong   #D6D5CE        border/strong   #2A2F36
  text/primary    #18191B        text/primary    #E7E9EC
  text/secondary  #565759        text/secondary  #98A0AA
  text/tertiary   #8C8E91        text/tertiary   #5E6670

Accent — module-specific (single accent per module)
  research        warm amber     #C97A3A  (light)  #E29964  (dark)
  ci              analyst blue   #2F6BFF  (light)  #5C8CFF  (dark)
  regulatory      reserved teal  #1E8A7E

Semantic
  success         #2E8B57 / #4CAF7A
  warning         #B7791F / #E0A14C
  danger          #B0301C / #E06B57
  info            #2F6BFF / #5C8CFF

Confidence tiers (used as glyph color, not background)
  confirmed       semantic.success
  reported        text/secondary
  inferred        warning
  disputed        danger

Impact tiers (used as glyph + sparing background)
  high            danger
  medium          warning
  low             text/tertiary
```

**Typography:**

```
Display    Söhne / Inter Display      36 / 28 / 24
Headline   Inter                       20 / 18 / 16
Body       Inter                       15 / 14 / 13
Mono       JetBrains Mono              13 / 12 / 11    (IDs, codes, citations)
Numerals   tabular-nums everywhere     dashboard data
```

Single sans family for body (Inter, system font fallback). Mono for any identifier (NCT IDs, citations, CIK, accession numbers). One display variant for hero numbers (signal counts, scores). No Fraunces — too editorial for an analyst tool.

**Spacing scale** — 4px base. `1, 2, 3, 4, 6, 8, 12, 16, 24` × 4px. No arbitrary values.

**Radius** — 6 (control), 10 (card), 14 (elevated card), 999 (pill). No 0px sharp edges.

**Motion** — spring-based, natural easing, never decorative.
- `motion.fast` 120ms (button press, hover state)
- `motion.medium` 200ms (card expand, sheet open)
- `motion.slow` 320ms (route transition, dialog)
- `prefers-reduced-motion` honored everywhere.

**Shadows** — three layered low-opacity tokens; never stacked decoratively.

**Density modes** — `compact` (analyst, default for triage views) / `comfortable` (default for read views) / `spacious` (dashboards on large displays). User-configurable; persisted per device.

### 4.4 Component primitives

The shared `packages/ui` library exports a small set; modules compose from this set, do not invent new primitives ad hoc.

| Primitive | Purpose |
|---|---|
| `<Card>` | Single composition primitive for everything. Variants: flat, elevated, interactive. |
| `<SignalCard>` | The atomic CI unit. Shows entity → event-type → impact tier → confidence tier → 1-line summary. Used in digest, search, watchlist. |
| `<EvidenceStack>` | Ordered list of source documents for a signal, grouped by confidence tier, expandable. Used in signal detail, brief composition, reviewer queue. |
| `<CitationPill>` | Inline `[edgar:0]` / `[ct.gov:1]` / `[signal:abc]`. Source-color coded. Click to jump. |
| `<ConflictBadge>` | Shown when a cluster has ≥2 confirmed-tier sources disagreeing. |
| `<ScoreTile>` | Apple Health-style metric card. One large number, label, trend sparkline. |
| `<TimeRangeSelector>` | D / W / M / Q / Y / Custom. Persisted per surface. |
| `<EntityChip>` | Inline mention of a company/drug/trial/person — color-coded by type, links to entity dossier. |
| `<KbqTag>` | Visual tag for KBQ membership, used on signal cards. |
| `<CommandPalette>` | ⌘K. Cross-module navigation, action invocation, search. |
| `<KeyboardHint>` | Footer/floating hint of available shortcuts on the current surface. |
| `<DataTable>` | Virtualized, filterable, exportable. Stripe-Dashboard quality. Used for trackers. |
| `<Sheet>` | Right-edge drawer for signal detail / brief composition / reviewer panel. |
| `<EmptyState>` | Honest empty states — "No signals match your filter" + a way out. |
| `<FreshnessIndicator>` | "Catalog updated 14 min ago" / "Stale: last update 3 days ago." |

### 4.5 Surfaces — the analyst's day, designed

**PulseAction · CI module surfaces** (Phase 1):

1. **Daily Digest** — landing for the CI module. Score tiles (signal volume, high-impact count, queue depth) above the fold. Below: signal cards grouped by KBQ section, sorted by impact. Keyboard-first triage (j/k navigate, e escalate, f flag, x dismiss, ↵ open).
2. **Signal Detail** — `<Sheet>` from the right when a signal is opened, OR full-page route if direct-linked from an alert. Header (entity, event type, dual tiers, supersedence indicator if applicable). Body: evidence stack ordered by confidence tier, side-by-side conflict view if `cluster.status='conflict'`, historical strip (last N events for entity), peer strip (competitor events in same indication / TA), inline ask-the-agent.
3. **Watchlist** — Spotify-library-style. User's saved companies / drugs / indications / KBQ filters. Smart suggestions ("watched together"). Personal vs team vs subscription tabs.
4. **Alerts** — rule editor (entity / KBQ / impact-tier minimums / channel), delivery history, throttle controls, snooze.
5. **Reviewer Queue** — list of `signals.status='candidate'`. Side-by-side evidence. One-key approve/edit/reject. Audit trail visible.
6. **(P1.5) Brief Composer** — pick company × date range × KBQs → orchestrator runs → reviewer queue → versioned artifact.
7. **(P1.5) Trackers** — Trial / PDUFA / LOE / Deal / Exec / Earnings, as `<DataTable>` views with filters and exports.
8. **(P1.5) Connector Health** — admin surface for catalog freshness, error rates, doc volume.

**PulseAction · Research module surfaces** (refactored for consistency, not rebuilt):
- Workspace (chat + canvas, retains Fraunces for chat warmth — kept as Research-module brand affordance).
- Sessions (saved conversations).
- Saved Research (bookmarked dossiers, comparisons, landscapes).
- Catalog browse (already exists).

The Research module gets a *visual refresh* to align with the platform design tokens (drops `bg-slate-*` Tailwind utilities, adopts CSS variables from `packages/design-tokens`) but keeps its workflow shape.

---

## 5. SWE foundations

The platform's longevity depends on these getting set up right at the start. None of them are exotic; all of them must be conventions, not opinions.

### 5.1 Repository structure (monorepo)

```
pulseaction/
├── apps/
│   ├── landing/            # Mission Control SPA (React 19 + Vite)
│   ├── ci/                 # PulseAction · CI module SPA
│   └── research/           # PulseAction · Research module SPA (refactored from frontend/)
│
├── packages/
│   ├── design-tokens/      # CSS variables + JSON tokens, single source of truth
│   ├── ui/                 # Shared component primitives, Storybook-backed
│   ├── api-client/         # Codegen'd TypeScript client for platform APIs
│   ├── domain-types/       # Shared TS types mirrored from Pydantic models
│   └── eslint-config/      # Shared lint rules
│
├── services/
│   ├── platform/           # Horizontal API: catalog + intel
│   │   ├── catalog/        # Catalog Layer routes + services
│   │   ├── intel/          # Intelligence Layer routes + services
│   │   └── shared/         # Auth, RBAC, telemetry, cost metering
│   ├── module_ci/          # CI module routes + services + tables
│   ├── module_research/    # Research module routes + services + tables
│   └── workers/            # Background: connectors, dedup, scoring, alerting
│
├── packages-py/
│   ├── catalog/            # Connectors, normalizer, resolver, cross-linker, domain pack
│   ├── intelligence/       # Signals, clustering, rule engine, scoring, synthesis
│   └── domain_pharma/      # The pharma DomainPack
│
├── schema/
│   ├── platform/           # platform-owned migrations (catalog + intel tables)
│   ├── modules/
│   │   ├── ci/             # CI-owned migrations
│   │   └── research/       # Research-owned migrations
│   └── README.md           # migration ownership rules
│
├── ops/
│   ├── docker/
│   ├── railway/
│   ├── github-actions/
│   └── observability/
│
├── docs/
│   ├── adrs/               # Architecture Decision Records
│   ├── runbooks/
│   └── api/                # OpenAPI specs, generated
│
├── tests/
│   ├── e2e/                # Playwright across modules
│   ├── integration/        # Cross-service pytest
│   └── perf/
│
├── pnpm-workspace.yaml
├── pyproject.toml          # Python workspace via uv or hatch workspaces
├── turbo.json              # Build orchestration
├── .github/
└── CODEOWNERS
```

**Migration to this layout from today's flat repo is itself a sprint.** Phase 0 task. Done in one PR with codemod scripts; no behavior change.

### 5.2 Backend foundations

- **Language:** Python 3.13 (existing).
- **Framework:** FastAPI (existing). Factor `api/app.py` into platform router + module routers.
- **DB:** Postgres + pgvector (existing). Migration ownership split per the schema layout above.
- **Migrations:** owner-scoped numbering. Platform: `platform/0001_…`. CI: `module_ci/0001_…`. Conflict prevention via per-folder sequence.
- **Models:** Pydantic v2 everywhere. Mirrored to TS via `packages/domain-types` codegen.
- **Background jobs:** APScheduler (existing) → migrate to Dramatiq + Redis when scaling demands. Connectors are jobs; clustering is a job; provenance audit is a job.
- **Auth:** existing migration 034 extended with module-scoped permissions (`ci.read`, `ci.review`, `research.read`, `platform.admin`). RBAC checked at router level; tenancy isolation is row-level.
- **Multi-tenancy:** Phase 1 single-tenant; Phase 2 schema-isolated tenants; Phase 3 row-level if scale demands.
- **API style:** REST/JSON, OpenAPI-first. GraphQL Federation deferred until cross-module read patterns demand it.
- **Idempotency:** every connector write keyed by content hash. Every signal write keyed by `event_hash`. Re-runs are no-ops, never duplicates.

### 5.3 Frontend foundations

- **Stack:** React 19, TypeScript strict, Vite, TanStack Query (server state), Zustand (client state), TanStack Router.
- **Styling:** Tailwind v4 with design-token CSS variables only. **No raw Tailwind color utilities.** Color tokens come from `packages/design-tokens`. (Codified rule from existing CLAUDE.md, applied platform-wide.)
- **Component library:** `packages/ui`, Storybook-backed, every primitive has a story + visual test.
- **Forms:** react-hook-form + Zod schemas mirrored from Pydantic.
- **Animation:** Framer Motion, used sparingly. `prefers-reduced-motion` respected.
- **Testing:** Vitest + Testing Library (component), Playwright (e2e per module + cross-module).
- **A11y:** axe-core in CI, keyboard-first interactions for every primitive, focus management for `<Sheet>` and `<CommandPalette>`.

### 5.4 Quality gates

Every PR must pass:

| Gate | Tool | Blocking |
|---|---|---|
| Lint | ESLint, ruff | yes |
| Format | Prettier, ruff format | yes |
| Type check | tsc --noEmit, mypy | yes |
| Unit tests | Vitest, pytest | yes (coverage ratchet) |
| Component tests | Vitest + Testing Library | yes |
| Visual regression | Storybook + Chromatic (or Playwright snapshot) | yes |
| E2E smoke | Playwright (mission-control + 1-surface-per-module) | yes |
| Security scan | npm audit, pip-audit, Trivy on Docker images | non-blocking, alerted |
| API contract | OpenAPI diff vs main | yes |
| Migration check | Custom: forward migrations idempotent, reversible (where feasible) | yes |
| Performance budget | Lighthouse CI for landing + key surfaces | non-blocking, alerted |

### 5.5 Observability

- **Logs:** structured JSON, correlation IDs per request, propagated through agents and tools.
- **Metrics:** Prometheus-format, exported per service. Per-module dashboards (signal volume, latency, error rate); per-layer dashboards (catalog freshness, intelligence pipeline lag).
- **Traces:** OpenTelemetry. Cross-service trace IDs from frontend → API → agents → DB.
- **Errors:** Sentry on frontend; structured logs with stack on backend.
- **Cost:** LLM tokens metered per call, attributed to (module, agent, workflow). Monthly rollup vs budget.
- **Audit log:** every signal state change (created/scored/reviewed/shipped/superseded) writes an event-sourced row. User-or-agent attribution. Used for the analyst-visible "why was this superseded?" affordance.

### 5.6 Security & compliance

- **Secrets:** Railway env vars now; HashiCorp Vault or 1Password Secrets Automation when team grows.
- **Auth:** existing user table + email/password; Phase 2 add SSO (Google Workspace, Okta).
- **PII handling:** investigators / executives are PII. Apply minimal-fields-stored rule; documented retention.
- **Tier 3 vendor data:** access-controlled at the entity/signal level. Every Tier 3-derived signal carries a `licensed_source` flag. Outputs flag licensed content. Legal sign-off required before Tier 3 procurement.
- **Adversarial inputs:** press releases are marketing; trade press has agendas. Source-bias registry; extraction skeptical of evaluative claims; no social-media ingestion in Phase 1.
- **Provenance integrity:** the periodic audit job (intelligence layer) is also the security check — orphaned citations could indicate tampering or data corruption. Fail loudly.

### 5.7 Documentation

- **ADRs** in `docs/adrs/`, numbered, immutable. Every architectural decision documented (this doc is ADR-016).
- **Runbooks** in `docs/runbooks/` — connector failure, DB recovery (carrying forward April postmortem), alert delivery failure, LLM provider outage.
- **API docs** generated from OpenAPI; published per release.
- **Storybook** is the design-system documentation; every component documented inline.
- **CLAUDE.md** stays as the agent-facing convention doc; updated to reflect the monorepo layout and module model.

---

## 6. Phase 0 — prerequisites (hard gate before Phase 1 sprint 1)

Three weeks. Cannot start Phase 1 until all of these close.

| # | Task | Owner | Done criteria |
|---|---|---|---|
| P0.1 | Land SPEC-010 schema drift cleanup | backend | All known schema drifts resolved; migration 032+ applied to prod; no `column does not exist` errors in steward logs for 7 days. |
| P0.2 | Index audit on `market_events` and `entity_links` | backend + DBA | Read-pattern profile captured; missing indexes added; query plans regression-tested under representative load. |
| P0.3 | Decide `trust_score` vs `confidence_tier` | platform-team | ADR written; migration plan documented; either deprecation or coexistence rule explicit. |
| P0.4 | Build evaluation regression set | NLP + product | 50 hand-labeled historical events with expected signal output, evidence stack, impact tier. Stored as fixtures. CI runs weekly. |
| P0.5 | Reviewer staffing decision | product + ops | FTE count committed; SLA-to-FTE math signed off; queue-depth alert thresholds set. |
| P0.6 | Tier 3 procurement kickoff | product + legal | Owner named; Cortellis + AlphaSense procurement initiated; redistribution-clause questions filed. |
| P0.7 | Monorepo restructure | full-stack | Repo migrated to `apps/ + packages/ + services/` layout; all existing tests pass; no behavior change. |
| P0.8 | Design system bootstrap | frontend + design | `packages/design-tokens` published with full token set; `packages/ui` skeleton with first 5 primitives in Storybook (Card, Pill, SignalCard skeleton, EvidenceStack skeleton, ScoreTile). |
| P0.9 | Mission Control + module routing | full-stack | `/`, `/ci`, `/research` routes exist; auth gates module access; cross-module command palette stub. |
| P0.10 | API contract scaffolding | backend | OpenAPI spec for catalog (`/catalog/*`) + intel (`/intel/*`) drafted. Contract published to `packages/api-client`. |

Phase 0 is the floor. Skipping any of P0.1–P0.5 will surface as an outage in Phase 1.

---

## 7. Phase 1 — sprint plan (16 weeks, three swimlanes)

Three swimlanes run in parallel: **Data Catalog**, **Intelligence**, **Consumption (CI module + Mission Control + Research refactor)**. Sprints are 2 weeks. Each task has acceptance criteria + test gate.

### Swimlane A — Data Catalog Layer

| Sprint | Tasks |
|---|---|
| A1 (wks 1–2) | **A1.1** Refactor connector base for outbound CDC (`catalog.events.*` topic emission). **A1.2** Extend schema: `companies.aliases jsonb`, `external_ids jsonb`, `parent_company_id`. **A1.3** Extend `drugs` with `modality`, `atc_codes[]`, `ndc_codes[]`, `unii`, `chembl_id`, `drugbank_id`. **A1.4** Add `trials.status_history jsonb`. |
| A2 (wks 3–4) | **A2.1** SEC EDGAR 8-K item-code parser (Items 1.01, 2.02, 5.02, 8.01) — rule-based item header detection + LLM structured extraction on body. **A2.2** Schema-locked extraction outputs validated against Pydantic models. |
| A3 (wks 5–6) | **A3.1** Trial diff service: emit `trial_status_change` events from CT.gov daily delta. **A3.2** Trial acronym alias table seeded from `Other Study ID Numbers`. **A3.3** Press-release-as-readout extraction path. |
| A4 (wks 7–8) | **A4.1** DailyMed SPL connector + section-keyed parser. **A4.2** SPL section-level semantic diff → `label_change` events with structured change payload. **A4.3** FDA designations connector (orphan, breakthrough, fast track, priority review) — structured + press-release-driven. |
| A5 (wks 9–10) | **A5.1** Patents table + USPTO PatentsView connector + Orange Book linkage. **A5.2** LOE computation service. **A5.3** Per-outlet news connector split (BioPharma Dive, FiercePharma, Endpoints, Reuters, STAT, FirstWord). |
| A6 (wks 11–12) | **A6.1** EMA CHMP opinion scraper. **A6.2** `predicted_approval` derived event from CHMP positive. **A6.3** FDA Drug Discontinuation List connector → `product_discontinuation` events. |
| A7 (wks 13–14) | **A7.1** Per-connector freshness metrics + dashboard endpoint. **A7.2** Connector idempotency + retry framework. **A7.3** Catalog read-replica wiring for module reads. |
| A8 (wks 15–16) | Buffer / hardening / docs / runbooks. |

### Swimlane B — Intelligence Layer

| Sprint | Tasks |
|---|---|
| B1 (wks 1–2) | **B1.1** Create `signals` table + Pydantic models. **B1.2** Build skeleton clustering service with per-event-type windows. **B1.3** Anchor selection rule + conflict detection. **B1.4** Migrate `InsightEngine` outputs to write into `signals`. |
| B2 (wks 3–4) | **B2.1** Confidence-tier enum + derivation service (source-class × fact-type matrix). **B2.2** Tier corroboration modifier. **B2.3** Time-decay rule. **B2.4** Late-arriving high-tier promotion path with explicit `signal_updated` emission. |
| B3 (wks 5–6) | **B3.1** Impact-tier rule registry as YAML, hot-reload. **B3.2** Impact scoring composite (event base × entity priority × magnitude × recency × corroboration). **B3.3** Rule versioning + per-signal `rule_version_id`. |
| B4 (wks 7–8) | **B4.1** KBQ rule engine: hard rules (HR1.1, HR1.3, HR2.1, HR2.4) executed at extraction. **B4.2** Suppressed-candidate logging. **B4.3** Rule conflict detector. |
| B5 (wks 9–10) | **B5.1** Pattern detector — emits meta-signals (3 exec departures / 4 trial starts in TA / etc.). **B5.2** Negative-event detector — `expected_event_missed` from PDUFA + primary completion calendars. **B5.3** Transition aggregator — exec exit + arrival linking via `transition_id`. |
| B6 (wks 11–12) | **B6.1** Synthesis service v2: schema-locked LLM output, per-sentence citations, tier-aware hedging. **B6.2** Semantic citation validator (LLM-as-judge on sentence/cited-text pairs). **B6.3** Wire `CTXContextBuilder` ContextGuard as default for all module-facing synthesis. |
| B7 (wks 13–14) | **B7.1** Provenance audit job. **B7.2** `signals.superseded_by` + `supersedence_reason` UX semantics encoded (correction vs progression). **B7.3** Deal-termination event type. |
| B8 (wks 15–16) | **B8.1** Eval harness: weekly run against P0.4 regression set; Slack report. **B8.2** Cost meter per agent + workflow. **B8.3** Hardening / docs / agent-execution audit trail. |

### Swimlane C — Consumption Layer

| Sprint | Tasks |
|---|---|
| C1 (wks 1–2) | **C1.1** Mission Control landing skeleton (auth, module switcher, recent-activity strip). **C1.2** Cross-module command palette. **C1.3** Platform health tile (consumes `/catalog/health` + `/intel/health`). |
| C2 (wks 3–4) | **C2.1** CI module shell: route, layout, sidebar. **C2.2** `<SignalCard>` v1. **C2.3** `<EvidenceStack>` v1. **C2.4** `<ScoreTile>` + `<TimeRangeSelector>`. **C2.5** Hook signals API. |
| C3 (wks 5–6) | **C3.1** Daily Digest surface (F1) — score tiles, KBQ-grouped signal feed, keyboard-first triage (j/k/e/f/x/↵). **C3.2** Watchlist filter wired. **C3.3** Digest snapshot persistence (`digest_views`). |
| C4 (wks 7–8) | **C4.1** Signal Detail surface (F2) — header, evidence stack, conflict view, historical strip, peer strip. **C4.2** Inline ask-the-agent panel. **C4.3** Tagging + escalate / follow-up / dismiss actions. |
| C5 (wks 9–10) | **C5.1** Watchlist Manager (F3) — personal / team / subscription tabs, smart suggestions, bulk edit. **C5.2** Watchlist evaluation engine (intel side). |
| C6 (wks 11–12) | **C6.1** Reviewer Queue (F7) — list, side-by-side evidence, approve/edit/reject, audit trail. **C6.2** Reviewer-action telemetry. |
| C7 (wks 13–14) | **C7.1** Alert Center (F6) — rule editor, channels (email + Slack), delivery history, throttle controls, snooze. **C7.2** Alert delivery worker. **C7.3** Reviewer-gated channel for impact=high. |
| C8 (wks 15–16) | **C8.1** Research module visual refresh (drop slate-* utilities, adopt design tokens). **C8.2** Cross-module Recent Activity timeline live. **C8.3** Polish, a11y audit, perf budget enforcement. |

**Phase 1 ships:** F1 + F2 + F3 + F6 + F7 (analyst's day), MVP KBQs 1, 2, 4, 5, 9, 10 plus FDA designations and CRL detection bundled. **Brief Composer (F4), Trackers (F9), Connector Health admin (F8), and Ad-hoc Q&A (F5) are Phase 1.5** — shipped 4–6 weeks after Phase 1 launch, when signal quality has been tuned against the eval set.

---

## 8. Phase 1.5 — quality + secondary surfaces (~6 weeks)

After Phase 1 launches to a small group of analysts, before broad rollout:

- Iterate signal quality against the eval set.
- Tune impact rules with analyst feedback.
- F4 Brief Composer.
- F8 Connector Health admin.
- F9 Trackers (Trial / PDUFA / LOE / Deal / Exec / Earnings).
- F5 Ad-hoc Q&A (cross-module Signal-aware chat).

---

## 9. Phase 2 — coverage depth (~10 weeks, post-launch)

Phase 2 stops being a single sprint and becomes **a continuous connector pipeline**. Each new connector is its own mini-project. Order by analyst demand:

1. Per-company IR scrapers (top 20 priority cos).
2. Conference scrapers (ASCO, ESMO, AACR, ASH).
3. AdCom calendar.
4. HTA agencies (NICE, IQWiG, HAS).
5. CMS IRA implementation.
6. Payer formulary PDF diff (top 5 commercial payers).
7. EU CTR.
8. USPTO PTAB.
9. Strategic theme classifier.
10. Earnings call transcripts (Tier 2 fragile path; Tier 3 via AlphaSense if procured).

---

## 10. Phase 3 — Tier 3 + scale (procurement-gated)

Cortellis (Reg + Deals + Pipeline), Citeline, AlphaSense, Bloomberg, Evaluate, Medi-Span, Lex Machina, CB Insights, 50-state Medicaid. Owner-driven; Phase 1 doesn't depend on it.

---

## 11. Risks + mitigations (delta vs SPEC-015)

| Risk | New mitigation in this design |
|---|---|
| Two products on one data plane | **Solved by the layer split.** CI writes to its own tables; reads from intel via contract. No write contention with Research. |
| `trust_score` vs `confidence_tier` confusion | P0.3 forces an explicit ADR before Phase 1 starts. |
| Phase 2's 10-week estimate was wrong | Reframed as continuous post-launch, not a sprint. |
| Reviewer SLA implies hiring | P0.5 is a hiring decision gate. |
| Tier 3 procurement silently blocks Phase 2 | P0.6 names an owner and starts the cycle in week 1. |
| Eval story missing | P0.4 builds the regression set. Weekly run from B8.1. |
| LLM cost unbudgeted | B8.2 metered per agent + workflow; Mission Control surfaces monthly burn. |
| Adversarial inputs (PR marketing tone, biased outlets) | Source-bias registry in catalog; extraction skepticism for evaluative claims; no social-media in Phase 1. |
| Provenance integrity at read time | B7.1 provenance audit; orphan signals pulled from active digests until reviewed. |
| Module proliferation chaos | Module Contract (§2) + CODEOWNERS + per-module schema folders prevent ad-hoc growth. |
| Schema-evolution-by-committee | Single platform-team owns horizontal layers; modules cannot alter platform schema directly — only consume contracts. |

---

## 12. What we're explicitly *not* doing

- Rebuilding the existing 17 connectors. They stay; they get the contract surface in front of them.
- Rebuilding the 6-strategy entity resolver. It stays; we extend the alias table and seed trial acronyms.
- Forking `/research`. It stays as PulseAction · Research module. Visual refresh, no workflow change.
- Property graph DB (Neo4j etc.). Postgres + materialized edges has carried us to 600K+ links; revisit only if a query pattern demonstrates need.
- GraphQL Federation. REST + OpenAPI is fine for two modules. Reconsider when there are five.
- Multi-tenant isolation in Phase 1. Single-tenant; tenancy in Phase 2.
- Mobile apps. Responsive web yes; native deferred.
- Deep social media ingestion. Adversarial surface; defer until adversarial-robustness story exists.
- Replacing the existing test infrastructure. pytest + Vitest + Playwright is right; we extend coverage, not the framework.

---

## 13. Open decisions still owed

1. **Module names within PulseAction.AI** — platform brand is locked to *PulseAction.AI*. Open: do modules carry the descriptive `PulseAction · CI` / `PulseAction · Research` form, or get distinct product names (e.g., *Pulse* for CI, *Atlas* for Research)? Decision needed before C2 starts (week 3). See SPEC-017 D1.
2. **Light vs dark default** — proposal: light default, dark available, persisted per device. Confirm.
3. **Density default** — proposal: comfortable for read views, compact for triage views (Daily Digest, Reviewer Queue). Confirm.
4. **SSO timing** — Phase 1 email/pw, Phase 2 SSO. Confirm acceptable for early users.
5. **Pricing / commercial story** — is the platform per-module licensed, or one platform license? Affects auth model design.
6. **External users** — Phase 1 internal only? If pilot includes external CI analysts, RBAC + audit log requirements tighten.
7. **Reviewer queue: who are the reviewers?** — Pulled from CI analyst pool, or a dedicated reviewer role? Drives F7 design (single workflow vs role-switched).
8. **Naming for the Signal supersedence reasons** — proposed enum: `corrected | progressed | downgraded | retracted | merged`. Confirm.

These don't block Phase 0 starting. They block Phase 1 sprint planning.

---

## 14. The next concrete step

If this document is approved as the architectural commitment, the immediate next actions are:

1. **Phase 0 kickoff.** Assign owners to P0.1 through P0.10. Three-week timer.
2. **Open ADR-016** (this document, formalized) into `docs/adrs/`.
3. **Begin monorepo restructure (P0.7)** — single PR, codemod-assisted, no behavior change. This unblocks every later swimlane.
4. **Begin design-system bootstrap (P0.8)** in parallel — `packages/design-tokens` + first 5 `packages/ui` primitives in Storybook.
5. **Schedule the Phase 0 → Phase 1 gate review** for week 3 end. Phase 1 sprints start the day after the gate clears.

The recommendation is: approve, kick off Phase 0, hold daily 15-minute standups across the three swimlanes, and treat Phase 0's three weeks as a hard gate. Phase 1 can ship the analyst's day in 16 weeks if Phase 0 closes clean.

---

*ADR-016. Authored against SPEC-015 + comp_intel_2.md + comp_intelligence.md + the existing PulseAction.AI codebase. Supersedes the architectural-shape recommendation in SPEC-015 §0; KBQ analysis and gap matrix in SPEC-015 remain valid as Phase 1 implementation reference.*
