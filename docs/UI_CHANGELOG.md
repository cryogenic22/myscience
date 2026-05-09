# UI Changelog

Append-only log of every frontend surface change. **Antigravity writes; Claude
reads at the start of every session.**

Format per entry: `## YYYY-MM-DD` then sections `### Surfaces`,
`### New components`, `### Backend dependencies` (link to API_CHANGELOG entries
this depends on), `### Open issues`. Omit empty sections.

Screenshots of material visual changes live under `docs/screenshots/`.

---

## 2026-05-09 (SPEC-030 — Decision Workspace v2; Loop #1 closed)

First mini-spec under the SPEC-029 reskin program; first frontend loop
delivered through the 7-stage Ralph Loop process documented in
`docs/runbooks/RALPH_LOOP.md`. Stage 1 (SPEC) → Stage 7 (DEPLOY) all
gates passed.

### Surfaces

- **`/ci?tab=decisions`** — replaces legacy `DecisionsTab` with new
  `BriefsTab` consuming `GET /decision-briefs` (cursor-paginated).
  Linear-style row anatomy: state-glyph + question (truncate-on-row,
  full-on-hover) + meta (trigger / horizon / option count / evidence
  refs). Keyboard: `j/k` navigate, `return` open, `n` new brief,
  `?` keyboard help, `esc` close any modal.
- **`/ci/decisions/:id`** — replaces legacy `DecisionDetailPage` with
  new 5-panel `DecisionWorkspace` (Brief / Evidence / Simulation /
  Recommendation / Reasoning Trace drawer). Reads `mz_density`
  (default `spacious`); compact mode halves `--space-*` tokens via
  `[data-density="compact"]` scope. Keyboard: `t` trace toggle,
  `g e/s/r` focus a panel, `cmd+enter` advance state, `esc` close.
- **`/ci/legacy-decisions/:id`** — explicit legacy escape hatch for
  the SPEC-021 `DecisionDetailPage` (committed → outcome capture flow).
  Reachable directly or via `localStorage.mz_legacy_decisions === 'true'`
  globally.

### State machine — first-class affordances

All 8 SPEC-023 brief states render with shape-glyph + color-token +
state-aware affordance per SPEC-030 §8.3:
`draft → human_review → simulation_pending → simulation_complete →
decision_pending → committed → in_review → closed`. New chip palette
in `--color-state-*` tokens (light + dark, AA-contrast verified).

### New components

```
frontend/src/components/ci/decisions/
├── BriefsTab.tsx              — list view (Linear-style)
├── DecisionWorkspace.tsx      — 5-panel composite
├── BriefPanel.tsx             — top: question + state chip + options
├── EvidencePanel.tsx          — left: refs grouped by type
├── SimulationPanel.tsx        — center: scenario / Monte Carlo /
│                                war-game (SPEC-032 placeholder)
├── RecommendationPanel.tsx    — right: top option + counter +
│                                rank disclaimer + commit CTA
├── ReasoningTraceDrawer.tsx   — Sentry-style timeline drawer
├── StateMachineChip.tsx       — pill + popover; nextForwardTransition
│                                helper; STATE_META + ALLOWED_TRANSITIONS
├── BriefEditableField.tsx     — Stripe-style inline-edit primitive
└── OptionEditor.tsx           — modal: add/edit/delete option
```

`frontend/src/api.ts` extended with `decisionBriefsApi` (list, get,
create, patch, archive, addOption, removeOption, transition) +
all SPEC-023 types (`BriefState`, `EvidenceRef`, `DecisionBrief`,
`DecisionBriefList`, etc.).

### Design tokens added

`frontend/src/index.css`: state-machine palette
(`--color-state-{draft,review,sim,decide,committed,review-out,closed}`),
density tokens (`--space-panel-pad/-gap/-row-gap`), per-panel shadow
(`--shadow-workspace-panel`), `[data-density="compact"]` halving
scope. Global `@media (prefers-reduced-motion: reduce)` block
neutralizes animation/transition durations and decorative transforms.

### Quality gate (Stage 4 + 6 + 7)

- `npm run build` → clean (1.23 MB JS / 67 KB CSS, 1m02s)
- `npx tsc --noEmit` → clean
- `npx vitest run` → **39 test files, 256 cases passing, 19 it.todo,
  zero failures, zero regressions** (was 240 before Stage 5; +16
  regression cases added in Stage 6)

### Stage 5 red-team / Stage 6 fix-all

13 actionable findings (5 blockers, 8 majors). Closed in Stage 6:
- All 5 blockers: contrast tokens (light + dark), Tab-reachable list
  rows, keyboard-activatable inline edit, forward-only `cmd+enter`.
- 7 of 8 majors: `prefers-reduced-motion`, save-error inline alerts,
  `simulation_complete` copy fix, announce-storm suppressed, drawer
  focus trap, 401 → `mz:auth-expired` event + redirect, "Top option"
  / "Counter option" labels with rank disclaimer.
- 1 major deferred (#12 Drawer primitive reuse — anti-slop, filed in
  AGENT_BACKLOG with reason).
- 12 minor + 5 nit items deferred to AGENT_BACKLOG with one-liner
  reasons.

### Backend dependencies

- `GET /decision-briefs` (list, cursor pagination)
- `GET /decision-briefs/{brief_id}` (full)
- `POST /decision-briefs` (create draft)
- `PATCH /decision-briefs/{brief_id}` (edit; draft/human_review only)
- `DELETE /decision-briefs/{brief_id}` (archive)
- `POST /decision-briefs/{brief_id}/options` (add)
- `DELETE /decision-briefs/{brief_id}/options/{id}` (remove)
- `POST /decision-briefs/{brief_id}/transitions` (advance state)

All shipped by backend Claude on 2026-05-09 (SPEC-023). See
`docs/API_CHANGELOG.md` for the corresponding entry.

### Backend asks (filed in `docs/AGENT_BACKLOG.md`)

- `[BACKEND]` `POST /decisions/from-brief?brief_id={id}` — mints a
  `decision_id` on commit (Q2 sign-off). Until shipped, "Commit
  decision" button renders disabled with tooltip.
- `[BACKEND]` `materiality_factors` JSONB shape on `/signals` items.
- `[BACKEND]` War-game adversary preview helper (SPEC-032).
- `[BACKEND]` Decision calibration time-series endpoint.

### Open issues / follow-ups

- **`/login` surface for `?session=expired` banner.** `App.tsx` now
  redirects on 401 but landing-page banner is the missing piece.
  Filed.
- **Lighthouse a11y on changed surfaces (light + dark, ≥95).** Stage
  5 environment had no headless Chromium; deferred to a deploy gate
  follow-up. Filed.
- **12 minor + 5 nit red-team items** — see `[FRONTEND] SPEC-030
  deferred items` in AGENT_BACKLOG.

### Spec

`specs/SPEC_030_decision_workspace_v2.md` — Status: **Shipped
2026-05-09**. Closes Loop #1 of SPEC-029. Loop #2 (SPEC-032
War-Game Multi-Adversary UI) opens next.

---

## 2026-05-09

### Surfaces
- **AGENTS.md protocol adopted.** All UI changes from this date forward will
  be logged here.

### Backend dependencies
- See `docs/API_CHANGELOG.md` for the corresponding entry.

### Open issues
- **InboxTab login wall** (filed in `docs/AGENT_BACKLOG.md`). First PR target
  for Antigravity to validate the workflow end-to-end. (RESOLVED)

## 2026-05-09 (Inbox Login Wall Fix)

### Surfaces
- **CIPage**: Default tab for unauthenticated users is now `digest` (which works without auth).
- **InboxTab**: Replaced the login-wall message with a real login CTA + button that routes to `/login`.

## 2026-05-09 (Phase 1 Cockpit Primitives)

### New components
- `MetricRing`: SVG progress indicator with semantic thresholds.
- `Sparkline`: Minimalist SVG line chart for trend visualization.
- `HeroCard`: Elevated component wrapper using Phase F shadows.
- `Timeline`: Vertical chronological list with `framer-motion`.
- `AgentStatusBar`: Live telemetry ticker indicating agent loops.

### Surfaces
- `index.css`: Added Phase F dark theme tokens (`#0d1117`, `#161b22`, etc.) and `Syne` / `DM Mono` typography.

## 2026-05-09 (Phase 2-4 Cockpit Primitives)

### New components
- `ConfidenceBadge`: A primitive to display explicit uncertainty bands and scores.
- `EvidenceAffordance`: A primitive to render deep-linkable evidence chains with source/passage visibility.
- `DisagreementPanel`: A surface for side-by-side agent/source conflict resolution.

### Surfaces
- **Sensing Feed**: Implemented `SensingFeed` as the new Always-On continuous feed.
- **InboxTab**: Replaced the default layout entirely with `SensingFeed`.

## 2026-05-09 (SPEC-023 Sign-off & Main Shell Upgrade)

### Surfaces
- **LandingPage**: Full visual overhaul using Phase F Cockpit design. Added dark glassmorphic components, `AgentStatusBar` telemetry, and dynamic background.
- **CIPage**: Redesigned the main application shell. Replaced horizontal topbar with a dark high-density sidebar. Added global agent telemetry monitoring the Flywheel.

### Cross-Cutting
- Signed off `SPEC_023_decision_briefs.md` for the backend data contract.
