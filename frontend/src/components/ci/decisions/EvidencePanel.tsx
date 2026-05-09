import type { DecisionBrief, EvidenceRef, EvidenceRefType } from '../../../api';

/**
 * SPEC_030 §8.2 / §8.3 — left panel grouping evidence_refs by type.
 * Empty CTA when in editable state and 0 refs. Click invokes onOpen.
 */

const TYPE_LABELS: Record<EvidenceRefType, { label: string; eyebrow: string }> = {
  kbq_view: { label: 'KBQ', eyebrow: 'KBQ Views' },
  signal:   { label: 'Signal', eyebrow: 'Signals' },
  entity:   { label: 'Entity', eyebrow: 'Entities' },
  document: { label: 'Document', eyebrow: 'Documents' },
};

const ORDER: EvidenceRefType[] = ['kbq_view', 'signal', 'entity', 'document'];

interface Props {
  brief: DecisionBrief;
  onOpen?: (ref: EvidenceRef) => void;
}

export default function EvidencePanel({ brief, onOpen }: Props) {
  const refs = brief.evidence_refs ?? [];
  const grouped = ORDER.map((t) => ({
    type: t,
    items: refs.filter((r) => r.type === t),
  })).filter((g) => g.items.length > 0);

  return (
    <section
      data-testid="panel-evidence"
      tabIndex={-1}
      style={{
        background: 'var(--color-surface)',
        borderRadius: 'var(--radius-panel, 16px)',
        padding: 'var(--space-panel-pad, 24px)',
        boxShadow: 'var(--shadow-workspace-panel, var(--shadow-sm))',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-panel-gap, 16px)',
        minHeight: 200,
      }}
    >
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <h2
          style={{
            margin: 0,
            fontFamily: 'var(--font-display)',
            fontSize: 18,
            fontWeight: 700,
            color: 'var(--color-ink)',
          }}
        >
          Evidence
        </h2>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--color-ink-3)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {refs.length}
        </span>
      </header>

      {refs.length === 0 && (
        <div
          style={{
            fontSize: 13,
            color: 'var(--color-ink-3)',
            padding: '24px 0',
            textAlign: 'center',
          }}
        >
          No evidence linked yet.
          {brief.state === 'draft' || brief.state === 'human_review' ? (
            <div style={{ marginTop: 8, fontSize: 12 }}>
              Link a signal, KBQ view, entity, or document.
            </div>
          ) : null}
        </div>
      )}

      {grouped.map(({ type, items }) => {
        const meta = TYPE_LABELS[type];
        return (
          <div key={type} style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'baseline',
                fontSize: 11,
                fontWeight: 600,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                color: 'var(--color-ink-3)',
              }}
            >
              <span>{meta.eyebrow}</span>
              <span style={{ fontFamily: 'var(--font-mono)' }}>{items.length}</span>
            </div>
            {items.map((ref) => (
              <button
                key={ref.id}
                type="button"
                onClick={() => onOpen?.(ref)}
                style={{
                  background: 'var(--color-surface-2)',
                  border: 'none',
                  borderRadius: 'var(--radius-card, 12px)',
                  padding: '8px 12px',
                  textAlign: 'left',
                  cursor: onOpen ? 'pointer' : 'default',
                  fontFamily: 'var(--font-mono)',
                  fontSize: 12,
                  color: 'var(--color-ink-2)',
                  transition: 'background 140ms linear',
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLElement).style.background = 'var(--color-surface-3)';
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLElement).style.background = 'var(--color-surface-2)';
                }}
              >
                {ref.id}
              </button>
            ))}
          </div>
        );
      })}
    </section>
  );
}
