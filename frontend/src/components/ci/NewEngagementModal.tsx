/**
 * Loop B2 — NewEngagementModal.
 *
 * Minimal modal for creating an engagement via the Loop A API. Fields:
 *   - name (required, 1–300 chars)
 *   - asset (required — drug:slug or company:slug etc.)
 *   - situation (required — launch / defense / lcm)
 *   - sponsor (optional)
 *
 * Submit → POST /engagements → caller receives the new engagement id
 * for navigation. Validation lives at the door (same chokepoint as the
 * backend's Pydantic body model).
 */
import { useState } from 'react';
import { engagementsApi, type EngagementDTO } from '../../api';

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (engagement: EngagementDTO) => void;
}

const SITUATIONS = [
  { value: 'launch', label: 'Launch — bringing a new asset to market' },
  { value: 'defense', label: 'Defense — protecting an existing position' },
  { value: 'lcm', label: 'LCM — life-cycle management of a mature asset' },
] as const;

export default function NewEngagementModal({ open, onClose, onCreated }: Props) {
  const [name, setName] = useState('');
  const [asset, setAsset] = useState('');
  const [situation, setSituation] = useState<'launch' | 'defense' | 'lcm'>('launch');
  const [sponsor, setSponsor] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!open) return null;

  const valid =
    name.trim().length > 0 &&
    asset.trim().length > 0;

  const submit = async () => {
    setError(null);
    if (!valid) {
      setError('Name and asset are required.');
      return;
    }
    setSubmitting(true);
    try {
      const created = await engagementsApi.create({
        name: name.trim(),
        asset: asset.trim(),
        situation,
        sponsor: sponsor.trim() || undefined,
      });
      onCreated(created);
      // Reset for next open.
      setName(''); setAsset(''); setSituation('launch'); setSponsor('');
    } catch (e: any) {
      setError(String(e?.message ?? e));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      data-testid="new-engagement-modal"
      role="dialog"
      aria-modal="true"
      style={{
        position: 'fixed', inset: 0, zIndex: 50,
        background: 'rgba(0,0,0,0.32)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 'var(--space-4)',
      }}
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
    >
      <div
        style={{
          background: 'var(--color-surface)',
          color: 'var(--color-ink)',
          borderRadius: 'var(--radius-panel)',
          boxShadow: 'var(--shadow-lg)',
          width: '100%', maxWidth: 520,
          padding: 'var(--space-6)',
        }}
      >
        <h2
          style={{
            margin: 0,
            fontFamily: 'var(--font-display)',
            fontSize: 24, fontWeight: 500,
            marginBottom: 'var(--space-2)',
          }}
        >
          New engagement
        </h2>
        <p
          style={{
            margin: 0,
            color: 'var(--color-ink-3)',
            fontSize: 14,
            marginBottom: 'var(--space-5)',
          }}
        >
          Scope a structured CI workshop. You can add the brief, sources,
          and scenarios after creation.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <Field label="Name">
            <input
              data-testid="ne-name"
              type="text" value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Wegovy MASH defense"
              style={inputStyle}
            />
          </Field>
          <Field label="Focal asset" hint="e.g. drug:wegovy or company:novo-nordisk">
            <input
              data-testid="ne-asset"
              type="text" value={asset}
              onChange={(e) => setAsset(e.target.value)}
              placeholder="drug:wegovy"
              style={inputStyle}
            />
          </Field>
          <Field label="Situation">
            <select
              data-testid="ne-situation"
              value={situation}
              onChange={(e) => setSituation(e.target.value as any)}
              style={inputStyle}
            >
              {SITUATIONS.map((s) => (
                <option key={s.value} value={s.value}>{s.label}</option>
              ))}
            </select>
          </Field>
          <Field label="Sponsor" hint="optional — the executive whose decision this informs">
            <input
              data-testid="ne-sponsor"
              type="text" value={sponsor}
              onChange={(e) => setSponsor(e.target.value)}
              placeholder="e.g. Maria Chen, CMO"
              style={inputStyle}
            />
          </Field>
        </div>

        {error && (
          <p
            data-testid="ne-error"
            style={{
              marginTop: 'var(--space-4)',
              color: 'var(--color-red)',
              fontSize: 13,
              fontFamily: 'var(--font-mono)',
            }}
          >
            {error}
          </p>
        )}

        <div
          style={{
            marginTop: 'var(--space-6)',
            display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-3)',
          }}
        >
          <button
            type="button" onClick={onClose}
            style={{
              ...ctaBase,
              background: 'var(--color-surface-2)',
              color: 'var(--color-ink)',
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            data-testid="ne-submit"
            onClick={submit}
            disabled={!valid || submitting}
            style={{
              ...ctaBase,
              background: 'var(--color-ink)',
              color: 'var(--color-bg)',
              opacity: !valid || submitting ? 0.6 : 1,
              cursor: !valid || submitting ? 'not-allowed' : 'pointer',
            }}
          >
            {submitting ? 'Creating…' : 'Create engagement'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({
  label, hint, children,
}: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 11, letterSpacing: '0.06em',
        textTransform: 'uppercase',
        color: 'var(--color-ink-3)',
      }}>
        {label}
      </span>
      {children}
      {hint && (
        <span style={{ fontSize: 12, color: 'var(--color-ink-4)' }}>
          {hint}
        </span>
      )}
    </label>
  );
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: '10px 14px',
  fontSize: 15,
  fontFamily: 'inherit',
  background: 'var(--color-surface-2)',
  color: 'var(--color-ink)',
  borderRadius: 'var(--radius-input)',
  border: 'none',
  outline: 'none',
};

const ctaBase: React.CSSProperties = {
  padding: '10px 18px',
  fontSize: 14, fontWeight: 500,
  borderRadius: 'var(--radius-pill)',
  border: 'none',
  cursor: 'pointer',
  transitionDuration: '180ms',
};
