import { useState, useRef, useEffect } from 'react';
import type { BriefState } from '../../../api';

/**
 * SPEC_030 §8.4 — visual brief-state chip.
 *
 * Non-interactive by default: renders <span role="status" aria-live="polite">
 * with a shape-glyph + label so color is never the only carrier of meaning.
 *
 * Interactive (interactive=true): the chip becomes a button; clicking opens
 * a popover dialog of allowed transitions. Each transition button calls
 * onTransition(toState) when its handler is provided.
 *
 * Color tokens: --color-state-{draft|review|sim|decide|committed|review-out|closed}.
 */

const STATE_META: Record<BriefState, { label: string; glyph: string; tokenVar: string }> = {
  draft:                { label: 'draft',                glyph: '◯', tokenVar: '--color-state-draft' },
  human_review:         { label: 'human review',         glyph: '▶', tokenVar: '--color-state-review' },
  simulation_pending:   { label: 'simulation pending',   glyph: '⟳', tokenVar: '--color-state-sim' },
  simulation_complete:  { label: 'simulation complete',  glyph: '⟳', tokenVar: '--color-state-sim' },
  decision_pending:     { label: 'decision pending',     glyph: '⊕', tokenVar: '--color-state-decide' },
  committed:            { label: 'committed',            glyph: '✓', tokenVar: '--color-state-committed' },
  in_review:            { label: 'in review',            glyph: '⊕', tokenVar: '--color-state-review-out' },
  closed:               { label: 'closed',               glyph: '◆', tokenVar: '--color-state-closed' },
};

const ALLOWED_TRANSITIONS: Record<BriefState, BriefState[]> = {
  draft:               ['human_review', 'closed'],
  human_review:        ['draft', 'simulation_pending', 'closed'],
  simulation_pending:  ['simulation_complete', 'human_review'],
  simulation_complete: ['decision_pending', 'human_review'],
  decision_pending:    ['committed', 'human_review'],
  committed:           ['in_review'],
  in_review:           ['closed'],
  closed:              [],
};

interface Props {
  state: BriefState;
  /** When true, the chip is a button and clicking opens the transitions popover. */
  interactive?: boolean;
  /** When provided, transitions in the popover are clickable and invoke this. */
  onTransition?: (toState: BriefState) => void;
  /** Optional pre-validated set of allowed transitions for this brief. If
   * omitted, the static state-machine map is used. Used by the workspace
   * to also disable transitions blocked by external rules (e.g. requires
   * ≥2 options). */
  allowed?: BriefState[];
}

export default function StateMachineChip({
  state,
  interactive = false,
  onTransition,
  allowed,
}: Props) {
  const meta = STATE_META[state];
  const [open, setOpen] = useState(false);
  const popoverRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    const onClick = (e: MouseEvent) => {
      if (
        popoverRef.current &&
        !popoverRef.current.contains(e.target as Node) &&
        !buttonRef.current?.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('mousedown', onClick);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('mousedown', onClick);
    };
  }, [open]);

  const chipStyle = {
    color: `var(${meta.tokenVar}, var(--color-ink-3))`,
    background: 'var(--color-surface-2)',
    border: `1px solid var(${meta.tokenVar}, var(--color-line))`,
    borderRadius: 'var(--radius-pill, 999px)',
    padding: '4px 12px',
    fontSize: '11px',
    fontWeight: 600,
    letterSpacing: '0.06em',
    textTransform: 'uppercase' as const,
    fontFamily: 'var(--font-body)',
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    cursor: interactive ? 'pointer' : 'default',
  };

  const labelText = `${meta.glyph} ${meta.label}`;

  if (!interactive) {
    return (
      <span role="status" aria-live="polite" style={chipStyle}>
        <span aria-hidden="true">{meta.glyph}</span>
        <span>{meta.label}</span>
      </span>
    );
  }

  const transitions = allowed ?? ALLOWED_TRANSITIONS[state];

  return (
    <span style={{ position: 'relative', display: 'inline-block' }}>
      <button
        ref={buttonRef}
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-label={`brief state: ${meta.label}, click to view allowed transitions`}
        style={chipStyle}
      >
        <span aria-hidden="true">{meta.glyph}</span>
        <span>{meta.label}</span>
      </button>
      {open && (
        <div
          ref={popoverRef}
          role="dialog"
          aria-label="State transitions"
          style={{
            position: 'absolute',
            top: 'calc(100% + 6px)',
            left: 0,
            background: 'var(--color-surface)',
            border: '1px solid var(--color-line)',
            borderRadius: 'var(--radius-card, 12px)',
            boxShadow: 'var(--shadow-md)',
            padding: '8px',
            minWidth: '220px',
            zIndex: 50,
          }}
        >
          <div
            style={{
              fontSize: '10px',
              fontWeight: 600,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              color: 'var(--color-ink-3)',
              padding: '6px 8px',
            }}
          >
            transitions
          </div>
          {transitions.length === 0 && (
            <div
              style={{
                fontSize: '12px',
                color: 'var(--color-ink-3)',
                padding: '6px 8px',
              }}
            >
              No transitions from {meta.label} (terminal state).
            </div>
          )}
          {transitions.map((to) => {
            const toMeta = STATE_META[to];
            const disabled = !onTransition;
            return (
              <button
                key={to}
                type="button"
                disabled={disabled}
                aria-disabled={disabled}
                onClick={() => {
                  if (onTransition) {
                    onTransition(to);
                    setOpen(false);
                  }
                }}
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  padding: '8px 10px',
                  borderRadius: '8px',
                  background: 'transparent',
                  border: 'none',
                  cursor: disabled ? 'not-allowed' : 'pointer',
                  fontSize: '13px',
                  color: 'var(--color-ink-2)',
                  opacity: disabled ? 0.5 : 1,
                  fontFamily: 'var(--font-body)',
                }}
              >
                <span aria-hidden="true" style={{ marginRight: 8 }}>
                  →
                </span>
                <span aria-hidden="true">{toMeta.glyph}</span>{' '}
                <span>{toMeta.label}</span>
              </button>
            );
          })}
        </div>
      )}
    </span>
  );
}

// Used by other components that need to compute disabled-states without
// re-importing the state machine.
export { ALLOWED_TRANSITIONS };

// Hidden export for tests / reasoning trace UI.
export { STATE_META };
