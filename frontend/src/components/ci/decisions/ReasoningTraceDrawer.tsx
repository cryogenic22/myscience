import { useEffect, useId } from 'react';
import type { DecisionBrief } from '../../../api';
import { STATE_META } from './StateMachineChip';

/**
 * SPEC_030 §8.1 — Sentry-breadcrumb-style right-side drawer rendering the
 * brief's state_log timeline. Future loop integrates with llm_call_log
 * via SPEC_026 telemetry; for now, state_log is the source of truth.
 */

interface Props {
  brief: DecisionBrief;
  open: boolean;
  onClose: () => void;
}

function fmtTime(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' });
  } catch {
    return iso;
  }
}

export default function ReasoningTraceDrawer({ brief, open, onClose }: Props) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onClose();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  const entries = [...(brief.state_log ?? [])].sort(
    (a, b) => new Date(a.transitioned_at).getTime() - new Date(b.transitioned_at).getTime(),
  );

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        bottom: 0,
        width: 'min(420px, 90vw)',
        background: 'var(--color-surface)',
        borderLeft: '1px solid var(--color-line)',
        boxShadow: 'var(--shadow-lg)',
        zIndex: 80,
        display: 'flex',
        flexDirection: 'column',
        animation: 'slide-in-right 280ms cubic-bezier(0.16,1,0.3,1)',
      }}
    >
      <header
        style={{
          padding: '20px 24px 16px',
          borderBottom: '1px solid var(--color-line)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <h3
          id={titleId}
          style={{
            margin: 0,
            fontFamily: 'var(--font-display)',
            fontSize: 18,
            fontWeight: 700,
            color: 'var(--color-ink)',
          }}
        >
          Reasoning trace
        </h3>
        <button
          type="button"
          onClick={onClose}
          aria-label="close"
          className="btn btn-ghost btn-sm"
          style={{ padding: '4px 10px' }}
        >
          ×
        </button>
      </header>

      <div
        style={{
          padding: '12px 16px',
          fontSize: 11,
          color: 'var(--color-ink-3)',
          textTransform: 'uppercase',
          letterSpacing: '0.06em',
          fontWeight: 600,
          fontFamily: 'var(--font-body)',
        }}
      >
        State log · {entries.length} entr{entries.length === 1 ? 'y' : 'ies'}
      </div>

      <ul
        role="list"
        style={{
          listStyle: 'none',
          margin: 0,
          padding: '0 16px 24px',
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          gap: 12,
        }}
      >
        {entries.map((e) => {
          const toMeta = STATE_META[e.to_state];
          const fromLabel = e.from_state ? STATE_META[e.from_state as keyof typeof STATE_META]?.label ?? e.from_state : null;
          return (
            <li
              key={e.log_id}
              role="listitem"
              style={{
                background: 'var(--color-surface-2)',
                borderRadius: 'var(--radius-card, 12px)',
                padding: '12px 14px',
                display: 'flex',
                flexDirection: 'column',
                gap: 6,
              }}
            >
              <div
                style={{
                  fontSize: 11,
                  color: 'var(--color-ink-3)',
                  fontFamily: 'var(--font-mono)',
                }}
              >
                {fmtTime(e.transitioned_at)}
              </div>
              <div style={{ fontSize: 13, color: 'var(--color-ink)' }}>
                <span aria-hidden="true">{toMeta?.glyph ?? '•'} </span>
                {fromLabel ? (
                  <>
                    <span style={{ color: 'var(--color-ink-3)' }}>{fromLabel}</span>
                    <span style={{ color: 'var(--color-ink-4)' }}> → </span>
                  </>
                ) : null}
                <strong>{e.to_state}</strong>
              </div>
              {e.actor_user_id && (
                <div style={{ fontSize: 12, color: 'var(--color-ink-2)' }}>
                  by <span style={{ fontFamily: 'var(--font-mono)' }}>{e.actor_user_id}</span>
                </div>
              )}
              {e.reason && (
                <div style={{ fontSize: 12, color: 'var(--color-ink-2)', lineHeight: 1.5 }}>
                  {e.reason}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
