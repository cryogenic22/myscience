import {
  type Fact,
  FACT_CLASS_GLYPH,
  FACT_CLASS_COLOR,
  FACT_CLASS_LABEL,
} from '../../pages/EngagementDossierPage';

/**
 * PB-UX03 — provenance side panel.
 *
 * The trust contract made visible: click any fact and see WHERE it came from.
 * A slide-in panel showing the claim, its confidence tier (fact class), the
 * source, and a drill-through to the source record (the shipped `sourceUrl`).
 *
 * Shared component — usable from any stage (dossier, synthesis, scenarios).
 * Renders nothing when `fact` is null.
 */

interface Props {
  fact: Fact | null;
  onClose: () => void;
}

export default function ProvenancePanel({ fact, onClose }: Props) {
  if (!fact) return null;
  const color = FACT_CLASS_COLOR[fact.factClass];

  return (
    <>
      {/* Backdrop — click to dismiss. */}
      <div
        aria-hidden
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.32)',
          zIndex: 60,
        }}
      />
      <aside
        role="dialog"
        aria-label="Fact provenance"
        data-testid="provenance-panel"
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          height: '100vh',
          width: 'min(440px, 92vw)',
          background: 'var(--color-bg)',
          borderLeft: '1px solid var(--color-line)',
          boxShadow: 'var(--shadow-lg, -8px 0 32px rgba(0,0,0,0.28))',
          zIndex: 61,
          display: 'flex',
          flexDirection: 'column',
          overflowY: 'auto',
        }}
      >
        {/* Header */}
        <header
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '18px 20px',
            borderBottom: '1px solid var(--color-divider)',
            position: 'sticky',
            top: 0,
            background: 'var(--color-bg)',
          }}
        >
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10.5,
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
              color: 'var(--color-ink-3)',
            }}
          >
            Provenance
          </span>
          <button
            type="button"
            onClick={onClose}
            data-testid="provenance-close"
            aria-label="Close provenance"
            style={{
              marginLeft: 'auto',
              border: 'none',
              background: 'transparent',
              cursor: 'pointer',
              color: 'var(--color-ink-3)',
              fontSize: 18,
              lineHeight: 1,
              padding: 4,
            }}
          >
            ×
          </button>
        </header>

        <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', gap: 18 }}>
          {/* Fact-class tier */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontFamily: 'var(--font-mono)', fontSize: 20, color, fontWeight: 600 }}>
              {FACT_CLASS_GLYPH[fact.factClass]}
            </span>
            <span style={{ fontSize: 12.5, color: 'var(--color-ink-2)' }}>
              {FACT_CLASS_LABEL[fact.factClass]}
            </span>
          </div>

          {/* The claim */}
          <div>
            <ChainLabel>Claim</ChainLabel>
            <p
              style={{
                margin: 0,
                fontSize: 15,
                lineHeight: 1.5,
                color: 'var(--color-ink)',
                fontFamily: 'var(--font-body)',
              }}
            >
              {fact.claim}
            </p>
          </div>

          {/* Evidence chain */}
          <div>
            <ChainLabel>Source</ChainLabel>
            <div
              style={{
                padding: '12px 14px',
                background: 'var(--color-surface)',
                border: '1px solid var(--color-line)',
                borderLeft: `3px solid ${color}`,
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}
            >
              <div style={{ fontFamily: 'var(--font-mono)', fontSize: 12, color: 'var(--color-ink-2)' }}>
                {fact.sourceLabel || '—'}
              </div>
              {fact.sourceUrl ? (
                <a
                  href={fact.sourceUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  data-testid="provenance-source-link"
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 11.5,
                    color: 'var(--color-accent)',
                    wordBreak: 'break-all',
                    textDecoration: 'none',
                  }}
                >
                  View source ↗
                </a>
              ) : (
                <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--color-ink-4)', fontStyle: 'italic' }}>
                  No external source link (derived / internal fact)
                </span>
              )}
            </div>
          </div>

          {/* Identity */}
          <div>
            <ChainLabel>Fact ID</ChainLabel>
            <code
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 11,
                color: 'var(--color-ink-3)',
                wordBreak: 'break-all',
              }}
            >
              {fact.id}
            </code>
          </div>

          <p style={{ margin: '4px 0 0', fontSize: 11.5, color: 'var(--color-ink-4)', lineHeight: 1.5 }}>
            Every claim traces to its source — the anti-hallucination contract. The
            glyph is the confidence tier; the link opens the record it was extracted from.
          </p>
        </div>
      </aside>
    </>
  );
}

function ChainLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 9.5,
        letterSpacing: '0.16em',
        textTransform: 'uppercase',
        color: 'var(--color-ink-4)',
        marginBottom: 6,
      }}
    >
      {children}
    </div>
  );
}
