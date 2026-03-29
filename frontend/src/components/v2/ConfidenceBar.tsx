import React from 'react';

interface ConfidenceBarProps {
  value: number;
  showLabel?: boolean;
}

function confidenceColor(value: number): string {
  if (value >= 0.7) return 'var(--confidence-high)';
  if (value >= 0.4) return 'var(--confidence-mid)';
  return 'var(--confidence-low)';
}

export default function ConfidenceBar({ value, showLabel = false }: ConfidenceBarProps) {
  const clamped = Math.max(0, Math.min(1, value));
  const pct = Math.round(clamped * 100);
  const color = confidenceColor(clamped);

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)' }}>
      <div
        style={{
          flex: 1,
          height: 4,
          borderRadius: 'var(--radius-full)',
          backgroundColor: 'var(--surface-secondary)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: '100%',
            borderRadius: 'var(--radius-full)',
            backgroundColor: color,
            transition: `width var(--duration-normal) var(--ease-out)`,
          }}
        />
      </div>
      {showLabel && (
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--text-xs)',
            color: 'var(--text-secondary)',
            minWidth: 32,
            textAlign: 'right',
          }}
        >
          {pct}%
        </span>
      )}
    </div>
  );
}
