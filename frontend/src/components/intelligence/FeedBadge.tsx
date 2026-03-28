import { useEffect, useState } from 'react';
import { api } from '../../api';

interface FeedBadgeProps {
  /** Override polling interval in ms (default 30000) */
  pollInterval?: number;
}

export function FeedBadge({ pollInterval = 30_000 }: FeedBadgeProps) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let cancelled = false;

    async function fetchSummary() {
      try {
        const summary = await api.intelligenceFeedSummary(24);
        if (!cancelled) setCount(summary.total_unread);
      } catch {
        // Silently ignore — feed may not be available yet
      }
    }

    void fetchSummary();
    const timer = setInterval(() => void fetchSummary(), pollInterval);
    return () => { cancelled = true; clearInterval(timer); };
  }, [pollInterval]);

  if (count <= 0) return null;

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        minWidth: '16px',
        height: '16px',
        padding: '0 4px',
        borderRadius: '999px',
        fontSize: '10px',
        fontWeight: 700,
        fontFamily: 'var(--font-body)',
        background: 'var(--color-severity-critical)',
        color: '#fff',
        lineHeight: 1,
      }}
    >
      {count > 99 ? '99+' : count}
    </span>
  );
}
