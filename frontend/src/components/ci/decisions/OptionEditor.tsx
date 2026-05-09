import { useState, useEffect } from 'react';
import type { DecisionBriefOptionInput } from '../../../api';

/**
 * SPEC_030 — Modal-style editor for adding / editing a brief option.
 * Validates label is non-empty before save.
 */

type Mode = 'create' | 'edit';

interface Props {
  mode: Mode;
  initial?: DecisionBriefOptionInput;
  onSave: (opt: DecisionBriefOptionInput) => void | Promise<void>;
  onClose: () => void;
  onRemove?: () => void | Promise<void>;
}

const EMPTY: DecisionBriefOptionInput = {
  label: '',
  description: null,
  predicted_outcome: null,
  cost_estimate: null,
  risk_notes: null,
};

export default function OptionEditor({
  mode,
  initial,
  onSave,
  onClose,
  onRemove,
}: Props) {
  const [label, setLabel] = useState(initial?.label ?? '');
  const [description, setDescription] = useState(initial?.description ?? '');
  const [predictedOutcome, setPredictedOutcome] = useState(initial?.predicted_outcome ?? '');
  const [costEstimate, setCostEstimate] = useState(initial?.cost_estimate ?? '');
  const [riskNotes, setRiskNotes] = useState(initial?.risk_notes ?? '');
  const [busy, setBusy] = useState(false);
  // Stage 6 fix #7 — surface save errors. The previous version used a
  // try/finally that swallowed rejection silently; users could only tell
  // by noticing the modal stayed open. Now we render the error inline
  // and keep the modal open so they can retry.
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const canSave = label.trim().length > 0 && !busy;

  const submit = async () => {
    if (!canSave) return;
    setBusy(true);
    setError(null);
    try {
      const payload: DecisionBriefOptionInput = {
        label: label.trim(),
        description: description.trim() || null,
        predicted_outcome: predictedOutcome.trim() || null,
        cost_estimate: costEstimate.trim() || null,
        risk_notes: riskNotes.trim() || null,
      };
      await onSave(payload);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const inputStyle = {
    width: '100%',
    background: 'var(--color-surface-2)',
    border: '1px solid var(--color-line)',
    borderRadius: 'var(--radius-input, 12px)',
    padding: '10px 14px',
    fontSize: '14px',
    color: 'var(--color-ink)',
    fontFamily: 'inherit',
    outline: 'none',
  };

  return (
    <div
      role="dialog"
      aria-label={mode === 'create' ? 'New option' : 'Edit option'}
      aria-modal="true"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        zIndex: 100,
      }}
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        style={{
          background: 'var(--color-surface)',
          borderRadius: 'var(--radius-card, 16px)',
          padding: 'var(--space-panel-pad, 24px)',
          maxWidth: 560,
          width: '100%',
          boxShadow: 'var(--shadow-lg)',
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-panel-gap, 16px)',
        }}
      >
        <h2
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 22,
            fontWeight: 700,
            margin: 0,
            color: 'var(--color-ink)',
          }}
        >
          {mode === 'create' ? 'New option' : 'Edit option'}
        </h2>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-ink-3)' }}>
            Label
          </span>
          <input
            aria-label="label"
            type="text"
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Accelerate Phase III readout"
            style={inputStyle}
            autoFocus
          />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-ink-3)' }}>
            Description
          </span>
          <textarea
            aria-label="description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Pull readout window forward by 8 weeks"
            rows={3}
            style={inputStyle}
          />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-ink-3)' }}>
            Predicted outcome
          </span>
          <input
            aria-label="predicted outcome"
            type="text"
            value={predictedOutcome}
            onChange={(e) => setPredictedOutcome(e.target.value)}
            placeholder="Expect 8–12% share gain over 18 months"
            style={inputStyle}
          />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-ink-3)' }}>
            Cost estimate
          </span>
          <input
            aria-label="cost estimate"
            type="text"
            value={costEstimate}
            onChange={(e) => setCostEstimate(e.target.value)}
            placeholder="$5M incremental, 4-month delay"
            style={inputStyle}
          />
        </label>

        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-ink-3)' }}>
            Risk notes
          </span>
          <textarea
            aria-label="risk notes"
            value={riskNotes}
            onChange={(e) => setRiskNotes(e.target.value)}
            placeholder="Lower data quality if final dataset thin"
            rows={2}
            style={inputStyle}
          />
        </label>

        {error && (
          <div
            role="alert"
            style={{
              fontSize: 12,
              color: 'var(--color-red, #C0392B)',
              background: 'var(--color-red-soft, #FEF2F2)',
              padding: '8px 12px',
              borderRadius: 'var(--radius-card, 12px)',
            }}
          >
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
          {mode === 'edit' && onRemove && (
            <button
              type="button"
              onClick={() => void onRemove()}
              className="btn btn-ghost"
              style={{ marginRight: 'auto', color: 'var(--color-red, #C0392B)' }}
            >
              Remove
            </button>
          )}
          <button type="button" onClick={onClose} className="btn btn-secondary">
            Cancel
          </button>
          <button
            type="button"
            disabled={!canSave}
            onClick={() => void submit()}
            className="btn btn-accent"
            aria-disabled={!canSave}
          >
            {busy ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </div>
  );
}
