# @mz/design-tokens

Single source of truth for Market Zero color, type, spacing, radius, motion, and shadow.

## Three surfaces, one source

- `src/tokens.json` — canonical token definitions. Edit here.
- `src/tokens.css` — CSS custom properties. Imported by apps; consumed via `var(--mz-*)`.
- `src/index.ts` — runtime TS access for code paths that need a value (animations, inline SVG fills, theme switching).

For now, `tokens.css` is hand-maintained. A `scripts/build.mjs` will auto-generate it from `tokens.json` in M1.

## Usage in an app

```ts
// In your app entry (e.g. apps/landing/src/main.tsx):
import '@mz/design-tokens/tokens.css';
```

Then style with CSS variables:

```css
.button {
  background: var(--mz-color-accent);
  color: var(--mz-color-text-inverse);
  padding: var(--mz-space-3) var(--mz-space-4);
  border-radius: var(--mz-radius-control);
  font-family: var(--mz-font-sans);
  font-size: var(--mz-text-body-2);
  transition: background var(--mz-duration-fast) var(--mz-ease-standard);
}
```

## Theme switching

Set on `<html>` or any container:

```html
<html data-theme="light" data-module="ci" data-density="compact">
```

- `data-theme`: `light` | `dark`
- `data-module`: `ci` | `research` | `regulatory` (drives `--mz-color-accent`)
- `data-density`: `compact` | `comfortable` | `spacious`

## Rules

- **Never use raw color values in components.** Always go through CSS variables or the TS helpers.
- **Never use Tailwind color utilities** (`bg-slate-*`, `text-gray-*`). Tailwind is for layout/spacing only; color is tokens.
- **One accent per module.** Don't introduce a second accent without an ADR.
