import { useState } from 'react';
import { Swords } from 'lucide-react';
import { signalsApi, warRoomApi, type Signal } from '../../api';
import ConfidenceBadge from './ConfidenceBadge';
import ImpactBadge from './ImpactBadge';
import EvidenceStack from './EvidenceStack';

interface Props {
  signal: Signal;
  reviewerMode?: boolean;
  onReviewed?: () => void;
  onOpenWarRoom?: (roomId: string) => void;
}

function getRole(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem('mz_auth_role');
}

function hasToken(): boolean {
  if (typeof window === 'undefined') return false;
  return !!window.localStorage.getItem('mz_auth_token');
}

export default function SignalDetail({ signal, reviewerMode = false, onReviewed, onOpenWarRoom }: Props) {
  const role = getRole();
  const isEnterprise = role === 'enterprise';
  const authed = hasToken();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [simulating, setSimulating] = useState(false);

  const simulate = async () => {
    if (!authed || !onOpenWarRoom) return;
    setSimulating(true);
    setError(null);
    try {
      const room = await warRoomApi.create({
        title: `What if: ${signal.headline}`,
        scenario_question: signal.summary || signal.headline,
        primary_entity_type: signal.primary_entity_type ?? undefined,
        primary_entity_id: signal.primary_entity_id ?? undefined,
        primary_entity_name: signal.primary_entity_name ?? undefined,
        source_signal_id: signal.id,
        game_phase: 'launch',
      });
      onOpenWarRoom(room.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSimulating(false);
    }
  };

  const review = async (status: 'reviewed' | 'shipped' | 'retracted') => {
    setBusy(status);
    setError(null);
    try {
      await signalsApi.review(signal.id, status);
      onReviewed?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  };

  const created = signal.created_at ? new Date(signal.created_at).toLocaleString() : '—';
  const reviewed = signal.reviewed_at ? new Date(signal.reviewed_at).toLocaleString() : null;
  const shipped = signal.shipped_at ? new Date(signal.shipped_at).toLocaleString() : null;

  return (
    <div className="flex-1 overflow-y-auto" style={{ padding: '24px 32px' }}>
      {/* Header */}
      <div style={{ marginBottom: '16px' }}>
        <div className="flex items-center gap-2 flex-wrap mb-2">
          <ConfidenceBadge tier={signal.confidence_tier} />
          <ImpactBadge tier={signal.impact_tier} />
          <span
            className="text-[10px] uppercase font-medium"
            style={{
              color: 'var(--color-ink-4)',
              letterSpacing: '0.06em',
              padding: '2px 7px',
              borderRadius: '4px',
              background: 'var(--color-surface-2)',
            }}
          >
            {signal.status}
          </span>
          {onOpenWarRoom && (
            <button
              type="button"
              onClick={simulate}
              disabled={!authed || simulating}
              className="text-[11px] font-medium ml-auto inline-flex items-center gap-1.5"
              style={{
                padding: '5px 12px',
                borderRadius: '6px',
                background: authed ? 'var(--color-accent)' : 'var(--color-surface-2)',
                color: authed ? 'white' : 'var(--color-ink-4)',
                cursor: authed && !simulating ? 'pointer' : 'not-allowed',
                border: 'none',
              }}
              title={authed ? 'Open this signal in a war room — pick a competitive move and model competitor reactions.' : 'Log in to simulate'}
            >
              <Swords size={12} />
              {simulating ? 'Opening…' : 'Simulate in War Room'}
            </button>
          )}
        </div>
        <h1
          className="font-display text-[20px] leading-snug"
          style={{ color: 'var(--color-ink)', letterSpacing: '-0.01em' }}
        >
          {signal.headline}
        </h1>
        <div className="text-[12px] mt-2" style={{ color: 'var(--color-ink-4)' }}>
          {signal.primary_entity_name} · {created}
        </div>
      </div>

      {/* Summary */}
      {signal.summary && (
        <div style={{ marginBottom: '20px' }}>
          <p className="text-[14px] leading-relaxed" style={{ color: 'var(--color-ink-2)' }}>
            {signal.summary}
          </p>
        </div>
      )}

      {/* KBQ tags */}
      {signal.kbq_tags.length > 0 && (
        <Field label="KBQ tags">
          <div className="flex flex-wrap gap-1.5">
            {signal.kbq_tags.map((tag) => (
              <span
                key={tag}
                className="text-[11px]"
                style={{
                  padding: '3px 8px',
                  borderRadius: '4px',
                  background: 'var(--color-surface-2)',
                  color: 'var(--color-ink-3)',
                }}
              >
                {tag}
              </span>
            ))}
          </div>
        </Field>
      )}

      {/* Evidence */}
      <Field label={`Evidence (${signal.evidence_document_ids.length})`}>
        <EvidenceStack signal={signal} />
      </Field>

      {/* Audit */}
      {(reviewed || shipped || signal.superseded_by) && (
        <Field label="Audit">
          <div className="text-[12px] space-y-1" style={{ color: 'var(--color-ink-3)' }}>
            {reviewed && <div>Reviewed: {reviewed}</div>}
            {shipped && <div>Shipped: {shipped}</div>}
            {signal.superseded_by && (
              <div>
                Superseded by{' '}
                <span className="font-mono">{signal.superseded_by.slice(0, 8)}</span>
                {signal.supersedence_reason && ` (${signal.supersedence_reason})`}
              </div>
            )}
          </div>
        </Field>
      )}

      {/* Reviewer actions */}
      {reviewerMode && (
        <div
          style={{
            marginTop: '24px',
            padding: '14px 16px',
            background: 'var(--color-surface-2)',
            borderRadius: '6px',
          }}
        >
          <div
            className="text-[10px] uppercase font-medium mb-3"
            style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em' }}
          >
            Reviewer actions
          </div>
          {!isEnterprise ? (
            <div className="text-[12px]" style={{ color: 'var(--color-ink-3)' }}>
              Read-only — log in as <strong>enterprise</strong> to review signals.
            </div>
          ) : (
            <>
              <div className="flex gap-2">
                <ReviewButton
                  label="Approve & ship"
                  onClick={() => review('shipped')}
                  primary
                  disabled={!!busy}
                  busy={busy === 'shipped'}
                />
                <ReviewButton
                  label="Reviewed only"
                  onClick={() => review('reviewed')}
                  disabled={!!busy}
                  busy={busy === 'reviewed'}
                />
                <ReviewButton
                  label="Retract"
                  onClick={() => review('retracted')}
                  danger
                  disabled={!!busy}
                  busy={busy === 'retracted'}
                />
              </div>
              {error && (
                <div className="text-[12px] mt-2" style={{ color: '#B91C1C' }}>
                  {error}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: '20px' }}>
      <div
        className="text-[10px] uppercase tracking-wider"
        style={{
          color: 'var(--color-ink-4)',
          marginBottom: '8px',
          letterSpacing: '0.06em',
          fontWeight: 500,
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}

function ReviewButton({
  label, onClick, primary, danger, disabled, busy,
}: {
  label: string;
  onClick: () => void;
  primary?: boolean;
  danger?: boolean;
  disabled?: boolean;
  busy?: boolean;
}) {
  const bg = danger ? '#FEE2E2' : primary ? 'var(--color-accent)' : 'var(--color-surface)';
  const fg = danger ? '#B91C1C' : primary ? 'white' : 'var(--color-ink)';
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="text-[12px] font-medium"
      style={{
        padding: '6px 14px',
        borderRadius: '6px',
        background: bg,
        color: fg,
        border: primary ? 'none' : '1px solid var(--color-line)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled && !busy ? 0.6 : 1,
      }}
    >
      {busy ? '…' : label}
    </button>
  );
}
