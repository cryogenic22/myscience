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
  if (ourMoves.length !== 2) {
    throw new Error(`adaptPayoffResponse: ourMoves must be exactly 2, got ${ourMoves.length}`);
  }
  if (adversaryStates.length !== 2) {
    throw new Error(`adaptPayoffResponse: adversaryStates must be exactly 2, got ${adversaryStates.length}`);
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

  let recommended: { row_id: string; col_id: string } | null = null;
  const rc = wire?.recommended_cell;
  if (Array.isArray(rc) && rc.length === 2 && rows[rc[0]] && cols[rc[1]]) {
    recommended = { row_id: rows[rc[0]].id, col_id: cols[rc[1]].id };
  }

  return {
    room_id: roomId,
    rows,
    cols,
    cells,
    recommended_cell: recommended,
  };
}

async function fetchPayoffMatrix(roomId: string): Promise<PayoffMatrix> {
  const body = {
    our_moves: DEFAULT_OUR_MOVES,
    adversary_states: DEFAULT_ADVERSARY_STATES,
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
  return adaptPayoffResponse(wire, roomId, DEFAULT_OUR_MOVES, DEFAULT_ADVERSARY_STATES);
}

export function usePayoffMatrix(roomId: string | null | undefined): UsePayoffMatrixResult {
  const [data, setData] = useState<PayoffMatrix | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(Boolean(roomId));

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
    fetchPayoffMatrix(roomId)
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
  }, [roomId]);

  return { data, error, isLoading };
}
