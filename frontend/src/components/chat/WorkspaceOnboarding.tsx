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

const FALLBACK_METRICS: KGMetric[] = [
  { label: 'Drugs', count: 1700, color: 'var(--color-drug)' },
  { label: 'Trials', count: 5300, color: 'var(--color-trial)' },
  { label: 'Companies', count: 1500, color: 'var(--color-company)' },
  { label: 'Mechanisms', count: 25, color: 'var(--color-mechanism)' },
];

export default function WorkspaceOnboarding({ onSendQuery }: WorkspaceOnboardingProps) {
  const [metrics, setMetrics] = useState<KGMetric[]>(FALLBACK_METRICS);

  useEffect(() => {
    let cancelled = false;
    api.catalogStats().then((stats: CatalogStats) => {
      if (cancelled) return;
      const ec = stats.entity_counts ?? {};
      const live: KGMetric[] = [
        { label: 'Drugs', count: ec.drug ?? ec.drugs ?? FALLBACK_METRICS[0].count, color: 'var(--color-drug)' },
        { label: 'Trials', count: ec.trial ?? ec.clinical_trials ?? ec.trials ?? FALLBACK_METRICS[1].count, color: 'var(--color-trial)' },
        { label: 'Companies', count: ec.company ?? ec.companies ?? FALLBACK_METRICS[2].count, color: 'var(--color-company)' },
        { label: 'Mechanisms', count: ec.mechanism ?? ec.mechanisms ?? FALLBACK_METRICS[3].count, color: 'var(--color-mechanism)' },
      ];
      setMetrics(live);
    }).catch(() => { /* keep fallback */ });
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
        {metrics.map((m) => (
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
        ))}
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
