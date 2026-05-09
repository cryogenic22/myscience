# SPEC_030: Decision Workspace v2 — consume `/decision-briefs` (SPEC_023)

Status: Stage 1 complete (✓ signed off by user 2026-05-09); proceeding to Stage 2 DESIGN
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

## 8. Design notes (Stage 2 will fill in)

Stage 2 (DESIGN) will add:
- ASCII wireframes for each state of each panel (or Figma exports under
  `docs/screenshots/SPEC_030/design/`).
- Token call-outs (which `--color-*`, `--shadow-*`, `--radius-*`, etc.).
- State diagram for BriefState → editable affordances.
- Light + dark thumbnails per panel state.
- Reference frames from Linear's "Issue page", Stripe Atlas, Apple Health
  decision flows.

This section is intentionally empty for sign-off; Stage 2 fills it in.

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
