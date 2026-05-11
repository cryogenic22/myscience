# Loop #10 — UI integration pass

**Status:** Shipped 2026-05-11
**Type:** refactor
**Source:** user feedback ("can we fix this and overall the UI should be more seamless and integrated")

## Why

Loops 5–9 shipped four new frontend surfaces. The user's qualitative feedback
was that they read as five strangers, not one app. This loop spends a
single Ralph Loop on integration polish so the surfaces feel cohesive.

## Four targeted fixes

1. **Retire the legacy `AgentStatusBar` mount from the CI cockpit
   sidebar.** The named-agent strip from Loop #8 is the canonical
   identity surface now; the static "Flywheel Active · 4 Agents
   Active" label was redundant. `AgentStatusBar` itself stays in the
   codebase — it's still used by `LandingPage` (hero status) and
   `SensingFeed` (loading state), which are different contexts.
2. **Wrap `DossierPage` in the shared app chrome** that
   `ConnectorsPage` already uses: 52px header bar with back button
   (→ `/ci`), `PRODUCT_NAME`, vertical separator, "Dossier"
   breadcrumb label, and a right-aligned `ThemeToggle`. The inner
   entity-name header is demoted from `<header>` to `<div>` so AT
   announce one banner per page rather than two.
3. **Group the war-room "Strategy" panel.** Payoff matrix + autonomous
   move suggestions + move selector were three siblings stacked in
   `WarRoomView`; now they sit inside one bordered `<section
   aria-label="Strategy">` with a small uppercase heading and a
   "Strategist · payoff matrix · move" caption. `PayoffMatrix` drops
   its own outer card border so it integrates as a sub-section rather
   than a nested card.
4. **Thread the Strategist identity onto the recommended cell.** The
   payoff matrix's "Recommended" caption becomes "Strategist
   recommends" with `data-agent="strategist"` and the violet tint
   that matches `AGENTS.strategist.rgb`. The cell border now uses the
   same violet, so the eye reads recommended → Strategist rather
   than recommended → generic accent. Broader agent-tint-everywhere
   (Sentinel on signal cards, Curator on evidence rows) is deferred
   to its own loop.

## Test plumbing

- New test file `__tests__/loop10/ui-integration.test.tsx` with 5
  cases (back button, breadcrumb, banner landmark, Strategist
  caption, Strategist data attribute).
- Existing `PayoffMatrix.test.tsx` "recommended" regex relaxed from
  `/recommended/i` to `/recommend/i` so "Strategist recommends"
  matches.
- Existing `DossierPage.test.tsx` wrapped in `ThemeProvider` (the
  new `ThemeToggle` in chrome requires it).
- `src/test/setup.ts` gained a `window.matchMedia` shim so any test
  mounting `ThemeProvider` works in jsdom. (Drive-by fix — also
  closed the intermittent flake in `DecisionWorkspace.test.tsx`
  cmd+enter test.)

## Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **345 passing, 22 todo, 0
  failures** (51 files; +6 over Loop #9).
- `python -m scripts.validate_product_backlog` → OK

## What's NOT in this loop

- Sentinel tint on signal cards
- Curator tint on evidence rows
- Cockpit-style chrome on `/search`, `/workspace`, `/newui` (those
  pages have their own headers; matching them is a bigger
  consolidation pass)
- Replacing `AgentStatusBar` in `LandingPage` + `SensingFeed` —
  those are non-cockpit surfaces with different status semantics
  (marketing pitch, feed loading); they're filed as separate
  follow-ups
