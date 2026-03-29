/**
 * FAIRSparkline — Tiny inline display showing FAIR quality score with trend.
 * Renders as "FAIR: 0.76 ^" with color coding.
 */

interface FAIRSparklineProps {
  score: number; // 0-1
  trend?: 'up' | 'down' | 'stable';
}

const TREND_SYMBOLS: Record<string, string> = {
  up: '\u25B2',
  down: '\u25BC',
  stable: '\u2013',
};

export default function FAIRSparkline({ score, trend = 'stable' }: FAIRSparklineProps) {
  const trendColor =
    trend === 'up'
      ? 'var(--confidence-high)'
      : trend === 'down'
        ? 'var(--confidence-low)'
        : 'var(--text-tertiary)';

  const scoreColor =
    score >= 0.7
      ? 'var(--confidence-high)'
      : score >= 0.4
        ? 'var(--confidence-mid)'
        : 'var(--confidence-low)';

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 'var(--space-1)',
        fontSize: 'var(--text-xs)',
        fontFamily: 'var(--font-mono)',
        whiteSpace: 'nowrap',
      }}
    >
      <span style={{ color: 'var(--text-tertiary)' }}>FAIR:</span>
      <span style={{ color: scoreColor, fontWeight: 600 }}>
        {score.toFixed(2)}
      </span>
      <span style={{ color: trendColor, fontSize: 10 }}>
        {TREND_SYMBOLS[trend]}
      </span>
    </span>
  );
}
