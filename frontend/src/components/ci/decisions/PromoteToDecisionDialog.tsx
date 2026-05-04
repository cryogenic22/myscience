import { useState } from 'react';
import { X, Target } from 'lucide-react';
import { decisionsApi, MOVE_TYPE_META, type WarRoomRound, type Decision } from '../../../api';

interface Props {
  round: WarRoomRound;
  onClose: () => void;
  onPromoted: (decision: Decision) => void;
}

export default function PromoteToDecisionDialog({ round, onClose, onPromoted }: Props) {
  const meta = MOVE_TYPE_META[round.move_type];
  const seedTitle = `${meta?.label ?? round.move_type}${
    round.move_payload?.target_drug ? ` — ${String(round.move_payload.target_drug)}` : ''
  }`;

  const [title, setTitle] = useState(seedTitle);
  const [rationale, setRationale] = useState('');
  const [targetMetric, setTargetMetric] = useState('market_share_delta');
  const [targetValue, setTargetValue] = useState('');
  const [deadline, setDeadline] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const d = await decisionsApi.promoteRound(round.id, {
        title: title.trim(),
        rationale: rationale.trim() || undefined,
        target_metric: targetMetric.trim() || undefined,
        target_value: targetValue.trim() || undefined,
        deadline: deadline || undefined,
      });
      onPromoted(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0,0,0,0.4)' }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-line)',
          borderRadius: '8px',
          padding: '24px',
          maxWidth: '520px',
          width: '90%',
          maxHeight: '90vh',
          overflowY: 'auto',
        }}
      >
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <Target size={16} style={{ color: 'var(--color-accent)' }} />
            <h2
              className="font-display text-[18px]"
              style={{ color: 'var(--color-ink)' }}
            >
              Promote to decision
            </h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: 'var(--color-ink-4)' }}
            aria-label="Close"
          >
            <X size={16} />
          </button>
        </div>

        <div
          className="text-[12px] mb-4 p-3"
          style={{
            background: 'var(--color-surface-2)',
            borderRadius: '6px',
            color: 'var(--color-ink-3)',
          }}
        >
          From <strong>Round {round.round_number}</strong> · {meta?.icon}{' '}
          {meta?.label ?? round.move_type}. Snapshot of the move + reaction
          confidence will be frozen into the ledger.
        </div>

        <form onSubmit={handleSubmit} className="space-y-3">
          <Field label="Decision title" required>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={300}
              required
              className="text-[13px] w-full"
              style={inputStyle}
            />
          </Field>

          <Field label="Rationale (optional)">
            <textarea
              value={rationale}
              onChange={(e) => setRationale(e.target.value)}
              rows={3}
              maxLength={4000}
              placeholder="Why we're committing to this — context for the future post-mortem"
              className="text-[13px] w-full"
              style={{ ...inputStyle, resize: 'vertical', minHeight: '64px' }}
            />
          </Field>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Target metric">
              <input
                value={targetMetric}
                onChange={(e) => setTargetMetric(e.target.value)}
                maxLength={200}
                placeholder="market_share_delta"
                className="text-[13px] w-full"
                style={inputStyle}
              />
            </Field>
            <Field label="Target value">
              <input
                value={targetValue}
                onChange={(e) => setTargetValue(e.target.value)}
                maxLength={200}
                placeholder="+3pp"
                className="text-[13px] w-full"
                style={inputStyle}
              />
            </Field>
          </div>

          <Field label="Deadline">
            <input
              type="date"
              value={deadline}
              onChange={(e) => setDeadline(e.target.value)}
              className="text-[13px] w-full"
              style={inputStyle}
            />
          </Field>

          {error && (
            <div className="text-[12px]" style={{ color: '#B91C1C' }}>
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="text-[13px]"
              style={{
                padding: '7px 14px',
                borderRadius: '6px',
                background: 'transparent',
                color: 'var(--color-ink-3)',
                border: '1px solid var(--color-line)',
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={busy || !title.trim()}
              className="text-[13px] font-medium"
              style={{
                padding: '7px 16px',
                borderRadius: '6px',
                background: busy || !title.trim() ? 'var(--color-surface-2)' : 'var(--color-accent)',
                color: busy || !title.trim() ? 'var(--color-ink-4)' : 'white',
                border: 'none',
                cursor: busy || !title.trim() ? 'not-allowed' : 'pointer',
              }}
            >
              {busy ? 'Committing…' : 'Commit decision'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

const inputStyle: React.CSSProperties = {
  padding: '7px 10px',
  borderRadius: '6px',
  border: '1px solid var(--color-line)',
  background: 'var(--color-surface)',
  color: 'var(--color-ink)',
};

function Field({ label, required, children }: {
  label: string; required?: boolean; children: React.ReactNode;
}) {
  return (
    <div>
      <div
        className="text-[10px] uppercase font-medium mb-1"
        style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}
      >
        {label}{required && ' *'}
      </div>
      {children}
    </div>
  );
}
