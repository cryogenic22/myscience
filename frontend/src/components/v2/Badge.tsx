
interface BadgeProps {
  label: string;
  variant?: 'default' | 'success' | 'warning' | 'error' | 'info';
  size?: 'sm' | 'md';
}

const VARIANT_STYLES: Record<string, { bg: string; text: string }> = {
  default: { bg: 'var(--surface-secondary)', text: 'var(--text-secondary)' },
  success: { bg: '#dcfce7', text: 'var(--confidence-high)' },
  warning: { bg: '#fef3c7', text: 'var(--confidence-mid)' },
  error:   { bg: '#fee2e2', text: 'var(--confidence-low)' },
  info:    { bg: 'var(--accent-soft)', text: 'var(--accent)' },
};

export default function Badge({ label, variant = 'default', size = 'sm' }: BadgeProps) {
  const style = VARIANT_STYLES[variant] ?? VARIANT_STYLES.default;
  const isMd = size === 'md';

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'var(--font-body)',
        fontSize: isMd ? 'var(--text-sm)' : 'var(--text-xs)',
        fontWeight: 500,
        lineHeight: 1,
        padding: isMd ? 'var(--space-1) var(--space-3)' : '2px var(--space-2)',
        borderRadius: 'var(--radius-full)',
        backgroundColor: style.bg,
        color: style.text,
        whiteSpace: 'nowrap',
      }}
    >
      {label}
    </span>
  );
}
