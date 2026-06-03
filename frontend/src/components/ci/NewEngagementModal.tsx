/**
 * NewEngagementModal — scope a CI workshop.
 *
 * Loop B2 created the minimal version. This revision (per design review):
 *   - Sleeker, airier layout; no boxy <select> — situation is a segmented
 *     control. Borderless, tone-shifted inputs (no "constrained" outlines).
 *   - "Brief the agents" section: free-text strategic context + key
 *     questions. These flow into `scope` (scope.context, scope.key_questions)
 *     so the downstream agents (brief generation, dossier, synthesis) have
 *     the human's framing to work from — not just an asset slug.
 *
 * Validation lives at the door (same chokepoint as the backend's Pydantic
 * body model): name + asset required. Context is optional but encouraged.
 *
 * Submit → POST /engagements → caller receives the new engagement for
 * navigation.
 */
import { useEffect, useState } from 'react';
import { engagementsApi, type EngagementDTO } from '../../api';

interface Props {
  open: boolean;
  onClose: () => void;
  onCreated: (engagement: EngagementDTO) => void;
  /** PB-IX01 — seed the form when promoting from a signal. */
  initialAsset?: string;
  initialName?: string;
  initialContext?: string;
}

type Situation = 'launch' | 'defense' | 'lcm';

const SITUATIONS: { value: Situation; label: string; blurb: string }[] = [
  { value: 'launch', label: 'Launch', blurb: 'Bringing a new asset to market' },
  { value: 'defense', label: 'Defense', blurb: 'Protecting an existing position' },
  { value: 'lcm', label: 'LCM', blurb: 'Life-cycle management of a mature asset' },
];

export default function NewEngagementModal({
  open, onClose, onCreated, initialAsset, initialName, initialContext,
}: Props) {
  const [name, setName] = useState('');
  const [asset, setAsset] = useState('');
  const [situation, setSituation] = useState<Situation>('launch');
  const [context, setContext] = useState('');
  const [questions, setQuestions] = useState('');
  const [sponsor, setSponsor] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // PB-IX01 — when promoting a signal, the modal opens pre-filled. Seed on
  // each open transition so a fresh promote always reflects the latest signal.
  useEffect(() => {
    if (!open) return;
    if (initialAsset) setAsset(initialAsset);
    if (initialName) setName(initialName);
    if (initialContext) setContext(initialContext);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  if (!open) return null;

  const valid = name.trim().length > 0 && asset.trim().length > 0;

  const reset = () => {
    setName(''); setAsset(''); setSituation('launch');
    setContext(''); setQuestions(''); setSponsor('');
  };

  const submit = async () => {
    setError(null);
    if (!valid) {
      setError('Name and asset are required.');
      return;
    }
    setSubmitting(true);
    try {
      // Pack the human's framing into scope so agents inherit it. Only
      // include keys the user actually filled — an empty scope stays {}.
      const keyQuestions = questions
        .split('\n')
        .map((q) => q.trim())
        .filter(Boolean);
      const scope: Record<string, unknown> = {};
      if (context.trim()) scope.context = context.trim();
      if (keyQuestions.length) scope.key_questions = keyQuestions;

      const body: {
        name: string; asset: string; situation: Situation;
        sponsor?: string; scope?: Record<string, unknown>;
      } = {
        name: name.trim(),
        asset: asset.trim(),
        situation,
        sponsor: sponsor.trim() || undefined,
      };
      if (Object.keys(scope).length) body.scope = scope;

      const created = await engagementsApi.create(body);
      onCreated(created);
      reset();
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
        background: 'rgba(0,0,0,0.40)',
        backdropFilter: 'blur(2px)',
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
          width: '100%', maxWidth: 580,
          maxHeight: '88vh', overflowY: 'auto',
          padding: 'var(--space-7, 40px)',
        }}
      >
        <h2
          style={{
            margin: 0,
            fontFamily: 'var(--font-display)',
            fontSize: 28, fontWeight: 500, letterSpacing: '-0.01em',
            marginBottom: 'var(--space-2)',
          }}
        >
          New engagement
        </h2>
        <p
          style={{
            margin: 0,
            color: 'var(--color-ink-3)',
            fontSize: 14, lineHeight: 1.5,
            marginBottom: 'var(--space-6)',
          }}
        >
          Scope a structured CI workshop. The framing you give here becomes
          the brief the agents work from.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-5)' }}>
          <Field label="Name">
            <input
              data-testid="ne-name"
              type="text" value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Wegovy MASH defense"
              style={inputStyle}
              autoFocus
            />
          </Field>

          <Field label="Focal asset" hint="drug:wegovy · company:novo-nordisk · mechanism:glp-1">
            <input
              data-testid="ne-asset"
              type="text" value={asset}
              onChange={(e) => setAsset(e.target.value)}
              placeholder="drug:wegovy"
              style={inputStyle}
            />
          </Field>

          <Field label="Situation">
            {/* Segmented control — sleeker than a <select>, no dropdown chrome. */}
            <div
              data-testid="ne-situation"
              role="radiogroup"
              aria-label="Situation"
              style={{
                display: 'flex', gap: 4, padding: 4,
                background: 'var(--color-surface-2)',
                borderRadius: 'var(--radius-pill)',
              }}
            >
              {SITUATIONS.map((s) => {
                const active = s.value === situation;
                return (
                  <button
                    key={s.value}
                    type="button"
                    role="radio"
                    aria-checked={active}
                    data-testid={`ne-situation-${s.value}`}
                    onClick={() => setSituation(s.value)}
                    style={{
                      flex: 1,
                      padding: '8px 10px',
                      fontSize: 13, fontWeight: 500,
                      fontFamily: 'inherit',
                      border: 'none',
                      borderRadius: 'var(--radius-pill)',
                      cursor: 'pointer',
                      transitionDuration: '160ms',
                      background: active ? 'var(--color-ink)' : 'transparent',
                      color: active ? 'var(--color-bg)' : 'var(--color-ink-3)',
                    }}
                  >
                    {s.label}
                  </button>
                );
              })}
            </div>
            <span style={{ fontSize: 12, color: 'var(--color-ink-4)', marginTop: 6 }}>
              {SITUATIONS.find((s) => s.value === situation)?.blurb}
            </span>
          </Field>

          {/* ── Brief the agents ── */}
          <div
            style={{
              background: 'var(--color-surface-2)',
              borderRadius: 'var(--radius-panel)',
              padding: 'var(--space-5)',
              display: 'flex', flexDirection: 'column', gap: 'var(--space-4)',
            }}
          >
            <div>
              <div style={{
                fontFamily: 'var(--font-mono)', fontSize: 11,
                letterSpacing: '0.08em', textTransform: 'uppercase',
                color: 'var(--color-accent)', marginBottom: 4,
              }}>
                Brief the agents
              </div>
              <div style={{ fontSize: 12.5, color: 'var(--color-ink-4)', lineHeight: 1.5 }}>
                Optional, but this is what the agents read first. The more
                context, the sharper the dossier and scenarios.
              </div>
            </div>

            <Field label="Strategic context">
              <textarea
                data-testid="ne-context"
                value={context}
                onChange={(e) => setContext(e.target.value)}
                placeholder="What's the situation? What decision does this inform, and what's at stake? Who are the key competitors and what are they likely to do?"
                rows={4}
                style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.5, background: 'var(--color-surface)' }}
              />
            </Field>

            <Field label="Key questions" hint="one per line — the questions the workshop must answer">
              <textarea
                data-testid="ne-questions"
                value={questions}
                onChange={(e) => setQuestions(e.target.value)}
                placeholder={'Will the competitor file for the MASH indication first?\nWhat is our defensible pricing floor?'}
                rows={3}
                style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.5, background: 'var(--color-surface)' }}
              />
            </Field>
          </div>

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
            style={{ ...ctaBase, background: 'var(--color-surface-2)', color: 'var(--color-ink)' }}
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
  padding: '11px 14px',
  fontSize: 15,
  fontFamily: 'inherit',
  background: 'var(--color-surface-2)',
  color: 'var(--color-ink)',
  borderRadius: 'var(--radius-input)',
  border: 'none',
  outline: 'none',
};

const ctaBase: React.CSSProperties = {
  padding: '11px 20px',
  fontSize: 14, fontWeight: 500,
  borderRadius: 'var(--radius-pill)',
  border: 'none',
  cursor: 'pointer',
  transitionDuration: '180ms',
};
