# UI Changelog

Append-only log of every frontend surface change. **Antigravity writes; Claude
reads at the start of every session.**

Format per entry: `## YYYY-MM-DD` then sections `### Surfaces`,
`### New components`, `### Backend dependencies` (link to API_CHANGELOG entries
this depends on), `### Open issues`. Omit empty sections.

Screenshots of material visual changes live under `docs/screenshots/`.

---

## 2026-05-09 (SPEC-042 — Centralized Product Backlog + repo doc cleanup; Loop #3 closed)

Pure docs / process loop. **No code surfaces touched, no API changes, no
frontend behavioral changes.** Shipped because the planning surface had
fragmented across 4 partially-overlapping backlog files and the repo
had accumulated 158 stale .md documents. Result: a single canonical
product backlog + a clean docs tree.

### What shipped

- **`docs/PRODUCT_BACKLOG.md`** — 76 PB-NNN items consolidated from
  `BACKLOG.md`, `ROADMAP.md`, `docs/backlog.md`, and the open asks in
  `docs/AGENT_BACKLOG.md`. Front-of-file dashboard with status counts
  (regenerable via `--regenerate-summary`). 7-state taxonomy:
  `proposed | triaged | blocked | in-progress | shipped | archived | wontfix`.
- **`scripts/validate_product_backlog.py`** — schema validator + dashboard
  regenerator. Exits 0 if every PB item has all required fields, IDs are
  unique, cross-references resolve.
- **`scripts/migrate_legacy_backlogs.py`** — one-shot migration helper
  (idempotent; re-runnable). Pure functions; library tests cover Phase
  skipping + agent-ask filtering.
- **`tests/test_product_backlog.py`** — 14 pytest cases covering schema,
  uniqueness, cross-refs, dashboard regeneration, migration, archive
  redirects.
- **`docs/archive/`** new directory tree with 158 archived files across
  6 categories (brainstorms, communications, reports, benchmarks,
  superseded-specs, legacy-backlogs). Each archived file has a 1-line
  redirect header at its original path pointing readers at the canonical
  successor.

### What got archived

| Category | Count | What |
|---|---|---|
| `brainstorms/` | 7 | Pre-Phase F vision rough drafts (Feb–Mar 2026) |
| `communications/` | 2 | `dev_2_lead.md`, `comp_intelligence.md` |
| `reports/` | 7 | One-time test/analysis reports |
| `benchmarks/` | 98 | Auto-generated `benchmark/reports/eval-*.md` |
| `superseded-specs/` | 40 | SPEC_001–SPEC_018 series + drafts (HARNESS_AUDIT, SESSION_REPORT, EXECUTION_PLAN, etc.) |
| `legacy-backlogs/` | 4 | `BACKLOG.md`, `ROADMAP.md`, `docs/backlog.md`, `docs/product_backlog_research_and_intelligence.md` |
| **Total** | **158** | |

### What stayed put (active)

- `CLAUDE.md`, `AGENTS.md`, `lead_notes_4_dev.md` (strategic, still
  referenced)
- `docs/AGENT_BACKLOG.md`, `docs/UI_CHANGELOG.md`, `docs/API_CHANGELOG.md`
- `feedback/*` (cron-managed)
- `frontend/README.md`, `harness/*`, `.claude/*`
- All current specs `SPEC_019` and newer (47 specs remain at `specs/`)
- `specs/CI_Agent_Reimagined_Spec.md` (north-star)
- `specs/SPEC_021_decision_flywheel.md` (still useful context)

### Quality gate

- `python -m scripts.validate_product_backlog` — clean
- `python -m pytest tests/test_product_backlog.py -v` — **14/14**

### Stage 5 red-team / Stage 6 fix-all

- 0 blockers
- 3 majors filed; 2 closed in Stage 6 (`AGENTS.md:211` redirect, `MEMORY.md`
  pointer); **M3 deferred by design** — the 74 migrated items need a
  triage pass to demote already-shipped items to `Status: shipped` and
  collapse duplicates. That's the next loop.

### Spec

`specs/SPEC_042_centralized_product_backlog.md` — Status: **Shipped
2026-05-09**.

### What's next

Per the user's directive ("then follow the rigor of working on the loop
step by step through the backlog"), Loop #4 begins by triaging the
74 unfiltered PB-rows: collapsing duplicates, demoting already-shipped
items to `Status: shipped` with the closing commit SHA, and assigning
`Owner` + `Priority` per remaining item. After triage, work begins on
the highest-priority `triaged` item.

---

## 2026-05-09 (SPEC-041 — User Feedback Loop; Loop #2 closed)

In-app feedback widget visible on every authenticated surface.
Captures bugs / issues / enhancements / features / data-quality /
data-request submissions, auto-attaches a privacy-filtered diagnostic
bundle (recent console errors + failed-fetch metadata + viewport +
theme + density + route), supports paste / drag screenshots, and
persists submissions to the existing `feedback_entries` table.
Triage runs on a 45-minute cron via three new slash commands.

### Surfaces

- **Floating "Feedback" pill** — bottom-right on every authenticated
  surface, bottom-LEFT on `/workspace` to clear the chat send button
  (Q4 sign-off). Hidden on `/`, `/login`, and when
  `localStorage.mz_feedback_disabled === 'true'`. Click dispatches
  `mz:open-feedback`.
- **Chat-style submission panel** — opens on `mz:open-feedback`.
  State machine: `greeting → category_selected →
  description_provided → priority_selected → confirmed →
  submitted | error`. 6 categories (bug / issue / enhancement /
  feature / data_quality / data_request). Esc closes; sessionStorage
  preserves the in-progress draft so an accidental Esc does not lose
  work. Tab is trapped inside the dialog (WCAG 2.4.3); initial focus
  lands on close button.
- **PII-filtered diagnostics** — `installDiagnostics()` runs once at
  App mount, wrapping `console.error` + `globalThis.fetch` (and
  `window.error` / `unhandledrejection`). URL search params with
  sensitive names (`token`, `api_key`, `authorization`, etc.) are
  redacted; bodies have JWTs and 32+-char alphanumeric runs scrubbed
  before truncation to 500 chars. Ring buffers cap at 50 entries each
  (FIFO eviction). Cleared after a successful submit.

### New components

```
frontend/src/components/feedback/
├── FeedbackButton.tsx       — floating pill (route-aware, theme-aware)
└── FeedbackWidget.tsx       — chat panel + state machine + draft persistence

frontend/src/lib/
└── diagnostics.ts            — install / collect / clear + PII redaction
```

`frontend/src/api.ts` extended with SPEC_041 types
(`FeedbackCategory`, `FeedbackPriority`, `FeedbackStatus`,
`FeedbackEntry`, `FeedbackCreateBody`, `FeedbackDiagnosticContext`,
`FeedbackEntityContext`, `FeedbackAttachment`,
`FeedbackListResponse`, `FeedbackStatsResponse`) +
`feedbackApi` (`submit` / `list` / `update` / `stats` / `remove`).

### Repo-level new files

```
feedback/
├── live_user_feedback.md   — append-only chronological tracker
├── backlog.jsonl            — machine-readable mirror of the queue
├── sync.sh                   — pulls /feedback?status=new and updates above
├── README.md                 — operator runbook for the loop
└── .gitignore                — ignores screenshots/* + .paused

.claude/commands/
├── triage-feedback.md       — assessment-only slash command
├── process-feedback.md      — full Ralph Loop on Implement items
└── feedback-cron.md          — 45-min cron entry point (sync → triage → safe-fix)
```

### Backend (no new tables — extended existing)

- New endpoint `DELETE /feedback/{id}` (returns 204) for privacy /
  GDPR retraction. Migration 020_feedback_entries.sql + the rest of
  the routes were shipped previously — this loop is purely
  additive.
- `tests/test_feedback_api.py` extended with 2 tests for
  `TestDeleteFeedback`.

### Cron + autonomous triage

- 45-minute cron (registered per-user via the `schedule` skill) runs
  `/feedback-cron`. Auto-fix gate per Q2 sign-off (SPEC_041 §8.1):
  ```
  verdict == 'Implement'
  && category == 'bug'
  && scope_estimate == 'S'
  && labels excludes any of: api, schema, auth, security
  ```
  Items inside the gate get shipped under `chore(feedback-cron):
  <id> <title>` commits (one per item, individually pushed for audit
  + revert friendliness). Items outside the gate stay `triaged` for
  human-driven `/process-feedback`. Pause via
  `touch feedback/.paused`.

### Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **43 files, 292 tests
  passing, 22 it.todo, zero failures, zero regressions** (was 256
  pre-loop)
- `python -m pytest tests/test_feedback_api.py -v` → **14/14**

### Stage 5 red-team / Stage 6 fix-all

4 majors filed in §13a; all 4 closed:
- M1 (PII filter on diagnostics)
- M2 (focus trap inside widget)
- M3 (sessionStorage draft persistence)
- M4 (`DELETE /feedback/{id}` endpoint + `feedbackApi.remove`)

15 minors + 5 nits deferred to AGENT_BACKLOG with reasons.

### Open issues / follow-ups

- **Admin retraction UI** for `DELETE /feedback/{id}` — currently
  only slash commands call it. Filed.
- **Vitest parallel-mode flakes** in 3 pre-existing primitive tests
  — not introduced by this loop. Filed.
- **15-minor backlog** under `[FRONTEND] SPEC-041 deferred items`.

### Spec

`specs/SPEC_041_user_feedback_loop.md` — Status: **Shipped
2026-05-09**. Loop #2 of the SPEC-029 reskin program is now closed.

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
