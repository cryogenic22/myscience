/**
 * Frame a signal as a Decision (the SENSE→FRAME step). Creates a Decision
 * Brief seeded from the signal, links it back to the signal for traceability,
 * and navigates into the decision workspace. Shared by the Sensing Feed and
 * the signal detail panel so "Frame" works the same everywhere.
 */
import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { decisionBriefsApi, type Signal } from '../api';

export interface UseFrameSignalResult {
  frame: (signal: Signal) => Promise<void>;
  framingId: string | null;
  error: string | null;
}

export function useFrameSignal(): UseFrameSignalResult {
  const navigate = useNavigate();
  const [framingId, setFramingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const frame = useCallback(async (signal: Signal) => {
    setFramingId(signal.id);
    setError(null);
    try {
      const brief = await decisionBriefsApi.create({
        // 'manual' — the user clicked Frame; trigger_signal_ids keeps the
        // link back to the originating signal for traceability.
        question: `${signal.headline} — how should we respond?`,
        trigger_kind: 'manual',
        trigger_signal_ids: [signal.id],
      });
      navigate(`/ci/decisions/${brief.brief_id}`);
    } catch (e) {
      setError(String((e as Error)?.message ?? e));
    } finally {
      setFramingId(null);
    }
  }, [navigate]);

  return { frame, framingId, error };
}
