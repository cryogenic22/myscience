import { useEffect, useState } from 'react';
import type { PayoffMatrix } from '../types/payoff';

/**
 * PB-501 — Payoff matrix hook.
 *
 * Mock today; when BE-8 (`POST /war-rooms/{id}/payoff-matrix`)
 * merges, replace the body of `fetchPayoffMatrix` with a real call
 * and drop `is_mock` from the type.
 */

export interface UsePayoffMatrixResult {
  data: PayoffMatrix | null;
  error: Error | null;
  isLoading: boolean;
}

function buildMockMatrix(roomId: string): PayoffMatrix {
  return {
    room_id: roomId,
    rows: [
      { id: 'r-defend',  label: 'Adversary defends' },
      { id: 'r-cede',    label: 'Adversary cedes' },
    ],
    cols: [
      { id: 'c-launch',  label: 'We launch Q3' },
      { id: 'c-wait',    label: 'We wait Q4' },
    ],
    cells: [
      { row_id: 'r-defend', col_id: 'c-launch', outcome: 'lose',    delta_pct: -8.0, confidence: 0.72 },
      { row_id: 'r-defend', col_id: 'c-wait',   outcome: 'neutral', delta_pct: -1.5, confidence: 0.65 },
      { row_id: 'r-cede',   col_id: 'c-launch', outcome: 'win',     delta_pct: 12.0, confidence: 0.84 },
      { row_id: 'r-cede',   col_id: 'c-wait',   outcome: 'win',     delta_pct: 6.0,  confidence: 0.79 },
    ],
    recommended_cell: { row_id: 'r-cede', col_id: 'c-launch' },
    is_mock: true,
  };
}

async function fetchPayoffMatrix(roomId: string): Promise<PayoffMatrix> {
  // TODO(BE-8 / PR #59): swap for
  //   const res = await fetch(`${BASE}/war-rooms/${roomId}/payoff-matrix`, {
  //     method: 'POST',
  //     headers: { 'Content-Type': 'application/json' },
  //     body: JSON.stringify({}),
  //   });
  //   if (!res.ok) {
  //     const err = new Error(`${res.status} ${res.statusText}`) as Error & { status?: number };
  //     err.status = res.status;
  //     throw err;
  //   }
  //   return res.json();
  return buildMockMatrix(roomId);
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
