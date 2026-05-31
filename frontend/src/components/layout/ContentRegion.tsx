/**
 * ContentRegion — the main scrollable area inside a CockpitShell.
 *
 * Design intent (SPEC_D1):
 *   - Generous padding (--space-7 = 48px) so content has air around it.
 *     The "constrained" feeling on the old CIPage came from py-6/px-10
 *     which is comfortable on a single column but cramped against a hard
 *     border. Here, no border + bigger padding = breathing room.
 *   - Max-width cap so on wide monitors we don't stretch to infinity.
 *     Default 'xl' (7xl in Tailwind = 80rem); page can override.
 */
import type { ReactNode } from 'react';

export interface ContentRegionProps {
  children: ReactNode;
  maxWidth?: 'lg' | 'xl' | '2xl' | 'none';
}

const MAX_WIDTH_CLASS: Record<NonNullable<ContentRegionProps['maxWidth']>, string> = {
  lg: 'max-w-5xl',
  xl: 'max-w-6xl',
  '2xl': 'max-w-7xl',
  none: '',
};

export function ContentRegion({
  children,
  maxWidth = 'xl',
}: ContentRegionProps) {
  return (
    <div
      className="w-full flex-1 flex flex-col"
      style={{
        paddingBlock: 'var(--space-7)',
        paddingInline: 'var(--space-6)',
      }}
    >
      <div
        data-testid="content-region"
        className={`w-full mx-auto flex-1 flex flex-col ${MAX_WIDTH_CLASS[maxWidth]}`}
        style={{ gap: 'var(--space-6)' }}
      >
        {children}
      </div>
    </div>
  );
}
