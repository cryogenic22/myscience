import type { ImpactTier } from '../../api';

const STYLES: Record<ImpactTier, { dot: string; label: string }> = {
  high:   { dot: '#DC2626', label: 'High' },
  medium: { dot: '#D97706', label: 'Medium' },
  low:    { dot: '#52525B', label: 'Low' },
};

export default function ImpactBadge({ tier }: { tier: ImpactTier }) {
  const s = STYLES[tier] ?? STYLES.low;
  return (
    <span
      className="inline-flex items-center gap-1 text-[11px]"
      style={{ color: 'var(--color-ink-3)' }}
    >
      <span
        className="h-1.5 w-1.5 rounded-full"
        style={{ background: s.dot }}
      />
      {s.label} impact
    </span>
  );
}
