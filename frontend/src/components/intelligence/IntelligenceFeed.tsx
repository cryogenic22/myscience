import { useCallback, useEffect, useState } from 'react';
import { Bell } from 'lucide-react';
import type { IntelligenceFeedItem } from '../../api';
import { api } from '../../api';
import { EventCard } from './EventCard';
import { EventDetailDrawer } from './EventDetailDrawer';

const SEVERITY_OPTIONS = ['all', 'critical', 'high', 'medium', 'low'] as const;

export function IntelligenceFeed() {
  const [items, setItems] = useState<IntelligenceFeedItem[]>([]);
  const [total, setTotal] = useState(0);
  const [severity, setSeverity] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [selectedEvent, setSelectedEvent] = useState<IntelligenceFeedItem | null>(null);

  const fetchFeed = useCallback(async () => {
    setLoading(true);
    try {
      const params: {limit: number; offset: number; severity?: string} = { limit: 50, offset: 0 };
      if (severity !== 'all') params.severity = severity;
      const result = await api.intelligenceFeed(params);
      setItems(result.items);
      setTotal(result.total);
    } catch {
      // Feed endpoint may not exist yet — show empty state
      setItems([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [severity]);

  useEffect(() => { void fetchFeed(); }, [fetchFeed]);

  const handleDismiss = useCallback(async (eventId: string) => {
    try {
      await api.intelligenceDismiss(eventId);
      setItems(prev => prev.filter(i => i.event_id !== eventId));
      setTotal(prev => Math.max(0, prev - 1));
    } catch {
      // Ignore dismiss failures
    }
  }, []);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        background: 'var(--color-bg)',
        fontFamily: 'var(--font-body)',
      }}
    >
      {/* Header + Filter bar */}
      <div
        style={{
          padding: '20px 24px 12px',
          borderBottom: '1px solid var(--color-line)',
          background: 'var(--color-surface)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
          <h2
            style={{
              fontSize: '18px',
              fontWeight: 600,
              color: 'var(--color-ink)',
              letterSpacing: '-0.02em',
            }}
          >
            Intelligence Feed
          </h2>
          <span style={{ fontSize: '12px', color: 'var(--color-ink-4)' }}>
            {total} event{total !== 1 ? 's' : ''}
          </span>
        </div>

        {/* Severity filter */}
        <div style={{ display: 'flex', gap: '4px' }}>
          {SEVERITY_OPTIONS.map(opt => (
            <button
              key={opt}
              type="button"
              onClick={() => setSeverity(opt)}
              style={{
                padding: '4px 12px',
                borderRadius: '6px',
                border: 'none',
                fontSize: '12px',
                fontWeight: severity === opt ? 600 : 400,
                fontFamily: 'var(--font-body)',
                cursor: 'pointer',
                background: severity === opt ? 'var(--color-accent-soft)' : 'transparent',
                color: severity === opt ? 'var(--color-accent)' : 'var(--color-ink-3)',
                textTransform: 'capitalize',
                transition: 'all 0.15s',
              }}
            >
              {opt}
            </button>
          ))}
        </div>
      </div>

      {/* Scrollable list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 16px' }}>
        {loading ? (
          <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--color-ink-4)', fontSize: '13px' }}>
            Loading feed...
          </div>
        ) : items.length === 0 ? (
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '60px 24px',
              gap: '12px',
            }}
          >
            <Bell size={32} style={{ color: 'var(--color-ink-4)', opacity: 0.5 }} />
            <span style={{ fontSize: '14px', color: 'var(--color-ink-3)' }}>
              All clear — no intelligence events
            </span>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', paddingTop: '4px' }}>
            {items.map(item => (
              <EventCard
                key={item.event_id}
                item={item}
                onClick={setSelectedEvent}
                onDismiss={handleDismiss}
              />
            ))}
          </div>
        )}
      </div>

      {/* Detail drawer */}
      <EventDetailDrawer
        item={selectedEvent}
        onClose={() => setSelectedEvent(null)}
        onDismiss={handleDismiss}
      />
    </div>
  );
}
