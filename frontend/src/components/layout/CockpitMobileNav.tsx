/**
 * CockpitMobileNav — bottom-bar nav for mobile (< md).
 *
 * Extracted from the previous inline CIPage mobile nav. The previous code
 * already used CSS variables correctly; this just packages it as a primitive
 * the CockpitShell can mount via its `mobileNav` slot.
 *
 * Design intent (SPEC_D1):
 *   - Active state uses the accent color (single decisive moment per view).
 *   - Inactive uses ink-3 (muted).
 *   - Surface tone-shift instead of a top border line.
 */
import type { ComponentType } from 'react';

export interface CockpitMobileNavProps<T extends string> {
  items: Array<{
    key: T;
    label: string;
    icon: ComponentType<{ size?: number }>;
  }>;
  active: T;
  onChange: (k: T) => void;
}

export function CockpitMobileNav<T extends string>({
  items,
  active,
  onChange,
}: CockpitMobileNavProps<T>) {
  return (
    <nav
      data-testid="cockpit-mobile-nav"
      className="flex items-center justify-around w-full"
      style={{
        background: 'var(--color-surface-2)',
        paddingBlock: 'var(--space-3)',
        paddingInline: 'var(--space-2)',
      }}
    >
      {items.map((t) => {
        const isActive = t.key === active;
        const Icon = t.icon;
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            className="flex flex-col items-center"
            style={{
              color: isActive ? 'var(--color-accent)' : 'var(--color-ink-3)',
              gap: 'var(--space-1)',
              fontSize: 'var(--text-xs)',
              fontWeight: 500,
            }}
          >
            <Icon size={20} />
            <span>{t.label}</span>
          </button>
        );
      })}
    </nav>
  );
}
