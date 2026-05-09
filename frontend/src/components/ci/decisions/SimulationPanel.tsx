import type { DecisionBrief } from '../../../api';

/**
 * SPEC_030 §5 + §8.3 — center panel.
 *
 * V1 ships structural placeholders for Scenario / Monte Carlo / War-Game
 * with state-aware affordances. The "Start war-game" CTA is
 * disabled-with-tooltip per Q3 sign-off (SPEC_032 wires the click).
 */

const RUN_STATES = new Set(['simulation_pending', 'simulation_complete']);
const ARCHIVE_STATES = new Set(['committed', 'in_review', 'closed']);

interface Props {
  brief: DecisionBrief;
}

export default function SimulationPanel({ brief }: Props) {
  const showRunControls = RUN_STATES.has(brief.state);
  const archived = ARCHIVE_STATES.has(brief.state);

  return (
    <section
      data-testid="panel-simulation"
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
        Simulation
      </h2>

      {!showRunControls && !archived && (
        <p style={{ fontSize: 13, color: 'var(--color-ink-3)', margin: 0 }}>
          Simulation runs once the brief enters <strong>simulation_pending</strong>.
        </p>
      )}

      {/* Scenario placeholder */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--color-ink-3)',
          }}
        >
          Scenario projection
        </span>
        <div
          style={{
            fontSize: 12,
            color: 'var(--color-ink-3)',
            background: 'var(--color-surface-2)',
            borderRadius: 'var(--radius-card, 12px)',
            padding: '12px 14px',
          }}
        >
          {archived ? 'Scenario archived.' : 'No scenario run yet.'}
        </div>
      </div>

      {/* Monte Carlo placeholder */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        <span
          style={{
            fontSize: 11,
            fontWeight: 600,
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
            color: 'var(--color-ink-3)',
          }}
        >
          Monte Carlo
        </span>
        <div
          style={{
            fontSize: 12,
            color: 'var(--color-ink-3)',
            background: 'var(--color-surface-2)',
            borderRadius: 'var(--radius-card, 12px)',
            padding: '12px 14px',
          }}
        >
          {archived ? 'Monte Carlo archived.' : 'Monte Carlo: not run.'}
        </div>
      </div>

      {/* War-game */}
      {showRunControls && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <span
            style={{
              fontSize: 11,
              fontWeight: 600,
              letterSpacing: '0.06em',
              textTransform: 'uppercase',
              color: 'var(--color-ink-3)',
            }}
          >
            War-game
          </span>
          <button
            type="button"
            disabled
            aria-disabled="true"
            title="Multi-adversary war-games ship in SPEC_032"
            aria-describedby="war-game-tooltip"
            className="btn btn-secondary"
            style={{ alignSelf: 'flex-start', opacity: 0.5, cursor: 'not-allowed' }}
          >
            ⊘ Start war-game
          </button>
          <span
            id="war-game-tooltip"
            style={{
              fontSize: 11,
              color: 'var(--color-ink-4)',
              fontStyle: 'italic',
            }}
          >
            Multi-adversary war-games ship in SPEC_032.
          </span>
        </div>
      )}
    </section>
  );
}
