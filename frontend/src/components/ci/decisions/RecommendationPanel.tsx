import type { DecisionBrief } from '../../../api';

/**
 * SPEC_030 §5 + §8.3 — right panel.
 *
 * - Pre-simulation: "awaiting simulation" message.
 * - simulation_complete onward: ranked options + dissent counter-rec block.
 * - decision_pending: "Commit decision" button (disabled until backend
 *   POST /decisions/from-brief lands per Q2 sign-off).
 * - committed: link/chip back to the linked decision_id.
 */

const READY_STATES = new Set([
  'simulation_complete',
  'decision_pending',
  'committed',
  'in_review',
  'closed',
]);

interface Props {
  brief: DecisionBrief;
  onCommit?: (briefId: string) => void;
}

export default function RecommendationPanel({ brief, onCommit }: Props) {
  const ready = READY_STATES.has(brief.state);
  // Stage 6 fix #13: SPEC_023 does not yet expose a post-simulation rank.
  // We can only show options in their stored ordinal order and label
  // them "Top" / "Counter" — never "Primary" — to avoid implying a rank
  // model that does not exist. Real ranking ships with SPEC-032.
  const sortedOptions = brief.options.slice().sort((a, b) => a.ordinal - b.ordinal);
  const top = sortedOptions[0];
  const counter = sortedOptions[sortedOptions.length - 1];
  const showCounter = sortedOptions.length > 1;

  return (
    <section
      data-testid="panel-recommendation"
      tabIndex={-1}
      style={{
        background: 'var(--color-surface)',
        borderRadius: 'var(--radius-panel, 16px)',
        padding: 'var(--space-panel-pad, 24px)',
        boxShadow: 'var(--shadow-workspace-panel, var(--shadow-sm))',
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-panel-gap, 16px)',
        minHeight: 200,
      }}
    >
      <h2
        style={{
          margin: 0,
          fontFamily: 'var(--font-display)',
          fontSize: 18,
          fontWeight: 700,
          color: 'var(--color-ink)',
        }}
      >
        Recommendation
      </h2>

      {!ready && (
        <p style={{ fontSize: 13, color: 'var(--color-ink-3)', margin: 0 }}>
          Awaiting simulation. Ranked options and dissent appear once the
          brief reaches <strong>simulation_complete</strong>.
        </p>
      )}

      {ready && sortedOptions.length === 0 && (
        <p style={{ fontSize: 13, color: 'var(--color-ink-3)', margin: 0 }}>
          No options to rank.
        </p>
      )}

      {ready && top && (
        <div
          style={{
            background: 'var(--color-accent-soft, rgba(28,110,247,0.08))',
            borderRadius: 'var(--radius-card, 12px)',
            padding: '12px 14px',
          }}
        >
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              color: 'var(--color-accent)',
              marginBottom: 6,
            }}
          >
            Top option
          </div>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--color-ink)' }}>
            {top.label}
          </div>
          {top.predicted_outcome && (
            <div style={{ fontSize: 12, color: 'var(--color-ink-2)', marginTop: 4 }}>
              {top.predicted_outcome}
            </div>
          )}
        </div>
      )}

      {ready && showCounter && counter && counter.option_id !== top?.option_id && (
        <div
          style={{
            background: 'var(--color-surface-2)',
            borderRadius: 'var(--radius-card, 12px)',
            padding: '12px 14px',
            border: '1px dashed var(--color-line)',
          }}
        >
          <div
            style={{
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              color: 'var(--color-ink-3)',
              marginBottom: 6,
            }}
          >
            Counter option
          </div>
          <div style={{ fontSize: 13, color: 'var(--color-ink)' }}>{counter.label}</div>
          {counter.predicted_outcome && (
            <div style={{ fontSize: 12, color: 'var(--color-ink-2)', marginTop: 4 }}>
              {counter.predicted_outcome}
            </div>
          )}
        </div>
      )}

      {ready && sortedOptions.length > 0 && (
        <p
          style={{
            fontSize: 11,
            color: 'var(--color-ink-3)',
            margin: 0,
            fontStyle: 'italic',
          }}
        >
          Order reflects ordinal, not simulation rank. Ranking ships in SPEC-032.
        </p>
      )}

      {brief.state === 'decision_pending' && (
        <button
          type="button"
          disabled
          aria-disabled="true"
          title="Commit endpoint not yet ready (backend AGENT_BACKLOG entry)"
          onClick={() => onCommit?.(brief.brief_id)}
          className="btn btn-accent"
          style={{ alignSelf: 'flex-start', opacity: 0.5, cursor: 'not-allowed' }}
        >
          Commit decision
        </button>
      )}

      {brief.state === 'committed' && brief.decision_id && (
        <div
          style={{
            fontSize: 12,
            color: 'var(--color-ink-2)',
            display: 'flex',
            alignItems: 'center',
            gap: 6,
          }}
        >
          <span style={{ color: 'var(--color-ink-3)' }}>Linked decision: </span>
          <a
            href={`/ci/legacy-decisions/${encodeURIComponent(brief.decision_id)}`}
            style={{
              color: 'var(--color-accent)',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              textDecoration: 'underline',
            }}
          >
            {brief.decision_id}
          </a>
        </div>
      )}
    </section>
  );
}
