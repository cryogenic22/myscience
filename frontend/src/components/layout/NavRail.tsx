/**
 * NavRail — left sidebar with header / body / footer slots.
 *
 * Design intent (SPEC_D1):
 *   - Separation from main content is via background tone-shift
 *     (`--color-surface-2`), NOT a vertical border line.
 *   - 16rem width (w-64) — matches the existing layout convention.
 *   - Vertical layout: header (fixed) → body (scrollable) → footer (fixed).
 *   - Spacing uses the token scale; no ad-hoc px in this primitive.
 */
import type { ReactNode } from 'react';

export interface NavRailProps {
  header?: ReactNode;
  footer?: ReactNode;
  children: ReactNode;
}

export function NavRail({ header, children, footer }: NavRailProps) {
  return (
    <aside
      data-testid="nav-rail"
      className="hidden md:flex w-64 flex-col shrink-0 h-full"
      style={{
        background: 'var(--color-surface-2)',
        color: 'var(--color-ink-2)',
      }}
    >
      {header && (
        <div
          className="flex items-center shrink-0"
          style={{
            paddingInline: 'var(--space-5)',
            height: 64,
          }}
        >
          {header}
        </div>
      )}

      <nav
        className="flex-1 overflow-y-auto flex flex-col"
        style={{
          paddingInline: 'var(--space-4)',
          paddingBlock: 'var(--space-5)',
          gap: 2,
        }}
      >
        {children}
      </nav>

      {footer && (
        <div
          className="shrink-0 flex flex-col"
          style={{
            padding: 'var(--space-4)',
            gap: 'var(--space-4)',
          }}
        >
          {footer}
        </div>
      )}
    </aside>
  );
}
