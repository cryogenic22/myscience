import { useEffect, useState } from 'react';
import { api, type CatalogStats } from '../../api';

interface WorkspaceOnboardingProps {
  onSendQuery: (query: string) => void;
}

interface KGMetric {
  label: string;
  count: number;
  color: string;
}

const SUGGESTION_CARDS = [
  {
    icon: '\u{1F30D}',
    title: 'GLP-1 competitive landscape',
    subtitle: 'Market dynamics across the GLP-1 class',
    query: 'GLP-1 competitive landscape',
  },
  {
    icon: '\u{1F50D}',
    title: 'Semaglutide deep dive',
    subtitle: 'Complete entity dossier with evidence',
    query: 'Tell me about semaglutide',
  },
  {
    icon: '\u2696\uFE0F',
    title: 'Compare semaglutide vs tirzepatide',
    subtitle: 'Head-to-head pipeline and trial analysis',
    query: 'Compare semaglutide vs tirzepatide',
  },
  {
    icon: '\u{1F9EA}',
    title: 'SGLT2 drugs in heart failure',
    subtitle: 'Therapeutic area landscape analysis',
    query: 'SGLT2 drugs in heart failure',
  },
  {
    icon: '\u{1F3E2}',
    title: 'Novo Nordisk portfolio',
    subtitle: 'Full drug portfolio and pipeline',
    query: 'Novo Nordisk portfolio',
  },
  {
    icon: '\u{1F4CA}',
    title: 'Phase 3 trial pipeline',
    subtitle: 'Active late-stage clinical trials',
    query: 'Phase 3 trial pipeline',
  },
] as const;

export default function WorkspaceOnboarding({ onSendQuery }: WorkspaceOnboardingProps) {
  // Counts are fetched live. We do NOT seed authoritative-looking fabricated
  // numbers — `null` renders a loading skeleton, and a fetch failure renders an
  // honest "unavailable" rather than invented counts on the user's first screen.
  const [metrics, setMetrics] = useState<KGMetric[] | null>(null);
  const [statsError, setStatsError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.catalogStats().then((stats: CatalogStats) => {
      if (cancelled) return;
      const ec = stats.entity_counts ?? {};
      setMetrics([
        { label: 'Drugs', count: ec.drug ?? ec.drugs ?? 0, color: 'var(--color-drug)' },
        { label: 'Trials', count: ec.trial ?? ec.clinical_trials ?? ec.trials ?? 0, color: 'var(--color-trial)' },
        { label: 'Companies', count: ec.company ?? ec.companies ?? 0, color: 'var(--color-company)' },
        { label: 'Mechanisms', count: ec.mechanism ?? ec.mechanisms ?? 0, color: 'var(--color-mechanism)' },
      ]);
    }).catch(() => { if (!cancelled) setStatsError(true); });
    return () => { cancelled = true; };
  }, []);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        height: '100%',
        padding: '48px 32px',
        background: 'var(--color-surface-2)',
        overflow: 'auto',
      }}
    >
      {/* Title */}
      <h2
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: '24px',
          fontWeight: 400,
          color: 'var(--color-ink)',
          marginBottom: '8px',
          letterSpacing: '-0.02em',
        }}
      >
        Knowledge Graph
      </h2>
      <p
        style={{
          fontSize: '13px',
          color: 'var(--color-ink-3)',
          marginBottom: '32px',
          maxWidth: '400px',
          textAlign: 'center',
          lineHeight: 1.5,
        }}
      >
        Explore pharma intelligence across drugs, trials, companies, and mechanisms.
      </p>

      {/* Metric strip */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: '12px',
          marginBottom: '40px',
          width: '100%',
          maxWidth: '480px',
        }}
      >
        {statsError ? (
          <div
            role="status"
            style={{
              gridColumn: '1 / -1',
              textAlign: 'center',
              fontSize: '12px',
              color: 'var(--color-ink-4)',
              padding: '16px',
            }}
          >
            Knowledge-graph counts unavailable
          </div>
        ) : metrics === null ? (
          [0, 1, 2, 3].map((i) => (
            <div
              key={i}
              aria-hidden
              data-testid="kg-metric-skeleton"
              style={{
                background: 'var(--color-surface)',
                borderRadius: '12px',
                padding: '16px 12px',
                boxShadow: 'var(--shadow-xs)',
              }}
            >
              <div style={{ height: '24px', borderRadius: '6px', background: 'var(--color-line)', opacity: 0.5 }} />
              <div style={{ height: '11px', width: '60%', margin: '8px auto 0', borderRadius: '4px', background: 'var(--color-line)', opacity: 0.4 }} />
            </div>
          ))
        ) : (
          metrics.map((m) => (
            <div
              key={m.label}
              style={{
                background: 'var(--color-surface)',
                borderRadius: '12px',
                padding: '16px 12px',
                textAlign: 'center',
                boxShadow: 'var(--shadow-xs)',
              }}
            >
              <div
                style={{
                  fontFamily: 'var(--font-display)',
                  fontSize: '24px',
                  fontWeight: 400,
                  color: 'var(--color-ink)',
                  lineHeight: 1.2,
                  letterSpacing: '-0.02em',
                }}
              >
                {m.count >= 1000
                  ? `${(m.count / 1000).toFixed(m.count % 1000 === 0 ? 0 : 1)}K`
                  : m.count.toLocaleString()}
              </div>
              <div
                style={{
                  fontSize: '11px',
                  fontWeight: 600,
                  letterSpacing: '0.04em',
                  textTransform: 'uppercase' as const,
                  color: m.color,
                  marginTop: '4px',
                }}
              >
                {m.label}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Suggestion cards */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
          gap: '10px',
          width: '100%',
          maxWidth: '720px',
        }}
      >
        {SUGGESTION_CARDS.map((card) => (
          <button
            key={card.query}
            type="button"
            onClick={() => onSendQuery(card.query)}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '12px',
              padding: '14px 16px',
              background: 'var(--color-surface)',
              border: '1px solid var(--color-line)',
              borderRadius: '12px',
              cursor: 'pointer',
              textAlign: 'left',
              transition: 'all 180ms ease',
              boxShadow: 'var(--shadow-xs)',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = 'translateY(-2px)';
              e.currentTarget.style.boxShadow = 'var(--shadow-sm)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = 'translateY(0)';
              e.currentTarget.style.boxShadow = 'var(--shadow-xs)';
            }}
          >
            <span
              style={{
                fontSize: '18px',
                lineHeight: 1,
                flexShrink: 0,
                marginTop: '2px',
              }}
            >
              {card.icon}
            </span>
            <div style={{ minWidth: 0 }}>
              <div
                style={{
                  fontSize: '13px',
                  fontWeight: 600,
                  color: 'var(--color-ink)',
                  lineHeight: 1.3,
                  marginBottom: '2px',
                }}
              >
                {card.title}
              </div>
              <div
                style={{
                  fontSize: '11px',
                  color: 'var(--color-ink-4)',
                  lineHeight: 1.4,
                }}
              >
                {card.subtitle}
              </div>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
