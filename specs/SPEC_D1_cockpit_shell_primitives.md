# SPEC D1 — Cockpit shell primitives + CIPage migration

*Loop D, Increment 1. The first surface to be migrated is `/ci` — the
product's home — because user feedback was that it "feels constrained
and not free-flowing."*

## Problem

`frontend/src/index.css` already defines the right tokens: 9-stop spacing
scale (4/8/12/16/24/32/48/64), 9-stop type scale, 3-tier surface elevation
(`--color-surface`, `--color-surface-2`, `--color-surface-3`), shadows
calibrated for soft depth, and an **explicit comment from a prior loop**:
> "stop drawing 1px boxes around panels; use background-elevation tiers
> + shadows for separation."

The tokens are good. **The pages don't use them.** CIPage in particular:

- Hardcodes `data-theme="dark"` on its root, **overriding** F1's theme toggle. The toggle is structurally inert on `/ci`.
- Bakes in hex codes everywhere: `#0a0b0e`, `#12141a`, `#23262d`, `#e8eaed`, `#5a5f69`, `#8a8f99`, `#1f232b`. Eight distinct greys that drift away from the token system.
- Uses `border-r`, `border-b`, `border-t` everywhere — hard borders create visible boxes (the "constrained" feeling).
- References fonts not loaded in `index.html`: `Instrument Serif`, `JetBrains Mono`. The actual loaded fonts are Fraunces + DM Sans + DM Mono.
- Mixes the legitimate `mz-text-*` utility classes with `text-[Npx]` arbitrary values.

The result is a UI that doesn't react to themes, doesn't follow the spacing rhythm the tokens encode, and visually fights itself. The "constrained" feeling is the byproduct.

## Decision

Build a small set of **headless shell primitives** that internalize the right patterns, then **refactor CIPage to use them**. Other surfaces migrate in later loops.

**Headless** = primitives render structure + spacing + surfaces, never page-specific content. They take children as slots. The page composes them.

The five primitives:

1. **`CockpitShell`** — root container. Honors current `data-theme` from context (does NOT hardcode it). Two slots: `nav` (left rail, hidden on mobile) and `main` (content region).
2. **`NavRail`** — left sidebar. Three slots: `header`, `body`, `footer`. Separation via `--color-surface-2` tone shift from the main region, NOT a border.
3. **`NavRailItem`** — single nav button with active/inactive states. Active = `--color-surface-3` background, no border ring.
4. **`ContentRegion`** — main scrollable area. Generous `--space-7` padding, max-width container, vertical rhythm enforced.
5. **`CockpitMobileNav`** — bottom nav on mobile. (Already correct in the current CIPage — just extracted as a primitive.)

The legacy `TopBar.tsx` and `WorkspaceLayout.tsx` are NOT touched — they belong to other surfaces and can migrate in their own loops.

## Acceptance test

A single runnable test in `__tests__/layout/cockpit-shell.test.tsx`:

```tsx
test('acceptance — cockpit shell honors theme + uses tokens, not hex', () => {
  // 1. CockpitShell does NOT hardcode data-theme.
  render(<CockpitShell nav={<NavRail>n</NavRail>}>main</CockpitShell>);
  const shell = screen.getByTestId('cockpit-shell');
  expect(shell).not.toHaveAttribute('data-theme');

  // 2. Inline styles use CSS variables, not hex literals.
  const inlineStyle = shell.getAttribute('style') || '';
  expect(inlineStyle).not.toMatch(/#[0-9a-fA-F]{3,8}/);

  // 3. NavRail uses tone-shift surface, never `border-r`.
  const rail = screen.getByTestId('nav-rail');
  expect(rail.className).not.toMatch(/border-r\b/);

  // 4. NavRailItem active state uses surface elevation, not ring.
  render(<NavRailItem label="x" icon={()=>null} active onClick={()=>{}} />);
  const item = screen.getByRole('button', { name: /x/i });
  expect(item.getAttribute('style') || '').not.toMatch(/#[0-9a-fA-F]{3,8}/);
});
```

A second test pins the CIPage migration:

```tsx
test('CIPage uses no hardcoded hex codes and respects theme toggle', () => {
  // Grep the rendered DOM string. No hex literals in style attributes.
  render(<CIPage />, { wrapper: TestWrapper });
  const html = document.body.innerHTML;
  // Allow hex inside src/href (e.g. SVG paths) but not in style="...".
  const styles = html.match(/style="[^"]*"/g) || [];
  for (const s of styles) {
    expect(s).not.toMatch(/#[0-9a-fA-F]{3,8}/);
  }

  // CIPage root has no `data-theme` attribute (was hardcoded "dark").
  const ciRoot = screen.getByTestId('cockpit-shell');
  expect(ciRoot).not.toHaveAttribute('data-theme');
});
```

## Module surface

```tsx
// frontend/src/components/layout/CockpitShell.tsx
export interface CockpitShellProps {
  nav: ReactNode;
  children: ReactNode;        // main content
  mobileNav?: ReactNode;
}
export function CockpitShell(p: CockpitShellProps): JSX.Element;

// frontend/src/components/layout/NavRail.tsx
export interface NavRailProps {
  header?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;        // the nav list
}
export function NavRail(p: NavRailProps): JSX.Element;

// frontend/src/components/layout/NavRailItem.tsx
export interface NavRailItemProps {
  label: string;
  icon: ComponentType<{ size?: number }>;
  active?: boolean;
  onClick: () => void;
}
export function NavRailItem(p: NavRailItemProps): JSX.Element;

// frontend/src/components/layout/ContentRegion.tsx
export interface ContentRegionProps {
  children: ReactNode;
  maxWidth?: 'lg' | 'xl' | '2xl' | 'none';   // default 'xl'
}
export function ContentRegion(p: ContentRegionProps): JSX.Element;

// frontend/src/components/layout/CockpitMobileNav.tsx
export interface CockpitMobileNavProps<T extends string> {
  items: Array<{ key: T; label: string; icon: ComponentType<{ size?: number }> }>;
  active: T;
  onChange: (k: T) => void;
}
export function CockpitMobileNav<T extends string>(p: CockpitMobileNavProps<T>): JSX.Element;
```

## Visual contract — what changes on `/ci`

**Before** (current):
- Hardcoded dark `#0a0b0e` regardless of user's theme
- Visible vertical line between left rail and content (`border-r #23262d`)
- Visible horizontal line under the branding header (`border-b #23262d`)
- Visible horizontal line above the agent activity footer (`border-t #23262d`)
- 8 distinct hardcoded greys
- Theme toggle has no visible effect

**After** (with this loop):
- Background reads from `var(--color-bg)` — dark in dark theme, warm-white in ZS
- Left rail uses `var(--color-surface-2)` — separated from main by tone, not a 1px line
- Branding/agent sections separated by spacing + tone, not borders
- All greys collapse into the 4-stop ink scale (`--color-ink`, `--color-ink-2`, `--color-ink-3`, `--color-ink-4`)
- F1 theme toggle finally works on `/ci` — click sparkles and the cockpit shifts to ZS

## Out of scope (Loop D-2 onwards)

- Migrating WorkspacePage, BridgePage, DossierPage to the new primitives (own loops)
- Restyling individual tab components (DigestTab, SignalsTab, etc.) — they live inside ContentRegion unchanged for this loop
- Adding new spacing/color tokens (the existing set covers this)
- Three-density mode (compact / comfortable / spacious) — already partially supported via `[data-density]`; not wired here

## Red-team checklist

1. **No-hex regression lint** — the acceptance test greps style attributes for hex codes. Will fail if any future PR adds a hardcoded hex back to CIPage.
2. **Theme override removal** — the `data-theme="dark"` hardcode on CIPage root is removed; F1 toggle now reaches the page. Tested.
3. **Border ban** — `border-r`, `border-b`, `border-t` removed from the migrated CIPage. Tested by regex.
4. **No behaviour change** — every tab still renders; tab switching still works; URL sync still works; mobile nav still works. Existing CIPage tests (if any) still pass.
5. **Font references corrected** — `'Instrument Serif'` and `'JetBrains Mono'` removed, replaced with `var(--font-display)` and `var(--font-mono)` which resolve to actually-loaded fonts (Fraunces / DM Mono).
6. **Anti-slop** — primitives go in `frontend/src/components/layout/` next to the existing `TopBar.tsx`, `WorkspaceLayout.tsx`, `EngagementShell.tsx`. No duplication; no parallel `cockpit/` directory.
7. **Headless contract** — primitives take children as slots. No primitive imports a tab component. No primitive references a page-specific concept.

## File plan

| File | Why |
|---|---|
| `specs/SPEC_D1_cockpit_shell_primitives.md` | This SPEC |
| `frontend/src/components/layout/CockpitShell.tsx` | NEW — root container |
| `frontend/src/components/layout/NavRail.tsx` | NEW — left rail with slots |
| `frontend/src/components/layout/NavRailItem.tsx` | NEW — sidebar nav item |
| `frontend/src/components/layout/ContentRegion.tsx` | NEW — main scrollable region |
| `frontend/src/components/layout/CockpitMobileNav.tsx` | NEW — extracted from CIPage |
| `frontend/__tests__/layout/cockpit-shell.test.tsx` | Primitive tests + acceptance test |
| `frontend/src/pages/CIPage.tsx` | Refactored to use the primitives |
| `frontend/__tests__/pages/CIPage.test.tsx` | Migration test (no hex / no override) |
