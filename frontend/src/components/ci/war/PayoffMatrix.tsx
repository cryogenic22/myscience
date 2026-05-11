import type { PayoffCell, PayoffMatrix as PayoffMatrixT, PayoffOutcome } from '../../../types/payoff';

/**
 * PB-501 — 2×2 payoff matrix view (scaffold).
 *
 * Renders one cell per (row, col) pairing with delta% + confidence
 * and a tier-coloured background (win/neutral/lose). The recommended
 * cell is outlined with the brand accent so the eye finds it first.
 *
 * Data plumbed via `usePayoffMatrix(roomId)`; backend composer ships
 * via BE-8 (PR #59).
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
      <section
        className="rounded-md"
        style={{
          padding: '20px',
          border: '1px solid var(--color-line)',
          background: 'var(--color-surface)',
        }}
      >
        <h3
          className="font-serif text-[16px] mb-2"
          style={{ color: 'var(--color-ink)' }}
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
    <section
      className="rounded-md"
      style={{
        border: '1px solid var(--color-line)',
        background: 'var(--color-surface)',
      }}
    >
      {matrix.is_mock && (
        <div
          role="status"
          className="text-[11px]"
          style={{
            padding: '6px 16px',
            background: 'var(--color-line)',
            borderTopLeftRadius: '6px',
            borderTopRightRadius: '6px',
            color: 'var(--color-ink-3)',
          }}
        >
          Showing placeholder data — backend composer (BE-8, PR #59) is not yet merged.
        </div>
      )}

      <header
        className="flex items-baseline justify-between"
        style={{
          padding: '16px 20px',
          borderBottom: '1px solid var(--color-line)',
        }}
      >
        <h3 className="font-serif text-[16px]" style={{ color: 'var(--color-ink)' }}>
          Payoff matrix
        </h3>
        <span className="text-[11px]" style={{ color: 'var(--color-ink-4)' }}>
          Posterior over 1,200 Monte Carlo simulations
        </span>
      </header>

      <div style={{ padding: '16px 20px', overflowX: 'auto' }}>
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
                          ? '2px solid var(--color-accent)'
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
                          className="text-[10px] uppercase tracking-wide mt-2 font-medium"
                          style={{ color: 'var(--color-accent)' }}
                        >
                          Recommended
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
