import { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  ArrowLeft, Target, Search, Trash2, Link as LinkIcon,
  Sparkles, Check, X, Activity, MessageSquare,
} from 'lucide-react';
import {
  decisionsApi, MOVE_TYPE_META,
  type Decision, type DecisionFullBundle, type DecisionStatus,
} from '../../../api';
import DeadlineChip from './DeadlineChip';
import CalibrationChip from './CalibrationChip';
import OutcomeDetector from './OutcomeDetector';
import ProvenanceTrail from '../ProvenanceTrail';
import CommentsPanel from '../war/CommentsPanel';

const STATUS_META: Record<DecisionStatus, { label: string; bg: string; fg: string }> = {
  open:        { label: 'Open',         bg: '#DBEAFE', fg: '#1E40AF' },
  in_progress: { label: 'In progress',  bg: '#FEF3C7', fg: '#A16207' },
  verified:    { label: 'Verified',     bg: '#DCFCE7', fg: '#15803D' },
  missed:      { label: 'Missed',       bg: '#FEE2E2', fg: '#B91C1C' },
  cancelled:   { label: 'Cancelled',    bg: 'var(--color-surface-2)', fg: 'var(--color-ink-4)' },
};

const STATUS_OPTIONS: DecisionStatus[] = ['open', 'in_progress', 'verified', 'missed', 'cancelled'];

function isOwner(d: Decision): boolean {
  if (typeof window === 'undefined') return false;
  try {
    const tok = window.localStorage.getItem('mz_auth_token');
    if (!tok) return false;
    const payload = tok.split('.')[1];
    if (!payload) return false;
    const b64 = payload.replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    const decoded = JSON.parse(atob(padded));
    return decoded?.sub === d.owner_user_id;
  } catch {
    return false;
  }
}

export default function DecisionDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [bundle, setBundle] = useState<DecisionFullBundle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [shareToast, setShareToast] = useState<string | null>(null);
  const [detecting, setDetecting] = useState(false);

  const reload = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    setError(null);
    try {
      const r = await decisionsApi.detailFull(id);
      setBundle(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => { void reload(); }, [reload]);

  if (loading && !bundle) {
    return (
      <div className="flex-1 flex items-center justify-center text-[13px]"
           style={{ color: 'var(--color-ink-4)' }}>
        Loading decision…
      </div>
    );
  }
  if (!bundle) {
    return (
      <div className="flex-1" style={{ padding: '40px' }}>
        <BackBar onBack={() => navigate('/ci?tab=decisions')} />
        <div className="text-[13px]" style={{ color: '#B91C1C' }}>
          {error || 'Decision not found.'}
        </div>
      </div>
    );
  }

  const owner = isOwner(bundle);
  const meta = STATUS_META[bundle.status];
  const moveMeta = MOVE_TYPE_META[bundle.move_type];

  const handleStatus = async (next: DecisionStatus) => {
    setBusy(true);
    setError(null);
    try {
      const updated = await decisionsApi.patch(bundle.id, { status: next });
      setBundle({ ...bundle, ...updated });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleShare = async () => {
    try {
      await navigator.clipboard.writeText(window.location.href);
      setShareToast('URL copied');
    } catch {
      setShareToast('Could not copy — URL is in the address bar');
    }
    setTimeout(() => setShareToast(null), 2200);
  };

  const handleDelete = async () => {
    if (!window.confirm(`Delete "${bundle.title}"? This is permanent.`)) return;
    try {
      await decisionsApi.remove(bundle.id);
      navigate('/ci?tab=decisions');
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const handleConfirmProposal = async (proposalId: string) => {
    setBusy(true);
    try {
      await decisionsApi.confirmProposal(bundle.id, proposalId);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const handleDismissProposal = async (proposalId: string) => {
    setBusy(true);
    try {
      await decisionsApi.dismissProposal(bundle.id, proposalId);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto" style={{ padding: '24px 32px', maxWidth: '900px', margin: '0 auto', width: '100%' }}>
      <BackBar onBack={() => navigate('/ci?tab=decisions')} />

      {/* Header */}
      <header className="mb-6">
        <div className="flex items-center gap-2 mb-2 flex-wrap">
          <span
            className="text-[10px] uppercase font-medium"
            style={{
              padding: '2px 8px', borderRadius: '4px',
              background: meta.bg, color: meta.fg,
              letterSpacing: '0.05em',
            }}
          >
            {meta.label}
          </span>
          <DeadlineChip
            deadline={bundle.deadline}
            daysToDeadline={bundle.days_to_deadline}
            overdue={bundle.overdue}
            status={bundle.status}
          />
          <CalibrationChip score={bundle.calibration_score} />
          <span style={{ fontSize: '12px' }}>{moveMeta?.icon}</span>
          <span className="text-[10px] uppercase" style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}>
            {moveMeta?.label ?? bundle.move_type}
          </span>
          <div className="ml-auto relative flex items-center gap-2">
            {shareToast && (
              <span className="text-[10px]" style={{ color: 'var(--color-ink-3)' }}>
                {shareToast}
              </span>
            )}
            <button
              type="button"
              onClick={handleShare}
              className="text-[11px] inline-flex items-center gap-1"
              style={{
                padding: '5px 10px', borderRadius: '6px',
                background: 'transparent', color: 'var(--color-ink-3)',
                border: '1px solid var(--color-line)', cursor: 'pointer',
              }}
            >
              <LinkIcon size={11} />
              Share
            </button>
            {owner && ['open', 'in_progress'].includes(bundle.status) && (
              <button
                type="button"
                onClick={() => setDetecting(true)}
                className="text-[11px] inline-flex items-center gap-1 font-medium"
                style={{
                  padding: '5px 12px', borderRadius: '6px',
                  background: 'var(--color-accent)', color: 'white',
                  border: 'none', cursor: 'pointer',
                }}
              >
                <Search size={11} />
                Detect outcome
              </button>
            )}
            {owner && (
              <button
                type="button"
                onClick={handleDelete}
                className="opacity-60 hover:opacity-100"
                style={{
                  padding: '5px', borderRadius: '6px',
                  background: 'transparent', color: 'var(--color-ink-4)',
                  border: '1px solid transparent', cursor: 'pointer',
                }}
                title="Delete decision"
                aria-label="Delete decision"
              >
                <Trash2 size={13} />
              </button>
            )}
          </div>
        </div>

        <h1
          className="font-display text-[26px] mb-2"
          style={{ color: 'var(--color-ink)', letterSpacing: '-0.01em' }}
        >
          {bundle.title}
        </h1>

        <div className="text-[12px]" style={{ color: 'var(--color-ink-4)' }}>
          <Target size={11} className="inline mr-1" />
          <span>{bundle.owner_display_name}</span>
          {bundle.created_at && (
            <span> · committed {new Date(bundle.created_at).toLocaleDateString()}</span>
          )}
          {typeof bundle.confidence_at_commit === 'number' && (
            <span> · at {(bundle.confidence_at_commit * 100).toFixed(0)}% confidence</span>
          )}
        </div>
      </header>

      {error && (
        <div
          className="text-[12px] mb-4"
          style={{
            padding: '10px 14px', borderRadius: '6px',
            background: '#FEF2F2', color: '#B91C1C',
          }}
        >
          {error}
        </div>
      )}

      <div className="space-y-6">
        {/* Provenance */}
        {(bundle.source_signal || bundle.war_room) && (
          <ProvenanceTrail
            sourceSignal={
              bundle.source_signal
                ? { id: bundle.source_signal.id, headline: bundle.source_signal.headline }
                : null
            }
            warRoom={
              bundle.war_room
                ? { id: bundle.war_room.id, title: bundle.war_room.title }
                : null
            }
            current={{ label: 'Decision', title: bundle.title }}
            onOpenWarRoom={(rid) => navigate(`/ci?tab=rooms&room=${rid}`)}
            variant="verbose"
          />
        )}

        {/* Target & rationale */}
        <Section title="Target & rationale">
          {(bundle.target_metric || bundle.target_value) && (
            <div
              className="text-[12px] mb-3"
              style={{ color: 'var(--color-ink-2)' }}
            >
              <strong style={{ color: 'var(--color-ink-3)' }}>Target:</strong>{' '}
              {bundle.target_metric}
              {bundle.target_value && ` = ${bundle.target_value}`}
            </div>
          )}
          {bundle.rationale ? (
            <div
              className="text-[13px] leading-relaxed whitespace-pre-wrap"
              style={{ color: 'var(--color-ink-2)' }}
            >
              {bundle.rationale}
            </div>
          ) : (
            <div className="text-[12px]" style={{ color: 'var(--color-ink-4)', fontStyle: 'italic' }}>
              No rationale recorded.
            </div>
          )}
        </Section>

        {/* Outcome (if captured) */}
        {bundle.actual_outcome && (
          <Section title="Outcome">
            <div className="flex items-center gap-2 mb-2 flex-wrap">
              <span
                className="text-[10px] uppercase font-medium"
                style={{
                  padding: '2px 7px', borderRadius: '4px',
                  background: meta.bg, color: meta.fg,
                  letterSpacing: '0.05em',
                }}
              >
                {meta.label}
              </span>
              {bundle.actual_outcome_recorded_at && (
                <span className="text-[10px]" style={{ color: 'var(--color-ink-4)' }}>
                  captured {new Date(bundle.actual_outcome_recorded_at).toLocaleDateString()}
                </span>
              )}
              <CalibrationChip score={bundle.calibration_score} />
            </div>
            <div
              className="text-[13px] leading-relaxed whitespace-pre-wrap"
              style={{ color: 'var(--color-ink-2)' }}
            >
              {bundle.actual_outcome}
            </div>
            {bundle.target_value && (
              <div className="text-[11px] mt-2" style={{ color: 'var(--color-ink-4)' }}>
                <Activity size={10} className="inline mr-1" />
                Predicted {bundle.target_value} → captured outcome above
              </div>
            )}
          </Section>
        )}

        {/* Pending auto-proposals */}
        {bundle.pending_proposals.length > 0 && (
          <Section title={`Auto-detected matches (${bundle.pending_proposals.length})`} icon={<Sparkles size={13} />}>
            <div className="space-y-2">
              {bundle.pending_proposals.map((p) => (
                <div
                  key={p.id}
                  style={{
                    padding: '12px 14px', borderRadius: '6px',
                    border: '1px solid var(--color-line)',
                    borderLeft: '3px solid #A16207',
                    background: 'var(--color-surface-2)',
                  }}
                >
                  <div className="flex items-center gap-2 mb-1 flex-wrap">
                    <span
                      className="text-[10px] uppercase font-medium"
                      style={{
                        padding: '2px 7px', borderRadius: '4px',
                        background: '#FEF3C7', color: '#A16207',
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
                          padding: '1px 6px', borderRadius: '3px',
                          background: 'var(--color-surface)',
                          color: 'var(--color-ink-4)',
                          letterSpacing: '0.04em',
                        }}
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                  <div className="text-[12px] mb-2" style={{ color: 'var(--color-ink-2)' }}>
                    {p.signal_headline}
                    {p.signal_entity && (
                      <span className="ml-1" style={{ color: 'var(--color-ink-4)' }}>
                        · {p.signal_entity}
                      </span>
                    )}
                  </div>
                  {owner && (
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => handleConfirmProposal(p.id)}
                        className="text-[11px] inline-flex items-center gap-1 font-medium"
                        style={{
                          padding: '4px 10px', borderRadius: '4px',
                          background: 'var(--color-accent)', color: 'white',
                          border: 'none', cursor: busy ? 'not-allowed' : 'pointer',
                        }}
                      >
                        <Check size={10} />
                        Confirm
                      </button>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => handleDismissProposal(p.id)}
                        className="text-[11px] inline-flex items-center gap-1"
                        style={{
                          padding: '4px 10px', borderRadius: '4px',
                          background: 'transparent', color: 'var(--color-ink-3)',
                          border: '1px solid var(--color-line)',
                          cursor: busy ? 'not-allowed' : 'pointer',
                        }}
                      >
                        <X size={10} />
                        Dismiss
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* Owner status changer */}
        {owner && (
          <Section title="Update status">
            <div className="flex items-center gap-1 flex-wrap">
              {STATUS_OPTIONS.map((s) => {
                const sm = STATUS_META[s];
                const active = s === bundle.status;
                return (
                  <button
                    key={s}
                    type="button"
                    disabled={busy || active}
                    onClick={() => handleStatus(s)}
                    className="text-[11px]"
                    style={{
                      padding: '5px 10px', borderRadius: '4px',
                      background: active ? sm.bg : 'transparent',
                      color: active ? sm.fg : 'var(--color-ink-3)',
                      border: `1px solid ${active ? sm.fg : 'var(--color-line)'}`,
                      cursor: active || busy ? 'default' : 'pointer',
                      opacity: busy ? 0.5 : 1,
                    }}
                  >
                    {sm.label}
                  </button>
                );
              })}
            </div>
          </Section>
        )}

        {/* Discussion */}
        {bundle.war_room && (
          <Section title="Discussion" icon={<MessageSquare size={13} />}>
            <CommentsPanel
              roomId={bundle.war_room.id}
              ownerUserId={bundle.owner_user_id}
            />
          </Section>
        )}
      </div>

      {detecting && (
        <OutcomeDetector
          decision={bundle}
          onClose={() => setDetecting(false)}
          onCaptured={(updated) => {
            setDetecting(false);
            setBundle({ ...bundle, ...updated });
          }}
        />
      )}
    </div>
  );
}

function BackBar({ onBack }: { onBack: () => void }) {
  return (
    <button
      type="button"
      onClick={onBack}
      className="text-[12px] mb-4 inline-flex items-center gap-1"
      style={{
        background: 'transparent', border: 'none', padding: 0,
        color: 'var(--color-ink-4)', cursor: 'pointer',
      }}
    >
      <ArrowLeft size={13} />
      Back to decisions
    </button>
  );
}

function Section({
  title, icon, children,
}: { title: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section>
      <div
        className="text-[10px] uppercase font-medium mb-2 inline-flex items-center gap-1"
        style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em' }}
      >
        {icon}
        {title}
      </div>
      <div
        style={{
          padding: '14px 16px',
          borderRadius: '6px',
          border: '1px solid var(--color-line)',
          background: 'var(--color-surface)',
        }}
      >
        {children}
      </div>
    </section>
  );
}
