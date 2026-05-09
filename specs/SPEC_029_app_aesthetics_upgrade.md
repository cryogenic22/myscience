# SPEC_029: App-wide Aesthetics Upgrade — "Cockpit-Grade Everywhere"

Status: Active (✓ signed off by user 2026-05-09)
Owner: Frontend Lead (Claude operating in Antigravity's seat — see AGENTS.md §11)
Light-first, dark-follows. Full app reskin — no surface left at "demo-grade".
Successor / superset of SPEC_022 (which scoped only `/ci`).

---

## 1. Goal

Bring every surface in the app — Landing, Workspace, Search, Catalog,
Connectors, CI Cockpit, and all cross-cutting flows — to the visual and
interaction bar set in `specs/test.tsx` and aligned with Oura, Apple Health,
Apple.com, Linear, Spotify. SPEC_022 framed the bar for `/ci` only; the user
has now asked to extend that bar across the app.

The deliverable is **a coherent design system, a documented audit per
surface, and per-surface mini-specs** (SPEC_030 onward), each shipped through
the ralph-style loop in §10.

## 2. Why now

- Phase F primitives have shipped (`HeroCard`, `MetricRing`, `Sparkline`,
  `Timeline`, `AgentStatusBar`, `ConfidenceBadge`, `EvidenceAffordance`,
  `DisagreementPanel`, `ProvenanceTrail`, `ThemeToggle`) but only the `/ci`
  shell uses them. The rest of the app still leans on legacy slate-tailwind
  and bespoke patterns.
- Backend has shipped four new contracts (SPEC_023 Decision Briefs, SPEC_026
  LLM Gateway, SPEC_027 Source Registry, SPEC_028 War-Game Adversaries) that
  have *no frontend consumer*. The aesthetic upgrade is the natural moment
  to wire each one in.
- The user has said the front door (Landing) and every workflow page must
  feel like the same product. Today they don't.

## 3. Non-goals

- **Not** rebuilding underlying flows. Every existing route stays where it
  is; we re-render it. Functionality regressions are blockers; new features
  ride along when they fall out for free.
- **Not** moving to a new framework, CSS engine, or component library.
  Tailwind v4 + CSS custom properties + framer-motion remain.
- **Not** waiting for backend. Anything backend-blocked is filed in
  `docs/AGENT_BACKLOG.md` under `[BACKEND]` and scheduled after the contract
  lands. Until then, surfaces use realistic fixtures with a clearly-marked
  "fixture mode" pill, never silent fakes.

## 4. Design system — the canon

### 4.1 Two themes, one product

The app remains **light-first** (the Apple-warm cream) and **dark-mirror**
(the GitHub-inspired #0d1117 cockpit). Each surface ships parity with both;
the toggle lives in the topbar.

**Light theme — refinement targets** (current values are a strong base):
- Promote `--shadow-sm/md/lg` to *barely-there Apple shadows* — already done.
- Ban hard 1px borders for surface separation; use background tone shifts.
- Tighten typographic rhythm (line-height 1.5–1.75 on prose, 1.15 on display).
- Glass blur only at the topbar / overlay layer (already done — preserve).

**Dark theme — refinement targets**:
- Tighten contrast on `--color-ink-3` so 12px metadata is still legible
  against `--color-surface` (`#161b22`) — currently 4.0, target 4.5.
- Add a `--shadow-glow` variant for accent emphases (the cockpit "alive"
  feel without blinking dots everywhere).
- Reserve `--color-accent` (`#58a6ff`) for affordances; `--color-amber`,
  `--color-green`, `--color-red` for state.

### 4.2 Typography contract (extends SPEC_022 §Typography)

| Use | Family | Tracking |
|---|---|---|
| Display headers (≥28px) | **Syne** 700/800 | -0.02em |
| Body, UI labels | **DM Sans** 400/500/600 | -0.01em |
| Numbers, IDs, telemetry | **DM Mono** 400/500 | 0 |
| Small caps metadata (≤12px uppercase) | DM Sans 600 | 0.06–0.08em |

`Fraunces` stays available as a fallback for the marketing landing where
Syne's weight feels too brutal; both tokens point at `--font-display`.

### 4.3 Motion contract

- Layout transitions: `framer-motion` `layout` + 220ms cubic-bezier(0.16,1,0.3,1).
- Hover lift: `translateY(-2px)` + `--shadow-md` bloom, 160ms.
- Skeletons: `0.4 → 1.0` opacity pulse, 1.6s loop.
- Page entry: stagger child fade-up at 30ms intervals; cap at 6 children.
- Reduced-motion: respect `prefers-reduced-motion: reduce`. All decorative
  motion goes to `transform: none` + `opacity: 1`.

### 4.4 Component primitives — present + missing

Present (do not duplicate — see `.claude/rules/anti-slop.md`):
`HeroCard`, `MetricRing`, `Sparkline`, `Timeline`, `AgentStatusBar`,
`ConfidenceBadge`, `EvidenceAffordance`, `DisagreementPanel`,
`ProvenanceTrail`, `ThemeToggle`.

To build under this spec:
| Primitive | Purpose | First consumer |
|---|---|---|
| `RadarChart` | 5-dim radar for SPEC_027 source quality + entity dossier strengths | Source Health |
| `FlowDiagram` | SVG node-link diagram for war-game transcripts and decision provenance | War-Game UI |
| `FactorBar` | Stacked horizontal bar attributing a 0-100 score to its drivers (materiality, calibration) | Sensing Feed |
| `CostTicker` | Compact live-cost + PII-hits chip for the cockpit footer | Global footer |
| `KeyboardHint` | Tooltip-style chip showing keyboard shortcut for an action | Sensing Feed list |
| `RangeReadout` | Range-with-confidence display (e.g. "8–12% over 18mo") | Decision Workspace |
| `StateChip` | State-machine state badge with allowed-transition popover | Decision Workspace |

### 4.5 Layout primitives

- `WorkspaceShell` — sidebar + content split, used by `/ci`, `/connectors`,
  and (new under this spec) the app-wide power-user shell.
- `Section` — typographic block with optional `eyebrow`, `title`, `actions`.
- `SplitPane` — resizable two-pane (currently in `WorkspaceLayout.tsx`); we
  generalise it into a primitive instead of a one-off.

### 4.6 Tokens to add to `index.css`

```
--shadow-glow:        0 0 0 1px var(--color-accent-soft), 0 8px 32px rgba(28,110,247,0.18);
--motion-out:         cubic-bezier(0.16, 1, 0.3, 1);
--motion-in:          cubic-bezier(0.32, 0, 0.67, 0);
--radius-card:        16px;
--radius-pill:        999px;
--radius-input:       12px;
--space-1: 4px; --space-2: 8px; --space-3: 12px; --space-4: 16px;
--space-5: 24px; --space-6: 32px; --space-7: 48px; --space-8: 64px;
```

## 5. Surface audit — what's at "demo-grade" today

Each surface gets a one-line audit and a target-state. Per-surface mini-specs
live in their own SPEC_NNN file (see §9).

| # | Route / Surface | Current state | Target | Mini-spec |
|---|---|---|---|---|
| L | `/` Landing | Hero + pillar grid; partial Phase F | Apple-marketing-grade hero, live KPIs, single dark/light flip, sub-3s LCP | SPEC_036 |
| W | `/workspace` Chat + Canvas | Two-pane, slate-heavy, mixed Tailwind | Coherent Section primitives, citation-first canvas, keyboard-driven | SPEC_037 |
| S | `/search` Search | Functional, dense; mixed colors | Linear-style command palette feel, faceted filters, evidence preview | SPEC_038 |
| Cat | Catalog (within Workspace right pane) | Catalog rows + featured cards | Quality dashboard headline + faceted browse + bulk-curate footer | SPEC_039 |
| Co | `/connectors` Connectors | Tabbed list + detail; mostly Phase F | Source quality strip from `/sources` (SPEC_027) + per-connector telemetry | SPEC_034 |
| CI-1 | `/ci` Sensing Feed (Inbox) | Phase F primitives wired | Factor-attributed materiality, keyboard nav (j/k/e/x), supersedence | SPEC_035 |
| CI-2 | `/ci?tab=signals` Signals DB | Renders `/signals` flat | Tier-aware filtering, evidence stack, share-out tracking | SPEC_035 |
| CI-3 | `/ci?tab=watchlist` Watchlist | Functional CRUD | Per-entity timeline, peer-context, alert preview | SPEC_035 |
| CI-4 | `/ci?tab=rooms` War Rooms (legacy) | SPEC_021 single-suggester | Rebadged "Move Studio"; new War-Game multi-adversary lives at `/ci/games/:id` | SPEC_032 |
| CI-5 | `/ci?tab=decisions` Decisions list | List of legacy decisions | Decision Brief list + status pipeline + outcome chips | SPEC_030 |
| CI-6 | `/ci/decisions/:id` Decision Detail | Legacy single-page | 5-panel Decision Workspace consuming `/decision-briefs` (SPEC_023) | SPEC_030 |
| CI-7 | New: `/ci/games/:run_id` War-Game Transcript | n/a | 4-lane adversary transcript consuming `/war-games` (SPEC_028) | SPEC_032 |
| CI-8 | New: `/ci?tab=sources` Source Health | n/a | 5-dim radar + freshness + license telemetry, SPEC_027 | SPEC_033 |
| CI-9 | Global footer | Empty | Live LLM cost / PII filter chip from SPEC_026 cost-summary | SPEC_033 |
| Au | `/login`, `/register` Auth | Functional, plain | Cockpit-grade login card with theme parity | SPEC_040 |

## 6. Backend dependencies (filed in `docs/AGENT_BACKLOG.md`)

Per AGENTS.md §3 the surfaces below cannot ship without the listed backend
support. Each will be filed in the backlog as a `[BACKEND]` entry with the
exact endpoint shape needed, when this spec is signed off.

| Surface | Backend ask | Status |
|---|---|---|
| Decision Workspace (CI-5/6) | `/decision-briefs` SPEC_023 — already shipped | ✅ unblocked |
| War-Game Transcript (CI-7) | `/war-games` SPEC_028 — already shipped | ✅ unblocked |
| Source Health (CI-8) | `/sources/health-summary`, `/sources/{id}/history` SPEC_027 — already shipped | ✅ unblocked |
| Cost Telemetry (CI-9) | `/llm-gateway/cost-summary` SPEC_026 — already shipped | ✅ unblocked |
| Sensing Feed factor bars | `materiality_factors` field on `/signals` items | ⛔ blocked — file `[BACKEND]` |
| Decision Brief from Signal | `POST /decision-briefs` accepts `trigger_signal_ids[]` (already in 023) but Sensing Feed needs a one-click action; verify endpoint surfaces `confidence_to_proceed` writeback | ✅ already specced |
| War-Game start | `POST /war-games` already exists; need a "preview adversaries" helper to suggest groundable evidence_ids per adversary kind without requiring the user to know UUIDs | ⛔ blocked — file `[BACKEND]` (low priority, can ship without) |
| Outcome history sparkline on Decisions | needs `GET /decisions/calibration?since=` time series | ⛔ blocked — file `[BACKEND]` |

## 7. Data contracts touched

This spec **does not** change any backend table or endpoint. It does
add/update typed clients in `frontend/src/api.ts`:
- `decisionBriefsApi`
- `warGamesApi`
- `sourcesApi`
- `llmGatewayApi`

Each generated by hand from `schema/openapi.json` (the contract source of
truth per AGENTS.md §3). Types live in `frontend/src/api.ts` next to their
peers; no separate types module unless duplication mounts.

## 8. Definition of Done — at the spec level

- [ ] `index.css` extended with §4.6 tokens; existing tokens unchanged.
- [ ] All 7 missing primitives in §4.4 implemented + Vitest-tested.
- [ ] Every surface in §5 has a mini-spec (SPEC_030–SPEC_038).
- [ ] Each mini-spec lands per the loop in §10 (TDD-first, red-team review,
      Lighthouse a11y ≥95, light + dark parity).
- [ ] `docs/UI_CHANGELOG.md` entry per landed PR.
- [ ] No regressions: `cd frontend && npm run build && npx tsc --noEmit && npx vitest run` clean at every PR boundary.
- [ ] Every surface uses CSS custom properties; zero new `bg-slate-*`,
      `text-slate-*`, or hardcoded color literals (legacy classes are
      compatibility-mapped in `index.css`, not freshly authored).

## 9. Per-surface mini-spec index

> SPEC_031 is reserved by the **backend Claude team** for Materiality Scoring
> (`materiality_factors` JSONB on signals) — see `specs/SPEC_031_materiality_scoring.md`.
> Frontend mini-specs skip 031 to avoid collision.

| Spec | Title | Land order | Surface |
|---|---|---|---|
| SPEC_030 | Decision Workspace v2 (consumes `/decision-briefs`) | First — most leverage, fully unblocked | CI-5/6 |
| SPEC_032 | War-Game Multi-Adversary UI (consumes `/war-games`) | Second — pairs with SPEC_030 | CI-4/7 |
| SPEC_033 | Source Health admin + LLM Cost Telemetry footer | Third | CI-8, CI-9 |
| SPEC_034 | Connectors page reskin (consumes `/sources`) | Fourth | Co |
| SPEC_035 | Sensing Feed v2 + Signals + Watchlist | Fifth — depends on backend SPEC_031 (`materiality_factors`) | CI-1/2/3 |
| SPEC_036 | Cockpit-grade Landing | Sixth — front door | L |
| SPEC_037 | Workspace (chat + canvas) reskin | Seventh | W |
| SPEC_038 | Search reskin | Eighth | S |
| SPEC_039 | Catalog reskin | Ninth | Cat |
| SPEC_040 | Auth surfaces | Tenth | Au |

A mini-spec ships only when the previous one is merged + zero regressions.

## 10. The ralph-style loop — how every mini-spec runs

Each SPEC_030–SPEC_038 ships via this 7-stage loop. The loop is documented
in `docs/runbooks/RALPH_LOOP.md` and referenced from each mini-spec's
"Acceptance" section.

```
SPEC ──▶ DESIGN ──▶ TDD ──▶ BUILD ──▶ RED-TEAM ──▶ FIX-ALL ──▶ DEPLOY
  ▲                                                                │
  └────────────── (post-deploy notes feed back to next loop) ◀─────┘
```

Stage definitions, inputs, outputs (full text in `docs/runbooks/RALPH_LOOP.md`):

1. **SPEC** — write `specs/SPEC_NNN_*.md`. Goal, contract, surfaces, DoD,
   open questions. Sign-off from user before code (per AGENTS.md §5).
2. **DESIGN** — wireframes / token call-outs / state diagrams in the spec
   itself, plus a screenshot of any reference UI being mimicked. Output:
   updated spec + `docs/screenshots/SPEC_NNN/design/`.
3. **TDD** — write Vitest specs for every new component, every state
   permutation (loading / empty / error / success / disagreement / busy),
   keyboard-nav assertions, light + dark snapshot tests. All tests must
   FAIL before any production code.
4. **BUILD** — implement against the failing tests, smallest unit first.
   No commits until tests pass.
5. **RED-TEAM** — review the diff against `.claude/rules/anti-slop.md`,
   AGENTS.md §7 "Definition of Done", SPEC_022 design rules. Failure modes:
   what breaks if the API returns 0 rows? 500? a 12k-row payload? what
   happens with `prefers-reduced-motion`? what happens at 320px width? The
   review is appended to the spec as `## Red-team`. Issues found go to §11.
6. **FIX-ALL** — every red-team issue closed. No "punt to v2" without an
   `[FRONTEND]` line in `docs/AGENT_BACKLOG.md`.
7. **DEPLOY** — final `npm run build && tsc --noEmit && vitest run`,
   screenshot pass into `docs/screenshots/SPEC_NNN/`, append
   `docs/UI_CHANGELOG.md`, commit on `claude-fe/spec-NNN-*` branch, PR with
   "Other-side impact: none" or link to backlog.

## 11. Risks + open issues

| # | Risk | Mitigation |
|---|---|---|
| R1 | Reskinning legacy `WorkspacePage` regresses chat behavior | Vitest covers chat handler call sites before any visual change; smoke test in dev |
| R2 | Legacy `bg-slate-*` overrides in `index.css` collide with new component styles | We're not removing the override layer in this spec — only forbidding *new* slate classes. Removal is its own follow-up |
| R3 | New cockpit-grade Landing tanks LCP | Image-free hero, system fonts as fallback until Syne/DM-Sans loads, Lighthouse perf budget ≥85 |
| R4 | Backend ships breaking change mid-loop | Per AGENTS.md §3, 14-day deprecation window. We pin api.ts types to a snapshot; new fields are additive |
| R5 | Two parallel war systems (legacy `/war-rooms` + new `/war-games`) confuse users | SPEC_031 explicitly migrates the tab label from "War Rooms" to "Move Studio" (legacy) and adds "War Games" (new) — see SPEC_031 §UX |
| R6 | Light-first emphasis under-invests in the dark cockpit | Each mini-spec's DoD includes light AND dark screenshots. CI fails if either is missing |
| R7 | Out-of-scope creep from "full app reskin" | Mini-specs are atomic. Each surface listed in §5 either gets its own spec or is explicitly out of scope. New asks beyond §5 require a new spec, not an in-flight extension |

## 12. Acceptance for THIS spec

- [ ] User signs off on §4 (design system canon) and §10 (loop process).
- [ ] `docs/runbooks/RALPH_LOOP.md` exists with the 7-stage definition.
- [ ] Backend dependencies in §6 marked `⛔` are filed in
      `docs/AGENT_BACKLOG.md` under `[BACKEND]`.
- [ ] SPEC_030 (Decision Workspace) is drafted as the first concrete loop.

Once accepted, this spec becomes the umbrella under which all subsequent
SPEC_030–SPEC_038 land.

## 13. Out of scope (deferred)

- Removing the legacy `bg-slate-*` override block in `index.css` —
  separate follow-up after every surface stops relying on it.
- Mobile-app shell (the responsive layout we ship is desktop-first with
  graceful degradation; native or mobile-PWA is out of scope).
- Visual rebrand (logos, brand colors as currently defined stay; we are
  refining tone, not renaming).
- Internationalisation. The current copy is English-only and stays so.
