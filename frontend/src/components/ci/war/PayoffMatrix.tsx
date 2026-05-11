import type { PayoffCell, PayoffMatrix as PayoffMatrixT, PayoffOutcome } from '../../../types/payoff';
import { AGENTS } from '../../primitives/AgentGlyph';

/**
 * 2×2 payoff matrix view. Renders one cell per (our_move,
 * adversary_state) pair with delta% + confidence and a tier-coloured
 * background (win/neutral/lose). The recommended cell is outlined
 * with the brand accent.
 *
 * Wired to the BE-8 composer (`POST /war-rooms/{id}/payoff-matrix`)
 * via `usePayoffMatrix`.
 */

interface Props {
  matrix: PayoffMatrixT;
}

const OUTCOME_BACKGROUND: Record<PayoffOutcome, string> = {
  win:     'rgba(34, 197, 94, 0.12)',   // green-500 @ 12%
  neutral: 'rgba(245, 158, 11, 0.10)',  // amber-500 @ 10%
  lose:    'rgba(239, 68, 68, 0.12)',   // red-500 @ 12%
};

const OUTCOME_BORDER: Record<PayoffOutcome, string> = {
  win:     'rgba(34, 197, 94, 0.55)',
  neutral: 'rgba(245, 158, 11, 0.55)',
  lose:    'rgba(239, 68, 68, 0.55)',
};

function formatDelta(d: number): string {
  const sign = d > 0 ? '+' : '';
  return `${sign}${d.toFixed(1)}%`;
}

function findCell(cells: PayoffCell[], rowId: string, colId: string): PayoffCell | undefined {
  return cells.find((c) => c.row_id === rowId && c.col_id === colId);
}

export default function PayoffMatrix({ matrix }: Props) {
  const { rows, cols, cells, recommended_cell } = matrix;

  if (rows.length === 0 || cols.length === 0) {
    return (
      <section className="mb-4">
        <h3
          className="font-serif text-[14px] mb-1"
          style={{ color: 'var(--color-ink-2)' }}
        >
          Payoff matrix
        </h3>
        <p className="text-[12px]" style={{ color: 'var(--color-ink-4)' }}>
          No scenarios yet — add adversary moves and your options to populate the matrix.
        </p>
      </section>
    );
  }

  return (
    <section className="mb-5">
      <header className="flex items-baseline justify-between mb-2">
        <h3 className="font-serif text-[14px]" style={{ color: 'var(--color-ink-2)' }}>
          Payoff matrix
        </h3>
        <span className="text-[11px]" style={{ color: 'var(--color-ink-4)' }}>
          Posterior over 1,200 Monte Carlo simulations
        </span>
      </header>

      <div style={{ overflowX: 'auto' }}>
        <table
          className="w-full border-collapse"
          style={{ minWidth: '420px' }}
          role="table"
          aria-label="Payoff matrix cells"
        >
          <thead>
            <tr>
              <th />
              {cols.map((c) => (
                <th
                  key={c.id}
                  className="text-[11px] font-medium uppercase tracking-wide"
                  style={{
                    padding: '6px 10px',
                    color: 'var(--color-ink-3)',
                    textAlign: 'left',
                    borderBottom: '1px solid var(--color-line)',
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
                  className="text-[11px] font-medium uppercase tracking-wide"
                  scope="row"
                  style={{
                    padding: '10px 10px 10px 0',
                    color: 'var(--color-ink-3)',
                    textAlign: 'left',
                    verticalAlign: 'top',
                    borderRight: '1px solid var(--color-line)',
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
                        style={{
                          padding: '12px 10px',
                          color: 'var(--color-ink-4)',
                          fontSize: '12px',
                        }}
                      >
                        —
                      </td>
                    );
                  }
                  const isRecommended =
                    recommended_cell !== null &&
                    recommended_cell.row_id === r.id &&
                    recommended_cell.col_id === c.id;
                  return (
                    <td
                      key={c.id}
                      data-outcome={cell.outcome}
                      data-recommended={isRecommended ? 'true' : 'false'}
                      style={{
                        padding: '12px',
                        background: OUTCOME_BACKGROUND[cell.outcome],
                        border: isRecommended
                          ? `2px solid rgb(${AGENTS.strategist.rgb})`
                          : `1px solid ${OUTCOME_BORDER[cell.outcome]}`,
                        borderRadius: '6px',
                        verticalAlign: 'top',
                      }}
                    >
                      <div
                        className="font-serif text-[18px] leading-none"
                        style={{ color: 'var(--color-ink)' }}
                      >
                        {formatDelta(cell.delta_pct)}
                      </div>
                      <div
                        className="text-[11px] mt-1"
                        style={{ color: 'var(--color-ink-3)' }}
                      >
                        {Math.round(cell.confidence * 100)}% conf
                      </div>
                      {isRecommended && (
                        <div
                          data-agent="strategist"
                          className="text-[10px] uppercase tracking-wide mt-2 font-medium"
                          style={{ color: `rgb(${AGENTS.strategist.rgb})` }}
                          title="Recommended by the Strategist agent based on posterior delta × confidence"
                        >
                          Strategist recommends
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
    </section>
  );
}
