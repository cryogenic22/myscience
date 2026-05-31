/**
 * CockpitShell — root container for the CI cockpit surface.
 *
 * Two slots: `nav` (the left rail, hidden on mobile) and `children` (the main
 * content). Optional `mobileNav` for the bottom-bar pattern on small viewports.
 *
 * Design intent (SPEC_D1):
 *   - Does NOT hardcode data-theme. Whatever theme the user picked via F1's
 *     ThemeToggle propagates from <html> down to here unchanged.
 *   - Background uses `var(--color-bg)` — dark in dark theme, warm-white in ZS.
 *   - No `border-r` between nav and main. Separation is via the nav rail's
 *     own `--color-surface-2` tone shift, not a 1px line.
 */
import type { ReactNode } from 'react';

export interface CockpitShellProps {
  nav: ReactNode;
  children: ReactNode;
  mobileNav?: ReactNode;
}

export function CockpitShell({ nav, children, mobileNav }: CockpitShellProps) {
  return (
    <div
      data-testid="cockpit-shell"
      className="flex h-screen w-full overflow-hidden flex-col md:flex-row"
      style={{
        background: 'var(--color-bg)',
        color: 'var(--color-ink)',
      }}
    >
      {/* Left rail — hidden on mobile, visible md+ */}
      <div className="hidden md:flex shrink-0">
        {nav}
      </div>

      {/* Main content region */}
      <main
        className="flex-1 relative flex flex-col min-w-0 overflow-y-auto"
        style={{ background: 'var(--color-bg)' }}
      >
        {children}
      </main>

      {/* Mobile bottom nav (optional) */}
      {mobileNav && (
        <div className="md:hidden shrink-0">
          {mobileNav}
        </div>
      )}
    </div>
  );
}
