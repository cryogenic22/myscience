import { useEffect, useRef, useState, useCallback } from 'react';
import { decisionBriefsApi, type DecisionBrief, type DecisionBriefList } from '../../../api';
import StateMachineChip, { STATE_META } from './StateMachineChip';

/**
 * SPEC_030 §8.5 — list view replacing legacy DecisionsTab.
 *
 * Linear-style row anatomy (state-glyph + question + meta), keyboard
 * navigation (j/k/return/n/?), empty/error/loading states.
 */

interface Props {
  onOpen: (briefId: string) => void;
}

export default function BriefsTab({ onOpen }: Props) {
  const [list, setList] = useState<DecisionBriefList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedIdx, setSelectedIdx] = useState(0);
  const [showNew, setShowNew] = useState(false);
  const [showHelp, setShowHelp] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await decisionBriefsApi.list({ limit: 50 });
      setList(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const briefs = list?.briefs ?? [];
  const briefsRef = useRef(briefs);
  briefsRef.current = briefs;
  const selectedRef = useRef(selectedIdx);
  selectedRef.current = selectedIdx;

  // Keyboard contract: j/k/return/n/?
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Don't capture keys when user is typing in inputs/textareas
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (tag === 'input' || tag === 'textarea') return;

      if (e.key === 'j') {
        e.preventDefault();
        const max = Math.max(0, briefsRef.current.length - 1);
        setSelectedIdx((i) => Math.min(i + 1, max));
      } else if (e.key === 'k') {
        e.preventDefault();
        setSelectedIdx((i) => Math.max(i - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        const target = briefsRef.current[selectedRef.current];
        if (target) onOpen(target.brief_id);
      } else if (e.key === 'n') {
        e.preventDefault();
        setShowNew(true);
      } else if (e.key === '?') {
        e.preventDefault();
        setShowHelp(true);
      } else if (e.key === 'Escape') {
        setShowNew(false);
        setShowHelp(false);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onOpen]);

  if (loading && !list) {
    return (
      <div
        aria-label="loading briefs"
        role="status"
        aria-live="polite"
        style={{
          padding: 'var(--space-panel-pad, 24px)',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            style={{
              height: 56,
              background: 'var(--color-surface-2)',
              borderRadius: 'var(--radius-card, 12px)',
              animation: 'skeleton-pulse 1.6s ease-in-out infinite',
            }}
          />
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          padding: 'var(--space-panel-pad, 24px)',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
          alignItems: 'flex-start',
        }}
      >
        <div style={{ fontSize: 13, color: 'var(--color-red, #C0392B)' }}>{error}</div>
        <button type="button" onClick={() => void load()} className="btn btn-secondary btn-sm">
          Retry
        </button>
      </div>
    );
  }

  if (briefs.length === 0) {
    return (
      <div
        style={{
          padding: 64,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: 16,
          textAlign: 'center',
        }}
      >
        <div
          style={{
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--color-ink-3)',
          }}
        >
          No briefs yet
        </div>
        <div style={{ fontSize: 14, color: 'var(--color-ink-2)', maxWidth: 360 }}>
          Frame a signal as a decision, or create a manual draft.
        </div>
        <button type="button" onClick={() => setShowNew(true)} className="btn btn-accent">
          + New brief
        </button>
        {showNew && <NewBriefDialog onClose={() => setShowNew(false)} onCreated={(id) => onOpen(id)} />}
      </div>
    );
  }

  return (
    <div
      role="listbox"
      aria-label="decision briefs"
      style={{
        padding: 'var(--space-panel-pad, 24px)',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-row-gap, 12px)',
      }}
    >
      {briefs.map((b, i) => (
        <BriefRow
          key={b.brief_id}
          brief={b}
          selected={i === selectedIdx}
          onClick={() => onOpen(b.brief_id)}
          onHover={() => setSelectedIdx(i)}
        />
      ))}
      {showNew && <NewBriefDialog onClose={() => setShowNew(false)} onCreated={(id) => onOpen(id)} />}
      {showHelp && <KeyboardHintDialog onClose={() => setShowHelp(false)} />}
    </div>
  );
}

interface RowProps {
  brief: DecisionBrief;
  selected: boolean;
  onClick: () => void;
  onHover: () => void;
}

function BriefRow({ brief, selected, onClick, onHover }: RowProps) {
  // Stage 6 fix #3: rows must be Tab-reachable. The selected row gets
  // tabIndex=0; non-selected rows get -1 so screen-reader users move
  // through the listbox via arrow keys (managed by the parent listbox)
  // rather than each row taking a Tab stop.
  return (
    <article
      role="option"
      aria-selected={selected}
      tabIndex={selected ? 0 : -1}
      onClick={onClick}
      onMouseEnter={onHover}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          onClick();
        }
      }}
      style={{
        background: 'var(--color-surface)',
        borderRadius: 'var(--radius-card, 12px)',
        boxShadow: selected
          ? '0 0 0 1px var(--color-accent), var(--shadow-sm)'
          : 'var(--shadow-xs)',
        padding: '14px 16px',
        cursor: 'pointer',
        outline: 'none',
        transition: 'transform 160ms cubic-bezier(0.16,1,0.3,1), box-shadow 160ms cubic-bezier(0.16,1,0.3,1)',
        display: 'flex',
        flexDirection: 'column',
        gap: 6,
        transform: selected ? 'translateY(-1px)' : 'none',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <StateMachineChip state={brief.state} />
        <span
          style={{
            fontSize: 14,
            fontWeight: 500,
            color: 'var(--color-ink)',
            flex: 1,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {brief.question}
        </span>
      </div>
      <div
        style={{
          fontSize: 11,
          color: 'var(--color-ink-3)',
          fontFamily: 'var(--font-body)',
          letterSpacing: '0.03em',
          paddingLeft: 4,
        }}
      >
        ↳ trigger: {brief.trigger_kind}
        {brief.time_horizon_days != null && ` · ${brief.time_horizon_days}d horizon`}
        {' '}· {brief.options.length} option{brief.options.length === 1 ? '' : 's'}
        {brief.evidence_refs.length > 0 && ` · ${brief.evidence_refs.length} evidence ref${brief.evidence_refs.length === 1 ? '' : 's'}`}
      </div>
    </article>
  );
}

function NewBriefDialog({ onClose, onCreated }: { onClose: () => void; onCreated: (id: string) => void }) {
  const [question, setQuestion] = useState('');
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const submit = async () => {
    if (!question.trim() || busy) return;
    setBusy(true);
    setErr(null);
    try {
      const created = await decisionBriefsApi.create({ question: question.trim() });
      onCreated(created.brief_id);
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="new brief"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
      }}
    >
      <div
        style={{
          background: 'var(--color-surface)',
          borderRadius: 'var(--radius-card, 16px)',
          padding: 24,
          maxWidth: 480,
          width: '92%',
          boxShadow: 'var(--shadow-lg)',
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
        }}
      >
        <h3
          style={{
            margin: 0,
            fontFamily: 'var(--font-display)',
            fontSize: 22,
            fontWeight: 700,
            color: 'var(--color-ink)',
          }}
        >
          New brief
        </h3>
        <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span style={{ fontSize: 11, fontWeight: 600, letterSpacing: '0.06em', textTransform: 'uppercase', color: 'var(--color-ink-3)' }}>
            Question
          </span>
          <textarea
            aria-label="question"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            rows={3}
            autoFocus
            placeholder="Should we accelerate Phase III readout in 2L NSCLC?"
            style={{
              background: 'var(--color-surface-2)',
              border: '1px solid var(--color-line)',
              borderRadius: 'var(--radius-input, 12px)',
              padding: '10px 14px',
              fontSize: 14,
              color: 'var(--color-ink)',
              fontFamily: 'inherit',
              outline: 'none',
              resize: 'vertical',
            }}
          />
        </label>
        {err && <div style={{ fontSize: 12, color: 'var(--color-red, #C0392B)' }}>{err}</div>}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button type="button" onClick={onClose} className="btn btn-secondary">Cancel</button>
          <button
            type="button"
            disabled={!question.trim() || busy}
            onClick={() => void submit()}
            className="btn btn-accent"
          >
            {busy ? 'Creating…' : 'Create'}
          </button>
        </div>
      </div>
    </div>
  );
}

function KeyboardHintDialog({ onClose }: { onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' || e.key === '?') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div
      role="dialog"
      aria-label="keyboard shortcuts"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(0,0,0,0.4)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 100,
      }}
    >
      <div
        style={{
          background: 'var(--color-surface)',
          borderRadius: 'var(--radius-card, 16px)',
          padding: 24,
          maxWidth: 380,
          width: '92%',
          boxShadow: 'var(--shadow-lg)',
        }}
      >
        <h3
          style={{
            margin: '0 0 16px 0',
            fontFamily: 'var(--font-display)',
            fontSize: 18,
            fontWeight: 700,
            color: 'var(--color-ink)',
          }}
        >
          Keyboard shortcuts
        </h3>
        <ul style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 8 }}>
          {[
            ['j', 'Next brief'],
            ['k', 'Previous brief'],
            ['return', 'Open selected brief'],
            ['n', 'New brief'],
            ['?', 'Show this help'],
            ['esc', 'Close dialog'],
          ].map(([key, label]) => (
            <li key={key} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13 }}>
              <kbd
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 11,
                  background: 'var(--color-surface-2)',
                  padding: '2px 8px',
                  borderRadius: 4,
                  color: 'var(--color-ink)',
                }}
              >
                {key}
              </kbd>
              <span style={{ color: 'var(--color-ink-2)' }}>{label}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

// re-export so consumers can use STATE_META if needed
export { STATE_META };
