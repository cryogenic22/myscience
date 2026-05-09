# The Ralph Loop — per-task execution protocol

Every frontend mini-spec under `specs/SPEC_029_app_aesthetics_upgrade.md`
ships through this 7-stage loop. The loop exists so that a non-trivial
cross-cutting change does not "drift" — each stage has explicit inputs,
explicit outputs, and an explicit gate before the next stage opens.

The loop is named after the Ralph-style lock-in execution model: one task at
a time, finished end-to-end, no half-built layers shipped to next iteration.

```
┌──────────────────────────────────────────────────────────────────┐
│   SPEC ──▶ DESIGN ──▶ TDD ──▶ BUILD ──▶ RED-TEAM ──▶ FIX-ALL ──▶ DEPLOY
│     ▲                                                          │  │
│     └─── post-deploy notes feed back into the next loop ◀──────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## Stage 1 — SPEC

**Input**
- A bullet from `specs/SPEC_029_app_aesthetics_upgrade.md` §5 surface audit,
  or a user request, or a `[FRONTEND]` item in `docs/AGENT_BACKLOG.md`.

**What you do**
- Draft `specs/SPEC_NNN_<surface>.md`. Required sections:
  1. **Goal** — one paragraph, what changes for the user.
  2. **Why now** — what blocks if we don't do this.
  3. **Surfaces touched** — exact files / routes.
  4. **Data contract** — endpoints consumed (link `schema/openapi.json`),
     types added to `frontend/src/api.ts`, no backend writes.
  5. **States to support** — loading, empty, error, success, disagreement,
     "fixture mode" if backend not yet ready, busy/optimistic.
  6. **Keyboard contract** — every interactive surface lists its shortcuts.
  7. **Accessibility contract** — focus order, ARIA roles, color-contrast
     decisions.
  8. **DoD** — checklist that `Stage 7 — DEPLOY` will tick.
  9. **Open questions** — flagged for user / backend before code.

**Output**
- The mini-spec at `specs/SPEC_NNN_*.md` with `Status: Draft`.

**Gate**
- User sign-off (line `✓ Signed off by user` at top). For cross-cutting
  changes (rare in a frontend-only mini-spec), backend agent sign-off too.
- Until the gate clears, do NOT proceed to Stage 2.

## Stage 2 — DESIGN

**Input**
- Signed-off mini-spec.

**What you do**
- Pull or sketch reference frames for each state listed in §5 of the spec.
  Sources we cite:
  - `specs/test.tsx` — the war-game prototype (north star for cockpit
    aesthetics).
  - Public references explicitly named: Apple Health, Apple.com, Oura, Linear,
    Spotify, Stripe, Vercel.
- Add a `## Design notes` section to the mini-spec with:
  - Wireframes (ASCII or `docs/screenshots/SPEC_NNN/design/*.png`).
  - State diagrams for any state machine (Decision Brief, War-Game run,
    fixture-mode toggle).
  - Token call-outs: which `--color-*`, `--shadow-*`, `--radius-*`, `--space-*`
    tokens this surface uses. New tokens go to `index.css` with rationale.
  - Motion call-outs: what animates, on what trigger, with what timing.
  - Light + dark thumbnails — every state, both themes.

**Output**
- Updated mini-spec.
- Reference assets under `docs/screenshots/SPEC_NNN/design/`.

**Gate**
- Self-review: does every state in §5 have a design? Does every interactive
  element have a keyboard story? Does the design respect
  `prefers-reduced-motion`?
- If any answer is no, loop back inside Stage 2.

## Stage 3 — TDD

**Input**
- Designed mini-spec.

**What you do**
- Author Vitest specs for every new or changed component:
  - One file per component: `frontend/__tests__/<dir>/<Component>.test.tsx`.
  - State permutations from spec §5 — each as a separate `it(...)`.
  - Keyboard-nav assertions where applicable (`fireEvent.keyDown`).
  - Snapshot tests in light AND dark (apply theme via `<ThemeProvider>` /
    `document.documentElement.classList`).
  - API client tests when adding to `api.ts` — mock `fetch`, assert request
    shape against `schema/openapi.json`.
- Author E2E smoke when route plumbing changes:
  `frontend/__tests__/e2e/<surface>.smoke.ts` (vitest + react-router test
  bed) — render the page mounted at the right path, assert headline /
  primary action exists.

**Output**
- All tests written. All tests FAIL (or skip with `it.todo`).
- Test file count + a list of names appended to spec under `## Tests`.

**Gate**
- `cd frontend && npx vitest run` shows the expected failures (the count
  matches the test list in the spec). No green tests yet.

## Stage 4 — BUILD

**Input**
- Failing test suite.

**What you do**
- Smallest unit first: API client → primitive → composite → page.
- One commit per logical step. Conventional commit format
  (`feat(spec-NNN): <thing>`).
- Run `vitest run --watch` while building. Tests turn green one by one.
- Reuse first — every "I need a thing" call-out in design must check
  `.claude/rules/anti-slop.md` before producing a new file.
- Inline styles for layout-critical surfaces; `var(--color-*)` only.

**Output**
- All tests green.
- `cd frontend && npm run build && npx tsc --noEmit && npx vitest run` clean.

**Gate**
- A single command: `npm run build && tsc --noEmit && vitest run` exits 0.
- If not, do NOT advance to red-team.

## Stage 5 — RED-TEAM

**Input**
- Green build.

**What you do — adversarial review against your own diff**
- Read the diff end-to-end as if you were a senior reviewer who had not
  seen the spec. For every component, ask:
  - What if the API returns 0 rows? 1 row? 10 000 rows?
  - What if the API returns 500? times out? returns malformed payload?
  - What if the user is unauthenticated? mid-session-expired?
  - What if the user has `prefers-reduced-motion: reduce`?
  - What if the viewport is 320px wide? 4K wide?
  - What if the user spams the action? double-clicks? loses connection
    mid-mutation?
  - Is every claim in the UI traceable to evidence (CI cardinal rule)?
  - Are all 8 design rules in `AGENTS.md §7 "Design rules"` honored?
  - Did I duplicate anything in `.claude/rules/anti-slop.md`?
- Run Lighthouse on the changed surface (light + dark). Target a11y ≥95.
- Run a screenshot diff if there's a previous version (manual is fine).

**Output**
- A `## Red-team` section appended to the spec listing every issue found.
  Format: numbered, with severity (`blocker | major | minor | nit`) and a
  one-line repro.
- A separate list at the bottom: "Decisions taken — not bugs" so future me
  doesn't re-litigate.

**Gate**
- Every `blocker` and `major` must move to FIX-ALL before deploy.
- `minor` and `nit` either fixed in FIX-ALL or filed under `[FRONTEND]` in
  `docs/AGENT_BACKLOG.md` with a defensible reason for deferring.

## Stage 6 — FIX-ALL

**Input**
- Red-team findings.

**What you do**
- Close every blocker + major. Add Vitest cases for any failure mode the
  red-team surfaced.
- Re-run Stage 4's gate command.
- If a fix changes the data contract (rare in frontend-only specs), update
  the spec, the AGENT_BACKLOG entry, and the `api.ts` types.

**Output**
- Updated spec with red-team items struck through (`~~item~~`) once fixed.
- Green build, again.

**Gate**
- Spec's `## Red-team` section: every `blocker` and `major` is struck.

## Stage 7 — DEPLOY

**Input**
- Spec with all gates passed.

**What you do**
- Final command sweep:
  - `cd frontend && npm run build`
  - `npx tsc --noEmit`
  - `npx vitest run`
- Capture screenshots into `docs/screenshots/SPEC_NNN/` (final / before /
  after — one per state per theme).
- Append `docs/UI_CHANGELOG.md` per AGENTS.md §4 template.
- Commit on a `claude-fe/spec-NNN-<short>` branch (per AGENTS.md §6;
  using `claude-fe/*` instead of the original `antigravity/*` prefix to
  signal the role-swap).
- Open a PR with the "Other-side impact: none" line OR a backlog link.
- Per AGENTS.md §6: squash merge, conventional commit message, paired with
  the changelog entry.

**Output**
- Merged PR. UI_CHANGELOG entry. Screenshots committed.
- Spec status flipped to `Status: Shipped <date>`.

**Gate**
- The next loop cannot begin until Stage 7 of the previous loop closes.
- Exception: if a stage is genuinely blocked on backend, file the
  `[BACKEND]` request, mark the spec `Status: Blocked on <ref>`, and start
  the NEXT spec's Stage 1. Do not stack two specs in Stage 4.

## Cross-cutting rules

- **One spec at a time in Stages 3–7.** Multiple specs may be in Stage 1–2
  simultaneously (specs are cheap; code is not).
- **Tests first, always.** No production line of code is written before its
  test exists and fails.
- **No silent fakes.** Anything not yet wired to a real backend renders a
  visible "fixture mode" pill so demos are honest.
- **Read the protocol every session.** AGENTS.md §11 daily handshake —
  read API_CHANGELOG, AGENT_BACKLOG, `git log --since=yesterday` before
  writing code.
- **Anti-slop catalogue first.** Before adding a function/component/util,
  search `.claude/rules/anti-slop.md` for an existing one to extend.
- **Never `useMemo` inside `.map()` loops.** Banned per CLAUDE.md (broke
  production once).

## Why this loop, vs. just shipping

A multi-surface reskin without a loop turns into:
- Half-built primitives (Sparkline ships, RadarChart never does).
- Drift between spec and code (spec says one state machine, code uses two).
- Skipped red-team (the bug found at demo time).
- Backend dependencies discovered mid-flight (and forgotten).

The loop is overhead the first time and saves the project the second. The
explicit gate between stages is what makes it Ralph-style: one stage open
at a time, one task complete before the next starts.

## Quick reference card

| Stage | Output artifact | Gate |
|---|---|---|
| 1 SPEC | `specs/SPEC_NNN_*.md` | User signs off |
| 2 DESIGN | Updated spec + `docs/screenshots/SPEC_NNN/design/` | Self-review checklist |
| 3 TDD | Vitest files; all failing | Test count matches spec |
| 4 BUILD | Green tests + clean tsc + clean build | Single command exits 0 |
| 5 RED-TEAM | `## Red-team` section in spec | Adversarial review complete |
| 6 FIX-ALL | Strike every blocker/major | Spec section all crossed out |
| 7 DEPLOY | Merged PR + UI_CHANGELOG + screenshots | PR merged to main |
