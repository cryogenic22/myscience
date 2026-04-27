import type { ReactNode } from 'react';
import { Card } from './Card';

export type ScoreTileTrend = 'up' | 'down' | 'flat';

export interface ScoreTileProps {
  /** Short uppercase label (e.g. "SIGNALS", "QUEUE", "BUDGET"). */
  label: string;
  /** Primary value — typically a number. */
  value: ReactNode;
  /** Optional descriptor below the value (e.g. "vs last week"). */
  caption?: string;
  /** Optional trend chip. */
  trend?: ScoreTileTrend;
  trendValue?: string;
  /** Click handler — clickable surfaces use Card's interactive variant. */
  onClick?: () => void;
}

const TREND_GLYPH: Record<ScoreTileTrend, string> = {
  up: '↑', down: '↓', flat: '→',
};

const TREND_COLOR: Record<ScoreTileTrend, string> = {
  up:   'var(--mz-color-success)',
  down: 'var(--mz-color-danger)',
  flat: 'var(--mz-color-text-tertiary)',
};

/**
 * ScoreTile — one big number, one short label. Apple Health / Oura
 * "score of the day" card. Used on Mission Control, Daily Digest header,
 * and as KPI tiles inside trackers.
 *
 * Composition rule: one ScoreTile = one metric. Don't crowd it.
 */
export function ScoreTile({
  label,
  value,
  caption,
  trend,
  trendValue,
  onClick,
}: ScoreTileProps) {
  return (
    <Card variant={onClick ? 'interactive' : 'flat'} onClick={onClick}>
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
          minWidth: 140,
        }}
      >
        <div
          style={{
            fontFamily: 'var(--mz-font-mono)',
            fontSize: 'var(--mz-text-mono-3)',
            color: 'var(--mz-color-text-tertiary)',
            letterSpacing: 'var(--mz-tracking-wide)',
            textTransform: 'uppercase',
          }}
        >
          {label}
        </div>

        <div
          style={{
            fontFamily: 'var(--mz-font-display)',
            fontSize: 'var(--mz-text-display-2)',
            fontWeight: 'var(--mz-weight-semibold)' as never,
            letterSpacing: 'var(--mz-tracking-tight)',
            color: 'var(--mz-color-text-primary)',
            lineHeight: 'var(--mz-leading-tight)',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {value}
        </div>

        {(caption || trend) && (
          <div
            style={{
              display: 'flex',
              alignItems: 'baseline',
              gap: 8,
              fontSize: 'var(--mz-text-body-3)',
              color: 'var(--mz-color-text-secondary)',
            }}
          >
            {trend && (
              <span style={{ color: TREND_COLOR[trend], fontVariantNumeric: 'tabular-nums' }}>
                <span aria-hidden style={{ marginRight: 2 }}>{TREND_GLYPH[trend]}</span>
                {trendValue}
              </span>
            )}
            {caption && <span>{caption}</span>}
          </div>
        )}
      </div>
    </Card>
  );
}
