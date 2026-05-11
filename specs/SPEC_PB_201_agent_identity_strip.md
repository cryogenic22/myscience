# PB-201 — Agent identity strip (Loop #8)

**Status:** Shipped 2026-05-11
**Type:** feature
**Priority:** high
**Owner:** frontend-claude (this loop) · backend-claude (BE-3, PR #50)
**Source:** `docs/PRODUCT_BACKLOG.md` PB-201
**Source ref:** `design-review-output/enhancement-backlog.md` E2.S2.1
**Closes:** Phase 5 finding "AgentStatusBar shows static '3 agents'" (frontend half).

## Why

The platform claims agentic intelligence but every surface today
shows the same opaque `AgentStatusBar` label ("Flywheel Active · 4
Agents Active"). The user has no way to know who's doing what. PB-201
gives the three named agents a consistent, visible identity:

- **Sentinel** (SE · teal · *Sense*) — the watchdog
- **Strategist** (ST · violet · *Frame · Simulate*) — the planner
- **Curator** (CU · green · *Learn · Recalibrate*) — the librarian

Phase 8 verification mandates the noun form. The aria-labels and
visible labels both use nouns ("Sentinel" not "Sensing", "Frame"
not "Framing").

## Scope of this loop

PB-201 only — the two primitives + one mount.

**Out of scope** (own PB items):
- PB-202 — live activity feed via SSE (`GET /agents/stream`, BE-4)
- PB-203 — addressable nudges per agent
- PB-204 — failed / paused state visibility

## What ships

1. **`AgentGlyph`** (`frontend/src/components/primitives/AgentGlyph.tsx`):
   - 28×28 tinted badge with 2-letter mark (SE / ST / CU).
   - Tints: teal / violet / green, semi-transparent fill, saturated
     text + border so the glyph reads on both light and dark
     surfaces.
   - Optional `showLabel` shows the agent name beside the badge.
   - Optional `status: 'idle' | 'active' | 'failed' | 'paused'` adds
     a corner dot for PB-202 wiring later.
   - Exports `AGENTS` metadata map for other surfaces to consume the
     canonical names + roles + tints.
2. **`AgentIdentityStrip`**
   (`frontend/src/components/primitives/AgentIdentityStrip.tsx`):
   - Fixed-order row: Sentinel → Strategist → Curator.
   - Each entry: glyph + name + role line (Sense / Frame · Simulate
     / Learn · Recalibrate).
   - `role="group"` + `aria-label="Active agents"` so AT announces
     the trio as one unit.
   - Optional `statuses` prop is a `Partial<Record<AgentId,
     AgentStatus>>` — PB-202 plugs SSE data in here.
3. **Mount in `CIPage` sidebar** — strip renders directly above the
   pre-existing `AgentStatusBar` so the three named agents are
   visible in the cockpit without removing the legacy bar.

## Tests

`frontend/__tests__/primitives/AgentGlyph.test.tsx` — 7 cases:
- SE / ST / CU glyphs render with correct letters + aria-labels.
- aria-labels use noun forms (Phase 8 guard).
- `showLabel` on/off toggles the visible name.
- `status` prop emits a corner dot with `data-status="<status>"`.

`frontend/__tests__/primitives/AgentIdentityStrip.test.tsx` — 4 cases:
- Fixed agent order: sentinel · strategist · curator.
- Agent names visible.
- Role lines visible.
- `role="group"` with descriptive `aria-label`.

## Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **328 passing, 22 todo, 0
  failures** (48 files; +11 over Loop #7)

## Follow-up

When PB-202 lands and SSE wires real per-agent state, the legacy
`AgentStatusBar` "X Agents Active" label can be retired in favour
of `AgentIdentityStrip` with live statuses. Filed for a future loop.

## Why this loop pivoted from PB-401

PB-401 (TipTap brief composer) requires installing `@tiptap/react` +
`@tiptap/starter-kit` + custom-mark extensions — ~10 transitive
packages + a careful TDD pass on the mark system. That warrants its
own focused loop, not a continuation of the rhythm we set in Loops
5–7 (each a same-shape "primitive + hook + scaffold + 9 tests"
delivery). PB-201 fits that shape; PB-401 will land in a dedicated
TipTap-install loop.
