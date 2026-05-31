/**
 * NavRailItem — a single nav button inside the NavRail.
 *
 * Design intent (SPEC_D1):
 *   - Active state = surface-3 background. No ring, no border. The elevation
 *     IS the indicator.
 *   - Inactive uses ink-3 (muted); active uses ink (full). Icon picks up
 *     `--color-accent` when active for the one decisive accent moment.
 *   - Generous padding and softer corners (radius-input).
 */
import type { ComponentType } from 'react';

export interface NavRailItemProps {
  label: string;
  icon: ComponentType<{ size?: number; style?: React.CSSProperties }>;
  active?: boolean;
  onClick: () => void;
}

export function NavRailItem({
  label,
  icon: Icon,
  active = false,
  onClick,
}: NavRailItemProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center text-left w-full transition-all"
      style={{
        background: active ? 'var(--color-surface-3)' : 'transparent',
        color: active ? 'var(--color-ink)' : 'var(--color-ink-3)',
        fontWeight: active ? 500 : 400,
        fontSize: 'var(--text-base)',
        gap: 'var(--space-3)',
        paddingInline: 'var(--space-3)',
        paddingBlock: 10,
        borderRadius: 'var(--radius-input)',
        transitionDuration: '180ms',
        transitionTimingFunction: 'var(--motion-out)',
      }}
    >
      <Icon
        size={16}
        style={{ color: active ? 'var(--color-accent)' : 'inherit' }}
      />
      {label}
    </button>
  );
}
