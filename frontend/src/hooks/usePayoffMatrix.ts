import { useEffect, useState } from 'react';
import { BASE } from '../api';
import type {
  PayoffCell,
  PayoffMatrix,
  PayoffOutcome,
} from '../types/payoff';

/**
 * `usePayoffMatrix(roomId)` — POSTs to `/war-rooms/{id}/payoff-matrix`
 * with sensible default `our_moves` + `adversary_states` and adapts
 * the BE-8 response into the frontend `PayoffMatrix` shape.
 *
 * Future PB (PB-502, PB-503) will let the analyst customise the
 * row/col labels; for now the defaults give a useful first render.
 */

export interface UsePayoffMatrixResult {
  data: PayoffMatrix | null;
  error: Error | null;
  isLoading: boolean;
}

const DEFAULT_OUR_MOVES: [string, string] = ['launch_q3', 'wait_q4'];
const DEFAULT_ADVERSARY_STATES: [string, string] = ['defend', 'cede'];

/** Outcome tier derived from delta sign + magnitude.
 *  |delta| < 2 → neutral; > 0 → win; < 0 → lose. */
function outcomeFromDelta(delta: number): PayoffOutcome {
  if (delta >= 2) return 'win';
  if (delta <= -2) return 'lose';
  return 'neutral';
}

/**
 * Adapt a BE-8 response (2D `cells[][]` + index-pair `recommended_cell`)
 * into the frontend `PayoffMatrix` (flat `cells[]` keyed by row_id /
 * col_id, named `recommended_cell`).
 *
 * Exposed for unit testing.
 */
export function adaptPayoffResponse(
  wire: any,
  roomId: string,
  ourMoves: string[],
  adversaryStates: string[],
): PayoffMatrix {
  // PB-H12 — N×N (2..5 per dim). Was a hard 2×2.
  if (ourMoves.length < 2) {
    throw new Error(`adaptPayoffResponse: ourMoves must be at least 2, got ${ourMoves.length}`);
  }
  if (adversaryStates.length < 2) {
    throw new Error(`adaptPayoffResponse: adversaryStates must be at least 2, got ${adversaryStates.length}`);
  }

  const rows = ourMoves.map((label) => ({ id: `r-${label}`, label }));
  const cols = adversaryStates.map((label) => ({ id: `c-${label}`, label }));

  const cells: PayoffCell[] = [];
  const wireCells: any[][] = wire?.cells ?? [];
  for (let i = 0; i < rows.length; i++) {
    const wireRow = wireCells[i] ?? [];
    for (let j = 0; j < cols.length; j++) {
      const w = wireRow[j] ?? {};
      const delta = Number(w.delta_pct ?? 0);
      cells.push({
        row_id: rows[i].id,
        col_id: cols[j].id,
        outcome: outcomeFromDelta(delta),
        delta_pct: delta,
        confidence: Number(w.confidence ?? 0),
      });
    }
  }

  const idxPair = (key: string): { row_id: string; col_id: string } | null => {
    const v = wire?.[key];
    if (Array.isArray(v) && v.length === 2 && rows[v[0]] && cols[v[1]]) {
      return { row_id: rows[v[0]].id, col_id: cols[v[1]].id };
    }
    return null;
  };

  return {
    room_id: roomId,
    rows,
    cols,
    cells,
    recommended_cell: idxPair('recommended_cell'),
    nash_cell: idxPair('nash_cell'),
    nash_reasoning: typeof wire?.nash_reasoning === 'string' ? wire.nash_reasoning : null,
  };
}

async function fetchPayoffMatrix(
  roomId: string,
  ourMoves: string[] = DEFAULT_OUR_MOVES,
  adversaryStates: string[] = DEFAULT_ADVERSARY_STATES,
): Promise<PayoffMatrix> {
  const body = {
    our_moves: ourMoves,
    adversary_states: adversaryStates,
    samples: 1200,
  };
  // Use shared auth header pattern — payoff matrix requires uploader role.
  const token = typeof window !== 'undefined' ? window.localStorage.getItem('mz_auth_token') : null;
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (token) headers['Authorization'] = `Bearer ${token}`;

  const res = await fetch(`${BASE}/war-rooms/${encodeURIComponent(roomId)}/payoff-matrix`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = new Error(`${res.status} ${res.statusText}`) as Error & { status?: number };
    err.status = res.status;
    throw err;
  }
  const wire = await res.json();
  return adaptPayoffResponse(wire, roomId, ourMoves, adversaryStates);
}

export interface UsePayoffMatrixOptions {
  /** Override the row strategies (our moves). Default 2×2. */
  ourMoves?: string[];
  /** Override the column strategies (adversary moves/states). Default 2×2. */
  adversaryStates?: string[];
}

export function usePayoffMatrix(
  roomId: string | null | undefined,
  opts: UsePayoffMatrixOptions = {},
): UsePayoffMatrixResult {
  const [data, setData] = useState<PayoffMatrix | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(Boolean(roomId));

  // Stable dep keys so the effect re-runs only when the strategy sets change.
  const ourKey = opts.ourMoves ? opts.ourMoves.join('|') : '';
  const advKey = opts.adversaryStates ? opts.adversaryStates.join('|') : '';

  useEffect(() => {
    let cancelled = false;
    if (!roomId) {
      setData(null);
      setError(null);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    fetchPayoffMatrix(
      roomId,
      ourKey ? ourKey.split('|') : undefined,
      advKey ? advKey.split('|') : undefined,
    )
      .then((m) => {
        if (!cancelled) {
          setData(m);
          setIsLoading(false);
        }
      })
      .catch((e: Error) => {
        if (!cancelled) {
          setData(null);
          setError(e);
          setIsLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [roomId, ourKey, advKey]);

  return { data, error, isLoading };
}
