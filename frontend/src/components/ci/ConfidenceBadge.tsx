import type { ConfidenceTier } from '../../api';

const STYLES: Record<ConfidenceTier, { bg: string; fg: string; label: string }> = {
  confirmed: { bg: '#DCFCE7', fg: '#15803D', label: 'Confirmed' },
  reported:  { bg: '#FEF3C7', fg: '#A16207', label: 'Reported' },
  inferred:  { bg: '#E0E7FF', fg: '#3730A3', label: 'Inferred' },
  disputed:  { bg: '#FEE2E2', fg: '#B91C1C', label: 'Disputed' },
};

export default function ConfidenceBadge({ tier }: { tier: ConfidenceTier }) {
  const s = STYLES[tier] ?? STYLES.inferred;
  return (
    <span
      className="text-[10px] font-medium uppercase"
      style={{
        background: s.bg,
        color: s.fg,
        padding: '2px 7px',
        borderRadius: '4px',
        letterSpacing: '0.06em',
      }}
    >
      {s.label}
    </span>
  );
}
