/**
 * ContentRegion — the main scrollable area inside a CockpitShell.
 *
 * Design intent:
 *   - Generous padding so content has air around it (tone + space separation,
 *     no hard borders).
 *   - A max-width cap so content doesn't stretch to infinity on ultra-wide
 *     monitors, but a GENEROUS one — the old 1152px cap felt cramped, leaving
 *     huge side gutters and a boxed-in look. Defaults are wider now.
 *
 * Layout is INLINE styles + design tokens, NOT Tailwind utilities: v4
 * auto-generates utilities by scanning from the Git root, and Railway/Nixpacks
 * builds without `.git`, so utility classes can silently no-op in production
 * (CLAUDE.md). Since every cockpit tab renders inside ContentRegion, a missing
 * `mx-auto`/`max-w-*` would make every tab look left-aligned/constrained. Plain
 * inline styles are deterministic in every environment.
 */
import type { ReactNode } from 'react';

export interface ContentRegionProps {
  children: ReactNode;
  maxWidth?: 'lg' | 'xl' | '2xl' | 'none';
}

// Generous, deliberate caps (px). 'xl' (default) widened from 1152 → 1440 so
// tabs use the screen instead of sitting in a narrow column.
const MAX_WIDTH: Record<NonNullable<ContentRegionProps['maxWidth']>, string> = {
  lg: '1120px',    // text-dense tabs that read better narrow
  xl: '1440px',    // default
  '2xl': '1760px', // data-dense tabs (tables, graphs)
  none: '100%',
};

export function ContentRegion({
  children,
  maxWidth = 'xl',
}: ContentRegionProps) {
  return (
    <div
      style={{
        width: '100%',
        flex: '1 1 auto',
        minHeight: 0,
        display: 'flex',
        flexDirection: 'column',
        paddingBlock: 'var(--space-7)',
        paddingInline: 'var(--space-6)',
      }}
    >
      <div
        data-testid="content-region"
        style={{
          width: '100%',
          maxWidth: MAX_WIDTH[maxWidth],
          marginInline: 'auto',
          flex: '1 1 auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-6)',
        }}
      >
        {children}
      </div>
    </div>
  );
}
