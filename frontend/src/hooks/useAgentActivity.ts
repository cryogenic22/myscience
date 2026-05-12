/**
 * Loop #21 — Poll /agents/activity at the server-advised cadence.
 *
 * EventSource would have been more elegant but it doesn't carry auth
 * headers and Railway's edge buffers SSE; polling on a short interval
 * gives the same felt liveness with zero infra risk.
 */
import { useEffect, useState } from 'react';
import { agentsApi } from '../api';
import type { AgentActivity } from '../types/agents';

export interface UseAgentActivityResult {
  activities: AgentActivity[];
  loading: boolean;
  error: string | null;
}

const MIN_INTERVAL_MS = 3_000;
const MAX_INTERVAL_MS = 60_000;
const DEFAULT_INTERVAL_MS = 5_000;

export function useAgentActivity(): UseAgentActivityResult {
  const [activities, setActivities] = useState<AgentActivity[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const tick = async () => {
      try {
        const res = await agentsApi.activity();
        if (cancelled) return;
        setActivities(res.activities);
        setError(null);
        const nextSec = res.poll_after_seconds ?? 5;
        const nextMs = Math.max(
          MIN_INTERVAL_MS,
          Math.min(MAX_INTERVAL_MS, nextSec * 1000),
        );
        timer = setTimeout(tick, nextMs);
      } catch (e) {
        if (cancelled) return;
        setError(String((e as Error)?.message ?? e));
        // Back off to default on error so we don't hammer.
        timer = setTimeout(tick, DEFAULT_INTERVAL_MS);
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  return { activities, loading, error };
}
