/**
 * DataHub · F5 — Connect wizard (the differentiator).
 *
 * A guided, four-step onboarding flow for the five automated source kinds
 * (REST / RSS / CSV / web-scrape / warehouse), per `docs/SPEC_DATA_HUB_FRONTEND.md`
 * §5 (Phase B). Manual mapping first:
 *
 *   1. Connector type   — pick the kind + declare identity (key, label, config)
 *   2. Mapping          — declare source-field → entity-field mappings
 *   3. Contract         — trust tier + must-capture fields (BLOCKS without them)
 *   4. Review & register — shows the draft→test→staged→prod lifecycle + registers
 *
 * The "contract gate" is the headline conservation guarantee: every onboarded
 * source must declare a trust tier + at least one must-capture field, or the
 * Register button stays disabled and the wizard surfaces why.
 *
 * Self-contained (owns its step state) but delegates the actual register to the
 * injected `onRegister` (defaults to the D-API-1 stub) so it's testable + the
 * backend swap is one line. Styling: CSS custom properties + inline styles (no
 * Tailwind color utilities, no dynamically-built class names).
 */
import { useMemo, useState } from 'react';
import {
  CONNECTOR_TYPES,
  LIFECYCLE_PATH,
  TRUST_TIERS,
  registerSource,
  validateContract,
  type ConnectorTypeName,
  type FieldMapping,
  type OnboardingDraft,
  type RegisterResult,
  type TrustTier,
} from '../lib/datahubOnboarding';

type StepId = 0 | 1 | 2 | 3;
const STEPS: Array<{ id: StepId; label: string }> = [
  { id: 0, label: 'Connector' },
  { id: 1, label: 'Mapping' },
  { id: 2, label: 'Contract' },
  { id: 3, label: 'Review' },
];

export interface ConnectWizardProps {
  /** Register handler — defaults to the D-API-1 stub. */
  onRegister?: (draft: OnboardingDraft) => Promise<RegisterResult>;
  /** Called after a successful register (e.g. close the wizard / refresh grid). */
  onDone?: (sourceKey: string) => void;
  /** Called when the curator cancels out of the wizard. */
  onCancel?: () => void;
}

function emptyDraft(): OnboardingDraft {
  return {
    source_key: '',
    label: '',
    connector_type: 'API_REST',
    config: {},
    mappings: [{ source_field: '', target_field: '' }],
    contract: { trust_tier: null, must_capture: [''], license: null },
  };
}

// ── Atoms ───────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10.5,
        letterSpacing: '0.16em',
        textTransform: 'uppercase',
        color: 'var(--color-ink-3)',
        marginBottom: 10,
      }}
    >
      {children}
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: '8px 12px',
  border: '1px solid var(--color-line)',
  borderRadius: 8,
  background: 'var(--color-surface)',
  color: 'var(--color-ink)',
  fontFamily: 'var(--font-body)',
  fontSize: 13,
  width: '100%',
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
      <span style={{ fontSize: 12, color: 'var(--color-ink-2)' }}>{label}</span>
      {children}
    </label>
  );
}

// ── Step rail ───────────────────────────────────────────────────────

function StepRail({ current }: { current: StepId }) {
  return (
    <div data-step-rail style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      {STEPS.map((s) => {
        const done = s.id < current;
        const active = s.id === current;
        const tone = active
          ? 'var(--color-accent)'
          : done
            ? 'var(--color-green, #15803d)'
            : 'var(--color-ink-4)';
        return (
          <div
            key={s.id}
            data-step={s.id}
            data-active={active}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '0.06em',
              color: tone,
            }}
          >
            <span
              style={{
                width: 18,
                height: 18,
                borderRadius: '50%',
                display: 'grid',
                placeItems: 'center',
                border: `1px solid ${tone}`,
                fontSize: 10,
                fontWeight: 700,
              }}
            >
              {done ? '✓' : s.id + 1}
            </span>
            {s.label}
          </div>
        );
      })}
    </div>
  );
}

// ── Lifecycle strip ─────────────────────────────────────────────────

function LifecycleStrip({ current }: { current: string }) {
  return (
    <div data-lifecycle-strip style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      {LIFECYCLE_PATH.map((stage, i) => {
        const isCurrent = stage === current;
        const tone = isCurrent ? 'var(--color-accent)' : 'var(--color-ink-4)';
        return (
          <div key={stage} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span
              data-lifecycle-stage={stage}
              data-current={isCurrent}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10.5,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                padding: '3px 9px',
                borderRadius: 6,
                border: `1px solid ${tone}`,
                color: tone,
                fontWeight: isCurrent ? 700 : 500,
              }}
            >
              {stage}
            </span>
            {i < LIFECYCLE_PATH.length - 1 && (
              <span style={{ color: 'var(--color-ink-4)' }}>→</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Wizard ──────────────────────────────────────────────────────────

export function ConnectWizard({ onRegister, onDone, onCancel }: ConnectWizardProps) {
  const register = onRegister ?? registerSource;
  const [step, setStep] = useState<StepId>(0);
  const [draft, setDraft] = useState<OnboardingDraft>(emptyDraft);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<RegisterResult | null>(null);

  const typeDef = useMemo(
    () => CONNECTOR_TYPES.find((t) => t.name === draft.connector_type),
    [draft.connector_type],
  );

  // The contract gate — recomputed live so the Register button + banner reflect it.
  const contractErrors = useMemo(() => validateContract(draft), [draft]);
  const contractComplete = contractErrors.length === 0;

  function patch(p: Partial<OnboardingDraft>) {
    setDraft((d) => ({ ...d, ...p }));
  }
  function patchConfig(key: string, value: string) {
    setDraft((d) => ({ ...d, config: { ...d.config, [key]: value } }));
  }
  function setMapping(i: number, p: Partial<FieldMapping>) {
    setDraft((d) => ({
      ...d,
      mappings: d.mappings.map((m, idx) => (idx === i ? { ...m, ...p } : m)),
    }));
  }
  function addMapping() {
    setDraft((d) => ({ ...d, mappings: [...d.mappings, { source_field: '', target_field: '' }] }));
  }
  function setCapture(i: number, value: string) {
    setDraft((d) => ({
      ...d,
      contract: { ...d.contract, must_capture: d.contract.must_capture.map((c, idx) => (idx === i ? value : c)) },
    }));
  }
  function addCapture() {
    setDraft((d) => ({ ...d, contract: { ...d.contract, must_capture: [...d.contract.must_capture, ''] } }));
  }

  async function handleRegister() {
    setSubmitting(true);
    try {
      const res = await register(draft);
      setResult(res);
      // Only signal completion when the source was actually PERSISTED. A preview
      // (contract validated, nothing written) must not read as "done".
      if (res.ok && res.record && !res.preview) onDone?.(res.record.source_id);
    } catch (e) {
      // Once register() does a real network write, a rejection (network / 500)
      // must surface via the existing error banner — not be swallowed, leaving
      // the button silently re-enabled as if nothing happened.
      setResult({ ok: false, errors: [e instanceof Error ? e.message : String(e)] });
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main
      role="main"
      aria-label="Connect a source"
      data-connect-wizard
      style={{
        padding: '24px 28px 40px',
        background: 'var(--color-bg)',
        color: 'var(--color-ink-2)',
        fontFamily: 'var(--font-body)',
        minHeight: '100%',
        // body is `overflow:hidden` + #root is height:100%, so this <main> must
        // be its OWN scroll container — without these, a step taller than the
        // viewport grows past the clipped body and the lower inputs / submit
        // button are unreachable (no page scroll exists to get to them).
        maxHeight: '100vh',
        overflowY: 'auto',
        display: 'flex',
        flexDirection: 'column',
        gap: 22,
        maxWidth: 760,
      }}
    >
      {/* Header */}
      <header style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: 'var(--color-ink-3)',
          }}
        >
          DataHub · Connect a source
        </div>
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 28,
            fontWeight: 400,
            color: 'var(--color-ink)',
            letterSpacing: '-0.014em',
            margin: 0,
          }}
        >
          Onboard any source
        </h1>
        <StepRail current={step} />
      </header>

      {/* Step body */}
      <section
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-line)',
          borderRadius: 14,
          padding: '20px 22px',
          display: 'flex',
          flexDirection: 'column',
          gap: 18,
        }}
      >
        {step === 0 && (
          <div data-step-body={0} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <SectionLabel>Connector type</SectionLabel>
            <div
              role="radiogroup"
              aria-label="Connector type"
              style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 10 }}
            >
              {CONNECTOR_TYPES.map((t) => {
                const selected = draft.connector_type === t.name;
                return (
                  <button
                    type="button"
                    key={t.name}
                    role="radio"
                    aria-checked={selected}
                    data-connector-option={t.name}
                    onClick={() => patch({ connector_type: t.name as ConnectorTypeName, config: {} })}
                    style={{
                      textAlign: 'left',
                      padding: '12px 14px',
                      borderRadius: 10,
                      cursor: 'pointer',
                      background: selected ? 'var(--color-surface-2)' : 'transparent',
                      border: `1px solid ${selected ? 'var(--color-accent)' : 'var(--color-line)'}`,
                      color: 'var(--color-ink)',
                    }}
                  >
                    <div style={{ fontFamily: 'var(--font-display)', fontSize: 14, fontWeight: 500 }}>{t.label}</div>
                    <div style={{ marginTop: 4, fontSize: 11.5, color: 'var(--color-ink-3)' }}>{t.description}</div>
                  </button>
                );
              })}
            </div>

            <SectionLabel>Identity</SectionLabel>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Field label="Source key">
                <input
                  aria-label="Source key"
                  value={draft.source_key}
                  onChange={(e) => patch({ source_key: e.target.value })}
                  placeholder="ema_chmp_opinions"
                  style={inputStyle}
                />
              </Field>
              <Field label="Display label">
                <input
                  aria-label="Display label"
                  value={draft.label}
                  onChange={(e) => patch({ label: e.target.value })}
                  placeholder="EMA CHMP Opinions"
                  style={inputStyle}
                />
              </Field>
            </div>

            {typeDef && typeDef.configFields.length > 0 && (
              <>
                <SectionLabel>{typeDef.label} config</SectionLabel>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {typeDef.configFields.map((f) => (
                    <Field key={f.key} label={`${f.label}${f.required ? ' *' : ''}`}>
                      <input
                        aria-label={f.label}
                        value={draft.config[f.key] ?? ''}
                        onChange={(e) => patchConfig(f.key, e.target.value)}
                        placeholder={f.placeholder}
                        style={inputStyle}
                      />
                    </Field>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {step === 1 && (
          <div data-step-body={1} style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <SectionLabel>Field mapping · source field → entity field</SectionLabel>
            <p style={{ margin: 0, fontSize: 12.5, color: 'var(--color-ink-3)' }}>
              Map each payload field to the canonical entity field it populates. Leave blank to skip a row.
            </p>
            {draft.mappings.map((m, i) => (
              <div key={i} data-mapping-row={i} style={{ display: 'grid', gridTemplateColumns: '1fr 24px 1fr', gap: 8, alignItems: 'center' }}>
                <input
                  aria-label={`Source field ${i + 1}`}
                  value={m.source_field}
                  onChange={(e) => setMapping(i, { source_field: e.target.value })}
                  placeholder="payload.title"
                  style={inputStyle}
                />
                <span style={{ textAlign: 'center', color: 'var(--color-ink-4)' }}>→</span>
                <input
                  aria-label={`Target field ${i + 1}`}
                  value={m.target_field}
                  onChange={(e) => setMapping(i, { target_field: e.target.value })}
                  placeholder="name"
                  style={inputStyle}
                />
              </div>
            ))}
            <button
              type="button"
              data-action="add-mapping"
              onClick={addMapping}
              style={ghostBtn}
            >
              + Add mapping
            </button>
          </div>
        )}

        {step === 2 && (
          <div data-step-body={2} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <SectionLabel>Trust tier *</SectionLabel>
            <div role="radiogroup" aria-label="Trust tier" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {TRUST_TIERS.map((t) => {
                const selected = draft.contract.trust_tier === t.tier;
                return (
                  <button
                    type="button"
                    key={t.tier}
                    role="radio"
                    aria-checked={selected}
                    data-trust-tier={t.tier}
                    onClick={() => patch({ contract: { ...draft.contract, trust_tier: t.tier as TrustTier } })}
                    style={{
                      textAlign: 'left',
                      padding: '10px 14px',
                      borderRadius: 10,
                      cursor: 'pointer',
                      background: selected ? 'var(--color-surface-2)' : 'transparent',
                      border: `1px solid ${selected ? 'var(--color-accent)' : 'var(--color-line)'}`,
                      color: 'var(--color-ink)',
                    }}
                  >
                    <div style={{ fontSize: 13, fontWeight: 500 }}>{t.label}</div>
                    <div style={{ marginTop: 3, fontSize: 11.5, color: 'var(--color-ink-3)' }}>{t.hint}</div>
                  </button>
                );
              })}
            </div>

            <SectionLabel>Must-capture fields *</SectionLabel>
            <p style={{ margin: 0, fontSize: 12.5, color: 'var(--color-ink-3)' }}>
              A record missing any of these is rejected — no silent loss. Declare at least one.
            </p>
            {draft.contract.must_capture.map((c, i) => (
              <input
                key={i}
                data-must-capture={i}
                aria-label={`Must-capture field ${i + 1}`}
                value={c}
                onChange={(e) => setCapture(i, e.target.value)}
                placeholder="source_doc_id"
                style={inputStyle}
              />
            ))}
            <button type="button" data-action="add-capture" onClick={addCapture} style={ghostBtn}>
              + Add must-capture field
            </button>

            <Field label="License (optional)">
              <input
                aria-label="License"
                value={draft.contract.license ?? ''}
                onChange={(e) => patch({ contract: { ...draft.contract, license: e.target.value || null } })}
                placeholder="CC-BY-4.0 / proprietary / …"
                style={inputStyle}
              />
            </Field>
          </div>
        )}

        {step === 3 && (
          <div data-step-body={3} style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            <SectionLabel>Lifecycle</SectionLabel>
            <LifecycleStrip current="draft" />
            <p style={{ margin: 0, fontSize: 12.5, color: 'var(--color-ink-3)' }}>
              Registering creates this source at <strong>draft</strong>; promote it through test → staged → prod as it proves out.
            </p>

            <SectionLabel>Review</SectionLabel>
            <dl data-review style={{ margin: 0, display: 'grid', gridTemplateColumns: 'auto 1fr', gap: '6px 16px', fontSize: 13 }}>
              <dt style={dtStyle}>Source key</dt><dd style={ddStyle}>{draft.source_key || '—'}</dd>
              <dt style={dtStyle}>Label</dt><dd style={ddStyle}>{draft.label || '—'}</dd>
              <dt style={dtStyle}>Connector</dt><dd style={ddStyle}>{typeDef?.label}</dd>
              <dt style={dtStyle}>Trust tier</dt><dd style={ddStyle}>{draft.contract.trust_tier ?? '— (required)'}</dd>
              <dt style={dtStyle}>Must-capture</dt>
              <dd style={ddStyle}>{draft.contract.must_capture.filter((c) => c.trim()).join(', ') || '— (required)'}</dd>
              <dt style={dtStyle}>Mappings</dt>
              <dd style={ddStyle}>{draft.mappings.filter((m) => m.source_field.trim()).length} declared</dd>
            </dl>

            {!contractComplete && (
              <div
                data-contract-block
                role="alert"
                style={{
                  padding: '12px 14px',
                  borderRadius: 10,
                  border: '1px solid var(--color-red)',
                  color: 'var(--color-red)',
                  fontSize: 12.5,
                  background: 'var(--color-surface-2)',
                }}
              >
                <strong>Contract incomplete — cannot register:</strong>
                <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                  {contractErrors.map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
              </div>
            )}

            {result && result.ok && result.preview && (
              <div
                data-register-preview
                role="status"
                style={{
                  padding: '12px 14px',
                  borderRadius: 10,
                  border: '1px solid var(--color-amber)',
                  color: 'var(--color-amber)',
                  fontSize: 12.5,
                  lineHeight: 1.5,
                }}
              >
                <strong>Preview only — not yet persisted.</strong> The contract for{' '}
                <strong>{result.record?.source_id}</strong> is valid, but the backend
                write-path isn’t wired yet, so nothing was saved. Onboarding will land
                once source-contract storage ships (tracked in COORDINATION §8.1).
              </div>
            )}
            {result && result.ok && !result.preview && (
              <div
                data-register-success
                role="status"
                style={{
                  padding: '12px 14px',
                  borderRadius: 10,
                  border: '1px solid var(--color-green, #15803d)',
                  color: 'var(--color-green, #15803d)',
                  fontSize: 12.5,
                }}
              >
                Registered <strong>{result.record?.source_id}</strong> at lifecycle status{' '}
                <strong>{result.record?.status}</strong>.
              </div>
            )}
            {result && !result.ok && (
              <div data-register-error role="alert" style={{ color: 'var(--color-red)', fontSize: 12.5 }}>
                {result.errors.join(' ')}
              </div>
            )}
          </div>
        )}
      </section>

      {/* Footer nav */}
      <footer style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
        {onCancel && (
          <button type="button" data-action="cancel" onClick={onCancel} style={ghostBtn}>
            Cancel
          </button>
        )}
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 10 }}>
          {step > 0 && (
            <button type="button" data-action="back" onClick={() => setStep((s) => (s - 1) as StepId)} style={ghostBtn}>
              ← Back
            </button>
          )}
          {step < 3 && (
            <button type="button" data-action="next" onClick={() => setStep((s) => (s + 1) as StepId)} style={primaryBtn}>
              Next →
            </button>
          )}
          {step === 3 && (
            <button
              type="button"
              data-action="register"
              disabled={!contractComplete || submitting || (result?.ok ?? false)}
              onClick={handleRegister}
              style={{
                ...primaryBtn,
                opacity: !contractComplete || submitting || result?.ok ? 0.5 : 1,
                cursor: !contractComplete || submitting || result?.ok ? 'not-allowed' : 'pointer',
              }}
            >
              {submitting
                ? 'Validating…'
                : result?.ok
                  ? result.preview
                    ? 'Preview ready'
                    : 'Registered ✓'
                  : 'Register source'}
            </button>
          )}
        </div>
      </footer>
    </main>
  );
}

const ghostBtn: React.CSSProperties = {
  background: 'transparent',
  border: '1px solid var(--color-line)',
  borderRadius: 8,
  color: 'var(--color-ink-3)',
  cursor: 'pointer',
  padding: '8px 14px',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
};

const primaryBtn: React.CSSProperties = {
  background: 'var(--color-accent)',
  border: '1px solid var(--color-accent)',
  borderRadius: 8,
  color: 'var(--color-on-accent, #fff)',
  cursor: 'pointer',
  padding: '8px 16px',
  fontFamily: 'var(--font-mono)',
  fontSize: 12,
  fontWeight: 600,
};

const dtStyle: React.CSSProperties = {
  fontFamily: 'var(--font-mono)',
  fontSize: 11,
  letterSpacing: '0.06em',
  textTransform: 'uppercase',
  color: 'var(--color-ink-3)',
};
const ddStyle: React.CSSProperties = { margin: 0, color: 'var(--color-ink)' };

export default ConnectWizard;
