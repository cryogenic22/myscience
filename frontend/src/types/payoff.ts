/**
 * Payoff matrix wire types — aligned with BE-8
 * (`POST /war-rooms/{id}/payoff-matrix`) shipped 2026-05-11 in PR #59.
 *
 * The hook (`usePayoffMatrix`) adapts the backend's 2D `cells[][]` and
 * `recommended_cell: [r, c]` into this flat shape so the renderer
 * (`PayoffMatrix.tsx`) stays stable.
 */

export type PayoffOutcome = 'win' | 'neutral' | 'lose';

export interface PayoffRow {
  id: string;
  /** Our move label, e.g. "Launch Q3". */
  label: string;
}

export interface PayoffCol {
  id: string;
  /** Adversary state label, e.g. "Defend". */
  label: string;
}

export interface PayoffCell {
  row_id: string;
  col_id: string;
  outcome: PayoffOutcome;
  /** Δ vs baseline NPV / share / whatever the room scores on, in
   *  percentage points. */
  delta_pct: number;
  /** Posterior confidence (0–1) from the 1,200-MC Bayesian run. */
  confidence: number;
}

export interface PayoffMatrix {
  room_id: string;
  rows: PayoffRow[];
  cols: PayoffCol[];
  cells: PayoffCell[];
  recommended_cell: { row_id: string; col_id: string } | null;
  /** PB-H12 — security (maximin) equilibrium cell + its justification. */
  nash_cell: { row_id: string; col_id: string } | null;
  nash_reasoning: string | null;
}
