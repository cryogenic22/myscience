import { useState } from 'react';

interface EntityMentionProps {
  name: string;
  type: string;
  onClick?: () => void;
}

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
};

export default function EntityMention({ name, type, onClick }: EntityMentionProps) {
  const [hovered, setHovered] = useState(false);
  const color = ENTITY_COLORS[type] ?? 'var(--text-secondary)';

  return (
    <span
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        cursor: onClick ? 'pointer' : 'default',
        borderBottom: `2px solid ${color}`,
        paddingBottom: 1,
        backgroundColor: hovered ? 'var(--accent-soft)' : 'transparent',
        borderRadius: 'var(--radius-sm)',
        transition: `background-color var(--duration-fast) var(--ease-out)`,
        color: 'var(--text-primary)',
        fontFamily: 'var(--font-body)',
        fontSize: 'var(--text-base)',
      }}
    >
      {name}
    </span>
  );
}
