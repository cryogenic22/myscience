import { describe, it, expect } from 'vitest';
import { adaptPayoffResponse } from '../../src/hooks/usePayoffMatrix';
import type { PayoffMatrix } from '../../src/types/payoff';

/**
 * BE-8 wire shape (see services/simulation/payoff.py build_payoff_matrix):
 *   { cells: [[{delta_pct, confidence, recommended}, ...], ...],
 *     recommended_cell: [row_idx, col_idx],
 *     samples_per_cell: int }
 *
 * Request labels (our_moves, adversary_states) are NOT echoed back —
 * the frontend supplies them.
 */

describe('adaptPayoffResponse — BE-8 wire shape → frontend PayoffMatrix', () => {
  const FIXTURE = {
    roomId: 'room-1',
    ourMoves: ['launch_q3', 'wait_q4'],
    adversaryStates: ['defend', 'cede'],
    response: {
      cells: [
        [{ delta_pct: 6.4,  confidence: 0.71, recommended: true  },
         { delta_pct: -2.1, confidence: 0.62, recommended: false }],
        [{ delta_pct: 1.2,  confidence: 0.55, recommended: false },
         { delta_pct: -3.4, confidence: 0.48, recommended: false }],
      ],
      recommended_cell: [0, 0],
      samples_per_cell: 1200,
    },
  };

  it('reshapes 2D cells[][] to a flat cells[] keyed by row_id/col_id', () => {
    const out: PayoffMatrix = adaptPayoffResponse(
      FIXTURE.response,
      FIXTURE.roomId,
      FIXTURE.ourMoves,
      FIXTURE.adversaryStates,
    );
    expect(out.cells).toHaveLength(4);
    expect(new Set(out.cells.map((c) => `${c.row_id}|${c.col_id}`))).toEqual(
      new Set([
        'r-launch_q3|c-defend',
        'r-launch_q3|c-cede',
        'r-wait_q4|c-defend',
        'r-wait_q4|c-cede',
      ]),
    );
  });

  it('puts our_moves on rows and adversary_states on cols', () => {
    const out = adaptPayoffResponse(
      FIXTURE.response,
      FIXTURE.roomId,
      FIXTURE.ourMoves,
      FIXTURE.adversaryStates,
    );
    expect(out.rows.map((r) => r.label)).toEqual(['launch_q3', 'wait_q4']);
    expect(out.cols.map((c) => c.label)).toEqual(['defend', 'cede']);
  });

  it('maps recommended_cell index pair to {row_id, col_id}', () => {
    const out = adaptPayoffResponse(
      FIXTURE.response,
      FIXTURE.roomId,
      FIXTURE.ourMoves,
      FIXTURE.adversaryStates,
    );
    expect(out.recommended_cell).toEqual({ row_id: 'r-launch_q3', col_id: 'c-defend' });
  });

  it('derives outcome (win/neutral/lose) from delta_pct sign + magnitude', () => {
    const out = adaptPayoffResponse(
      FIXTURE.response,
      FIXTURE.roomId,
      FIXTURE.ourMoves,
      FIXTURE.adversaryStates,
    );
    const byKey = (rowLabel: string, colLabel: string) =>
      out.cells.find((c) => c.row_id === `r-${rowLabel}` && c.col_id === `c-${colLabel}`);
    // |delta| >= 2 → win/lose; |delta| < 2 → neutral
    expect(byKey('launch_q3', 'defend')?.outcome).toBe('win');     // +6.4
    expect(byKey('launch_q3', 'cede')?.outcome).toBe('lose');      // -2.1
    expect(byKey('wait_q4',   'defend')?.outcome).toBe('neutral'); // +1.2
    expect(byKey('wait_q4',   'cede')?.outcome).toBe('lose');      // -3.4
  });

  it('handles a null recommended_cell from the backend by leaving it null', () => {
    const r = { ...FIXTURE.response, recommended_cell: null };
    const out = adaptPayoffResponse(r as any, FIXTURE.roomId, FIXTURE.ourMoves, FIXTURE.adversaryStates);
    expect(out.recommended_cell).toBeNull();
  });

  it('throws if our_moves length is not 2', () => {
    expect(() =>
      adaptPayoffResponse(FIXTURE.response, FIXTURE.roomId, ['only-one'] as any, FIXTURE.adversaryStates),
    ).toThrow(/exactly 2/);
  });

  it('throws if adversary_states length is not 2', () => {
    expect(() =>
      adaptPayoffResponse(FIXTURE.response, FIXTURE.roomId, FIXTURE.ourMoves, ['only-one'] as any),
    ).toThrow(/exactly 2/);
  });
});
