/**
 * CurateView — Center zone content when lens === 'curate'.
 *
 * Shows pipeline status grid, knowledge graph stats,
 * and drug completeness bars on a dark graph background.
 */

import FAIRSparkline from './FAIRSparkline';

/* ── Types ────────────────────────────────────────────── */

interface PipelineConnector {
  source_key: string;
  label: string;
  schedule: string;
  last_run: string | null;
  days_since: number | null;
  records: number;
  status: string;
}

interface GraphSummary {
  link_types: Array<{ type: string; count: number }>;
  total_links: number;
  total_entities: number;
  drug_completeness: Record<string, number>;
}

interface CurateViewProps {
  pipelineStatus: PipelineConnector[] | null;
  graphSummary: GraphSummary | null;
  onRefreshSource: (source: string) => void;
}

/* ── Helpers ──────────────────────────────────────────── */

function statusVariant(status: string): {
  label: string;
  bg: string;
  fg: string;
} {
  switch (status.toLowerCase()) {
    case 'fresh':
    case 'live':
      return { label: 'Live', bg: 'rgba(22,163,74,0.15)', fg: 'var(--confidence-high)' };
    case 'ok':
      return { label: 'OK', bg: 'rgba(22,163,74,0.10)', fg: 'var(--confidence-high)' };
    case 'stale':
      return { label: 'Stale', bg: 'rgba(217,119,6,0.15)', fg: 'var(--confidence-mid)' };
    case 'error':
    case 'failed':
      return { label: 'Error', bg: 'rgba(239,68,68,0.15)', fg: 'var(--confidence-low)' };
    case 'never':
      return { label: 'Never Run', bg: 'rgba(239,68,68,0.08)', fg: 'var(--confidence-low)' };
    default:
      return { label: status || 'Unknown', bg: 'rgba(255,255,255,0.06)', fg: 'var(--text-tertiary)' };
  }
}

function formatLastRun(lastRun: string | null, daysSince: number | null): string {
  if (!lastRun) return 'Never';
  if (daysSince !== null && daysSince < 1) return 'Today';
  if (daysSince !== null && daysSince < 2) return 'Yesterday';
  if (daysSince !== null && daysSince < 7) return `${Math.round(daysSince)}d ago`;
  if (daysSince !== null && daysSince < 30) return `${Math.round(daysSince)}d ago`;
  return new Date(lastRun).toLocaleDateString();
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

/* ── Connector Card ──────────────────────────────────── */

function ConnectorCard({
  connector,
  onRefresh,
}: {
  connector: PipelineConnector;
  onRefresh: () => void;
}) {
  const sv = statusVariant(connector.status);

  return (
    <div
      style={{
        background: 'rgba(255,255,255,0.05)',
        borderRadius: 'var(--radius-md)',
        padding: 'var(--space-3) var(--space-4)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
        border: '1px solid rgba(255,255,255,0.06)',
        animation: 'fade-in var(--duration-normal) var(--ease-out)',
      }}
    >
      {/* Top row: label + status */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 'var(--space-2)',
        }}
      >
        <span
          style={{
            fontSize: 'var(--text-sm)',
            fontWeight: 500,
            color: 'var(--text-inverse)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
            flex: 1,
          }}
        >
          {connector.label}
        </span>
        <span
          style={{
            fontSize: 'var(--text-xs)',
            fontWeight: 600,
            padding: '2px var(--space-2)',
            borderRadius: 'var(--radius-full)',
            background: sv.bg,
            color: sv.fg,
            whiteSpace: 'nowrap',
            flexShrink: 0,
          }}
        >
          {sv.label}
        </span>
      </div>

      {/* Schedule */}
      <div
        style={{
          fontSize: 'var(--text-xs)',
          color: 'rgba(255,255,255,0.4)',
        }}
      >
        {connector.schedule}
      </div>

      {/* Records + last run row */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          fontSize: 'var(--text-xs)',
          color: 'rgba(255,255,255,0.6)',
        }}
      >
        <span>{formatNumber(connector.records)} records</span>
        <span>{formatLastRun(connector.last_run, connector.days_since)}</span>
      </div>

      {/* Refresh button */}
      <button
        type="button"
        onClick={onRefresh}
        style={{
          fontSize: 'var(--text-xs)',
          fontFamily: 'var(--font-body)',
          fontWeight: 500,
          color: 'var(--accent)',
          background: 'rgba(37,99,235,0.1)',
          border: '1px solid rgba(37,99,235,0.2)',
          borderRadius: 'var(--radius-sm)',
          padding: 'var(--space-1) var(--space-3)',
          cursor: 'pointer',
          transition: `all var(--duration-fast) ease`,
          alignSelf: 'flex-start',
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLElement).style.background = 'rgba(37,99,235,0.2)';
        }}
        onMouseLeave={(e) => {
          (e.currentTarget as HTMLElement).style.background = 'rgba(37,99,235,0.1)';
        }}
      >
        Refresh
      </button>
    </div>
  );
}

/* ── Completeness Bar ────────────────────────────────── */

function CompletenessBar({ label, value }: { label: string; value: number }) {
  const pct = Math.min(Math.max(value, 0), 100);
  const color =
    pct >= 70
      ? 'var(--confidence-high)'
      : pct >= 40
        ? 'var(--confidence-mid)'
        : 'var(--confidence-low)';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          fontSize: 'var(--text-xs)',
        }}
      >
        <span style={{ color: 'rgba(255,255,255,0.6)', textTransform: 'capitalize' }}>
          {label.replace(/_/g, ' ')}
        </span>
        <span style={{ color: 'rgba(255,255,255,0.8)', fontFamily: 'var(--font-mono)' }}>
          {pct.toFixed(0)}%
        </span>
      </div>
      <div
        style={{
          height: 6,
          borderRadius: 'var(--radius-full)',
          background: 'rgba(255,255,255,0.08)',
          overflow: 'hidden',
        }}
      >
        <div
          style={{
            height: '100%',
            width: `${pct}%`,
            borderRadius: 'var(--radius-full)',
            background: color,
            transition: `width var(--duration-slow) var(--ease-out)`,
          }}
        />
      </div>
    </div>
  );
}

/* ── Main Component ──────────────────────────────────── */

export default function CurateView({
  pipelineStatus,
  graphSummary,
  onRefreshSource,
}: CurateViewProps) {
  // Compute average completeness as a rough FAIR proxy
  const avgCompleteness = graphSummary?.drug_completeness
    ? Object.values(graphSummary.drug_completeness).reduce((a, b) => a + b, 0) /
      Math.max(Object.values(graphSummary.drug_completeness).length, 1) / 100
    : 0;

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        overflowY: 'auto',
        padding: 'var(--space-8)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-8)',
        animation: 'fade-in var(--duration-normal) var(--ease-out)',
      }}
    >
      {/* ── Header ────────────────────────────────────────── */}
      <div>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 'var(--space-4)',
            marginBottom: 'var(--space-2)',
          }}
        >
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'var(--text-2xl)',
              fontWeight: 400,
              color: 'var(--text-inverse)',
              margin: 0,
              letterSpacing: '-0.01em',
            }}
          >
            Data Supply Chain
          </h1>
          {graphSummary && (
            <FAIRSparkline
              score={avgCompleteness}
              trend={avgCompleteness > 0.5 ? 'up' : 'stable'}
            />
          )}
        </div>
        <p
          style={{
            fontSize: 'var(--text-sm)',
            color: 'rgba(255,255,255,0.4)',
            margin: 0,
            lineHeight: 1.5,
          }}
        >
          Monitor connectors, review graph health, and trigger enrichment.
        </p>
      </div>

      {/* ── Pipeline Status Grid ─────────────────────────── */}
      <section>
        <h2
          style={{
            fontSize: 'var(--text-xs)',
            fontWeight: 600,
            letterSpacing: '0.04em',
            textTransform: 'uppercase' as const,
            color: 'rgba(255,255,255,0.4)',
            margin: '0 0 var(--space-3) 0',
          }}
        >
          Connectors
        </h2>
        {pipelineStatus ? (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
              gap: 'var(--space-3)',
            }}
          >
            {pipelineStatus.map((c) => (
              <ConnectorCard
                key={c.source_key}
                connector={c}
                onRefresh={() => onRefreshSource(c.source_key)}
              />
            ))}
          </div>
        ) : (
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))',
              gap: 'var(--space-3)',
            }}
          >
            {[1, 2, 3, 4].map((i) => (
              <div
                key={i}
                style={{
                  background: 'rgba(255,255,255,0.03)',
                  borderRadius: 'var(--radius-md)',
                  height: 120,
                  animation: 'shimmer 1.5s infinite',
                  backgroundImage:
                    'linear-gradient(90deg, rgba(255,255,255,0.03) 25%, rgba(255,255,255,0.06) 50%, rgba(255,255,255,0.03) 75%)',
                  backgroundSize: '200% 100%',
                }}
              />
            ))}
          </div>
        )}
      </section>

      {/* ── Knowledge Graph Stats ────────────────────────── */}
      {graphSummary && (
        <section>
          <h2
            style={{
              fontSize: 'var(--text-xs)',
              fontWeight: 600,
              letterSpacing: '0.04em',
              textTransform: 'uppercase' as const,
              color: 'rgba(255,255,255,0.4)',
              margin: '0 0 var(--space-3) 0',
            }}
          >
            Knowledge Graph
          </h2>

          {/* Stat pills */}
          <div
            style={{
              display: 'flex',
              gap: 'var(--space-3)',
              flexWrap: 'wrap',
              marginBottom: 'var(--space-4)',
            }}
          >
            <StatPill label="Entities" value={formatNumber(graphSummary.total_entities)} />
            <StatPill label="Links" value={formatNumber(graphSummary.total_links)} />
          </div>

          {/* Link type distribution */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 'var(--space-2)',
              marginBottom: 'var(--space-6)',
            }}
          >
            {graphSummary.link_types
              .sort((a, b) => b.count - a.count)
              .slice(0, 12)
              .map((lt) => (
                <span
                  key={lt.type}
                  style={{
                    fontSize: 'var(--text-xs)',
                    fontFamily: 'var(--font-mono)',
                    padding: '2px var(--space-2)',
                    borderRadius: 'var(--radius-full)',
                    background: 'rgba(255,255,255,0.06)',
                    color: 'rgba(255,255,255,0.5)',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {lt.type.replace(/_/g, ' ').toLowerCase()} {formatNumber(lt.count)}
                </span>
              ))}
          </div>

          {/* Drug completeness */}
          {graphSummary.drug_completeness &&
            Object.keys(graphSummary.drug_completeness).length > 0 && (
              <>
                <h3
                  style={{
                    fontSize: 'var(--text-xs)',
                    fontWeight: 600,
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase' as const,
                    color: 'rgba(255,255,255,0.4)',
                    margin: '0 0 var(--space-3) 0',
                  }}
                >
                  Drug Completeness
                </h3>
                <div
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 'var(--space-3)',
                    maxWidth: 480,
                  }}
                >
                  {Object.entries(graphSummary.drug_completeness)
                    .sort(([, a], [, b]) => b - a)
                    .map(([field, pct]) => (
                      <CompletenessBar key={field} label={field} value={pct} />
                    ))}
                </div>
              </>
            )}
        </section>
      )}
    </div>
  );
}

/* ── Stat Pill ───────────────────────────────────────── */

function StatPill({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'baseline',
        gap: 'var(--space-2)',
        padding: 'var(--space-2) var(--space-4)',
        background: 'rgba(255,255,255,0.05)',
        borderRadius: 'var(--radius-md)',
        border: '1px solid rgba(255,255,255,0.06)',
      }}
    >
      <span
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 'var(--text-lg)',
          fontWeight: 600,
          color: 'var(--text-inverse)',
        }}
      >
        {value}
      </span>
      <span
        style={{
          fontSize: 'var(--text-xs)',
          color: 'rgba(255,255,255,0.4)',
          textTransform: 'uppercase' as const,
          letterSpacing: '0.04em',
        }}
      >
        {label}
      </span>
    </div>
  );
}
