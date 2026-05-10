# SPEC-018 — Design System v2: PulseAction.AI UX Research + Implementation Spec

**Status:** Draft — 2026-04-29
**Audience:** Frontend engineering team executing Phase 1 swimlane C (Epic 8) + product / design stakeholders.
**Inputs:** SPEC-016 §3–4 (platform architecture, design system v1), SPEC-017 §D1–D8 (open decisions), `comp_intel_2.md` §3 (the analyst's hour-by-hour workflow), `comp_intelligence.md` §8 (CI workflows), the existing v1 scaffold under `apps/landing/`, `apps/ci/`, `packages/ui/`, `packages/design-tokens/`.
**Distinct from:** `SPEC_018_auth_roles.md` (a pre-existing spec that re-used the same number under the legacy numbering scheme).

---

## 0. What this document is

The user asked for "best designers" and "really forward-looking and valuable user interface." This SPEC is the design research and implementation spec that meets that bar.

It is **not**:
- A new color palette (tokens.json owns that).
- A brand identity exercise (the platform brand is locked to PulseAction.AI; modules are *Pulse* for CI and *Atlas* for Research — see §7).
- A pixel-perfect mockup. There are no images. Every layout idea is sketched in code blocks. Engineering reads this with reference URLs open in a second monitor.

It **is**:
- An opinionated design north-star essay (§1).
- An information-architecture sketch for every Phase 1 surface (§2).
- A complete primitive set with rationale and reference patterns (§3).
- A keyboard / interaction language (§4).
- Typography, density, motion craft beyond the v1 tokens (§5).
- Accessibility and responsive contracts (§6).
- Decisions on SPEC-017's eight open questions (§7).
- A visual-references appendix (§8).
- A Phase 1 component-build sequence the engineering team can execute (§9).

The v1 scaffold (Card / Pill / KbqTag / CitationPill / ScoreTile + Mission Control + CI Daily Digest) is honest but minimal. This document is the upgrade path.

---

## 1. North star + design principles

### 1.1 The product's emotional register

PulseAction.AI is **a professional instrument, not a feed**. The analyst is on it for 5–8 hours a day, three years running. It needs to feel like:

- *Bloomberg Terminal's seriousness*, without the typographic violence.
- *Apple Health's restraint*, scaled up for density.
- *Linear's keyboard reverence* — the workflow is so fluent that the mouse becomes optional.
- *Stripe Dashboard's data fluency* — tables that don't lie, tabular numerals everywhere.
- *Spotify's "library" mental model* — your watchlist is yours, accumulated, intimate.
- *Perplexity's trust theatre* — every claim has a citation pill, every citation jumps to evidence.

It explicitly is **not**:
- Instagram-style feed. The unit of consumption is the *Signal* (one event, multiple sources, scored), not a card with an emoji.
- Google News. We don't surface "5 articles about X"; we surface "Pfizer raised guidance, confirmed in 8-K + press + 2 wires."
- Dashboard kitsch. No gradients, no big colour blocks, no "your weekly stats!" copywriting.
- Slack. Notifications are second-class to triage. The chat-style chat lives in Atlas (research), not in Pulse.

### 1.2 Design principles (5)

**P1 — Glanceable hierarchy.**
A signal card answers four questions in under a second: *What entity? What event type? How important? How trusted?* The design must not require reading prose to triage. (Reference: Apple Health's "Activity rings" — the analyst is reading their portfolio's pulse the same way you read your move ring.)

**P2 — Provenance is a first-class UI affordance.**
Every claim, sentence, and number is one click from its source. Citation pills are inline, source-class colour-coded, hover-previews available. (Reference: Perplexity AI's inline citation pills — `[1] [2] [3]` style. Wikipedia's reference styling. Substack's footnote interactions.)

**P3 — Keyboard is canonical.**
Mouse-only paths exist (per accessibility) but every action has a keyboard binding and the binding is shown. Power users live in the command palette and j/k/x. (Reference: Linear, Things 3, Vim, Superhuman email.)

**P4 — Density is contextual.**
Triage views (Daily Digest, Reviewer Queue, Trackers) default to *compact*. Read views (Signal Detail, Brief Composer, Research Workspace) default to *comfortable*. Density is user-overridable per surface. (Reference: Linear's density toggle, Notion's "compact mode", Stripe Dashboard's row-height options.)

**P5 — Honest about gaps.**
When a question has no signal, the system says so explicitly. When supersedence happens, the prior signal stays visible, marked. When confidence is *inferred* not *confirmed*, language is hedged. (Reference: Perplexity's "I don't have information on..." pattern. Wikipedia's `{{citation needed}}`.)

### 1.3 What we explicitly reject

- **Pure-black dark mode.** OLED-tax, eye-strain on long sessions. Use a warm graphite (`#0E0F11–#14161A`).
- **Gradient-on-everything dashboards.** Restraint signals quality.
- **Decorative motion.** A signal card doesn't need a parallax effect to slide in. Spring-curve only when serving meaning (collapse/expand, focus migration).
- **Emoji in product UI.** Source-class indicators, severity glyphs, KBQ tags are typographic. (Storybook stories may use emoji for documentation playfulness; production UI does not.)
- **Verbose copywriting.** No "Welcome back, Kapil! Here's your daily digest. ✨" The user knows where they are.
- **"Your weekly summary" newsletter aesthetic.** This is a tool, not a Substack.
- **Tailwind colour utilities directly in components.** All colour goes through `var(--mz-*)` per the v1 rule.
- **Mixed icon sets.** Standardize on Lucide (already a dep). No emoji-as-icon, no clipart, no emoji-flag-as-country.
- **Date-time strings without explicit timezone affordance.** "Today" and "Tomorrow" are user-locale; everything else shows timezone or relative ("4h ago").

---

## 2. Information architecture — surface by surface

### 2.1 Mission Control (`/`)

**Pattern reference:** Arc browser sidebar + Mercury home + Apple iOS Today screen.

**Mental model:** "Where am I, what's my pulse, what's pending across modules."

```
┌──────────────────────────────────────────────────────────────┐
│  ◐ PulseAction.AI                              kapil@…  ⌘K  │ ← sticky header
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Good morning.                                               │ ← greeting
│  Wednesday, 29 April · 09:14 UTC+1                           │ ← absolute date
│                                                              │
│  ┌──────────────────────────┐  ┌──────────────────────────┐  │
│  │  PULSE                   │  │  ATLAS                   │  │
│  │  Competitive Intel       │  │  Pharma Research         │  │
│  │                          │  │                          │  │
│  │  12  2     4             │  │  3   14   4h             │  │
│  │  new HI    queue         │  │  runs mem  last          │  │
│  │                          │  │                          │  │
│  │  ●  Watchlist healthy    │  │  ● 3 active research     │  │
│  │  Open Pulse →            │  │  Open Atlas →            │  │
│  └──────────────────────────┘  └──────────────────────────┘  │
│                                                              │
│  PLATFORM                                                    │
│  ─────────                                                   │
│  Catalog freshness ✓ all sources < 24h                       │
│  Signals · 7d        612  ↑ 47                               │
│  Guard pass          89% on synthesis                        │
│  LLM spend           $1,847 / $5,000 this month              │
│                                                              │
│  RECENT — across modules                                     │
│  ─────────────────────────                                   │
│  ●─PULSE   2h  Pfizer 8-K Item 5.02 — CMO transition         │
│  ○─ATLAS   4h  "Tirzepatide MACE outcomes"                   │
│  ●─PULSE   6h  Novo CHMP positive — semaglutide              │
│  ●─PULSE   9h  BMS 8-K Item 1.01 — KRAS license-in deal      │
│  ○─ATLAS  11h  "GLP-1 cardio meta-analysis"                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**IA decisions:**
- *Two large module cards above the fold.* Glanceable. Each shows three numbers (one per module-meaningful KPI) + status pill + open CTA.
- *Platform health below.* Trust comes from transparency. Catalog freshness, intel volume, guard pass rate, LLM spend.
- *Recent activity is cross-module.* Tagged source dot (filled = Pulse, hollow = Atlas, future modules add shapes). Powers "did I see X today?" without forcing a switch.
- *⌘K command palette is the global escape.* Search, navigate, run actions, no module assumed.

**What's NOT here:** the digest itself, signal cards, watchlist UI, alerts UI. Those live in Pulse. Mission Control is a switcher with status, not a content surface.

### 2.2 Pulse — Daily Digest (`/ci`)

**Pattern reference:** Linear inbox + Apple Mail VIP filter + Superhuman triage.

**Mental model:** "10 minutes from sit-down to triaged. Keyboard-only path exists."

```
┌────────────────────────────────────────────────────────────────────────┐
│ [sidebar]    │ TODAY · 12 SIGNALS                              FILTER │
│              │ ─────────────────                                       │
│ DAILY DIGEST │                                                         │
│ Watchlist    │ ┌── REGULATORY · 9 signals ─────────────────────────┐   │
│ Reviewer Q   │ │                                                   │   │
│ Alerts       │ │ ●HIGH · CONFIRMED                          2h ago │   │
│ ─────────    │ │  Sarepta · CRL · NDA #218237 · SRP-9001          │   │
│ COMING NEXT  │ │  FDA cited additional efficacy data + CMC        │   │
│ Briefs       │ │  [edgar:0] [press:1] [news:2] [news:3]           │   │
│ Trackers     │ │                                                   │   │
│ Health       │ │ ●HIGH · CONFIRMED                          6h ago │   │
│              │ │  Novo · CHMP positive opinion                    │   │
│              │ │  semaglutide cardiovascular indication           │   │
│              │ │  [ema:0] [press:1]                                │   │
│              │ │                                                   │   │
│              │ │ ◌MED · CONFIRMED                           9h ago │   │
│              │ │  Pfizer · approval · oncology                    │   │
│              │ │  ...                                              │   │
│              │ └───────────────────────────────────────────────────┘   │
│              │                                                         │
│              │ ┌── M&A · 1 signal ─────────────────────────────────┐   │
│              │ │ ●HIGH · CONFIRMED                          9h ago │   │
│              │ │  BMS · license-in · KRAS · $50M / $500M / 8-14%  │   │
│              │ └───────────────────────────────────────────────────┘   │
│              │                                                         │
│              │ ┌── EXEC · 1 signal ────────────────────────────────┐   │
│              │ │ ●HIGH · CONFIRMED                          2h ago │   │
│              │ │  Pfizer · CSO Mikael Dolsten retirement          │   │
│              │ └───────────────────────────────────────────────────┘   │
│              │                                                         │
│              │ ─────────────────────────────────────────────────────   │
│              │ j/k navigate · ↵ open · e escalate · f flag · x dismiss │
│              │ ─────────────────────────────────────────────────────   │
└────────────────────────────────────────────────────────────────────────┘
```

**IA decisions:**
- *Grouping by KBQ section, not by time.* Time is an attribute, not a scaffold. The analyst's mental model is "what's happening in regulatory, what's happening in clinical."
- *Within a section, sort by impact tier descending, then recency.* Not by time. A medium-impact signal from 6:00 AM should not push down a high-impact signal from 22:00 the prior evening.
- *One row = one signal card = one event.* Never two signals collapsed into a paragraph.
- *Source pills are inline below the summary.* Click to jump to the originating doc. Source-class colour-coded.
- *No filter chrome by default.* Filter affordance is right-side, opens a panel. (Linear's pattern.)
- *Keyboard hints visible at the bottom.* No hidden bindings. Every binding is discoverable.

**Information density:** at `compact`, ~14–15 signal rows fit above the fold on a 13" screen. At `comfortable`, ~9.

### 2.3 Pulse — Signal Detail (`/ci/signals/:id`)

**Pattern reference:** Stripe Dashboard transaction-detail sheet + Superhuman email view + Notion document with right-side citations panel.

**Mental model:** "Give me everything about this single signal. I need to either escalate, dismiss, or send to someone."

```
┌──── Sheet (right edge, ~720px) ────────────────────────────────────┐
│                                                              ✕     │
│  Pfizer Inc. · 8-K Item 5.02                                       │
│  ┌──────────┐ ┌──────────┐ ┌────────────┐                          │
│  │ ●HIGH    │ │ CONFIRMED│ │ EXEC       │                          │
│  └──────────┘ └──────────┘ └────────────┘                          │
│                                                                    │
│  CMO transition: Mikael Dolsten retirement                         │
│  Effective June 30, 2026. Successor search initiated.              │
│                                                                    │
│  ┌─ EVIDENCE ─────────────────────────────────── 4 docs · sorted ─┐│
│  │  [edgar:0]  Pfizer 8-K Item 5.02 · 2026-04-15  CONFIRMED      ││
│  │   ▸ excerpt: "Mikael Dolsten, M.D., Ph.D., Chief Scientific…" ││
│  │  ─────────────────────────────────────────────────────        ││
│  │  [press:1]  Pfizer press release · 2026-04-15   CONFIRMED     ││
│  │   ▸ excerpt: "...effective June 30, 2026..."                  ││
│  │  ─────────────────────────────────────────────────────        ││
│  │  [news:2]   Reuters · 2026-04-15                REPORTED      ││
│  │   ▸ excerpt: "Pfizer's research chief to retire..."           ││
│  │  ─────────────────────────────────────────────────────        ││
│  │  [news:3]   FiercePharma · 2026-04-15           REPORTED      ││
│  └────────────────────────────────────────────────────────────────┘│
│                                                                    │
│  ┌─ ENTITY HISTORY (last 3 events for Pfizer) ─────────────────┐   │
│  │  Mar 2026  guidance raised FY2026 (financial)               │   │
│  │  Feb 2026  acquisition closed: Trillium (M&A)               │   │
│  │  Jan 2026  CFO succession (exec — same KBQ)                 │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌─ PEER CONTEXT ────────────────────────────────────────────────┐ │
│  │  Eli Lilly  Apr 20  CFO transition                          │ │
│  │  Moderna    Apr 12  CMO promotion                           │ │
│  │  → 3 exec_change events in this TA cluster · 30d window      │ │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ┌─ ASK ATLAS ───────────────────────────────────────────────────┐ │
│  │  > What does this mean for Pfizer's pipeline reprioritisation? │
│  │  ────────────────────────────────────────────────────────       │
│  │  [Atlas answers here, with cited Signals]                     │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
│  ─── Actions ─────────────────────────────────────────────────     │
│  [E] Escalate   [F] Flag for follow-up   [B] Promote to brief      │
│  [X] Dismiss as noise                                              │
└────────────────────────────────────────────────────────────────────┘
```

**IA decisions:**
- *Right-edge sheet, not a route push.* The user retains the digest list behind it. ESC closes; ↑↓ navigates between signals without leaving the sheet.
- *Tier badges directly under the entity name.* Three badges: impact, confidence, KBQ. Glanceable.
- *Evidence stack is the centerpiece.* Ordered by confidence tier descending. Source-class colour. Click expands; double-click opens raw doc in a new sheet.
- *Entity history strip.* Last 3–5 events for the same entity, regardless of KBQ. Lets the analyst see the pattern.
- *Peer context strip.* Top-3 related signals from the cluster (same KBQ, related entity). When pattern-detection fires (3 exec changes in 30d in same TA), the meta-signal banner appears here.
- *Ask Atlas inline.* The CI module embeds an Atlas (Research) Q&A widget so the analyst can ask "what does this mean" without context-switching. The answer cites Signals (not raw docs) — proving the cross-module substrate is real.
- *Action row at the bottom, keyboard-bound.* Linear pattern.

### 2.4 Pulse — Watchlist Manager (`/ci/watchlist`)

**Pattern reference:** Spotify Liked Songs + Things 3 Areas + Notion database with views.

**Mental model:** "These are MY entities. Accumulated. Curated. Smart suggestions exist but human owns the list."

Three tabs at the top: **Personal**, **Team**, **Subscriptions**. Each is a list of entity rows (companies / drugs / indications / KBQ filters). Inline edit. Drag-to-reorder. Add via fuzzy search.

Smart suggestions — *"companies often watched together"* — appear as a quiet sidebar, not as Notification-style cards. (Reference: Spotify's "Made For You", but professional. NOT Spotify's auto-add behaviour.)

### 2.5 Pulse — Reviewer Queue (`/ci/review`)

**Pattern reference:** GitHub PR review screen + Linear triage + Stripe Radar dispute review.

**Mental model:** "10–20 high-impact signals, side-by-side evidence, fast verdict."

```
┌────────────────────────────────────────────────────────────────────────┐
│ Reviewer Queue · 4 pending                       SLA: 2 business hours │
├────────────────────────────────────────────────────────────────────────┤
│ ┌─ Signal #abc123 ──────────────────────────────────────────────────┐  │
│ │ Pfizer · CMO transition · EXEC · ●HIGH                           │  │
│ │                                                                  │  │
│ │ ┌───────────────────────┬────────────────────────────────────┐   │  │
│ │ │ DRAFT NARRATIVE        │ EVIDENCE                          │   │  │
│ │ │                        │                                   │   │  │
│ │ │ Pfizer disclosed CSO   │ [edgar:0] Pfizer 8-K Item 5.02   │   │  │
│ │ │ Mikael Dolsten's       │  "Mikael Dolsten, M.D., Ph.D.,   │   │  │
│ │ │ retirement, effective  │   Chief Scientific Officer and   │   │  │
│ │ │ June 30, 2026[edgar:0].│   President, Worldwide Research  │   │  │
│ │ │ The company has begun  │   ...notified the Company of his │   │  │
│ │ │ a search for the       │   decision to retire from the    │   │  │
│ │ │ successor[press:1].    │   Company, effective June 30..." │   │  │
│ │ │                        │                                   │   │  │
│ │ │                        │ [press:1] Pfizer press release   │   │  │
│ │ │                        │  "...The Company has commenced a │   │  │
│ │ │                        │   search for his successor."     │   │  │
│ │ └────────────────────────┴───────────────────────────────────┘   │  │
│ │                                                                  │  │
│ │ [✓ Approve]  [✎ Edit]  [✗ Reject]  [↩ Defer]    j↓ k↑ ↵ approve │  │
│ └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
```

**IA decisions:**
- *Side-by-side narrative + evidence.* Like a GitHub diff. Reviewer scans both at the same time.
- *Citation pills in the narrative are clickable and SCROLL the evidence panel to the cited source.* Reference: Notion's `@` mentions; GitHub's `#1234` links.
- *Approve / Edit / Reject / Defer in keyboard reach.* The reviewer's hand never leaves the keyboard.
- *SLA indicator at the top.* "2 business hours" — sets the temperature.
- *Conflict mode.* When `cluster.status='conflict'`, two evidence panels appear side-by-side with a CONFLICT badge between. Reviewer picks an anchor; that's how the disagreement gets resolved.

### 2.6 Pulse — Alert Center (`/ci/alerts`)

**Pattern reference:** Stripe Webhooks + Linear notifications settings + Slack workflow rules.

**Mental model:** "I configure when I get pulled out of triage."

Three tabs: **Rules**, **Delivery History**, **Channels**. Rule editor is a quiet form (no fanfare): scope (entity / KBQ / impact tier), delivery (email / Slack / Teams), throttle (max-N-per-day per scope), reviewer-gating toggle for impact=high. Delivery history is a Stripe-style table.

### 2.7 Atlas — Workspace (`/research`, refactored)

**Pattern reference:** Notion document + Anthropic Claude artifacts + Perplexity Pro.

**Mental model:** "I'm asking the graph a question. The answer cites Signals. I can branch off into a research run if I want depth."

Existing chat+canvas pattern stays — it's the right shape for ad-hoc Q&A. Visual refresh aligns with PulseAction's tokens (drop the slate-* utilities; adopt CSS variables). The chat keeps Fraunces-style warmth as Atlas's brand affordance — distinct from Pulse's professional graphite-blue register.

### 2.8 (Phase 1.5) Brief Composer (`/ci/briefs/new`)

Defer to Phase 1.5 (after signal quality is tuned). Mental model: Notion-style document compose + Stripe-style review queue + DOCX export. Reference: Stripe's quote editor; Linear's docs feature.

---

## 3. Component primitive set v2

The v1 set in `packages/ui/`:
- `Card` (flat | elevated | interactive)
- `Pill` (tone × size × subtle)
- `KbqTag`
- `CitationPill`
- `ScoreTile`

The v2 additions, ordered by build dependency:

### 3.1 Foundation (build first, no deps on each other)

| Primitive | Purpose | Variants | Reference patterns |
|---|---|---|---|
| `Sheet` | Right-edge drawer for detail views | size: sm/md/lg; collapsible; nested-allowed | Stripe Dashboard sheet, Linear issue sheet |
| `Kbd` | Inline keyboard glyph | single key, chord, with-modifier | macOS HIG, Linear |
| `Tooltip` | Hover reveal | with delay, positioning, arrow-optional | Radix Tooltip primitive |
| `Popover` | Click reveal | anchor, positioning | Radix Popover |
| `Tabs` | Surface tabs | underlined, segmented, vertical | Stripe Dashboard tabs |
| `Toggle` | Boolean control | switch, checkbox-row | Apple iOS toggle |
| `Avatar` | Person/entity glyph | initials, image, gradient-fallback | Linear |
| `EmptyState` | Honest empty | with primary action, with illustration-allowed | Notion empty docs |
| `LoadingSkeleton` | Pre-fetch placeholder | rectangular, text-line, table-row | Stripe Dashboard skeletons |
| `FreshnessIndicator` | "Updated 14m ago" | inline, prominent (header) | Stripe Dashboard event timestamp |

### 3.2 Composition (depend on foundation)

| Primitive | Purpose | Variants | Reference patterns |
|---|---|---|---|
| `EntityChip` | Inline entity reference | drug / company / trial / person / patent / deal — one accent each | Notion `@` mentions, GitHub `@user` |
| `EvidenceItem` | One row in the evidence stack | citation pill + title + excerpt + tier badge + timestamp | Perplexity citation row, Notion linked pages |
| `EvidenceStack` | Ordered evidence list | grouped by confidence tier; expand/collapse; conflict-badged | Perplexity sources panel, Wikipedia refs |
| `ConflictBadge` | Visual marker for disagreement | inline, with hover tooltip | unique to PulseAction |
| `ImpactPill` | High/medium/low impact glyph | dot + label, dot-only at small | unique |
| `ConfidencePill` | Confirmed/reported/inferred/disputed glyph | dot + label, dot-only at small | Wikipedia `{{citation needed}}` style |
| `KbqTag` (already shipped, gets variants) | KBQ membership | full label / abbreviated | unique |
| `TimeRangeSelector` | D / W / M / Q / Y / Custom | persisted per surface, keyboard-bindable | Apple Health, Stripe Dashboard |

### 3.3 Signal-centric (the heart)

| Primitive | Purpose | Variants | Reference patterns |
|---|---|---|---|
| `SignalCard` | The atomic CI unit | digest / detail-header / brief-fragment / alert / watchlist-row | unique to PulseAction |
| `SignalRow` | Compact single-line signal | digest-row / search-result | Linear inbox row, Superhuman triage row |
| `SignalSupersededIndicator` | "This was updated by [link]" | banner above older signal | unique |
| `CitedSentenceParagraph` | Synthesis paragraph with inline citations | sentences as JSON; each pill clickable | Perplexity answer paragraph |
| `ProvenanceRail` | Right-side citations panel that scrolls in sync | for brief composer + signal detail | Notion's pages-linked rail |

### 3.4 Tabular + dashboard

| Primitive | Purpose | Variants | Reference patterns |
|---|---|---|---|
| `DataTable` | Virtualized, sortable, filterable | default + density-aware | Stripe Dashboard tables |
| `FilterChip` | Active filter indicator with × | inline, count badge | Linear filter chips |
| `FilterPanel` | Right-side filter drawer | groupable, multi-select | Linear right panel |
| `Tracker` | Calendar-or-table view of events | PDUFA tracker, LOE tracker, deal tracker | Stripe Dashboard timeline |
| `ScoreTile` (already shipped, gets variants) | Glanceable metric | trend / sparkline / compact | Apple Health tile, Wealthfront card |
| `DataSparkline` | 30-day trend chart | inline (in tile), full-width | GitHub contribution sparkline |
| `LineChart` / `BarChart` | Trend / comparison charts | with explicit zero-baseline rule | unique (NOT Recharts default — see §5.6) |

### 3.5 Navigation + commands

| Primitive | Purpose | Variants | Reference patterns |
|---|---|---|---|
| `CommandPalette` | ⌘K — fuzzy search, scoped commands, recent | with sections, recent-items tracked | Linear ⌘K, Raycast, Arc |
| `KeyboardHint` | Footer of available shortcuts | always-visible (default) / on-demand | Notion, Linear |
| `Breadcrumb` | Path back up | with overflow ellipsis | Notion, GitHub |
| `Sidebar` (CI shell already has v1) | Module nav + workflow nav | collapsible, active-item glyph | Spotify, Arc |
| `NavItem` | Single sidebar entry | with kbd hint, with badge | Linear, Spotify |

### 3.6 Forms + input

| Primitive | Purpose | Variants | Reference patterns |
|---|---|---|---|
| `Input` | Text field | sizes, with-icon, with-clear | Stripe Dashboard input |
| `Select` | Native+styled select | typeahead-search variant | Linear, Radix Select |
| `Combobox` | Autocomplete with results | for entity-add to watchlist | Linear, Algolia |
| `RuleEditor` | Alert rule composer | scope picker → predicate → channel | unique-ish (Stripe Radar) |

### 3.7 Status + feedback

| Primitive | Purpose | Variants | Reference patterns |
|---|---|---|---|
| `Banner` | Surface-wide notice | info / warning / danger / promo | Stripe Dashboard banners |
| `Toast` | Transient notification | success / error / info | Linear toasts |
| `ProgressBar` | Long-running task feedback | indeterminate / determinate | macOS HIG |
| `EmptyState` (foundation, included here for visibility) | When data is absent | with primary action | Notion empty doc |

**Total v2 primitives:** ~38. Of those, 5 are shipped (v1). 33 are net-new.

---

## 4. Interaction language

### 4.1 Global keymap

| Key | Action |
|---|---|
| ⌘K / Ctrl+K | Open command palette |
| ⌘. / Ctrl+. | Quick switcher (between modules) |
| ? | Toggle keyboard cheatsheet for current surface |
| ESC | Close sheet / popover / modal |
| / | Focus surface search input (Daily Digest filter, Watchlist search) |

### 4.2 Daily Digest keymap

| Key | Action |
|---|---|
| j / ↓ | Next signal |
| k / ↑ | Previous signal |
| ↵ | Open signal detail (sheet) |
| e | Escalate (paint blue dot, send to senior queue) |
| f | Flag for follow-up (paint amber dot) |
| x | Dismiss as noise (move to dismissed) |
| b | Promote to brief draft |
| u | Undo last action |
| g d | Go to Daily Digest (from anywhere in CI) |
| g w | Go to Watchlist |
| g r | Go to Reviewer Queue |
| g a | Go to Alerts |

### 4.3 Signal Detail (sheet) keymap

| Key | Action |
|---|---|
| ↑ / ↓ | Previous / next signal in the digest |
| ESC | Close sheet, return to digest |
| ↵ | Default action for current focus |
| 1–9 | Jump to evidence item N |
| / | Focus the "Ask Atlas" inline input |

### 4.4 Reviewer Queue keymap

| Key | Action |
|---|---|
| j / k | Next / previous signal |
| a / ↵ | Approve |
| e | Edit narrative inline |
| r | Reject (with reason picker) |
| d | Defer (back to queue) |
| 1–9 | Jump to evidence item N for current signal |

### 4.5 Modal vs Sheet vs Popover

- **Modal:** rare. Confirm-destructive only (e.g., bulk dismiss 50 signals). Body scroll locked.
- **Sheet:** the default for *detail* views. Right-edge, ~520–720px wide, stack-allowed up to 2 deep. Body of the surface remains visible behind, dimmed.
- **Popover:** for hover-or-click reveals (citation preview, entity chip detail, kbd hint expansion). Anchored. ESC dismisses.

### 4.6 Hover and focus states

- **Hover:** subtle background tone-shift (1 step lighter / darker depending on theme), no border change. Cursor changes to pointer for interactive cards.
- **Focus (keyboard):** 2px solid ring at `--mz-color-accent`, 2px offset, radius matching the element's radius. Single visual language across the platform (already in `packages/ui/src/styles.css` — extend everywhere).
- **Active (pressed):** background drops one tone, scale: 0.99 over 80ms.

---

## 5. Typography, density, motion

### 5.1 Type stack

Already in v1 tokens: Inter (sans), Inter Display (display), JetBrains Mono (mono).

**Decisions on usage:**
- **Display** (Inter Display): hero numbers in ScoreTile + module-card stats + section H1 only. Never body.
- **Sans** (Inter): everything else.
- **Mono** (JetBrains Mono): IDs (NCT, CIK, DOI, application_number), citation pills, kbd glyphs, source pills, KBQ tags. Never body.
- **Tabular numerals** (`font-feature-settings: 'tnum'`): every column of numbers in tables, every score, every percentage. Already enabled globally in `packages/ui/src/styles.css`.

**Size discipline:**
- Display sizes (36/28/24) used sparingly. Most numbers go in headline-1 (20).
- Body-3 (13) is the digest-row default. Body-2 (14) is signal-detail body. Body-1 (15) is Atlas chat output and brief composer.
- Mono-3 (11) for citation pills + KBQ tags. Mono-2 (12) for IDs in detail views.

### 5.2 Density toggle

Per SPEC-017 D3, density default per surface:

| Surface | Default | User override available? |
|---|---|---|
| Mission Control | comfortable | yes |
| Daily Digest | compact | yes |
| Signal Detail | comfortable | yes |
| Watchlist | compact | yes |
| Reviewer Queue | compact | yes |
| Alert Center | comfortable | yes |
| Trackers | compact | yes |
| Brief Composer | comfortable | yes |
| Atlas Workspace | comfortable | yes |

Persisted per device in localStorage under `pulse:density:<surface>`.

### 5.3 Motion craft

**Durations** (already in v1 tokens):
- `--mz-duration-fast` 120ms — hover, button press
- `--mz-duration-medium` 200ms — sheet open, card expand, popover
- `--mz-duration-slow` 320ms — route transition, dialog

**Curves:**
- `--mz-ease-spring` `cubic-bezier(0.34, 1.56, 0.64, 1)` — for state changes that feel physical (sheet open, card expand)
- `--mz-ease-standard` `cubic-bezier(0.4, 0, 0.2, 1)` — for property animations (color, opacity)
- `--mz-ease-decelerate` for entries
- `--mz-ease-accelerate` for exits

**Specific gestures:**
- **Sheet open**: `translateX(100%) → translateX(0)` over 200ms, spring curve, with concurrent backdrop fade-in (`opacity 0 → 0.4`) over 200ms standard curve.
- **Sheet close**: same but reversed; spring removed (felt rubber-bandy on close — exit should accelerate out).
- **Signal card hover**: background tone-shift 120ms standard.
- **Signal card click→open**: card scales briefly (0.98 → 1.0 over 80ms) before sheet opens. Confirms the click landed.
- **Loading skeleton shimmer**: 1.6s linear infinite, very subtle (8% opacity range).
- **Toast enter**: slide up + fade in, 200ms decelerate.
- **Toast exit**: slide down + fade out, 160ms accelerate.

**Reduced motion** (`prefers-reduced-motion: reduce`):
- All durations clamp to 0ms (already in v1 tokens).
- Sheet shows/hides instantaneously.
- Loading skeleton becomes static (no shimmer).
- Hover background changes still occur (functional, not decorative).

### 5.4 Sound

None. We are professional analyst tooling, not Slack. (Reference: Apple iOS muted system sound by default; Stripe Dashboard makes no sound.)

### 5.5 Theme switching

- **Light** is default per SPEC-017 D2. Soft-warm canvas (`#FAFAF7`).
- **Dark** is opt-in via toggle, persisted per device in localStorage `pulse:theme`.
- **System preference** is honoured on first load only — after that, user override wins (so the setting stays where the user put it).
- **Module accent** (CI blue / Research amber) follows the active module via `[data-module]` on `<html>`. Already in v1 tokens.

### 5.6 Charting

`packages/ui` does NOT export raw Recharts. We export a thin opinionated wrapper that enforces:
- Always show the zero baseline on bar charts (no truncated y-axis).
- Tabular numerals on axes.
- Confidence intervals shown as a faded band, never as separate "low" and "high" lines.
- One series per chart by default. Multi-series allowed but requires explicit `series` prop with a legend.
- Hover tooltip uses our `Popover` primitive, not Recharts default.

Reference: Stripe Dashboard charts. Substack analytics charts. NOT GitHub Insights (which does the truncated-y-axis thing and confuses the eye).

---

## 6. Accessibility + responsive

### 6.1 WCAG AA minimum

- All text contrast ≥ 4.5:1 (normal) / 3:1 (large). v1 tokens are in compliance; verify with `axe-core` in CI.
- Focus ring visible on every interactive element.
- No color-only signals — every tier badge has both colour AND a glyph or label.
- Form inputs always have `<label>`.

### 6.2 Keyboard-only flows

The entire analyst's day must be keyboard-driveable end-to-end:

1. ⌘K → open palette → "open daily digest" → ↵
2. j / k through signal list, ↵ to open
3. In sheet: 1–9 to jump to evidence, ↑/↓ for siblings, ESC to close
4. e to escalate, f to flag, x to dismiss
5. ⌘K → "compose brief" → form fields all keyboard

**Test gate:** `apps/ci` ships an e2e test (Playwright) where the entire critical analyst flow is performed with keyboard only.

### 6.3 Screen reader

- Live region (`aria-live="polite"`) on the Daily Digest header announces "12 signals, 2 high-impact" on load and on update.
- Signal cards announce as `"Pfizer, exec change, high impact, confirmed, 2 hours ago"` (via aria-label composed from the four tiers + entity + age).
- Sheet open/close announces ("Signal detail opened" / "Signal detail closed").
- Citation pills announce as `"Citation: SEC EDGAR document 0"` (the Pill is `<button>` with aria-label).

### 6.4 Responsive breakpoints

Analysts use desktop primarily (>1280px). Tablet (768–1279px) is partial — primary triage flows must work; trackers and brief composer are desktop-only at MVP.

| Breakpoint | Behaviour |
|---|---|
| ≥1280 | Full layout. Sidebar 232px + content. Sheet 720px. |
| 768–1279 | Sidebar collapses to 64px icon bar (hover-expand). Sheet 100% width on narrower screens. Trackers / Brief Composer show "best viewed on desktop" banner. |
| <768 (mobile) | **Alerts only.** Mobile users get a stripped-down alert deep-link view. Other surfaces show "Open in desktop" CTA. Phase 1 scope explicitly excludes mobile triage. |

### 6.5 Internationalization

Phase 1: English only. UI strings extracted into `packages/ui/i18n/en.json` so future locales are mechanical.

Date/time:
- Absolute timestamps formatted per user locale via `Intl.DateTimeFormat`.
- Relative ("4h ago") capped at 24h then switches to absolute.
- Server-side stores all timestamps in UTC; UI converts to user's `Intl.DateTimeFormat().resolvedOptions().timeZone`.

---

## 7. Decisions register — SPEC-017 resolutions

This section makes concrete recommendations on D1–D8.

### D1 — Module names ✅

**Decision: Distinct product names.** *Pulse* for CI, *Atlas* for Research. Co-located platform mark "PulseAction.AI · Pulse" / "PulseAction.AI · Atlas" in the header at headline-3 size. Module name dominates; platform name is sub-mark.

Rationale: pharma analysts say "did you check Pulse this morning?" — naturally. *Atlas* maps to graph/exploration semantics. Reserved future names: *Compass* (Regulatory), *Beacon* (Market Access), *Forum* (KOL).

### D2 — Light vs dark default ✅

**Decision: Light default**, with `prefers-color-scheme: dark` honoured on first load and a manual toggle persisted per-device.

Rationale: Light is the right default impression for a new commercial product. Dark mode is one click away for analysts who prefer it. Match Apple HIG.

### D3 — Density per surface ✅

**Decision: per the table in §5.2.** Compact for triage (Digest/Watchlist/Reviewer/Trackers); comfortable for read views (Mission Control / Signal Detail / Brief / Atlas).

User can override per surface, persisted per device.

### D4 — SSO timing ⚠️

**Recommendation: Email/password Phase 1; SSO Phase 2.** Migration 034 (`users_and_auth`) already exists. Phase 2 adds Okta (the most common enterprise IdP for pharma).

Magic-link is rejected — some enterprise email gateways block them; not standard for daily-use tools.

### D5 — Commercial model ⚠️

**Recommendation: Per-module licensing.** Each module is sold separately. Mission Control's empty state shows "Discover Pulse" / "Discover Atlas" cards for non-licensed modules with marketing copy.

Per-module pricing aligns with the platform thesis (each module is its own product on shared substrate). RBAC complexity is real but we're paying for it anyway because of D7.

### D6 — External pilots in Phase 1 ⚠️

**Recommendation: Internal-only Phase 1.** 4–8 internal analysts. Onboard one external pilot at Phase 1.5 (signal quality stable). Going external before signals are accurate damages reference value.

### D7 — Reviewer role ⚠️

**Recommendation: Hybrid model.** Dedicated reviewer (0.3–0.5 FTE senior CI lead) for impact=high signals → 2-business-hour SLA. Analysts self-review impact=medium with random spot-checks by the dedicated reviewer. Impact=low auto-ships.

This is the only configuration that hits the SLA at sustainable cost. Pure-analyst-pool review burns triage time; pure-dedicated bottlenecks on absences.

### D8 — Supersedence enum ✅

**Decision: 5-value enum** as proposed: `corrected | progressed | downgraded | retracted | merged`. Each has distinct UX semantics:

| Value | UI |
|---|---|
| `corrected` | Old hidden in active digest, link "see correction" |
| `progressed` | Both shown in entity history strip |
| `downgraded` | Still visible with tier-badge change |
| `retracted` | Old struck through, prominent retraction notice |
| `merged` | Old soft-hidden, evidence absorbed into new |

Matches what migration 037 (signals table) already encodes in its CHECK constraint.

---

## 8. Visual references appendix

| Reference | What we take | URL |
|---|---|---|
| **Apple Health** | Score-tile glanceability; D/W/M/Q/Y time-bucket selector; activity-ring glyph as prior art for impact gauges. | https://www.apple.com/ios/health/ |
| **Oura app** | Soft-dark mode (warm graphite, not pure black); score-of-the-day pattern; contributing-factors strip below the score. | https://ouraring.com/app |
| **Linear** | Keyboard-first reverence; ⌘K command palette; filter chips below toolbar with active count; density modes. The single biggest pattern source. | https://linear.app |
| **Things 3** | Typography craftsmanship; quiet card surfaces; spring-curve micro-interactions. | https://culturedcode.com/things/ |
| **Stripe Dashboard** | Tabular data done right; tabular numerals throughout; right-edge sheet for transaction details; banner pattern; chart conventions. | https://stripe.com/docs/dashboard |
| **Vercel Dashboard** | Multi-app composition; deploy timeline UX; project switcher (analogous to Mission Control). | https://vercel.com |
| **Figma** | Multi-pane composition; command palette; contextual right panel (analogous to Sheet). | https://figma.com |
| **Spotify desktop** | Library mental model for Watchlist; sidebar nav with collections; "Made For You" suggestions (used selectively, never auto-add). | https://spotify.com |
| **Arc browser** | Sidebar with module/space switching; command bar; multi-context navigation. | https://arc.net |
| **Notion** | Block composition; `@` mention chips; right-side citations rail in linked pages. | https://notion.so |
| **Mercury (banking)** | Card-based dashboard with one-clear-number-per-card; restraint; tabular numerals. | https://mercury.com |
| **Wealthfront / Robinhood** | One-tile-one-metric dashboard composition; trend sparklines inline with cards. | https://wealthfront.com / https://robinhood.com |
| **Substack reader** | Feed triage mechanics — mark-as-read, per-source filters. | https://substack.com |
| **Perplexity AI** | Inline citation pills (`[1] [2]`); source pop-overs; trust theatre. THE primary reference for our citation UX. | https://perplexity.ai |
| **Elicit** | Research grounding UX; per-claim citations. | https://elicit.com |
| **Wikipedia reference styling** | Footnote hover preview; `{{citation needed}}` honesty pattern. | https://en.wikipedia.org |
| **Apple HIG (motion + a11y)** | Reduced-motion handling; focus-visible patterns; respect-system-preference defaults. | https://developer.apple.com/design/human-interface-guidelines/ |
| **Material Design 3 motion** | Curve definitions (we use a subset). | https://m3.material.io/styles/motion |
| **Superhuman** | Triage row anatomy; keyboard-first; "the next one" implicit-flow. | https://superhuman.com |
| **GitHub PR review screen** | Side-by-side narrative + evidence pattern; line-anchored comments analogous to citation pills. | https://github.com |

---

## 9. Phase 1 implementation backlog (mapped to swimlane C sprints)

Engineering reads this section to plan sprint-by-sprint primitive build.

### Sprint C1 — Mission Control + Foundation (week 1)
*Already partially shipped in v1 scaffold; this sprint hardens.*

| Primitive | Dependencies | Acceptance | References |
|---|---|---|---|
| Theme + density runtime | `@pulse/design-tokens` | `data-theme` + `data-module` + `data-density` switch on `<html>`; localStorage persistence; ` prefers-color-scheme` honoured on first load | Apple HIG |
| `Kbd` | none | macOS-style key glyph; chord support (⌘K) | Linear |
| `Tooltip` | none | Radix-backed; hover delay 600ms; arrow optional | Radix |
| `Popover` | none | Radix-backed; ESC dismiss; focus-trap-optional | Radix |
| Mission Control v2 | above + existing v1 cards | Hardened header, real auth gate, `⌘K` works | Mercury, Vercel |

### Sprint C2 — Signal primitives (weeks 2–3)
*Highest-leverage sprint. This is what makes Pulse Pulse.*

| Primitive | Dependencies | Acceptance | References |
|---|---|---|---|
| `EntityChip` | `Tooltip` | One per entity type with accent colour; hover shows entity-summary popover | Notion @, GitHub @user |
| `ImpactPill`, `ConfidencePill` | foundation | Dot-glyph + label; aria-label includes tier name | Wikipedia citation needed |
| `EvidenceItem` | `CitationPill`, `ConfidencePill` | Source colour-coded; expandable; double-click opens raw | Perplexity row |
| `EvidenceStack` | `EvidenceItem` | Grouped by tier desc; conflict-mode side-by-side; aria-tree | Perplexity sources |
| `SignalCard` | above | 5 variants (digest/detail/brief/alert/watchlist); responsive at all densities | unique to Pulse |
| `SignalRow` | foundation | Compact 1-line version; keyboard navigable | Linear inbox |
| `KbqTag` variants | already exists | full / abbreviated / icon-only; tooltip-on-truncate | unique |
| `ConflictBadge` | foundation | Inline marker; tooltip explains; shown only when `cluster.status='conflict'` | unique |

### Sprint C3 — Daily Digest live (weeks 4–5)
| Primitive | Dependencies | Acceptance | References |
|---|---|---|---|
| Daily Digest page | C2 primitives + signals API | Live data; KBQ-grouped; keyboard triage j/k/e/f/x; live-region aria-announce | Linear inbox, Superhuman |
| `KeyboardHint` (footer) | `Kbd` | Always-visible default; collapsible | Notion, Linear |
| Digest filter panel | `Popover`, `FilterChip` | Watchlist filter, KBQ filter, tier filter, date range | Linear filter panel |
| `FilterChip` | `Pill` | Active filter chip with × | Linear |
| `TimeRangeSelector` | foundation | D/W/M/Q/Y/Custom; persisted per surface | Apple Health, Stripe |
| `FreshnessIndicator` | foundation | "Catalog updated 14m ago"; warning if >24h stale | Stripe |

### Sprint C4 — Signal Detail (weeks 6–7)
| Primitive | Dependencies | Acceptance | References |
|---|---|---|---|
| `Sheet` | foundation | Right-edge drawer; stack 2 deep; size sm/md/lg; keyboard ESC; aria-modal | Stripe, Linear |
| Signal Detail surface | `Sheet` + C2 primitives | All sections from §2.3; conflict view; entity history strip; peer strip | unique |
| `SupersededIndicator` banner | foundation | "Updated by [link]"; dismissible | unique |
| Inline Atlas Q&A widget | existing chat infra | Embedded in signal detail; cites Signals not docs | Perplexity inline |
| `CitedSentenceParagraph` | `CitationPill` | JSON sentences-with-citations; clickable pills scroll evidence | Perplexity answer |

### Sprint C5 — Watchlist (weeks 8–9)
| Primitive | Dependencies | Acceptance | References |
|---|---|---|---|
| Watchlist Manager | `Tabs`, `Combobox`, `EntityChip` | 3 tabs (Personal/Team/Subs); fuzzy add via combobox; drag reorder; smart suggestions sidebar | Spotify Library, Things 3 |
| `Combobox` | `Popover`, `Input` | Autocomplete on entities; keyboard-only navigable; Algolia-class | Linear, Algolia |
| `Tabs` | foundation | Underlined variant; segmented variant; keyboard arrow-nav | Stripe |

### Sprint C6 — Reviewer Queue (weeks 10–11)
| Primitive | Dependencies | Acceptance | References |
|---|---|---|---|
| Reviewer Queue surface | C2 primitives + `Sheet` | Side-by-side narrative + evidence; conflict mode; SLA indicator; approve/edit/reject/defer | GitHub PR review |
| Inline narrative editor | foundation + lexical or similar | Edit narrative in-place before approve | Notion inline edit |
| `Banner` | foundation | SLA indicator; danger-coloured at <30 min remaining | Stripe |

### Sprint C7 — Alert Center (weeks 12–13)
| Primitive | Dependencies | Acceptance | References |
|---|---|---|---|
| Alert Center | `Tabs`, `DataTable`, `RuleEditor` | 3 tabs (Rules/History/Channels); rule editor; delivery log table | Stripe Webhooks |
| `RuleEditor` | foundation forms | Scope picker → predicate → channel; preview pane | unique-ish |
| `DataTable` | foundation | Virtualized; sortable; filterable; exportable to CSV | Stripe |

### Sprint C8 — Polish + Atlas refresh (weeks 14)
| Primitive | Dependencies | Acceptance | References |
|---|---|---|---|
| Atlas visual refresh | tokens migration | Drop slate-* utilities; adopt CSS vars; warmer Atlas accent (amber) | already-existing chat |
| a11y audit pass | axe-core in CI | Every surface passes axe at WCAG AA | axe-core |
| Performance budget | Lighthouse CI | Mission Control + Daily Digest < 2.5s LCP | Lighthouse |

---

## 10. What this SPEC does not cover

- **Brand visuals** — wordmark refinement, logo variants, marketing site. Separate brand exercise.
- **Email design** — alert delivery emails. Brief design system; in Phase 1 sprint C7.
- **Marketing pages** — `/pricing`, `/about`, etc. Phase 2.
- **Mobile native apps** — explicitly out of Phase 1 scope (alerts only; see §6.4).
- **Phase 2 surfaces** — Brief Composer (defer to 1.5), Trackers (defer to 1.5), Connector Health admin (defer to 1.5).

---

## 11. How to use this document

**Engineering**: §3 is the build manifest. §9 is the sprint sequence. §4 is the keymap canon. §5.6 is the chart law.

**Design** (when designers join): §1 is the north star. §8 is the reference shelf. §7 is the decision register.

**Product**: §7 is the open-decisions resolution table. §2 sketches the IA per surface for sign-off.

**Reviewer**: this document supersedes SPEC-016 §4 (design system v1). When in doubt, this spec wins on UX questions; SPEC-016 wins on architecture questions.

---

*Authored 2026-04-29. This SPEC is the upgrade path for the v1 scaffold currently in `apps/landing`, `apps/ci`, `packages/ui`, `packages/design-tokens`. Successor revisions ship per swimlane C sprint.*
