import { useCallback, useEffect, useState } from 'react';
import {
  Inbox, AlertCircle, AlertTriangle, Sparkles, Activity, Check, X, Target, Calendar,
} from 'lucide-react';
import {
  inboxApi, decisionsApi,
  type InboxResponse, type InboxProposal,
} from '../../api';

interface Props {
  onOpenDecision: (id: string) => void;
  onOpenWarRoom: (id: string, signalKbq?: string) => void;
  onOpenSignals?: () => void;
  onOpenInsights?: () => void;
}

function hasToken(): boolean {
  if (typeof window === 'undefined') return false;
  return !!window.localStorage.getItem('mz_auth_token');
}

export default function InboxTab({
  onOpenDecision, onOpenWarRoom, onOpenInsights,
}: Props) {
  const authed = hasToken();
  const [data, setData] = useState<InboxResponse | null>(null);
  const [loading, setLoading] = useState(authed);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!authed) return;
    setLoading(true);
    setError(null);
    try {
      const r = await inboxApi.get();
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
        <div className="text-center max-w-md">
          <div
            className="text-[13px] mb-4"
            style={{ color: 'var(--color-ink-3)' }}
          >
            Log in (viewer or above) to see your decision inbox.
          </div>
          <button
            type="button"
            onClick={() => { window.location.href = '/login'; }}
            className="btn-primary"
          >
            Log In
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto" style={{ padding: '24px 32px' }}>
      <div className="mb-6">
        <div
          className="text-[10px] uppercase font-medium mb-1 inline-flex items-center gap-1"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em' }}
        >
          <Inbox size={11} />
          Inbox
        </div>
        <h1
          className="font-display text-[22px]"
          style={{ color: 'var(--color-ink)', letterSpacing: '-0.01em' }}
        >
          What needs your attention
        </h1>
        <div className="text-[12px] mt-1" style={{ color: 'var(--color-ink-4)' }}>
          The agentic loop runs in the background. Confirm matches, address overdue
          decisions, war-game fresh signals.
        </div>
      </div>

      {loading && !data ? (
        <SkeletonInbox />
      ) : error ? (
        <ErrorBox message={error} />
      ) : data ? (
        <div className="space-y-6">
          <ProposalsSection
            proposals={data.pending_proposals}
            onConfirm={async (p) => {
              try {
                await decisionsApi.confirmProposal(p.decision_id, p.proposal_id);
                await reload();
              } catch (e) {
                setError(e instanceof Error ? e.message : String(e));
              }
            }}
            onDismiss={async (p) => {
              try {
                await decisionsApi.dismissProposal(p.decision_id, p.proposal_id);
                await reload();
              } catch (e) {
                setError(e instanceof Error ? e.message : String(e));
              }
            }}
            onOpen={(decisionId) => onOpenDecision(decisionId)}
          />

          <OverdueSection
            decisions={data.overdue_decisions}
            onOpen={onOpenDecision}
          />

          <SignalsSection
            signals={data.high_impact_signals}
            onSimulate={(s) => {
              const tag = s.kbq_tags?.[0];
              onOpenWarRoom(`new-from-signal-${s.id}`, tag);
            }}
          />

          <CalibrationSection
            summary={data.calibration_summary}
            onOpenInsights={onOpenInsights}

          />
        </div>
      ) : null}
    </div>
  );
}

// ────────────────────────────────────────────────────────────────────
// Sections
// ────────────────────────────────────────────────────────────────────

function SectionHeader({
  icon, color, title, count,
}: {
  icon: React.ReactNode;
  color: string;
  title: string;
  count: number | null;
}) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <span style={{ color }}>{icon}</span>
      <h2
        className="text-[14px] font-medium"
        style={{ color: 'var(--color-ink)' }}
      >
        {title}
      </h2>
      {count !== null && (
        <span
          className="text-[10px] uppercase font-medium"
          style={{
            padding: '1px 7px',
            borderRadius: '4px',
            background: 'var(--color-surface-2)',
            color: 'var(--color-ink-3)',
            letterSpacing: '0.04em',
          }}
        >
          {count}
        </span>
      )}
    </div>
  );
}

function ProposalsSection({
  proposals, onConfirm, onDismiss, onOpen,
}: {
  proposals: InboxProposal[];
  onConfirm: (p: InboxProposal) => void;
  onDismiss: (p: InboxProposal) => void;
  onOpen: (decisionId: string) => void;
}) {
  return (
    <section>
      <SectionHeader
        icon={<AlertCircle size={14} />}
        color="#A16207"
        title="Outcome proposals awaiting confirm"
        count={proposals.length}
      />
      {proposals.length === 0 ? (
        <EmptyState
          icon={<Sparkles size={20} />}
          title="No proposals yet"
          body="The system scans every hour for signals that match your open decisions. Confirmations arrive here when the match score crosses 0.75."
        />
      ) : (
        <div className="space-y-2">
          {proposals.map((p) => (
            <div
              key={p.proposal_id}
              style={{
                padding: '14px 16px',
                borderRadius: '6px',
                border: '1px solid var(--color-line)',
                borderLeft: '3px solid #A16207',
                background: 'var(--color-surface)',
              }}
            >
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <span
                  className="text-[10px] uppercase font-medium"
                  style={{
                    padding: '2px 7px',
                    borderRadius: '4px',
                    background: '#FEF3C7',
                    color: '#A16207',
                    letterSpacing: '0.05em',
                  }}
                  title={`Entity ${p.match_components.entity_overlap.toFixed(2)} · KBQ ${p.match_components.kbq_overlap.toFixed(2)} · Temporal ${p.match_components.temporal_proximity.toFixed(2)}`}
                >
                  Match {(p.match_score * 100).toFixed(0)}%
                </span>
                {p.signal_kbq_tags.slice(0, 2).map((t) => (
                  <span
                    key={t}
                    className="text-[9px] uppercase"
                    style={{
                      padding: '1px 6px',
                      borderRadius: '3px',
                      background: 'var(--color-surface-2)',
                      color: 'var(--color-ink-4)',
                      letterSpacing: '0.04em',
                    }}
                  >
                    {t}
                  </span>
                ))}
                <span className="ml-auto text-[10px]" style={{ color: 'var(--color-ink-4)' }}>
                  {p.proposed_at ? new Date(p.proposed_at).toLocaleDateString() : ''}
                </span>
              </div>
              <div className="text-[12px] mb-1" style={{ color: 'var(--color-ink-3)' }}>
                <strong style={{ color: 'var(--color-ink)' }}>{p.signal_headline}</strong>
                {p.signal_entity && <span> · {p.signal_entity}</span>}
              </div>
              <div className="text-[11px] mb-3" style={{ color: 'var(--color-ink-4)' }}>
                Matches your decision:{' '}
                <button
                  type="button"
                  onClick={() => onOpen(p.decision_id)}
                  style={{
                    background: 'transparent',
                    border: 'none',
                    color: 'var(--color-accent)',
                    padding: 0,
                    cursor: 'pointer',
                    textDecoration: 'underline',
                  }}
                >
                  {p.decision_title}
                </button>
              </div>
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={() => onConfirm(p)}
                  className="text-[11px] inline-flex items-center gap-1 font-medium"
                  style={{
                    padding: '5px 12px',
                    borderRadius: '6px',
                    background: 'var(--color-accent)',
                    color: 'white',
                    border: 'none',
                    cursor: 'pointer',
                  }}
                >
                  <Check size={11} />
                  Confirm
                </button>
                <button
                  type="button"
                  onClick={() => onDismiss(p)}
                  className="text-[11px] inline-flex items-center gap-1"
                  style={{
                    padding: '5px 12px',
                    borderRadius: '6px',
                    background: 'transparent',
                    color: 'var(--color-ink-3)',
                    border: '1px solid var(--color-line)',
                    cursor: 'pointer',
                  }}
                >
                  <X size={11} />
                  Dismiss
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function OverdueSection({
  decisions, onOpen,
}: {
  decisions: InboxResponse['overdue_decisions'];
  onOpen: (id: string) => void;
}) {
  return (
    <section>
      <SectionHeader
        icon={<AlertTriangle size={14} />}
        color="#B91C1C"
        title="Overdue decisions"
        count={decisions.length}
      />
      {decisions.length === 0 ? (
        <EmptyState
          icon={<Calendar size={20} />}
          title="You're on top of your deadlines"
          body="No open decisions past their target date. Keep going."
        />
      ) : (
        <div className="space-y-2">
          {decisions.map((d) => (
            <button
              key={d.id}
              type="button"
              onClick={() => onOpen(d.id)}
              className="text-left w-full"
              style={{
                padding: '12px 14px',
                borderRadius: '6px',
                border: '1px solid var(--color-line)',
                borderLeft: '3px solid #B91C1C',
                background: 'var(--color-surface)',
                cursor: 'pointer',
              }}
            >
              <div className="flex items-center gap-2 mb-1">
                <span
                  className="text-[10px] uppercase font-medium"
                  style={{
                    padding: '2px 7px',
                    borderRadius: '4px',
                    background: '#FEE2E2',
                    color: '#B91C1C',
                    letterSpacing: '0.05em',
                  }}
                >
                  {d.days_overdue}d overdue
                </span>
                <span
                  className="text-[10px] uppercase"
                  style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}
                >
                  {d.status}
                </span>
                <span
                  className="ml-auto text-[10px]"
                  style={{ color: 'var(--color-ink-4)' }}
                >
                  Due {d.deadline ? new Date(d.deadline).toLocaleDateString() : '—'}
                </span>
              </div>
              <div
                className="text-[13px] font-medium"
                style={{ color: 'var(--color-ink)' }}
              >
                {d.title}
              </div>
              {d.target_metric && (
                <div className="text-[11px] mt-1" style={{ color: 'var(--color-ink-4)' }}>
                  <Target size={10} className="inline mr-1" />
                  {d.target_metric}{d.target_value && `: ${d.target_value}`}
                </div>
              )}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}

function SignalsSection({
  signals, onSimulate,
}: {
  signals: InboxResponse['high_impact_signals'];
  onSimulate: (s: InboxResponse['high_impact_signals'][0]) => void;
}) {
  return (
    <section>
      <SectionHeader
        icon={<Sparkles size={14} />}
        color="#15803D"
        title="High-impact signals worth war-gaming"
        count={signals.length}
      />
      {signals.length === 0 ? (
        <EmptyState
          icon={<Sparkles size={20} />}
          title="No fresh high-impact signals"
          body="The DataSteward is watching across sources. Nothing high-impact in the last 7 days. Browse the Signals tab for full feed."
        />
      ) : (
        <div className="space-y-2">
          {signals.map((s) => (
            <div
              key={s.id}
              style={{
                padding: '12px 14px',
                borderRadius: '6px',
                border: '1px solid var(--color-line)',
                borderLeft: '3px solid #15803D',
                background: 'var(--color-surface)',
              }}
            >
              <div className="flex items-center gap-2 mb-1">
                {s.kbq_tags.slice(0, 2).map((t) => (
                  <span
                    key={t}
                    className="text-[9px] uppercase"
                    style={{
                      padding: '1px 6px',
                      borderRadius: '3px',
                      background: 'var(--color-surface-2)',
                      color: 'var(--color-ink-4)',
                      letterSpacing: '0.04em',
                    }}
                  >
                    {t}
                  </span>
                ))}
                <span className="ml-auto text-[10px]" style={{ color: 'var(--color-ink-4)' }}>
                  {s.created_at ? new Date(s.created_at).toLocaleDateString() : ''}
                </span>
              </div>
              <div
                className="text-[13px] font-medium mb-1"
                style={{ color: 'var(--color-ink)' }}
              >
                {s.headline}
              </div>
              {s.primary_entity_name && (
                <div className="text-[11px] mb-2" style={{ color: 'var(--color-ink-4)' }}>
                  {s.primary_entity_name}
                </div>
              )}
              <button
                type="button"
                onClick={() => onSimulate(s)}
                className="text-[11px] inline-flex items-center gap-1 font-medium"
                style={{
                  padding: '4px 10px',
                  borderRadius: '4px',
                  background: 'var(--color-accent)',
                  color: 'white',
                  border: 'none',
                  cursor: 'pointer',
                }}
              >
                <Sparkles size={10} />
                Simulate in war room
              </button>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function CalibrationSection({
  summary, onOpenInsights,
}: {
  summary: InboxResponse['calibration_summary'];
  onOpenInsights?: () => void;
}) {
  const meanPct = summary.last_30d_mean !== null
    ? (summary.last_30d_mean * 100).toFixed(0)
    : null;
  return (
    <section>
      <SectionHeader
        icon={<Activity size={14} />}
        color="var(--color-accent)"
        title="Your calibration this month"
        count={summary.total}
      />
      {summary.total === 0 ? (
        <EmptyState
          icon={<Activity size={20} />}
          title="No outcomes captured yet this month"
          body="When you capture outcomes for your decisions, your calibration score (predicted vs actual) shows here."
        />
      ) : (
        <div
          style={{
            padding: '16px 18px',
            borderRadius: '6px',
            border: '1px solid var(--color-line)',
            background: 'var(--color-surface)',
          }}
        >
          <div className="flex items-baseline gap-3">
            <div
              className="font-display text-[40px]"
              style={{
                color: meanPct
                  ? (parseInt(meanPct) >= 66 ? '#15803D' : parseInt(meanPct) >= 33 ? '#A16207' : '#B91C1C')
                  : 'var(--color-ink-4)',
                letterSpacing: '-0.02em',
                lineHeight: 1,
              }}
            >
              {meanPct ?? '—'}
              {meanPct && <span className="text-[20px]" style={{ marginLeft: '2px' }}>%</span>}
            </div>
            <div className="text-[12px]" style={{ color: 'var(--color-ink-4)' }}>
              mean calibration · trailing 30 days
            </div>
          </div>
          <div className="text-[11px] mt-2" style={{ color: 'var(--color-ink-4)' }}>
            <span style={{ color: '#15803D' }}>{summary.verified_count} verified</span>
            {' · '}
            <span style={{ color: '#B91C1C' }}>{summary.missed_count} missed</span>
            {' · '}
            <span>{summary.total} total</span>
          </div>
          {onOpenInsights && (
            <button
              type="button"
              onClick={onOpenInsights}
              className="text-[11px] mt-3"
              style={{
                background: 'transparent',
                border: 'none',
                color: 'var(--color-accent)',
                padding: 0,
                cursor: 'pointer',
                textDecoration: 'underline',
              }}
            >
              View calibration trends →
            </button>
          )}
        </div>
      )}
    </section>
  );
}

// ────────────────────────────────────────────────────────────────────
// Shared
// ────────────────────────────────────────────────────────────────────

function EmptyState({
  icon, title, body,
}: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div
      style={{
        padding: '24px 18px',
        borderRadius: '6px',
        border: '1px dashed var(--color-line)',
        background: 'var(--color-surface)',
        textAlign: 'center',
      }}
    >
      <div className="flex justify-center mb-2" style={{ color: 'var(--color-ink-4)' }}>
        {icon}
      </div>
      <div
        className="text-[13px] font-medium mb-1"
        style={{ color: 'var(--color-ink-2)' }}
      >
        {title}
      </div>
      <div
        className="text-[11px] mx-auto"
        style={{ color: 'var(--color-ink-4)', maxWidth: '420px' }}
      >
        {body}
      </div>
    </div>
  );
}

function SkeletonInbox() {
  return (
    <div className="space-y-6">
      {[0, 1, 2, 3].map((i) => (
        <div key={i}>
          <div
            style={{
              height: '16px',
              width: '180px',
              background: 'var(--color-surface-2)',
              borderRadius: '4px',
              marginBottom: '12px',
            }}
          />
          <div
            style={{
              height: '88px',
              background: 'var(--color-surface-2)',
              borderRadius: '6px',
            }}
          />
        </div>
      ))}
    </div>
  );
}

function ErrorBox({ message }: { message: string }) {
  return (
    <div
      className="text-[12px]"
      style={{
        padding: '12px 14px',
        borderRadius: '6px',
        background: '#FEF2F2',
        color: '#B91C1C',
      }}
    >
      {message}
    </div>
  );
}
