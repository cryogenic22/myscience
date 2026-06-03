import { useState } from 'react';
import { Swords, BookOpen, Briefcase } from 'lucide-react';
import { signalsApi, warRoomApi, type Signal } from '../../api';
import ConfidenceBadge from './ConfidenceBadge';
import ImpactBadge from './ImpactBadge';
import FactClassGlyph from './FactClassGlyph';
import type { FactClass } from '../../lib/helix';
import EvidenceStack from './EvidenceStack';
import MaterialityDrawer from './MaterialityDrawer';
import { useEvidenceDocuments } from '../../hooks/useEvidenceDocuments';
import { useFrameSignal } from '../../hooks/useFrameSignal';

function sumContributions(
  factors: Signal['materiality_factors'] | undefined | null,
): number | null {
  if (!factors) return null;
  const total =
    (factors.source_tier?.contribution ?? 0) +
    (factors.entity_criticality?.contribution ?? 0) +
    (factors.claim_type?.contribution ?? 0) +
    (factors.recency?.contribution ?? 0);
  return Math.round(total * 10) / 10;
}

interface Props {
  signal: Signal;
  reviewerMode?: boolean;
  onReviewed?: () => void;
  onOpenWarRoom?: (roomId: string, signalKbq?: string) => void;
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
  const [materialityOpen, setMaterialityOpen] = useState(false);
  const materialityScore = sumContributions(signal.materiality_factors);
  const { frame, framingId } = useFrameSignal();
  const isFraming = framingId === signal.id;

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
      // Pass the first KBQ tag so WarRoomView can pre-suggest a move type
      onOpenWarRoom(room.id, signal.kbq_tags?.[0]);
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

  // PB-IX01 — promote bridge: seed downstream work from this signal. War-room
  // (Simulate) + Decision (Frame) already exist above; these complete the set
  // with a standalone dossier and a full engagement, URL-driven like the
  // existing "View dossier" link so no extra prop threading is needed.
  const entityRef =
    signal.primary_entity_type && signal.primary_entity_id && signal.primary_entity_id !== 'market'
      ? `${signal.primary_entity_type}:${signal.primary_entity_id}`
      : null;
  const seedName = signal.primary_entity_name
    ? `${signal.primary_entity_name} — signal response`
    : signal.headline.slice(0, 80);
  const seedContext = signal.summary || signal.headline;
  const dossierHref = entityRef
    ? `/ci?tab=dossier&asset=${encodeURIComponent(entityRef)}`
    : null;
  const engagementHref = entityRef
    ? `/ci?tab=engagements&new=1&asset=${encodeURIComponent(entityRef)}` +
      `&seedName=${encodeURIComponent(seedName)}&seedContext=${encodeURIComponent(seedContext)}`
    : null;

  const created = signal.created_at ? new Date(signal.created_at).toLocaleString() : '—';
  const reviewed = signal.reviewed_at ? new Date(signal.reviewed_at).toLocaleString() : null;
  const shipped = signal.shipped_at ? new Date(signal.shipped_at).toLocaleString() : null;

  return (
    <div className="flex-1 overflow-y-auto" style={{ padding: '24px 32px' }}>
      {/* Header */}
      <div style={{ marginBottom: '16px' }}>
        <div className="flex items-center gap-2 flex-wrap mb-2">
          <FactClassGlyph
            confidence_tier={signal.confidence_tier}
            source_id={signal.evidence_document_ids?.[0]}
            size={16}
            withLabel
          />
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
          {materialityScore != null && (
            <button
              type="button"
              data-materiality-trigger
              onClick={() => setMaterialityOpen(true)}
              className="text-[10px] uppercase font-medium"
              style={{
                color: 'var(--color-ink)',
                letterSpacing: '0.06em',
                padding: '2px 8px',
                borderRadius: '4px',
                background: 'transparent',
                border: '1px solid var(--color-line)',
                cursor: 'pointer',
              }}
              title="Show materiality breakdown"
            >
              Materiality {materialityScore.toFixed(0)}
              <span style={{ marginLeft: '4px', color: 'var(--color-ink-4)' }}>
                ›
              </span>
            </button>
          )}
          <button
            type="button"
            onClick={() => frame(signal)}
            disabled={!authed || isFraming}
            className="text-[11px] font-medium ml-auto inline-flex items-center gap-1.5"
            style={{
              padding: '5px 12px', borderRadius: '6px',
              background: authed ? 'var(--color-accent)' : 'var(--color-surface-2)',
              color: authed ? 'white' : 'var(--color-ink-4)',
              cursor: authed && !isFraming ? 'pointer' : 'not-allowed', border: 'none',
            }}
            title={authed ? 'Frame this signal as a decision — creates a Decision Brief and opens the workspace.' : 'Log in to frame'}
          >
            {isFraming ? 'Framing…' : 'Frame as Decision'}
          </button>
          {onOpenWarRoom && (
            <button
              type="button"
              onClick={simulate}
              disabled={!authed || simulating}
              className="text-[11px] font-medium inline-flex items-center gap-1.5"
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
        {signal.primary_entity_id && signal.primary_entity_id !== 'market' && signal.primary_entity_type && (
          <a
            href={`/ci/dossier/${signal.primary_entity_type}/${signal.primary_entity_id}`}
            className="text-[12px] mt-1 inline-block"
            style={{ color: 'var(--color-accent)', textDecoration: 'none' }}
          >
            View {signal.primary_entity_name || 'entity'} dossier →
          </a>
        )}

        {/* PB-IX01 — promote bridge: seed a dossier or an engagement from this signal. */}
        {entityRef && (
          <div data-testid="signal-promote" className="flex items-center gap-2 flex-wrap mt-3">
            <span
              className="text-[10px] uppercase font-medium"
              style={{ color: 'var(--color-ink-4)', letterSpacing: '0.08em' }}
            >
              Promote
            </span>
            <a
              data-testid="promote-dossier"
              href={dossierHref!}
              className="text-[11px] font-medium inline-flex items-center gap-1.5"
              style={{
                padding: '5px 12px', borderRadius: '6px', textDecoration: 'none',
                border: '1px solid var(--color-line)', color: 'var(--color-ink)',
              }}
              title="Build a standalone 8-domain dossier for this asset, seeded from the signal."
            >
              <BookOpen size={12} /> Build dossier
            </a>
            <a
              data-testid="promote-engagement"
              href={engagementHref!}
              className="text-[11px] font-medium inline-flex items-center gap-1.5"
              style={{
                padding: '5px 12px', borderRadius: '6px', textDecoration: 'none',
                border: '1px solid var(--color-line)', color: 'var(--color-ink)',
              }}
              title="Start a full CI engagement on this asset, pre-briefed with the signal."
            >
              <Briefcase size={12} /> Start engagement
            </a>
          </div>
        )}
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
      <EvidenceField signal={signal} />

      {/* PB-SL05 — facts this signal feeds (forward provenance) */}
      {signal.linked_facts && signal.linked_facts.length > 0 && (
        <Field label={`Feeds ${signal.linked_facts.length} fact${signal.linked_facts.length === 1 ? '' : 's'}`}>
          <div className="space-y-2">
            {signal.linked_facts.map((f) => (
              <div
                key={f.fact_id}
                className="flex items-start gap-2"
                style={{
                  padding: '8px 10px', borderRadius: '8px',
                  background: 'var(--color-surface-2)',
                  border: '1px solid var(--color-line)',
                }}
              >
                <FactClassGlyph factClass={(f.fact_class ?? 'signal') as FactClass} size={15} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="text-[12.5px]" style={{ color: 'var(--color-ink)', lineHeight: 1.4 }}>
                    {f.claim ?? f.predicate}
                  </div>
                  <div className="text-[10px] mt-1" style={{ fontFamily: 'var(--font-mono)', color: 'var(--color-ink-4)' }}>
                    {f.predicate} · {f.role}
                    {f.source_id && <> · {f.source_id}</>}
                    {f.source_url && (
                      <>
                        {' · '}
                        <a href={f.source_url} target="_blank" rel="noreferrer"
                           style={{ color: 'var(--color-accent)' }}>source ↗</a>
                      </>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </Field>
      )}

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
      <MaterialityDrawer
        open={materialityOpen}
        factors={signal.materiality_factors ?? null}
        score={materialityScore}
        onClose={() => setMaterialityOpen(false)}
      />
    </div>
  );
}

function EvidenceField({ signal }: { signal: Signal }) {
  const { documents, loading } = useEvidenceDocuments(signal.evidence_document_ids);
  const count = signal.evidence_document_ids.length;
  const label = loading
    ? `Evidence (${count}, loading…)`
    : `Evidence (${count})`;
  return (
    <Field label={label}>
      <EvidenceStack signal={signal} documents={documents} />
    </Field>
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
