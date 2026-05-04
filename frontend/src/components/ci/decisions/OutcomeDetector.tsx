import { useState } from 'react';
import { X, Search, CheckCircle2, XCircle, MinusCircle } from 'lucide-react';
import { decisionsApi, type Decision, type OutcomeCandidate } from '../../../api';

interface Props {
  decision: Decision;
  onClose: () => void;
  onCaptured: (updated: Decision) => void;
}

type Verdict = 'verified' | 'missed' | 'cancelled';

const VERDICTS: { key: Verdict; label: string; color: string; icon: React.ReactNode }[] = [
  { key: 'verified',  label: 'Verified — prediction was right',          color: '#15803D', icon: <CheckCircle2 size={13} /> },
  { key: 'missed',    label: 'Missed — prediction was wrong',            color: '#B91C1C', icon: <XCircle size={13} /> },
  { key: 'cancelled', label: 'Cancelled — decision no longer applies',   color: 'var(--color-ink-4)', icon: <MinusCircle size={13} /> },
];

export default function OutcomeDetector({ decision, onClose, onCaptured }: Props) {
  const [phase, setPhase] = useState<'detecting' | 'picked' | 'capturing'>('detecting');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [candidates, setCandidates] = useState<OutcomeCandidate[] | null>(null);
  const [picked, setPicked] = useState<OutcomeCandidate | null>(null);
  const [verdict, setVerdict] = useState<Verdict>('verified');
  const [actualOutcome, setActualOutcome] = useState('');
  const [notes, setNotes] = useState('');

  const runDetect = async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await decisionsApi.suggestOutcome(decision.id);
      setCandidates(r.candidates);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  const pickCandidate = (c: OutcomeCandidate) => {
    setPicked(c);
    setActualOutcome(c.headline); // pre-fill
    setPhase('picked');
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!picked || !actualOutcome.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const updated = await decisionsApi.captureOutcome(decision.id, {
        signal_id: picked.signal_id,
        verdict,
        actual_outcome: actualOutcome.trim(),
        notes: notes.trim() || undefined,
      });
      onCaptured(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setLoading(false);
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
          maxWidth: '640px',
          width: '92%',
          maxHeight: '90vh',
          overflowY: 'auto',
        }}
      >
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-2">
            <Search size={16} style={{ color: 'var(--color-accent)' }} />
            <h2 className="font-display text-[18px]" style={{ color: 'var(--color-ink)' }}>
              {phase === 'picked' ? 'Capture outcome' : 'Detect outcome'}
            </h2>
            <span
              className="text-[10px] uppercase font-medium"
              style={{
                padding: '1px 7px', borderRadius: '4px',
                background: 'var(--color-accent)', color: 'white',
                letterSpacing: '0.05em',
              }}
              title="Phase D MVP — system suggests, you decide. Still AI-informed."
            >
              D
            </span>
          </div>
          <button
            type="button" onClick={onClose}
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
          <strong>{decision.title}</strong>
          {typeof decision.confidence_at_commit === 'number' && (
            <span> · committed at {(decision.confidence_at_commit * 100).toFixed(0)}% confidence</span>
          )}
        </div>

        {phase === 'detecting' && (
          <>
            {!candidates && !loading && (
              <div className="text-center py-6">
                <div
                  className="text-[12px] mb-4"
                  style={{ color: 'var(--color-ink-3)' }}
                >
                  Search recent signals for an outcome that matches this decision.
                  Matcher scores on entity overlap, KBQ overlap, and temporal
                  proximity to the deadline window.
                </div>
                <button
                  type="button"
                  onClick={runDetect}
                  className="text-[13px] font-medium"
                  style={{
                    padding: '8px 18px', borderRadius: '6px',
                    background: 'var(--color-accent)', color: 'white',
                    border: 'none', cursor: 'pointer',
                  }}
                >
                  Run detection
                </button>
              </div>
            )}

            {loading && (
              <div
                className="text-[12px] text-center py-6"
                style={{ color: 'var(--color-ink-4)' }}
              >
                Scanning signals…
              </div>
            )}

            {error && (
              <div className="text-[12px] mb-3" style={{ color: '#B91C1C' }}>
                {error}
              </div>
            )}

            {candidates && candidates.length === 0 && !loading && (
              <div
                className="text-[12px] py-4 text-center"
                style={{ color: 'var(--color-ink-4)', fontStyle: 'italic' }}
              >
                No matching signals found above the 0.4 threshold. Honest
                fallback — try again later as more signals land, or capture
                outcome manually.
              </div>
            )}

            {candidates && candidates.length > 0 && (
              <div className="space-y-2">
                <div
                  className="text-[10px] uppercase mb-1"
                  style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}
                >
                  {candidates.length} candidate{candidates.length === 1 ? '' : 's'} ranked by match score
                </div>
                {candidates.map((c) => (
                  <CandidateCard key={c.signal_id} candidate={c} onPick={() => pickCandidate(c)} />
                ))}
              </div>
            )}
          </>
        )}

        {phase === 'picked' && picked && (
          <form onSubmit={submit} className="space-y-3">
            <div
              className="text-[11px] p-3"
              style={{
                background: 'var(--color-surface-2)',
                borderRadius: '6px',
                color: 'var(--color-ink-3)',
              }}
            >
              <div
                className="text-[10px] uppercase font-medium mb-1"
                style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}
              >
                Selected signal · match {(picked.match_score * 100).toFixed(0)}%
              </div>
              <div style={{ color: 'var(--color-ink-2)' }}>{picked.headline}</div>
              {picked.primary_entity_name && (
                <div className="text-[10px] mt-1">{picked.primary_entity_name}</div>
              )}
            </div>

            <Field label="Verdict">
              <div className="space-y-1">
                {VERDICTS.map((v) => (
                  <label
                    key={v.key}
                    className="flex items-start gap-2 text-[12px] cursor-pointer"
                    style={{ padding: '6px 0' }}
                  >
                    <input
                      type="radio"
                      checked={verdict === v.key}
                      onChange={() => setVerdict(v.key)}
                      style={{ marginTop: '2px' }}
                    />
                    <span style={{ color: v.color }} className="inline-flex items-center gap-1">
                      {v.icon}
                      {v.label}
                    </span>
                  </label>
                ))}
              </div>
            </Field>

            <Field label="Actual outcome (text)">
              <textarea
                value={actualOutcome}
                onChange={(e) => setActualOutcome(e.target.value)}
                rows={3}
                maxLength={4000}
                required
                className="text-[13px] w-full"
                style={{ ...inputStyle, resize: 'vertical', minHeight: '64px' }}
              />
            </Field>

            <Field label="Notes (optional)">
              <textarea
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                rows={2}
                maxLength={4000}
                placeholder="Context for the post-mortem"
                className="text-[12px] w-full"
                style={{ ...inputStyle, resize: 'vertical', minHeight: '48px' }}
              />
            </Field>

            {error && (
              <div className="text-[12px]" style={{ color: '#B91C1C' }}>
                {error}
              </div>
            )}

            <div className="flex justify-between items-center pt-2">
              <button
                type="button"
                onClick={() => { setPhase('detecting'); setPicked(null); }}
                className="text-[12px]"
                style={{
                  padding: '7px 12px', borderRadius: '6px',
                  background: 'transparent', color: 'var(--color-ink-3)',
                  border: '1px solid var(--color-line)', cursor: 'pointer',
                }}
              >
                ← Back to candidates
              </button>
              <button
                type="submit"
                disabled={loading || !actualOutcome.trim()}
                className="text-[13px] font-medium"
                style={{
                  padding: '7px 18px', borderRadius: '6px',
                  background: loading || !actualOutcome.trim() ? 'var(--color-surface-2)' : 'var(--color-accent)',
                  color: loading || !actualOutcome.trim() ? 'var(--color-ink-4)' : 'white',
                  border: 'none', cursor: loading || !actualOutcome.trim() ? 'not-allowed' : 'pointer',
                }}
              >
                {loading ? 'Capturing…' : 'Capture outcome'}
              </button>
            </div>
          </form>
        )}
      </div>
    </div>
  );
}

function CandidateCard({
  candidate, onPick,
}: {
  candidate: OutcomeCandidate;
  onPick: () => void;
}) {
  const c = candidate;
  return (
    <button
      type="button"
      onClick={onPick}
      className="text-left w-full"
      style={{
        padding: '12px 14px',
        borderRadius: '6px',
        border: '1px solid var(--color-line)',
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
            background: '#DCFCE7',
            color: '#15803D',
            letterSpacing: '0.05em',
          }}
          title={`Entity: ${c.match_components.entity_overlap.toFixed(2)} · KBQ: ${c.match_components.kbq_overlap.toFixed(2)} · Temporal: ${c.match_components.temporal_proximity.toFixed(2)}`}
        >
          Match {(c.match_score * 100).toFixed(0)}%
        </span>
        {c.kbq_tags.map((t) => (
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
          {c.created_at ? new Date(c.created_at).toLocaleDateString() : ''}
        </span>
      </div>
      <div className="text-[13px]" style={{ color: 'var(--color-ink)' }}>
        {c.headline}
      </div>
      {c.primary_entity_name && (
        <div className="text-[11px] mt-1" style={{ color: 'var(--color-ink-4)' }}>
          {c.primary_entity_name}
          {c.confidence_tier && ` · ${c.confidence_tier}`}
        </div>
      )}
    </button>
  );
}

const inputStyle: React.CSSProperties = {
  padding: '7px 10px',
  borderRadius: '6px',
  border: '1px solid var(--color-line)',
  background: 'var(--color-surface)',
  color: 'var(--color-ink)',
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div
        className="text-[10px] uppercase font-medium mb-1"
        style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}
