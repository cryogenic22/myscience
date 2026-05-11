/**
 * PB-501 — Payoff matrix scaffold types.
 *
 * Wire shape for `POST /war-rooms/{id}/payoff-matrix` (AGENT_BACKLOG#BE-8,
 * PR #59). While BE-8 is unmerged, `usePayoffMatrix` returns a mock
 * fixture with `is_mock: true` so the panel can render against
 * realistic data.
 */

export type PayoffOutcome = 'win' | 'neutral' | 'lose';

export interface PayoffRow {
  id: string;
  /** Adversary move (e.g. "Lilly defends Mounjaro"). */
  label: string;
}

export interface PayoffCol {
  id: string;
  /** Our option (e.g. "Launch Q3"). */
  label: string;
}

export interface PayoffCell {
  row_id: string;
  col_id: string;
  outcome: PayoffOutcome;
  /** Δ vs baseline NPV / share / whatever the room is scored on, expressed
   *  in percentage points. */
  delta_pct: number;
  /** Posterior confidence (0–1) from the 1,200-MC simulation in
   *  `services/game_theory.py::run_bayesian()`. */
  confidence: number;
}

export interface PayoffMatrix {
  room_id: string;
  rows: PayoffRow[];
  cols: PayoffCol[];
  cells: PayoffCell[];
  /** Highest expected-value cell (delta * confidence) the strategist
   *  recommends; null if the matrix is empty. */
  recommended_cell: { row_id: string; col_id: string } | null;
  /** Frontend-only — drop once BE-8 ships. */
  is_mock?: boolean;
}
