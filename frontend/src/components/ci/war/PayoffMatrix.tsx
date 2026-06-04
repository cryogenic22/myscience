import type { PayoffCell, PayoffMatrix as PayoffMatrixT, PayoffOutcome } from '../../../types/payoff';
import { AGENTS } from '../../primitives/AgentGlyph';

/**
 * 2×2 payoff matrix. Renders one cell per (our_move, adversary_state)
 * pair with delta% + confidence and a tier-coloured background
 * (win/neutral/lose). The recommended cell carries the Strategist's
 * violet inset ring so the eye reads recommended → Strategist.
 *
 * Loop #11 — borderless surface. The matrix no longer ships its own
 * outer card border; it composes inside a parent panel (the war-room
 * Strategy group). Tier-coloured cell fills + the Strategist inset
 * ring are the only borders that remain.
 *
 * Data via `usePayoffMatrix(roomId)` (BE-8 composer).
 */

interface Props {
  matrix: PayoffMatrixT;
}

const OUTCOME_BACKGROUND: Record<PayoffOutcome, string> = {
  win:     'rgba(34, 197, 94, 0.10)',
  neutral: 'rgba(245, 158, 11, 0.08)',
  lose:    'rgba(239, 68, 68, 0.10)',
};

function formatDelta(d: number): string {
  const sign = d > 0 ? '+' : '';
  return `${sign}${d.toFixed(1)}%`;
}

function findCell(cells: PayoffCell[], rowId: string, colId: string): PayoffCell | undefined {
  return cells.find((c) => c.row_id === rowId && c.col_id === colId);
}

export default function PayoffMatrix({ matrix }: Props) {
  const { rows, cols, cells, recommended_cell, nash_cell, nash_reasoning } = matrix;

  if (rows.length === 0 || cols.length === 0) {
    return (
      <section style={{ marginBottom: '16px' }}>
        <h3
          className="font-display"
          style={{ color: 'var(--color-ink-2)', fontSize: 'var(--text-md)', marginBottom: '6px' }}
        >
          Payoff matrix
        </h3>
        <p className="mz-text-sm" style={{ color: 'var(--color-ink-4)' }}>
          No scenarios yet — add adversary moves and your options to populate the matrix.
        </p>
      </section>
    );
  }

  return (
    <section style={{ marginBottom: '24px' }}>
      <header
        className="flex items-baseline justify-between"
        style={{ marginBottom: '12px' }}
      >
        <h3
          className="font-display"
          style={{ color: 'var(--color-ink-2)', fontSize: 'var(--text-md)' }}
        >
          Payoff matrix
        </h3>
        <span className="mz-text-xs" style={{ color: 'var(--color-ink-4)' }}>
          Posterior over 1,200 Monte Carlo simulations
        </span>
      </header>

      <div style={{ overflowX: 'auto' }}>
        <table
          className="w-full"
          style={{ minWidth: '420px', borderCollapse: 'separate', borderSpacing: '8px' }}
          role="table"
          aria-label="Payoff matrix cells"
        >
          <thead>
            <tr>
              <th />
              {cols.map((c) => (
                <th
                  key={c.id}
                  className="mz-text-xs uppercase"
                  style={{
                    padding: '4px 12px',
                    color: 'var(--color-ink-3)',
                    textAlign: 'left',
                    letterSpacing: '0.06em',
                    fontWeight: 600,
                  }}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.id}>
                <th
                  className="mz-text-xs uppercase"
                  scope="row"
                  style={{
                    padding: '14px 12px 14px 0',
                    color: 'var(--color-ink-3)',
                    textAlign: 'left',
                    verticalAlign: 'top',
                    letterSpacing: '0.06em',
                    fontWeight: 600,
                  }}
                >
                  {r.label}
                </th>
                {cols.map((c) => {
                  const cell = findCell(cells, r.id, c.id);
                  if (!cell) {
                    return (
                      <td
                        key={c.id}
                        className="mz-text-sm"
                        style={{ padding: '14px', color: 'var(--color-ink-4)' }}
                      >
                        —
                      </td>
                    );
                  }
                  const isRecommended =
                    recommended_cell !== null &&
                    recommended_cell.row_id === r.id &&
                    recommended_cell.col_id === c.id;
                  const isNash =
                    !!nash_cell &&
                    nash_cell.row_id === r.id &&
                    nash_cell.col_id === c.id;
                  // Recommended (EV) takes the violet ring; a Nash-only cell
                  // gets a dashed ink ring so the two picks read distinctly.
                  const ring = isRecommended
                    ? `inset 0 0 0 2px rgb(${AGENTS.strategist.rgb})`
                    : isNash
                      ? 'inset 0 0 0 2px var(--color-ink-3)'
                      : 'none';
                  return (
                    <td
                      key={c.id}
                      data-outcome={cell.outcome}
                      data-recommended={isRecommended ? 'true' : 'false'}
                      data-nash={isNash ? 'true' : 'false'}
                      style={{
                        padding: '16px',
                        background: OUTCOME_BACKGROUND[cell.outcome],
                        boxShadow: ring,
                        borderRadius: 'var(--radius-card)',
                        verticalAlign: 'top',
                      }}
                    >
                      <div
                        className="font-display"
                        style={{
                          color: 'var(--color-ink)',
                          fontSize: 'var(--text-xl)',
                          lineHeight: '1',
                          letterSpacing: '-0.015em',
                        }}
                      >
                        {formatDelta(cell.delta_pct)}
                      </div>
                      <div
                        className="mz-text-xs"
                        style={{ color: 'var(--color-ink-3)', marginTop: '6px' }}
                      >
                        {Math.round(cell.confidence * 100)}% conf
                      </div>
                      {isRecommended && (
                        <div
                          data-agent="strategist"
                          className="mz-text-xs uppercase font-medium"
                          style={{
                            color: `rgb(${AGENTS.strategist.rgb})`,
                            letterSpacing: '0.08em',
                            marginTop: '10px',
                          }}
                          title="Recommended by the Strategist agent based on posterior delta × confidence"
                        >
                          Strategist recommends
                        </div>
                      )}
                      {isNash && !isRecommended && (
                        <div
                          data-nash-badge="true"
                          className="mz-text-xs uppercase font-medium"
                          style={{
                            color: 'var(--color-ink-3)',
                            letterSpacing: '0.08em',
                            marginTop: '10px',
                          }}
                          title="Security (maximin) equilibrium — best worst-case outcome"
                        >
                          Nash · security
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {nash_reasoning && (
        <p
          data-nash-reasoning
          className="mz-text-xs"
          style={{ color: 'var(--color-ink-4)', marginTop: '10px', lineHeight: 1.5 }}
        >
          {nash_reasoning}
        </p>
      )}
    </section>
  );
}
