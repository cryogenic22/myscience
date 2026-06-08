
interface EntityDotProps {
  type: string;
  size?: 'sm' | 'md' | 'lg';
}

const SIZES: Record<string, number> = { sm: 8, md: 12, lg: 16 };

const ENTITY_COLORS: Record<string, string> = {
  drug: 'var(--entity-drug)',
  company: 'var(--entity-company)',
  trial: 'var(--entity-trial)',
  target: 'var(--entity-target)',
  mechanism: 'var(--entity-mechanism)',
  literature: 'var(--entity-literature)',
  therapeutic_area: 'var(--entity-ta)',
  ta: 'var(--entity-ta)',
  event: 'var(--entity-safety)',
  safety: 'var(--entity-safety)',
  investigator: 'var(--text-secondary)',
  patent: 'var(--text-tertiary)',
};

export default function EntityDot({ type, size = 'md' }: EntityDotProps) {
  const px = SIZES[size] ?? SIZES.md;
  const color = ENTITY_COLORS[type] ?? 'var(--text-tertiary)';

  return (
    <span
      aria-label={`${type} entity`}
      style={{
        display: 'inline-block',
        width: px,
        height: px,
        borderRadius: 'var(--radius-full)',
        backgroundColor: color,
        flexShrink: 0,
      }}
    />
  );
}
