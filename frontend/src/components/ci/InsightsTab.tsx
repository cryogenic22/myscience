import { useCallback, useEffect, useState } from 'react';
import {
  Activity, TrendingUp, CheckCircle2, AlertCircle, Sparkles, Target,
} from 'lucide-react';
import {
  insightsApi,
  type InsightsResponse, type InsightsCalibrationBucket, type InsightsOutcomeEvent,
} from '../../api';

interface Props {
  onOpenDecision: (id: string) => void;
}

function hasToken(): boolean {
  if (typeof window === 'undefined') return false;
  return !!window.localStorage.getItem('mz_auth_token');
}

export default function InsightsTab({ onOpenDecision }: Props) {
  const authed = hasToken();
  const [data, setData] = useState<InsightsResponse | null>(null);
  const [loading, setLoading] = useState(authed);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!authed) return;
    setLoading(true);
    setError(null);
    try {
      const r = await insightsApi.get();
      setData(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [authed]);

  useEffect(() => { void reload(); }, [reload]);

  if (!authed) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ padding: '40px' }}>
        <div className="text-[13px] text-center max-w-md" style={{ color: 'var(--color-ink-3)' }}>
          Log in to see your prediction insights.
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto" style={{ padding: '24px 32px', maxWidth: '900px', margin: '0 auto', width: '100%' }}>
      <header className="mb-6">
        <div
          className="text-[10px] uppercase font-medium mb-1 inline-flex items-center gap-1"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em' }}
        >
          <TrendingUp size={11} />
          Insights
        </div>
        <h1
          className="font-display text-[22px]"
          style={{ color: 'var(--color-ink)', letterSpacing: '-0.01em' }}
        >
          How well are your predictions calibrated?
        </h1>
        <div className="text-[12px] mt-1" style={{ color: 'var(--color-ink-4)' }}>
          The flywheel only matters if it learns. Your prediction quality over time
          and the autonomous loop's recent activity.
        </div>
      </header>

      {loading && !data ? (
        <Skeleton />
      ) : error ? (
        <ErrorBox message={error} />
      ) : data ? (
        <div className="space-y-6">
          <CalibrationDashboard data={data} />
          <OutcomeStream events={data.outcome_stream} onOpenDecision={onOpenDecision} />
        </div>
      ) : null}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Calibration dashboard (big number + 12-month sparkline)
// ────────────────────────────────────────────────────────────────────

function CalibrationDashboard({ data }: { data: InsightsResponse }) {
  const meanPct = data.summary.last_30d_mean !== null
    ? Math.round(data.summary.last_30d_mean * 100) : null;

  return (
    <section>
      <SectionHeader icon={<Activity size={14} />} title="Calibration over time" />
      <div
        style={{
          padding: '20px',
          borderRadius: '8px',
          border: '1px solid var(--color-line)',
          background: 'var(--color-surface)',
        }}
      >
        {/* Big number */}
        <div className="flex items-baseline gap-3 mb-1">
          <div
            className="font-display text-[48px]"
            style={{
              color: meanPct !== null
                ? (meanPct >= 66 ? '#15803D' : meanPct >= 33 ? '#A16207' : '#B91C1C')
                : 'var(--color-ink-4)',
              letterSpacing: '-0.02em',
              lineHeight: 1,
            }}
          >
            {meanPct ?? '—'}
            {meanPct !== null && (
              <span className="text-[24px]" style={{ marginLeft: '2px' }}>%</span>
            )}
          </div>
          <div className="text-[13px]" style={{ color: 'var(--color-ink-3)' }}>
            mean calibration · trailing 30 days
          </div>
        </div>
        <div className="text-[11px] mb-4" style={{ color: 'var(--color-ink-4)' }}>
          <span style={{ color: '#15803D' }}>{data.summary.verified_count} verified</span>
          {' · '}
          <span style={{ color: '#B91C1C' }}>{data.summary.missed_count} missed</span>
          {' · '}
          {data.summary.total} total this month
        </div>

        {/* 12-month sparkline */}
        {data.calibration_trend.length > 0 ? (
          <Sparkline buckets={data.calibration_trend} />
        ) : (
          <div className="text-[12px]" style={{ color: 'var(--color-ink-4)', fontStyle: 'italic' }}>
            12-month trend appears once you have outcomes captured across multiple months.
          </div>
        )}
      </div>
    </section>
  );
}

function Sparkline({ buckets }: { buckets: InsightsCalibrationBucket[] }) {
  // Render as inline bar chart — height = mean_score, label = month
  const max = Math.max(0.01, ...buckets.map((b) => b.mean_score ?? 0));
  return (
    <div>
      <div className="flex items-end gap-1" style={{ height: '60px' }}>
        {buckets.map((b) => {
          const score = b.mean_score ?? 0;
          const heightPct = (score / Math.max(max, 1)) * 100;
          const color = score >= 0.66 ? '#15803D' : score >= 0.33 ? '#A16207' : '#B91C1C';
          return (
            <div
              key={b.month}
              title={`${b.month}: ${b.total} captures, mean ${(score * 100).toFixed(0)}%`}
              style={{
                flex: 1,
                height: `${heightPct}%`,
                background: color,
                borderRadius: '2px',
                minHeight: '2px',
              }}
            />
          );
        })}
      </div>
      <div className="flex justify-between mt-2 text-[9px]" style={{ color: 'var(--color-ink-4)' }}>
        <span>{buckets[0]?.month ? new Date(buckets[0].month).toLocaleDateString(undefined, { month: 'short', year: '2-digit' }) : ''}</span>
        <span>{buckets[buckets.length - 1]?.month ? new Date(buckets[buckets.length - 1].month).toLocaleDateString(undefined, { month: 'short', year: '2-digit' }) : ''}</span>
      </div>
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Outcome stream — chronological feed
// ────────────────────────────────────────────────────────────────────

function OutcomeStream({
  events, onOpenDecision,
}: { events: InsightsOutcomeEvent[]; onOpenDecision: (id: string) => void }) {
  return (
    <section>
      <SectionHeader icon={<Sparkles size={14} />} title={`Outcome stream (${events.length})`} />
      {events.length === 0 ? (
        <EmptyState
          icon={<Activity size={20} />}
          title="No outcome events yet"
          body="When the autonomous scheduler proposes matches or you capture outcomes, the activity stream renders here."
        />
      ) : (
        <div className="space-y-1">
          {events.map((e, i) => (
            <EventRow key={i} event={e} onOpen={() => e.decision_id && onOpenDecision(e.decision_id)} />
          ))}
        </div>
      )}
    </section>
  );
}

function EventRow({
  event, onOpen,
}: { event: InsightsOutcomeEvent; onOpen: () => void }) {
  const isCapture = event.event_type === 'capture';
  const isVerified = event.decision_status === 'verified';
  const icon = isCapture
    ? (isVerified ? <CheckCircle2 size={14} style={{ color: '#15803D' }} /> : <AlertCircle size={14} style={{ color: '#B91C1C' }} />)
    : <Sparkles size={14} style={{ color: '#A16207' }} />;

  return (
    <button
      type="button"
      onClick={onOpen}
      className="text-left w-full flex items-start gap-3"
      style={{
        padding: '10px 14px',
        borderRadius: '6px',
        border: '1px solid var(--color-line)',
        background: 'var(--color-surface)',
        cursor: 'pointer',
      }}
    >
      <div style={{ marginTop: '2px' }}>{icon}</div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap mb-1">
          <span
            className="text-[10px] uppercase font-medium"
            style={{
              padding: '1px 6px', borderRadius: '3px',
              background: isCapture ? 'var(--color-surface-2)' : '#FEF3C7',
              color: isCapture ? 'var(--color-ink-3)' : '#A16207',
              letterSpacing: '0.04em',
            }}
          >
            {isCapture ? 'capture' : 'proposal'}
          </span>
          {event.detail_score !== null && (
            <span className="text-[10px]" style={{ color: 'var(--color-ink-4)' }}>
              {isCapture ? `cal ${(event.detail_score * 100).toFixed(0)}%` : `match ${(event.detail_score * 100).toFixed(0)}%`}
            </span>
          )}
          <span className="ml-auto text-[10px]" style={{ color: 'var(--color-ink-4)' }}>
            {event.event_at ? new Date(event.event_at).toLocaleString() : ''}
          </span>
        </div>
        <div className="text-[12px]" style={{ color: 'var(--color-ink)' }}>
          {event.decision_title}
        </div>
        {event.signal_headline && (
          <div className="text-[11px] mt-0.5" style={{ color: 'var(--color-ink-4)' }}>
            <Target size={9} className="inline mr-1" />
            {event.signal_headline}
          </div>
        )}
        {event.detail_text && (
          <div className="text-[11px] mt-0.5 line-clamp-2" style={{ color: 'var(--color-ink-3)' }}>
            {event.detail_text}
          </div>
        )}
      </div>
    </button>
  );
}

// ────────────────────────────────────────────────────────────────────
// Helpers
// ────────────────────────────────────────────────────────────────────

function SectionHeader({ icon, title }: { icon: React.ReactNode; title: string }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <span style={{ color: 'var(--color-ink-3)' }}>{icon}</span>
      <h2 className="text-[14px] font-medium" style={{ color: 'var(--color-ink)' }}>
        {title}
      </h2>
    </div>
  );
}

function EmptyState({
  icon, title, body,
}: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div
      style={{
        padding: '24px 18px', borderRadius: '6px',
        border: '1px dashed var(--color-line)',
        background: 'var(--color-surface)', textAlign: 'center',
      }}
    >
      <div className="flex justify-center mb-2" style={{ color: 'var(--color-ink-4)' }}>{icon}</div>
      <div className="text-[13px] font-medium mb-1" style={{ color: 'var(--color-ink-2)' }}>{title}</div>
      <div className="text-[11px] mx-auto" style={{ color: 'var(--color-ink-4)', maxWidth: '420px' }}>{body}</div>
    </div>
  );
}

function Skeleton() {
  return (
    <div className="space-y-6">
      <div style={{ height: '180px', background: 'var(--color-surface-2)', borderRadius: '6px' }} />
      {[0, 1, 2].map((i) => (
        <div key={i} style={{ height: '64px', background: 'var(--color-surface-2)', borderRadius: '6px' }} />
      ))}
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div
      className="text-[12px]"
      style={{ padding: '12px 14px', borderRadius: '6px', background: '#FEF2F2', color: '#B91C1C' }}
    >
      {message}
    </div>
  );
}
