# SPEC_030: Decision Workspace v2 — consume `/decision-briefs` (SPEC_023)

Status: Stage 6 complete (FIX-ALL closed 2026-05-09); DEPLOY opens next
Owner: Frontend Lead (Claude in Antigravity's seat)
Parent: `specs/SPEC_029_app_aesthetics_upgrade.md` §9, §5 row CI-5/CI-6
Loop: `docs/runbooks/RALPH_LOOP.md`
Depends on: SPEC_023 (Decision Briefs — backend, shipped 2026-05-09)
Related: SPEC_032 (War-Game UI — will be invoked from this workspace)

---

## 1. Goal

Replace the legacy single-page `DecisionDetailPage.tsx` (which consumes
`/decisions/{id}/full` from SPEC_021) with a **5-panel Decision Workspace**
that renders a `DecisionBrief` from SPEC_023 — the canonical framing object
of the flywheel. Surface the brief's question, options, evidence references,
state-machine, and reasoning trace as first-class panels.

This is loop #1 in the SPEC_029 sequence and the most leverage move in the
plan: every other CI surface (Sensing Feed → frame as decision; War-Game →
attach to brief; Insights → outcome of decisions) ultimately points at this
workspace.

## 2. Why now

- The backend contract (`/decision-briefs`, full state machine, options,
  state log) shipped 2026-05-09 and has zero frontend consumer today.
- Decision flywheel §6.4.1 of `CI_Agent_Reimagined_Spec.md` mandates the
  5-panel surface (Brief / Evidence / Simulation / Recommendation / Trace).
  The current page is single-pane and only renders the *committed*
  decision — not the framing layer.
- Without this workspace, "frame as decision" actions on signals have no
  destination, and the upcoming War-Game UI (SPEC_032) has no parent.

## 3. Surfaces touched

### 3.1 Routes (already in `App.tsx`, retargeted here)

| Route | Today renders | After SPEC_030 |
|---|---|---|
| `/ci?tab=decisions` | `DecisionsTab` over legacy `/decisions` | New `BriefsTab` over `/decision-briefs` |
| `/ci/decisions/:id` | `DecisionDetailPage` (`/decisions/{id}/full`) | New `DecisionWorkspace` (`/decision-briefs/{id}`) |

The legacy `DecisionsTab` and `DecisionDetailPage` are **not deleted** in
this loop; they move behind a `localStorage.mz_legacy_decisions === 'true'`
escape hatch routed at `/ci/legacy-decisions/:id`. This preserves the
SPEC_021 inbox + outcome capture flow while we migrate.

### 3.2 New files

```
frontend/src/components/ci/decisions/
├── BriefsTab.tsx                    — list view (replaces DecisionsTab in default tab)
├── DecisionWorkspace.tsx            — 5-panel page (replaces DecisionDetailPage)
├── BriefPanel.tsx                   — top: question, options, time horizon, stakeholders
├── EvidencePanel.tsx                — left: evidence_refs grouped by type (kbq/signal/entity/document)
├── SimulationPanel.tsx              — center: war-game runs + Monte Carlo placeholders
├── RecommendationPanel.tsx          — right: ranked options + dissent view
├── ReasoningTraceDrawer.tsx         — collapsible: state_log + future llm_call_log
├── StateMachineChip.tsx             — visual state badge with allowed-transitions popover
├── BriefEditableField.tsx           — inline-edit fields (only legal in draft/human_review)
└── OptionEditor.tsx                 — add/edit/delete option modal
```

### 3.3 Files modified

```
frontend/src/api.ts                  — append decisionBriefsApi + types
frontend/src/App.tsx                 — route `/ci/decisions/:id` to DecisionWorkspace
frontend/src/pages/CIPage.tsx        — `decisions` tab body switches to BriefsTab
docs/UI_CHANGELOG.md                 — append SPEC_030 entry on land
```

## 4. Data contract

### 4.1 Endpoints consumed (from `schema/openapi.json`)

```
GET    /decision-briefs                          → list with cursor pagination
GET    /decision-briefs/{brief_id}               → full brief incl. options + state_log
POST   /decision-briefs                          → create draft (manual trigger)
PATCH  /decision-briefs/{brief_id}               → edit fields (legal in draft/human_review only)
DELETE /decision-briefs/{brief_id}               → archive (sets archived_at)
POST   /decision-briefs/{brief_id}/options       → add option
DELETE /decision-briefs/{brief_id}/options/{id}  → remove option (legal in draft/human_review only)
POST   /decision-briefs/{brief_id}/transitions   → advance state machine
```

All endpoints require auth (`viewer` for GET, `uploader` for mutations).
Standard error envelope per `api/exception_handlers.py`.

### 4.2 TypeScript types added to `frontend/src/api.ts`

```ts
export type BriefState =
  | 'draft' | 'human_review' | 'simulation_pending' | 'simulation_complete'
  | 'decision_pending' | 'committed' | 'in_review' | 'closed';

export type TriggerKind = 'manual' | 'threshold' | 'cluster' | 'calendar';

export type EvidenceRefType = 'kbq_view' | 'signal' | 'entity' | 'document';

export interface EvidenceRef {
  type: EvidenceRefType;
  id: string;
  snapshot_at?: string;
}

export interface DecisionBriefOption {
  option_id: string;
  brief_id: string;
  ordinal: number;
  label: string;
  description: string | null;
  predicted_outcome: string | null;
  cost_estimate: string | null;
  risk_notes: string | null;
  created_at: string;
}

export interface BriefStateLogEntry {
  log_id: string;
  brief_id: string;
  from_state: string | null;
  to_state: BriefState;
  actor_user_id: string | null;
  reason: string | null;
  transitioned_at: string;
}

export interface DecisionBrief {
  brief_id: string;
  question: string;
  trigger_kind: TriggerKind;
  trigger_signal_ids: string[];
  trigger_metadata: Record<string, unknown>;
  stakeholders: string[];
  time_horizon_days: number | null;
  evidence_refs: EvidenceRef[];
  constraints: string[];
  success_criteria: string | null;
  confidence_to_proceed: number | null;
  state: BriefState;
  owner_user_id: string | null;
  war_room_id: string | null;
  decision_id: string | null;
  archived_at: string | null;
  created_at: string;
  updated_at: string;
  options: DecisionBriefOption[];
  state_log: BriefStateLogEntry[];
}

export interface DecisionBriefListFilters {
  state?: BriefState;
  owner_user_id?: string;
  trigger_kind?: TriggerKind;
  cursor?: string;
  limit?: number;
}

export interface DecisionBriefList {
  briefs: DecisionBrief[];
  next_cursor: string | null;
  count: number;
}

export const decisionBriefsApi = {
  list: (filters?: DecisionBriefListFilters): Promise<DecisionBriefList> => /* ... */,
  get: (briefId: string): Promise<DecisionBrief> => /* ... */,
  create: (body: Partial<DecisionBrief> & { question: string }): Promise<DecisionBrief> => /* ... */,
  patch: (briefId: string, patch: Partial<DecisionBrief>): Promise<DecisionBrief> => /* ... */,
  archive: (briefId: string): Promise<{ ok: true }> => /* ... */,
  addOption: (briefId: string, opt: Omit<DecisionBriefOption, 'option_id' | 'brief_id' | 'ordinal' | 'created_at'>): Promise<DecisionBriefOption> => /* ... */,
  removeOption: (briefId: string, optionId: string): Promise<{ ok: true }> => /* ... */,
  transition: (briefId: string, toState: BriefState, reason?: string): Promise<DecisionBrief> => /* ... */,
};
```

## 5. States to support — every panel × every state

For each panel (BriefPanel / EvidencePanel / SimulationPanel /
RecommendationPanel / ReasoningTraceDrawer):

| State | What renders | Failure mode |
|---|---|---|
| Loading | Skeleton with `animate-pulse` matching final shape; not a spinner | n/a |
| Empty (legitimate) | Call-to-action: "No options yet — add one" / "No evidence linked yet" | n/a |
| Empty (probably bug) | Diagnostic card: "Brief loaded but options array is empty — backend bug?" + retry | Only when array invariants violated |
| Error | Card with HTTP code, error.detail, "retry" button | Network 5xx, 4xx with envelope |
| Locked-by-state | Disabled inputs with state chip "Editing locked: brief is `simulation_pending`" | After transition |
| Optimistic / Busy | Visual disabled + spinner overlay during PATCH | Returns to idle on resolve |
| Disagreement | Side-by-side panel from `DisagreementPanel` primitive — when two sources disagree on an evidence_ref | Future loop; UI hooks ready in v1 |
| Fixture-mode | Top-of-page yellow strip "Fixture mode — backend not connected" | Only when API fetch fails *and* `localStorage.mz_fixture_mode === 'true'` |

Brief-level states (the SPEC_023 state machine) are first-class:
- `draft` → editable, big "Send to review" button
- `human_review` → reviewer-only edits, "Send to simulation" button (requires ≥2 options)
- `simulation_pending` → read-only, simulation panel shows running state
- `simulation_complete` → read-only, simulation panel shows results
- `decision_pending` → ready-to-commit, big "Commit decision" button
- `committed` → read-only, decision_id chip clickable to legacy outcome capture
- `in_review` → read-only, banner "Outcome review in progress"
- `closed` → archived appearance, restore action requires uploader+

## 6. Keyboard contract

| Surface | Shortcut | Action |
|---|---|---|
| BriefsTab list | `j` / `k` | Move selection down / up |
| BriefsTab list | `return` | Open selected brief |
| BriefsTab list | `n` | New brief (manual draft) |
| BriefsTab list | `?` | Show keyboard hint overlay |
| DecisionWorkspace | `e` | Edit-mode toggle (only legal states) |
| DecisionWorkspace | `g e` | Focus Evidence panel |
| DecisionWorkspace | `g s` | Focus Simulation panel |
| DecisionWorkspace | `g r` | Focus Recommendation panel |
| DecisionWorkspace | `t` | Toggle Reasoning Trace drawer |
| DecisionWorkspace | `cmd+enter` | Advance state (if currently allowed) |
| DecisionWorkspace | `escape` | Close any modal / drawer |

Shortcut hints render via the new `KeyboardHint` primitive on hover (see
SPEC_029 §4.4).

## 7. Accessibility contract

- All interactive elements reachable via `Tab`, focus visible per
  SPEC_022 (`box-shadow: 0 0 0 3px rgba(28,110,247,0.15)` light;
  `rgba(88,166,255,0.18)` dark).
- StateMachineChip uses `role="status"` with `aria-live="polite"` so state
  changes announce to screen readers.
- ReasoningTraceDrawer is a proper `<dialog>` semantic with
  `aria-labelledby` pointing at its title.
- All panels have skip-link targets so keyboard users can jump between
  them; `g e` / `g s` / `g r` shortcuts also work via skip-links.
- Color is never the sole carrier of meaning: every state chip has a
  shape-suffix (◆ for terminal, ▶ for in-flight, ◯ for editable) plus its
  text label.
- Lighthouse a11y target: ≥95 on both routes, light AND dark.

## 8. Design notes (Stage 2 — completed 2026-05-09)

### 8.1 Reference frames — what we're stealing from

| Surface | Lift from | What |
|---|---|---|
| List (BriefsTab) | **Linear inbox** | Dense single-line rows, leading state-glyph, trailing meta. Hover reveals quick actions. ⌘K palette. |
| Workspace shell | **Linear issue page** | Top-bar with state chip + actions; right meta column; left/center content split. |
| Panel rhythm | **Apple Health "Browse"** | Big serif eyebrows, generous spacing, rounded surfaces, no hard borders. |
| Editable fields | **Stripe Dashboard** | Inline-edit affordance: faint underline on hover, expands to input on click, save on blur. |
| State machine | **Vercel deployment statuses** | Pill chip + shape-glyph; popover on click shows allowed transitions and the reason for the current state. |
| Reasoning trace drawer | **Sentry breadcrumbs** | Right-side dialog, vertical timeline, monospace metadata, expandable rows. |
| Empty states | **Notion** | One short sentence + one CTA, no illustration. |

References are public products the team can pull up; no exported assets in
this loop. Stage 7 will commit our own screenshots to
`docs/screenshots/SPEC_030/`.

### 8.2 Layout grid — DecisionWorkspace at 1440px (default spacious density)

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  ⌘ TopBar 52h  |  ← back   |  Brief #b7ca…  ◯ draft                [t] trace  │
├────────────────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────────────── BriefPanel (full width) ───────────────────────┐ │
│ │  Question — Syne 28/600, editable inline                                  │ │
│ │   "Should we accelerate Phase III readout in 2L NSCLC?"                   │ │
│ │ ─────────────────────────────────────────────────────────────────────────  │ │
│ │  ◯ draft  →  ▶ human_review  →  ⟳ sim_pending  →  ⊕ decide  →  ✓ committed │ │
│ │  Time horizon: 14 days · Stakeholders: Commercial · Medical · R&D         │ │
│ │  Trigger: manual · Confidence to proceed: 0.65                            │ │
│ │ ─────────────────────────────────────────────────────────────────────────  │ │
│ │  Options (2 / 5)                                          [+ add option]  │ │
│ │   1. Accelerate readout — 8–12% share gain · ~$5M cost                    │ │
│ │   2. Hold position — preserves data quality · $0                          │ │
│ └─────────────────────────────────────────────────────────────────────────────┘ │
│                                                                                  │
│ ┌── EvidencePanel ─────┐ ┌── SimulationPanel ─────┐ ┌── RecommendationPanel ─┐ │
│ │  Linked evidence (4) │ │  No simulation yet      │ │  Awaiting simulation    │ │
│ │                       │ │                          │ │                          │ │
│ │  KBQ-3 Clinical (1)  │ │  ┌──────────────────────┐│ │                          │ │
│ │   • NCT04567890      │ │  │  ⊘ Start war-game    ││ │                          │ │
│ │                       │ │  │  Disabled — SPEC-032 ││ │                          │ │
│ │  Signals (2)         │ │  └──────────────────────┘│ │                          │ │
│ │   • s_8a3…           │ │                          │ │                          │ │
│ │   • s_b7c…           │ │  Monte Carlo: not run    │ │                          │ │
│ │                       │ │                          │ │                          │ │
│ │  Documents (1)       │ │                          │ │                          │ │
│ │   • doc:filing_8K…   │ │                          │ │                          │ │
│ └───────────────────────┘ └─────────────────────────┘ └──────────────────────────┘ │
│                                                                                  │
│  [⌘↵ Send to review]              [g e] Evidence  [g s] Sim  [g r] Rec  [t] Trace│
└──────────────────────────────────────────────────────────────────────────────────┘
```

At ≤1024px the three middle panels collapse into a tab strip
("Evidence / Simulation / Recommendation") and BriefPanel becomes a sticky
top card. ReasoningTraceDrawer slides over the right 38% on tablet,
full-width on mobile.

### 8.3 Per-state affordance matrix

Cell key: ✏️ editable · 🔒 locked · ⏵ primary CTA · ⊘ disabled CTA · — n/a

| State                | BriefPanel | Options    | Evidence | Sim run | Recommend | Primary CTA |
|----------------------|------------|------------|----------|---------|-----------|-------------|
| `draft`              | ✏️ all     | ✏️ add/del | ✏️ add   | —       | —         | ⏵ "Send to review" |
| `human_review`       | ✏️ all     | ✏️ add/del | ✏️ add   | —       | —         | ⏵ "Send to simulation" (requires ≥2 options) |
| `simulation_pending` | 🔒         | 🔒         | 🔒       | ⏵ start | —         | ⊘ "Start war-game" until SPEC-032 |
| `simulation_complete`| 🔒         | 🔒         | 🔒       | view    | view      | ⏵ "Send to decision" |
| `decision_pending`   | 🔒         | 🔒         | 🔒       | view    | ⏵ commit  | ⊘ "Commit decision" until backend `/decisions/from-brief` |
| `committed`          | 🔒         | 🔒         | 🔒       | archive | view      | View linked decision |
| `in_review`          | 🔒         | 🔒         | 🔒       | archive | view      | (read-only banner) |
| `closed`             | 🔒         | 🔒         | 🔒       | archive | archive   | "Restore" (uploader+) |

### 8.4 State-machine visual

`StateMachineChip` renders as a horizontal pill with a shape-glyph + label.
Click opens a popover showing the full DAG; the current state pulses;
allowed transitions are clickable.

```
  ◯ draft  →  ▶ human_review  →  ⟳ sim_pending  →  ⟳ sim_complete
                    ↑                                    │
                    │                                    ↓
                    └───── (back) ──────  ⊕ decision_pending
                                                  │
                                                  ↓
              ◆ closed  ←  ⊕ in_review  ←──  ✓ committed
```

Glyph dictionary:
- ◯ open, accepting edits (`draft`, `human_review`)
- ▶ accepting input (`human_review` waiting on options ≥ 2)
- ⟳ in-flight, async (`simulation_*`)
- ⊕ awaiting human (`decision_pending`, `in_review`)
- ✓ committed, immutable
- ◆ terminal (`closed`)

Each state has a paired color token in §8.6.

### 8.5 BriefsTab — row anatomy

```
┌───────────────────────────────────────────────────────────────────────┐
│ ◯ DRAFT      Should we accelerate Phase III readout in 2L NSCLC?      │
│              ↳ trigger: manual · 14d horizon · 2 options              │
│              Pfizer Oncology · NSCLC · 2 evidence refs                │
│ ────────────────────────────────────────────────────────────────────── │
│ ▶ HUMAN_REVIEW   Drop tier-2 formulary in 4 plans?                    │
│              ↳ trigger: cluster (3 signals) · 7d horizon · 3 options  │
│              CVS Caremark · multi-product                             │
└───────────────────────────────────────────────────────────────────────┘
```

Per-row composition: `[state-glyph + state-label]` (8ch column) ·
`question` (1-line truncate, full on hover/focus) · meta-row
(small caps DM Sans 11px, `--color-ink-3`). Hover lifts the row 1px and
reveals `[open ↗]` `[archive 🗑]` quick actions on the right.

Empty: spacious card with eyebrow "No briefs yet" + DM Sans body
"Frame a signal as a decision, or create a manual draft." + primary
button "+ New brief".

### 8.6 Token call-outs

New tokens added under this spec live in `frontend/src/index.css` next to
existing ones; the `@theme` block holds light values; `html.dark`
overrides dark values.

```css
/* New tokens (add to @theme + html.dark) */

/* State-machine palette — one chip color per BriefState */
--color-state-draft:        var(--color-ink-3);          /* neutral grey */
--color-state-review:       #B45309;                     /* warm amber */
--color-state-sim:          var(--color-accent);         /* blue, in-flight */
--color-state-decide:       #7C3AED;                     /* violet */
--color-state-committed:    var(--color-green);          /* green */
--color-state-review-out:   #0EA5E9;                     /* sky */
--color-state-closed:       var(--color-ink-4);          /* muted */

/* Density tokens (spacious is default; compact halves these) */
--space-panel-pad:          24px;     /* compact: 12px */
--space-panel-gap:          16px;     /* compact: 8px */
--space-row-gap:            12px;     /* compact: 6px */

/* SPEC_030-specific */
--shadow-workspace-panel:   var(--shadow-sm);            /* light */
                            /* dark uses var(--shadow-glow) when in-flight */
```

Existing tokens consumed (no changes):
`--color-ink/-2/-3/-4`, `--color-surface/-2/-3`, `--color-accent`,
`--color-accent-soft`, `--color-line`, `--color-divider`, `--shadow-xs/sm/md`,
`--shadow-glow` (from SPEC_029 §4.6), `--font-display` (Syne) for question
and section eyebrows, `--font-body` (DM Sans) for prose, `--font-mono`
(DM Mono) for IDs/timestamps/state-log lines.

### 8.7 Motion specs

| Element | Trigger | Animation | Duration | Easing |
|---|---|---|---|---|
| Page enter | mount | stagger fade-up children at 30ms | 240ms total | `--motion-out` |
| State change | brief.state change | morph chip color + glyph | 220ms | `--motion-out` |
| Reasoning trace drawer | toggle | slide-in from right | 280ms | `--motion-out` |
| Inline-edit reveal | field hover/focus | underline 0→1px + width pulse | 140ms | linear |
| Optimistic save | PATCH in flight | content opacity 1.0→0.6, spinner fade-in | 120ms | linear |
| State-machine popover | click chip | scale 0.96→1 + opacity 0→1 | 180ms | `--motion-out` |
| Row hover (list) | hover | translateY(-1px) + shadow bloom | 160ms | `--motion-out` |

All motion gated by `prefers-reduced-motion: reduce`: animations become
`opacity` only, durations halved, transforms suppressed.

### 8.8 Density scoping

1. On `<DecisionWorkspace>` mount, read `localStorage.mz_density`.
2. Wrap the workspace tree in `<div data-density={density}>`.
3. CSS scope picks up `[data-density="compact"]` overrides:

```css
[data-density="compact"] {
  --space-panel-pad: 12px;
  --space-panel-gap:  8px;
  --space-row-gap:    6px;
}
```

Read-once on mount (no live-toggle in v1) — keeps the implementation
simple and avoids ResizeObserver work.

### 8.9 Self-review checklist (gate to Stage 3)

- [x] Every state in §5 has a layout/affordance line (see §8.3).
- [x] Every interactive element has a keyboard story (§6 + §8.2).
- [x] Light + dark token plan documented (§8.6).
- [x] Motion respects `prefers-reduced-motion` (§8.7).
- [x] Density story documented (§8.8).
- [x] Reference frames cited (§8.1).
- [x] State-machine diagram drawn (§8.4).
- [x] Empty / loading / error / locked / fixture states all addressed (§5 + §8.3).

Self-review passes. **Stage 3 (TDD) opens.**

## 9. Definition of Done (the Stage 7 checklist)

- [ ] All 9 new files in §3.2 implemented + Vitest-tested.
- [ ] `frontend/src/api.ts` extended with §4.2 types — types match
      `schema/openapi.json` exactly.
- [ ] `BriefsTab` replaces `DecisionsTab` in `CIPage.tsx`. Legacy lives
      behind `mz_legacy_decisions` flag.
- [ ] `DecisionWorkspace` replaces `DecisionDetailPage` in `App.tsx`. Old
      page reachable at `/ci/legacy-decisions/:id` (flag-gated).
- [ ] All keyboard shortcuts in §6 work; `KeyboardHint` overlay opens on `?`.
- [ ] Lighthouse a11y ≥95 in light AND dark mode.
- [ ] Vitest runs covering: every state in §5 × every panel; every
      transition button × every legal state; every keyboard shortcut.
- [ ] `cd frontend && npm run build && npx tsc --noEmit && npx vitest run`
      exits 0.
- [ ] `docs/UI_CHANGELOG.md` entry appended.
- [ ] Screenshots committed to `docs/screenshots/SPEC_030/` for at least
      these states: list (light/dark, 0/1/many), workspace draft (l/d),
      workspace simulation_pending (l/d), workspace committed (l/d),
      reasoning-trace drawer open (l/d).
- [ ] No regressions: existing `/ci/decisions/:id` route still works for
      pre-SPEC_030 legacy decisions via the flag-gated escape hatch.

## 10. Open questions — RESOLVED at sign-off (2026-05-09)

1. **Q1 — Legacy `/decisions` UI fate.** ✓ Resolved: (c) flag-gated
   escape hatch. Move legacy page to `/ci/legacy-decisions/:id` behind
   `localStorage.mz_legacy_decisions === 'true'`. Preserves SPEC_021
   outcome-capture flow until SPEC_023 grows outcome semantics.

2. **Q2 — Minting `decision_id` for `committed` transition.** ✓ Resolved:
   file `[BACKEND]` request for `POST /decisions/from-brief?brief_id={id}`
   → returns `{ decision_id }` and links it on the brief automatically.
   Frontend ships the "Commit decision" button **disabled with tooltip**
   "Commit endpoint not yet ready (backend AGENT_BACKLOG entry)" until
   the endpoint lands. Once shipped, button enables in `decision_pending`
   state.
   *(Backend ask filed in `docs/AGENT_BACKLOG.md` — see commit body.)*

3. **Q3 — "Start war-game" CTA.** ✓ Resolved: render the button **disabled
   with tooltip** "Multi-adversary war-games ship in SPEC_032". The CTA
   appears in `simulation_pending` and later states. SPEC_032 will wire
   the click handler.

4. **Q4 — Default density.** ✓ Resolved: **spacious Apple-Health** is the
   default. Power users opt into compact via
   `localStorage.mz_density === 'compact'` which halves `--space-*`
   tokens. Density flag is read once on `<DecisionWorkspace>` mount and
   applied via a wrapping `<div data-density="compact|spacious">` whose
   children read scoped tokens.

## 11. Tests (Stage 3 will list, Stage 1 enumerates the count)

Stage 3 will produce ~40 Vitest specs across:
- `BriefsTab.test.tsx` — list rendering, filters, keyboard nav, empty/error
- `DecisionWorkspace.test.tsx` — panel mount, state-aware affordances
- `BriefPanel.test.tsx` — inline edit, locked vs editable
- `EvidencePanel.test.tsx` — grouping by type, empty, evidence-affordance click
- `SimulationPanel.test.tsx` — pending/complete/empty, "start war-game" CTA
- `RecommendationPanel.test.tsx` — ranked options, dissent visible
- `ReasoningTraceDrawer.test.tsx` — open/close, state-log render
- `StateMachineChip.test.tsx` — every state's label/shape/color; transition popover
- `BriefEditableField.test.tsx` — locked-state, optimistic update, error rollback
- `OptionEditor.test.tsx` — add, edit, remove, validation
- `decisionBriefsApi.test.ts` — request shape per OpenAPI; 4xx/5xx envelope handling

## 12. Acceptance for Stage 1 (this document, before Stage 2 starts)

- [ ] User signs off below by replacing this line with `✓ Signed off by user 2026-05-09`.
- [ ] User answers Q1–Q4 (or accepts proposed defaults).
- [ ] Backend asks in §10 Q2 filed in `docs/AGENT_BACKLOG.md` if needed.

Once accepted, Stage 2 (DESIGN) opens.

## 13. Out of scope (this loop)

- Bayesian / Stackelberg / POMDP simulation visuals — SPEC_025 backend
  exists but the UI viz is its own follow-up under SPEC_032 or later.
- Multi-user real-time war-room (the "war room" feel where multiple
  strategists collaborate live on the same brief). Real-time channels
  not in scope; v2 of this surface or its own SPEC.
- Embedding outcome capture from SPEC_021 D2 inside the new workspace —
  legacy page handles it for now.
- Auto-creating briefs from threshold/cluster triggers (SPEC_029
  framing-trigger backlog item, backend-blocked).

## 14. Red-team (Stage 5 — completed 2026-05-09)

Adversarial review of the diff `main..claude-fe/spec-029-aesthetics`
(commits `053dce1..78c8b3f`). Reviewer pretended not to have written the
spec. Findings are numbered, with severity and one-line repro. Every
`blocker` and `major` must be closed in Stage 6 (FIX-ALL); `minor`/`nit`
either fixed or filed under `[FRONTEND]` in `docs/AGENT_BACKLOG.md`.

### Blockers

1. ~~**WCAG-AA contrast failure on three state chips**~~ — `blocker` —
   ✅ closed Stage 6. Tokens `--color-state-{draft,closed,review-out}`
   bumped to ≥4.5:1 in light theme; matched dark overrides added.
2. ~~**Dark-mode `closed` chip is invisible**~~ — `blocker` —
   ✅ closed Stage 6. Dark `--color-state-closed` lifted from
   `#21262d` (1.0:1) to `#8b949e` (~4.8:1).
3. ~~**Brief rows are not Tab-reachable**~~ — `blocker` (a11y) —
   ✅ closed Stage 6. Selected row gets `tabIndex={0}` + `onKeyDown`
   for Enter/Space; non-selected rows get `-1` (managed roving
   tabindex pattern, ARIA-Practices §3.18 listbox).
4. ~~**Inline-editable fields are not keyboard-activatable**~~ —
   `blocker` (a11y) — ✅ closed Stage 6. Non-locked field is now a
   real `<button>` so Tab reaches it and Enter/Space activates;
   locked field is a static `<span>` (no fake-button affordance).
   Also fixes #14 (invalid `role="text"`) by removing it.
5. ~~**`cmd+enter` advances backwards from `human_review`**~~ —
   `blocker` (UX) — ✅ closed Stage 6. New
   `nextForwardTransition(state)` walks the state-rank table and
   picks the smallest forward transition; backward picks are
   impossible.

### Major

6. ~~**No `prefers-reduced-motion` honoring anywhere**~~ — `major`
   (a11y) — ✅ closed Stage 6. Global
   `@media (prefers-reduced-motion: reduce)` block in `index.css`
   neutralizes animation/transition durations, suppresses transforms
   on dialog/option/density-scoped trees, and dims skeleton loops.
7. ~~**Save errors swallowed silently**~~ — `major` (UX/correctness) —
   ✅ closed Stage 6. `BriefEditableField` and `OptionEditor` now
   `try/catch` around `onSave`, render the error inline as
   `role="alert"`, and keep the field/modal open so users can retry
   without losing the draft.
8. ~~**`SimulationPanel` lies in `simulation_complete`**~~ — `major`
   (correctness) — ✅ closed Stage 6. State-aware copy: ran-states
   render "Scenario complete — results UI ships in SPEC-032";
   archive-states render "Scenario archived"; pre-run states keep
   "No scenario run yet."
9. ~~**`aria-live="polite"` on every chip → announce-storm**~~ —
   `major` (a11y) — ✅ closed Stage 6. `<StateMachineChip>` accepts
   an `announce` prop (default `false`) — list rows are silent;
   `BriefPanel` flips `announce` on its single primary chip so the
   workspace still announces state changes.
10. ~~**`ReasoningTraceDrawer` doesn't focus-trap or take focus**~~ —
    `major` (a11y) — ✅ closed Stage 6. On open we stash the previous
    `activeElement`, focus the close button, trap Tab inside the
    drawer (Shift+Tab from first → last; Tab from last → first), and
    restore focus on close.
11. ~~**No 401 → redirect; raw status leaks to UI**~~ — `major` —
    ✅ closed Stage 6. `expectJson()` clears the stored token+role
    and dispatches `mz:auth-expired` on 401; `App.tsx` listens and
    `navigate('/?session=expired', { replace: true })`. Landing-page
    banner for `?session=expired` is filed as a follow-up.
12. **`ReasoningTraceDrawer` rolls its own drawer** — `major`
    (anti-slop) — **deferred to backlog** with reason: existing
    `<Drawer>` primitive's title/subtitle/children API doesn't fit
    timeline content; refactoring Drawer to a slot API first is the
    cleaner path. Anti-slop, not UX. See AGENT_BACKLOG `[FRONTEND]
    SPEC-030 deferred items` #12.
13. ~~**"Primary / Dissent" picked by ordinal — semantically wrong**~~
    — `major` (correctness) — ✅ closed Stage 6. Renamed labels to
    "Top option" / "Counter option"; added an italic disclaimer
    "Order reflects ordinal, not simulation rank. Ranking ships in
    SPEC-032." Removes the false "Primary" claim until SPEC_023 grows
    a rank column.

### Minor

14. **`role="text"` is not a valid ARIA role** — `minor` (a11y) —
    `BriefEditableField.tsx:92`. Browsers ignore it; AT will fall back
    to the implicit role of the `<span>` (none). Should be removed.
15. **`getRole()` duplicated 4× in the codebase** — `minor`
    (anti-slop) — three pre-existing copies (`CIPage`,
    `ConnectorPermissionsTab`, `SignalDetail`); SPEC_030 added a fourth
    in `BriefPanel`. Should consolidate into a hook (e.g.
    `frontend/src/hooks/useRole.ts`).
16. **Three modal patterns rolled separately** — `minor` (anti-slop) —
    `NewBriefDialog`, `KeyboardHintDialog`, `OptionEditor` each
    reimplement backdrop + centered card + esc-to-close + click-out
    -to-close. No shared `<Modal>` primitive in `components/ui/`.
17. **"Options (N / 5)" hardcoded max** — `minor` — UI shows
    "Options (6 / 5)" if backend returns 6 options. Either the cap is
    a backend invariant (then pull it from a constant) or it isn't
    and the slash UI is misleading.
18. **No edit-option flow wired** — `minor` — `OptionEditor` supports
    `mode="edit"` + `onRemove`, but `BriefPanel` only invokes it with
    `mode="create"`. Users can add and delete (via `×` button) but not
    edit fields once added.
19. **No add-evidence affordance in editable states** — `minor` —
    Spec §8.3 affordance matrix lists ✏️ for `draft` and
    `human_review` evidence cells. UI is read-only across all states.
20. **Destructive remove-option without confirm** — `minor` (UX) —
    `BriefPanel` delete button calls `onRemoveOption(opt.option_id)`
    immediately. No confirm; no undo.
21. **Mouse hover sets selected index** — `minor` (UX) —
    `BriefRow.onMouseEnter` calls `onHover()` which calls
    `setSelectedIdx(i)`. A user steering with `j/k` can have selection
    yanked away by an incidental mouse move.
22. **Pagination silently truncates at 50** — `minor` —
    `BriefsTab.load` always passes `{ limit: 50 }` and ignores
    `next_cursor`. List with 51+ briefs has no UX path to subsequent
    pages. `it.todo` exists; should be filed in backlog with a
    deferred reason.
23. **Filter chip group not implemented** — `minor` — Spec §8.5
    showed a state-filter strip and §11 listed filtering by state /
    owner / trigger as locked-in tests; only `it.todo` exists.
24. **"Commit decision" button has no on-button help** — `minor`
    (a11y) — disabled button shows tooltip via `title` only; no
    `aria-describedby` to a visible note like the war-game tooltip
    does. Screen readers may skip `title`.
25. **War-game tooltip is `title` + sibling span** — `minor` (a11y) —
    `title="Multi-adversary war-games ship in SPEC_032"` is widely
    inaccessible (mouseover-only, varies by AT). The
    `aria-describedby` does point to a visible italic span — that
    half is fine, but the `title` should be redundant or removed.

### Nits

26. **Dead variable** — `nit` — `StateMachineChip.tsx:102` declares
    `const labelText = …` and never uses it.
27. **Redundant `role="textbox"`** — `nit` — `BriefEditableField` sets
    `role="textbox"` on `<input>` and `<textarea>`, both of which
    have implicit textbox role.
28. **`STATE_META` re-exported via `BriefsTab`** — `nit` — already
    exported by `StateMachineChip`. The trailing
    `export { STATE_META }` in `BriefsTab.tsx:439` is dead.
29. **`confidence_to_proceed.toFixed(2)` does not guard NaN** — `nit`
    — defensive, but `toFixed(2)` of `NaN` returns `"NaN"`; backend
    invariants make this unreachable today.
30. **`fmtTime` catch is unreachable** — `nit` —
    `new Date('garbage').toLocaleString()` returns `"Invalid Date"`,
    it does not throw. The `try/catch` cannot fire.

### Lighthouse / screenshot diff

- Lighthouse not run in this loop (no headless Chromium in current
  environment). **Filing as `[FRONTEND] SPEC-030 deploy gate: run
  Lighthouse a11y on `/ci?tab=decisions` and `/ci/decisions/:id`,
  light + dark, target ≥95** in `docs/AGENT_BACKLOG.md` to be
  satisfied before Stage 7 (DEPLOY).
- Screenshot diff vs. legacy `DecisionDetailPage` deferred to Stage 7
  alongside the spec's required `docs/screenshots/SPEC_030/` set.

### Decisions taken — not bugs

The following were considered during red-team and explicitly accepted:

- **Density read-once on mount, no live toggle** — Q4 sign-off /
  §8.8. Live toggling would need a global density context; deferred.
- **"Commit decision" button always disabled** — Q2 sign-off; backend
  `/decisions/from-brief` not yet shipped (filed as `[BACKEND]` in
  AGENT_BACKLOG).
- **"Start war-game" button always disabled** — Q3 sign-off;
  SPEC_032 will wire the click handler.
- **Legacy `DecisionDetailPage` lives behind
  `mz_legacy_decisions === 'true'`** — Q1 sign-off. Not deleted in
  this loop.
- **Demo auto-login as `enterprise` (CIPage:79)** — pre-existing in
  `cryogenic22/myscience` main; out of scope for SPEC_030. Real
  authentication is filed under SPEC_021 follow-ups, not here.
- **Backend role enum is `viewer/uploader/enterprise`, not the
  `viewer/editor/enterprise` that AGENTS.md §7 documents** — verified
  against `services/auth.py:31`. AGENTS.md is stale; filing
  `[PROTOCOL]` note rather than aligning here.
- **`role="listbox"` with `<article role="option">` rows** — kept
  despite article-as-option being unusual; ARIA attribute roles
  override implicit roles for AT, and the visual semantics of an
  article (heading + meta) match what we want. The Tab-reachability
  problem (#3) is what's broken, not the role.
- **`mz_fixture_mode` only renders chip on error path** — by design
  (RALPH_LOOP §"No silent fakes" honors the *visible-on-failure*
  contract; the chip's job is to keep demos honest, not annoy the
  default success path).
- **`it.todo` test stubs intentionally left red** — pagination,
  filter chips, save-error toast: each has a documented future loop.

### Stage 5 gate

Stage 5 closes once this section is appended and committed. Stage 6
(FIX-ALL) opens. Items 1–5 (blockers) and 6–13 (majors) are the FIX-
ALL backlog; items 14–25 (minors) and 26–30 (nits) are candidates for
deferral via AGENT_BACKLOG; the Lighthouse run is itself a deploy-gate
backlog item.

### Stage 6 — FIX-ALL closed (2026-05-09)

| Severity | Closed in Stage 6 | Deferred to backlog |
|---|---|---|
| Blocker | 1, 2, 3, 4, 5 (5/5) | — |
| Major   | 6, 7, 8, 9, 10, 11, 13 (7/8) | 12 (Drawer reuse — anti-slop) |
| Minor   | 14, 26 (also closed as a side-effect of #4 / #9) | 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25 |
| Nit     | 26, 27, 28, 29, 30 | 27, 28, 29, 30 |

Regression tests added at
`frontend/__tests__/ci/decisions/_stage6_regressions.test.tsx`
(16 cases, one or more per fix). Final gate:
`npx tsc --noEmit && npx vitest run` ⇒ **39 test files, 256 cases
passing, 19 it.todo, zero failures, zero regressions** (was 240 at
end of Stage 4 — net +16).

Deferred items live under `[FRONTEND] SPEC-030 deferred items` in
`docs/AGENT_BACKLOG.md` with one-line defensible reasons each.

Stage 7 (DEPLOY) opens next.
