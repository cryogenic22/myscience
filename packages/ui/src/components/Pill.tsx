import type { ReactNode } from 'react';

export type PillTone = 'neutral' | 'accent' | 'success' | 'warning' | 'danger' | 'info';
export type PillSize = 'sm' | 'md';

export interface PillProps {
  tone?: PillTone;
  size?: PillSize;
  /** Subtle uses a transparent tinted background instead of a filled one. */
  subtle?: boolean;
  /** Optional left adornment (icon, dot, glyph). */
  leading?: ReactNode;
  children: ReactNode;
  title?: string;
}

const TONE_VARS: Record<PillTone, { bg: string; fg: string }> = {
  neutral: { bg: 'var(--mz-color-elevated)',    fg: 'var(--mz-color-text-secondary)' },
  accent:  { bg: 'var(--mz-color-accent)',      fg: 'var(--mz-color-text-inverse)'   },
  success: { bg: 'var(--mz-color-success)',     fg: 'var(--mz-color-text-inverse)'   },
  warning: { bg: 'var(--mz-color-warning)',     fg: 'var(--mz-color-text-inverse)'   },
  danger:  { bg: 'var(--mz-color-danger)',      fg: 'var(--mz-color-text-inverse)'   },
  info:    { bg: 'var(--mz-color-info)',        fg: 'var(--mz-color-text-inverse)'   },
};

/**
 * Pill — small, single-purpose label. Used for tier badges, statuses,
 * counts. Always one short word/short phrase, never a sentence.
 */
export function Pill({
  tone = 'neutral',
  size = 'md',
  subtle = false,
  leading,
  children,
  title,
}: PillProps) {
  const tones = TONE_VARS[tone];
  const padY = size === 'sm' ? '2px' : '4px';
  const padX = size === 'sm' ? '6px' : '8px';
  const fontSize = size === 'sm' ? 'var(--mz-text-mono-3)' : 'var(--mz-text-mono-2)';

  const style: React.CSSProperties = subtle
    ? {
        background: `color-mix(in oklab, ${tones.bg} 16%, transparent)`,
        color: tones.bg === 'var(--mz-color-elevated)' ? tones.fg : tones.bg,
        border: `1px solid color-mix(in oklab, ${tones.bg} 28%, transparent)`,
      }
    : {
        background: tones.bg,
        color: tones.fg,
        border: '1px solid transparent',
      };

  return (
    <span
      title={title}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: `${padY} ${padX}`,
        borderRadius: 'var(--mz-radius-pill)',
        fontFamily: 'var(--mz-font-mono)',
        fontSize,
        fontWeight: 'var(--mz-weight-medium)' as never,
        letterSpacing: 'var(--mz-tracking-wide)',
        textTransform: 'uppercase',
        whiteSpace: 'nowrap',
        ...style,
      }}
    >
      {leading}
      {children}
    </span>
  );
}
