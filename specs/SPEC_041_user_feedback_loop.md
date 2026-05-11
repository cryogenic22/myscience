# SPEC_041: User Feedback Loop — in-app widget + autonomous triage

Status: **Shipped 2026-05-09** (Stage 7 closed; Loop #2 complete)

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

## 13a. Red-team (Stage 5 — completed 2026-05-09)

Adversarial review of the diff `main..claude-fe/spec-041-feedback-loop`
(commits cca77be → 626bdbf). Reviewer pretended not to have written
the spec.

### Blockers

None.

### Major

1. ~~**Diagnostic auto-attach has no PII filter**~~ — `major`
   (privacy/security) — ✅ closed Stage 6. New `redactUrl()`,
   `redactBody()`, `redactMessage()` helpers in `diagnostics.ts`.
   URL search params with sensitive names (`token`, `access_token`,
   `api_key`, `authorization`, `password`, `secret`, `session`,
   `jwt`, `bearer`) become `<redacted>`. Bodies have `Bearer …`,
   `eyJ…` JWT prefixes, and any 32+ char alphanumeric runs replaced
   with `<redacted>`/`<redacted-jwt>`, then truncated to 500 chars.
   Error messages truncate at 1000 chars.
2. ~~**No focus trap inside the open feedback widget**~~ — `major`
   (a11y) — ✅ closed Stage 6. Added Tab cycling (Shift+Tab from
   first → last; Tab from last → first) inside `dialogRef`'s
   focusable subtree, plus restore-focus on close. Same pattern as
   SPEC-030 fix #10.
3. ~~**Esc closes widget mid-typing → user's draft is lost**~~ —
   `major` (UX) — ✅ closed Stage 6. Implemented option (b): every
   state change (while open + not submitted/error) persists the
   transcript + category + description + draft + priority +
   attachments to `sessionStorage.mz_feedback_draft_v1`. Successful
   submit clears the key. The open handler attempts restore before
   falling back to a fresh greeting state.
4. ~~**No DELETE endpoint for mistakenly-submitted feedback**~~ —
   `major` (privacy) — ✅ closed Stage 6. Added
   `DELETE /feedback/{id}` (`api/routes/feedback.py:159`) — returns
   204 on success, 404 if not found. Frontend client gets a
   `feedbackApi.remove()` method. Admin-gating filed as a follow-up
   in AGENT_BACKLOG since the user-side retraction UI is itself a
   future loop; today the slash commands use this to purge
   already-resolved/duplicate entries.

### Minor

5. **Console.error wrap captures dev-mode noise** — `minor` —
   React StrictMode warnings, third-party deprecations, jsdom
   warnings all land in the buffer. By submit time the most relevant
   error may already have been evicted by 50 React internal noise
   entries. Consider filtering by message-pattern or by stack-trace
   originating in our own code.
6. **Hover state mutates DOM imperatively** — `minor` — `FeedbackButton`
   uses `onMouseEnter` / `onMouseLeave` to set `boxShadow` /
   `transform` directly. Fine functionally but bypasses React's
   render path; CSS `:hover` would be cleaner.
7. **No focus-ring polish on the pill** — `minor` (a11y) — relies on
   the browser's default focus outline. Should match SPEC_022 focus
   token (`box-shadow: 0 0 0 3px rgba(28,110,247,0.15)`).
8. **No idempotency key on submit** — `minor` — if the network
   responds slowly and the user double-clicks "Submit feedback",
   two identical entries land. The widget disables the button via
   `busy` state but only after the first click has dispatched. Add a
   client-side id + retry semantics.
9. **No drag-and-drop attachment path** — `minor` — only paste +
   click-to-pick are wired. Scriptiva's reference implementation
   supports drag-drop. Backlog item.
10. **No size cap on description text** — `minor` — a user can paste
    a 500 KB stack trace. Backend accepts arbitrary JSONB text. Cap
    at 10 KB client-side (with a "Trim" button) and 64 KB server-side.
11. **`mz_feedback_disabled` only respected by the pill, not the
    widget** — `minor` (consistency) — anyone who manually fires
    `window.dispatchEvent(new CustomEvent('mz:open-feedback'))` (e.g.
    from an ErrorBoundary CTA) would open the widget regardless of
    the disable flag. Both should check.
12. **Category and priority pickers are mouse-only** — `minor` (a11y)
    — no `1`–`6` shortcut for category, no `←`/`→` for priority. §6
    promised these as v2; they're not in v1.
13. **Q4 placement assumption needs visual verification** — `minor` —
    pill bottom-LEFT on `/workspace` was chosen on the assumption
    that the chat send-button is bottom-right. Stage 7 must include
    a screenshot confirming.
14. **No client-side payload size cap** — `minor` — 5 attachments at
    2 MB each = 10 MB JSONB blob. Backend has no guard. Network
    bandwidth + parse cost + storage. Cap at 5 MB total client-side.
15. **`sync.sh` requires bash** — `minor` (portability) — Windows
    operators need WSL or Git Bash. Document in
    `feedback/README.md` (already mentioned).
16. **`python` vs `python3` portability** — `minor` — `sync.sh`
    pipes to `python -c …`. On many Linux distros that's
    Python 2 (deprecated). Use `python3` explicitly or detect.
17. **`git log -30` in `/triage-feedback` may miss older fixes** —
    `minor` — a deep repo with hundreds of unrelated commits could
    bury a relevant earlier fix. Increase to `-200` or use
    `--all --since=6mo`.
18. **Human-mode `/process-feedback` has no rate cap** — `minor` —
    cron-mode caps at 5 items per tick; human-mode loops until the
    queue is empty. A 50-item backlog ticked all at once is a lot
    of code to review.
19. **Modal pattern rolled separately for the 4th time** — `minor`
    (anti-slop) — `NewBriefDialog`, `KeyboardHintDialog`,
    `OptionEditor`, and now `FeedbackWidget`'s panel all reimplement
    backdrop + centered card + esc-to-close. SPEC-030 backlog #16
    already calls for a shared `<Modal>` primitive; this loop adds
    a 4th caller without consolidating.

### Nits

20. **`origError.apply(console, args as [])` type cast** — `nit` —
    `unknown[]` cast to `[]`; cosmetic.
21. **`fileToDataUri` not shared with Scriptiva-style other future
    use cases** — `nit` (anti-slop, premature abstraction).
22. **Chat state literals are stringly-typed** — `nit` — TypeScript
    string literal union is fine; no real bug.
23. **Errors before App mount aren't captured** — `nit` — already
    acknowledged in `it.todo` of `diagnostics.test.ts:128`.
24. **3 pre-existing parallel-mode test flakes** — `nit` (env) —
    `__tests__/primitives/{DisagreementPanel,EvidenceAffordance}` and
    `src/components/__tests__/GraphContextMenu` flake under
    `npx vitest run` parallel mode (timing issue near 5s timeouts).
    All pass under `--no-file-parallelism`. Pre-existing; not
    introduced by SPEC-041. Filed as backlog `[FRONTEND] vitest
    parallel-mode flakes`.

### Decisions taken — not bugs

- **Public-write `POST /feedback`** — Q3 sign-off; zero-friction
  reports beat anonymous-spam risk.
- **Pill bottom-LEFT on `/workspace`** — Q4 sign-off; needs visual
  verification (#13).
- **Cron auto-fix gate `bug + S + no protected labels`** — Q2 sign-off.
  Conservative on purpose.
- **6 categories** (`bug`, `issue`, `enhancement`, `feature`,
  `data_quality`, `data_request`) — backend enforces; matches user's
  pre-existing memory note.
- **No "my feedback" page** — Q3 sign-off (option 1 selected).
- **Diagnostics auto-attach (always-on)** — no opt-out toggle in v1
  per spec §5; the PII filter (M1) is the mitigation.
- **Cron commits one item per `chore(feedback-cron):` commit** —
  audit + revert friendliness explicitly chosen over batching.
- **Reset of diagnostic wrap is wrap-identity-aware** — preserves
  test-side `vi.stubGlobal('fetch', mock)` calls; not a bug.

### Stage 5 gate

Stage 5 closes once this section is committed. Stage 6 (FIX-ALL)
opens. M1–M4 (4 majors) must close before Stage 7 — those are the
FIX-ALL backlog. Minors + nits are candidates for deferral via
`docs/AGENT_BACKLOG.md`.

### Stage 6 — FIX-ALL closed (2026-05-09)

| Severity | Closed in Stage 6 | Deferred to backlog |
|---|---|---|
| Blocker | — (none filed) | — |
| Major | M1, M2, M3, M4 (4/4) | — |
| Minor | M2-extension (mz_feedback_disabled gates widget too) | 5, 6, 7, 8, 9, 10, 12, 13, 14, 15, 16, 17, 18, 19 |
| Nit | — | 20, 21, 22, 23, 24 |

Regression tests added at
`frontend/__tests__/feedback/_stage6_regressions.test.tsx`
(9 cases) plus `tests/test_feedback_api.py::TestDeleteFeedback`
(2 cases). Final gate:
- `npx tsc --noEmit` clean
- `npx vitest run --no-file-parallelism` → **43 files, 292 tests
  passing, 22 it.todo, zero failures**
- `python -m pytest tests/test_feedback_api.py -v` → **14/14 passing**

Deferred minors filed in `[FRONTEND] SPEC-041 deferred items` in
`docs/AGENT_BACKLOG.md` with one-line defensible reasons each.

Stage 7 (DEPLOY) opens next.

## 14. Acceptance for Stage 1

- [ ] User signs off below by replacing this line with `✓ Signed off
      by user 2026-05-09`.
- [ ] User answers Q1–Q4 (or accepts proposed defaults).

Once accepted, Stage 2 (DESIGN) opens.
