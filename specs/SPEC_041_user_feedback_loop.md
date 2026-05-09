# SPEC_041: User Feedback Loop — in-app widget + autonomous triage

Status: **Stage 2 complete (DESIGN appended 2026-05-09); Stage 3 (TDD) opens**

✓ Signed off by user 2026-05-09 (recommended defaults selected for Q1–Q4)
Owner: Frontend Claude (cross-cutting — backend already shipped)
Loop: `docs/runbooks/RALPH_LOOP.md`
Depends on: backend feedback infra (shipped: migration 020, `api/routes/feedback.py`,
`services/steward_signals.py` already pulls from `feedback_entries`).
Inspired by: `C:\Users\kapil\Scriptiva_SCA` feedback system; user-asked port.

---

## 1. Goal

Ship an **in-app feedback widget** visible on every authenticated Market
Zero surface so any user can report a bug, file a feature request, flag a
data-quality issue, or request new data with one click. Each submission
attaches the route, the entity context (when on a brief / dossier / war
room), screenshots (paste / drag-drop), and an auto-collected diagnostic
bundle (console errors + failed requests + page state). The submission is
durable in the existing `feedback_entries` table, mirrored to a checked-in
markdown tracker, and triaged + (where safe) auto-fixed by Claude on a
45-minute cron via the Ralph Loop.

The point: **close the loop**. Today users hit a bug and have nowhere to
log it; the next time they open the app, the same bug is still there. After
this loop, they can submit, see "received," and either come back to a fix
the next session or — for `data_quality` / `data_request` items — see the
Data Steward auto-resolve.

## 2. Why now

- The backend (migration 020 + `/feedback` routes + steward auto-routing
  for `data_quality` / `data_request` categories via
  `services/steward_signals.py:150`) **already shipped** and has zero
  frontend consumer today.
- Market Zero is moving from "demo grade" to "production polish" (the
  whole point of SPEC_029); a feedback channel is the cheapest way to
  learn what's actually breaking for real users.
- The user has explicitly asked for this and called out the Scriptiva
  system as the reference implementation.
- The auto-triage cron lets me (Claude) keep the queue from rotting
  between user-initiated sessions.

## 3. Surfaces touched

### 3.1 New frontend files

```
frontend/src/lib/diagnostics.ts                — global install: console.error + fetch wrappers
frontend/src/components/feedback/FeedbackWidget.tsx     — chat-style submission flow
frontend/src/components/feedback/FeedbackButton.tsx     — floating pill (bottom-right)
frontend/src/components/feedback/index.ts                — re-exports
frontend/__tests__/feedback/FeedbackWidget.test.tsx
frontend/__tests__/feedback/FeedbackButton.test.tsx
frontend/__tests__/feedback/diagnostics.test.ts
```

### 3.2 Frontend files modified

```
frontend/src/api.ts        — append `feedbackApi` (submit, list, update, stats)
frontend/src/App.tsx       — mount <FeedbackButton/> at root (auth-aware, route-aware)
frontend/src/index.css     — small additions for the feedback pill / panel tokens
```

### 3.3 Repo-level new files

```
feedback/live_user_feedback.md   — append-only chronological tracker (in repo)
feedback/backlog.jsonl           — machine-readable queue mirror (in repo)
feedback/sync.sh                  — fetches /feedback?status=new and updates the tracker + jsonl
feedback/process.sh               — runs triage; optionally fixes auto-safe items
feedback/.gitignore               — ignore screenshots/* by default
.claude/commands/triage-feedback.md   — assessment-only slash command
.claude/commands/process-feedback.md  — full Ralph Loop slash command
.claude/commands/feedback-cron.md     — cron entrypoint (sync → triage → safe-fix)
docs/UI_CHANGELOG.md             — entry on land
docs/API_CHANGELOG.md            — entry on land (no new endpoints, but documents
                                   the now-active consumer + steward routing
                                   behavior)
```

### 3.4 Backend (already shipped — verify only)

- `schema/migrations/020_feedback_entries.sql` ✓ exists
- `api/routes/feedback.py` ✓ exists (POST/GET/PATCH/stats; 6 categories,
  4 priorities, 5 statuses)
- `services/steward_signals.py:150` ✓ pulls `feedback_entries` where
  `category IN ('data_quality', 'data_request')` into the steward queue
- `tests/test_feedback_api.py` ✓ exists (191 lines, validation + CRUD)

The only backend gap (filed as a follow-up, **not** blocking this loop):
the `attachments` JSONB column accepts arbitrary blobs but there's no
size-limit / mime-type guard on the API side. We mitigate client-side
(2 MB / `image/*` only). Backend hardening filed as `[BACKEND]` in
AGENT_BACKLOG.

## 4. Data contract

### 4.1 Endpoints consumed

```
POST   /feedback                  → submit; returns { feedback: { id, ... } }
GET    /feedback                  → list (filters: status, category, limit, offset)
GET    /feedback/stats            → totals by category / status / steward auto-resolve count
PATCH  /feedback/{feedback_id}    → update status / priority / resolution / resolved_by
```

All routes are public-write today (`POST` does not call `require_role`);
this matches the user's intent — anyone reporting a bug should not be
forced to authenticate. Listing / patching is for triage tooling.

### 4.2 TypeScript types added to `frontend/src/api.ts`

```ts
export type FeedbackCategory =
  | 'bug' | 'issue' | 'enhancement' | 'feature'
  | 'data_quality' | 'data_request';

export type FeedbackPriority = 'low' | 'medium' | 'high' | 'critical';
export type FeedbackStatus =
  | 'new' | 'triaged' | 'in_progress' | 'resolved' | 'rejected';

export interface FeedbackAttachment {
  data: string;          // data:URI base64
  filename: string;
  mime_type: string;
  size_bytes: number;
}

export interface FeedbackDiagnosticContext {
  errors: Array<{ ts: string; message: string; stack?: string }>;
  failed_requests: Array<{ ts: string; method: string; url: string; status?: number; body?: string }>;
  user_agent: string;
  viewport: { w: number; h: number };
  theme: 'light' | 'dark';
  density?: 'spacious' | 'compact';
  route: string;
}

export interface FeedbackEntityContext {
  brief_id?: string;
  signal_id?: string;
  decision_id?: string;
  entity_type?: string;
  entity_id?: string;
  war_room_id?: string;
}

export interface FeedbackCreateBody {
  category: FeedbackCategory;
  title: string;
  description?: string;
  priority?: FeedbackPriority;
  page_url?: string;
  user_id?: string;
  session_id?: string;
  entity_context?: FeedbackEntityContext;
  diagnostic_context?: FeedbackDiagnosticContext;
  attachments?: FeedbackAttachment[];
}

export interface FeedbackEntry {
  id: string;
  category: FeedbackCategory;
  title: string;
  description?: string;
  priority: FeedbackPriority;
  status: FeedbackStatus;
  resolution?: string;
  resolved_by?: 'human' | 'steward' | string;
  page_url?: string;
  entity_context?: FeedbackEntityContext;
  diagnostic_context?: FeedbackDiagnosticContext;
  attachments: FeedbackAttachment[];
  steward_action_id?: string;
  created_at: string;
  updated_at: string;
}

export const feedbackApi = {
  submit:  (body: FeedbackCreateBody): Promise<{ feedback: FeedbackEntry }>  => /* POST */,
  list:    (filter?: { status?: FeedbackStatus; category?: FeedbackCategory;
                       limit?: number; offset?: number }): Promise<{
            items: FeedbackEntry[]; total: number; limit: number; offset: number; }> => /* GET */,
  update:  (id: string, patch: { status?: FeedbackStatus; priority?: FeedbackPriority;
                                 resolution?: string; resolved_by?: string }):
            Promise<{ feedback: FeedbackEntry }> => /* PATCH */,
  stats:   (): Promise<{ total: number; by_category: Record<string, number>;
                         by_status: Record<string, number>;
                         auto_resolved_by_steward: number }> => /* GET /stats */,
};
```

The widget itself uses only `submit`. The slash commands + cron call
`list` + `update`. `stats` is for the future admin dashboard
(out of scope this loop).

## 5. States to support

For the widget:

| State | What renders | Failure mode |
|---|---|---|
| Pill closed | Floating bottom-right pill ("Feedback") with subtle shadow | n/a |
| Open / greeting | 6-button category grid | n/a |
| Category selected | Multi-line textarea + screenshot affordances | n/a |
| Description provided | Priority pill row (low / medium / high / critical) | n/a |
| Priority selected | Confirm summary card + Submit / Start over | n/a |
| Submitting | Disabled UI + "Submitting…" message | — |
| Submitted | "Recorded! ID: abc12345…" + Close button | n/a |
| Error | Inline `role="alert"` + Try again | Network 5xx, validation 4xx |
| Disabled (route) | Pill not rendered | Landing `/` and `/login` |
| Disabled (config) | Pill not rendered | `localStorage.mz_feedback_disabled === 'true'` (dev override) |

For the page lifecycle:

- `installDiagnostics()` runs **once per session** at App mount; wraps
  `console.error` and `window.fetch` (and `XMLHttpRequest` if needed) to
  push into a ring buffer (max 50 entries each, FIFO) so we don't grow
  unbounded.
- `collectDiagnostics()` snapshots the buffer + page metadata at submit
  time.
- `clearDiagnostics()` empties the buffer after a successful submit so
  the next report starts clean.

## 6. Keyboard contract

| Surface | Shortcut | Action |
|---|---|---|
| Anywhere | `?+f` | Open feedback widget (filed as a future enhancement; v1 is mouse-driven) |
| Pill closed | `Tab` to it, `Enter` | Open the panel |
| Panel open | `Esc` | Close panel |
| Greeting | `1`–`6` (or arrow + `Enter`) | Pick a category |
| Description state | `Cmd+Enter` | Submit textarea |
| Description state | `Ctrl+V` | Paste a screenshot |
| Anywhere with attachments | `Backspace` on a thumbnail | Remove that attachment |
| Priority state | `←` / `→` | Move selection across priority pills |
| Priority state | `Enter` | Confirm selected priority |
| Confirm state | `Cmd+Enter` | Submit |

## 7. Accessibility contract

- The pill is a `<button>` with `aria-haspopup="dialog"`. The panel is
  `role="dialog" aria-modal="true" aria-labelledby="feedback-title"`.
- Initial focus on open lands inside the panel (first category button).
- Tab is trapped inside the open dialog (first ↔ last cycle).
- Esc closes; `aria-live="polite"` announces state transitions
  ("category selected", "priority selected", "submitted").
- Submission errors render in `role="alert"` so screen readers announce.
- Color is never the sole carrier — every priority pill has a shape
  glyph (◯ low, ◐ medium, ◑ high, ● critical) plus its label.
- `prefers-reduced-motion: reduce` collapses pill open/close and panel
  slide animations to opacity-only (the global `index.css` block from
  SPEC_030 covers this — no widget-level work needed).

## 8. Slash commands + cron — autonomous triage

### 8.1 Three commands (under `.claude/commands/`)

- **`triage-feedback.md`** — assessment only. Reads the new entries,
  reproduces each from code, classifies each (`Implement` /
  `Human Decision Needed` / `Out of Scope` / `Already fixed`), updates
  status to `triaged` + writes a Jira-style assessment to
  `feedback/live_user_feedback.md`. **No code changes.**
- **`process-feedback.md`** — full Ralph Loop. Runs triage + a Stage
  4–7 loop on each `Implement` item: spec → tdd → build → red-team →
  fix-all → deploy. Used by the human (`/process-feedback`) and the
  cron (in restricted mode).
- **`feedback-cron.md`** — the entry point the 45-minute cron calls.
  Internally:
  1. Run `bash feedback/sync.sh` — pulls all `status='new'` entries
     from `/feedback?status=new` into `feedback/backlog.jsonl` and
     appends a header to `feedback/live_user_feedback.md`.
  2. If queue empty: log `chore(feedback-cron): empty queue` and exit.
  3. Run `/triage-feedback` (assessment only). Status → `triaged`.
  4. **Restricted auto-fix gate** — for each item where
     `verdict === 'Implement' && scope_estimate === 'S' && labels does
     NOT include any of [api, schema, auth, security]`, run
     `/process-feedback` against ONLY that one item.
  5. Items not auto-fix-safe stay `triaged` for the next human-driven
     `/process-feedback` invocation.
  6. Commit any changes under `chore(feedback-cron): <n> items` and
     `git push`.

### 8.2 Pause switch

A flag file `feedback/.paused` (or env `MZ_FEEDBACK_CRON_PAUSED=true`)
short-circuits the cron at step 1 with a `chore(feedback-cron): paused`
log. Human can pause via:
```
touch feedback/.paused && git commit -am 'chore: pause feedback cron'
```

### 8.3 Cron registration

Use the `schedule` skill on first deploy: `/schedule` with
`--every 45m --command /feedback-cron`. The cron lives in the user's
local `~/.claude/schedules/` (or wherever the harness stores them) —
not committed to the repo. The repo carries the script and slash
commands; the schedule is per-user per-machine.

## 9. Markdown tracker — `feedback/live_user_feedback.md`

Append-only. Two sections per cron tick:

```
## 2026-05-09T14:30Z — sync (cron)

3 new submissions pulled. Backlog now: 7 new + 4 triaged.

### New entries

- [`abc12345`] **bug** · `/ci/decisions/d-001` · _high_ — "Brief panel
  scrolls instead of expanding when I add a 4th option"
  → Assessment: Implement; scope: S; labels: ui, decisions
- [`def67890`] **data_quality** · `/ci?tab=signals` · _medium_ —
  "Shire UK lists pre-2019 mergers as active sponsor"
  → Auto-routed to Data Steward (steward_action_id: s-9911)
- [`9f8e7d6c`] **enhancement** · `/ci/decisions/d-001` · _low_ —
  "Make t-trace drawer remember last open state per brief"
  → Assessment: Human Decision Needed (per-brief vs per-user state)

### Triaged this tick

- [`abc12345`] picked up by /process-feedback; result: shipped in
  commit 7e3bf0e (frontend/src/components/ci/decisions/BriefPanel.tsx)

### Awaiting human

- [`9f8e7d6c`] Human Decision Needed
```

Each `### New entries` line cross-references the AGENT_BACKLOG so a
[FRONTEND] or [BACKEND] item is auto-filed for any "Human Decision
Needed" verdict.

## 10. Definition of Done

- [ ] All 7 new frontend files in §3.1 implemented + Vitest-tested.
- [ ] `frontend/src/api.ts` extended with §4.2 types — names match
      `schema/openapi.json` exactly (regen once with backend).
- [ ] `<FeedbackButton/>` mounted in `App.tsx`, hidden on `/`, `/login`,
      and when `localStorage.mz_feedback_disabled === 'true'`.
- [ ] Diagnostics auto-installed at App mount; ring buffers cap at 50
      each.
- [ ] Screenshot paste / drag-drop / file-picker; cap 5 images at 2 MB
      each; client-side mime check.
- [ ] All keyboard shortcuts in §6 work; `Esc` closes; focus is trapped.
- [ ] Lighthouse a11y ≥95 on at least one route mounting the widget
      (light + dark).
- [ ] `feedback/live_user_feedback.md` + `feedback/backlog.jsonl` +
      `feedback/sync.sh` + `feedback/process.sh` checked in.
- [ ] Slash commands at `.claude/commands/triage-feedback.md`,
      `process-feedback.md`, `feedback-cron.md` checked in.
- [ ] Cron registered (per-user instruction in `feedback/README.md`
      since the schedule itself is not repo-state).
- [ ] `cd frontend && npm run build && npx tsc --noEmit && npx vitest run`
      exits 0.
- [ ] `python -m pytest tests/test_feedback_api.py -v` exits 0
      (existing tests continue to pass).
- [ ] `docs/UI_CHANGELOG.md` + `docs/API_CHANGELOG.md` entries appended.
- [ ] Screenshots committed to `docs/screenshots/SPEC_041/` (closed pill,
      open panel, screenshot-attached state, submitted state, light + dark).
- [ ] No regressions to existing 256-test vitest suite.

## 11. Tests (Stage 3 will list)

- `FeedbackButton.test.tsx` — visible on `/ci`, hidden on `/` and
  `/login`; pill click opens panel; respects `mz_feedback_disabled`.
- `FeedbackWidget.test.tsx` — every chat state; category pick → input
  shown; submit happy path; error path renders alert; screenshot
  paste appends thumbnail; remove screenshot button; Esc closes; focus
  trapped.
- `diagnostics.test.ts` — install wraps `console.error` and `fetch`;
  buffer caps at 50; collect snapshots metadata; clear empties.
- E2E smoke: render `<App/>` with `mz_auth_token` present, mount
  `/ci`, find feedback pill, simulate full submission against a
  mocked `feedbackApi.submit`.

## 12. Open questions — RESOLVED at sign-off (2026-05-09)

1. **Q1 — Landing-page visibility.** ✓ Resolved: hide on `/` and
   `/login`. Widget is product-only.
2. **Q2 — Auto-fix-safe gate threshold.** ✓ Resolved: cron auto-fixes
   ONLY when `verdict=Implement && category=bug && scope_estimate=S
   && labels excludes any of [api, schema, auth, security]`. All other
   verdicts stay `triaged`.
3. **Q3 — Authenticated-only submission?** ✓ Resolved: keep the
   POST public-write (zero-friction reports). Anonymous-spam mitigation
   is filed as a `[BACKEND]` follow-up (rate-limit by IP).
4. **Q4 — Pill placement.** ✓ Resolved: bottom-right on every
   surface EXCEPT `/workspace` where it auto-shifts to bottom-LEFT to
   clear the chat send-button. Single conditional in the component.

## 12a. Design notes (Stage 2 — completed 2026-05-09)

### 12a.1 Reference frames

| Surface | Lift from | What |
|---|---|---|
| Floating pill | **Linear "?" / Stripe support widget** | Tiny rounded-pill bottom-right with subtle accent ring; a single icon + word. |
| Chat-style flow | **Scriptiva FeedbackWidget** (paste-proven) | Chat bubble back-and-forth, category pick → describe → priority → confirm. Translates 1:1 to our design tokens. |
| Confirm summary | **Apple Mail send sheet** | Card preview of what will be sent, big primary action, "Start over" secondary. |
| Submitted state | **Linear "issue created"** toast | ID chip + "Recorded" + soft glow. |

We're stealing the *flow* and *anatomy* from Scriptiva, but the visual
language is Market Zero's: Syne for the panel title, DM Sans for body,
DM Mono for the ID chip; CSS custom properties (`var(--color-accent)`,
`var(--color-surface)`, etc.) — no Tailwind color utilities.

### 12a.2 Layout — closed pill (44 × 116 px, bottom-right)

```
                            ┌─────────────────┐
                            │ 💬  Feedback    │  <— --color-accent ring,
                            └─────────────────┘     --shadow-sm,
                                ↑ 24px from edge    radius-pill
```

On `/workspace` the SAME pill renders bottom-LEFT instead (Q4
resolution). Component reads `useLocation().pathname` and chooses
`right: 24px` vs `left: 24px`.

### 12a.3 Layout — open panel (420 px wide, max 640 px tall, light theme)

```
┌────────────────────────────────────────────┐
│ 💬  Feedback                            [×]│  <— --font-display Syne 14, 600
├────────────────────────────────────────────┤
│  [assistant]  Hi! What kind of feedback?   │  <— bg --color-surface-2,
│                                              │      ink-2, radius-card
│                                              │
│  [Bug] [Issue] [Enhancement]               │
│  [Feature] [Data quality] [Data request]   │  <— 6 buttons, 2 cols
│                                              │
│                                              │
│                                              │
│ ─────────────────────────────────────────── │
│                                              │  <— action area (per state)
│  ◯ low   ◐ medium   ◑ high   ● critical    │      shape glyph + label
│                                              │
└────────────────────────────────────────────┘
   ↑ 24px from edge, radius-card 16px, --shadow-lg
```

When a screenshot is attached, a 56×56 thumbnail strip appears between
the messages and the action area, with `[×]` hover-to-remove.

Submitted state replaces the action area with:
```
  Recorded! ID: abc12345…
  We'll triage on the next 45-min cron tick.
  [Close]
```

### 12a.4 Per-state action area

| Chat state | What renders in the action area |
|---|---|
| `greeting` | 2×3 grid of category buttons with shape-glyph + label |
| `category_selected` | textarea + send button + paperclip button |
| `description_provided` | 4-button priority pill row |
| `priority_selected` | "Submit feedback" primary + "Start over" secondary |
| `confirmed` (busy) | full-width disabled bar with "Submitting…" pulse |
| `submitted` | "Close" full-width secondary |
| `error` | inline `role="alert"` red pill + "Try again" + "Close" |

### 12a.5 Token call-outs (none new — reuse SPEC_029 + SPEC_030)

```
--color-surface         panel bg
--color-surface-2       category buttons + textarea bg
--color-accent          primary submit / pill ring
--color-accent-soft     pill hover halo
--color-line            divider between header / messages / action area
--color-ink / -2 / -3   text
--color-red / -soft     error path
--shadow-sm / -lg       pill / panel
--radius-pill           floating pill
--radius-card           panel (16) + thumbnails (12) + buttons (12)
--font-display          panel title
--font-body             prose
--font-mono             ID chip on submitted state
```

No new tokens this loop. The SPEC_029 §4.6 set covers it.

### 12a.6 Motion specs

| Element | Trigger | Animation | Duration | Easing |
|---|---|---|---|---|
| Pill enter | mount | opacity 0→1 + translateY 8→0 | 220ms | `--motion-out` |
| Panel open | pill click | scale 0.96→1 + opacity 0→1 + translateY 8→0 (origin = pill) | 240ms | `--motion-out` |
| Message append | new chat bubble | fade-up 0→1 + translateY 4→0 | 180ms | `--motion-out` |
| Submit pulse | submitting state | content opacity 1→0.6 + caption pulse | 120ms | linear |
| Submitted | resolve | green-soft check fades in | 240ms | `--motion-out` |
| Error pill | reject | shake 2× translateX ±2px | 160ms | linear |
| Pill hover | hover | shadow `sm → md` + ring opacity 0→1 | 140ms | linear |

All gated by `prefers-reduced-motion: reduce` via the SPEC_030 global
block — no widget-local @media query needed.

### 12a.7 Light + dark thumbnails

- **Light**: `--color-surface = #FFFFFF` panel; pill text uses
  `var(--color-ink)`; primary button uses `var(--color-accent)` with
  white text.
- **Dark**: `--color-surface = #161b22` panel; pill text uses
  `#c9d1d9`; primary button still `var(--color-accent)` (which switches
  to `#58a6ff` per `html.dark` overrides). Both verified ≥ 4.5:1
  contrast on the foreground / background pair.

### 12a.8 Self-review checklist (gate to Stage 3)

- [x] Every state in §5 has a layout/affordance line (§12a.4).
- [x] Every interactive element has a keyboard story (§6 + §12a.4).
- [x] Light + dark token plan documented (§12a.5 + §12a.7).
- [x] Motion respects `prefers-reduced-motion` (§12a.6 — inherits
      SPEC_030 global block).
- [x] Reference frames cited (§12a.1).
- [x] Tab focus order documented (panel-open: close button → first
      category → submit). Trapped per §7.
- [x] Empty / loading / error / submitted states all addressed.

Self-review passes. **Stage 3 (TDD) opens.**

## 13. Out of scope (this loop)

- Admin triage dashboard inside the app (`/admin/feedback`) — filed
  as a future loop; today triage happens via the slash commands +
  markdown tracker.
- Email / Slack notifications when a `critical` item lands.
- Per-feedback attachments hardening on the backend (size + mime
  guard) — filed as `[BACKEND]` follow-up.
- Per-user "my feedback" page — explicitly chosen out at sign-off
  (option 1 selected; user-side visibility is just the submission ID
  + the codebase-side tracker).
- E2E test against a real Postgres — backend tests already cover
  CRUD; frontend tests use `vi.stubGlobal('fetch', ...)`.

## 14. Acceptance for Stage 1

- [ ] User signs off below by replacing this line with `✓ Signed off
      by user 2026-05-09`.
- [ ] User answers Q1–Q4 (or accepts proposed defaults).

Once accepted, Stage 2 (DESIGN) opens.
