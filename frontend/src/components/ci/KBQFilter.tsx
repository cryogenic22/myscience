interface Props {
  selected: string | null;
  onSelect: (kbq: string | null) => void;
}

const KBQS: Array<{ key: string; label: string }> = [
  { key: 'financial', label: 'Financial' },
  { key: 'governance', label: 'Governance' },
  { key: 'strategic', label: 'Strategic' },
  { key: 'clinical', label: 'Clinical' },
  { key: 'product', label: 'Product' },
  { key: 'regulatory', label: 'Regulatory' },
  { key: 'm_and_a', label: 'M&A' },
  { key: 'pricing_access', label: 'Pricing & Access' },
  { key: 'ai_digital', label: 'AI & Digital' },
  { key: 'esg_supply', label: 'ESG & Supply' },
];

export default function KBQFilter({ selected, onSelect }: Props) {
  return (
    <div className="flex flex-wrap gap-1.5">
      <Chip label="All" active={selected === null} onClick={() => onSelect(null)} />
      {KBQS.map((k) => (
        <Chip
          key={k.key}
          label={k.label}
          active={selected === k.key}
          onClick={() => onSelect(selected === k.key ? null : k.key)}
        />
      ))}
    </div>
  );
}

function Chip({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="text-[11px] font-medium"
      style={{
        padding: '4px 10px',
        borderRadius: '14px',
        border: `1px solid ${active ? 'var(--color-accent)' : 'var(--color-line)'}`,
        background: active ? 'var(--color-accent)' : 'transparent',
        color: active ? 'white' : 'var(--color-ink-3)',
        cursor: 'pointer',
      }}
    >
      {label}
    </button>
  );
}
