import { useCallback, useEffect, useMemo, useState } from 'react';
import { Bell } from 'lucide-react';
import type { IntelligenceFeedItem } from '../../api';
import { api } from '../../api';
import { EventCard, DigestCard, groupEventsForDigest } from './EventCard';
import { EventDetailDrawer } from './EventDetailDrawer';

const SEVERITY_OPTIONS = ['all', 'critical', 'high', 'medium', 'low'] as const;
type ViewMode = 'all' | 'digest';

export interface IntelligenceFeedProps {
  onAskInChat?: (question: string) => void;
}

export function IntelligenceFeed({ onAskInChat }: IntelligenceFeedProps) {
  const [items, setItems] = useState<IntelligenceFeedItem[]>([]);
  const [total, setTotal] = useState(0);
  const [severity, setSeverity] = useState<string>('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<IntelligenceFeedItem | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('all');

  const fetchFeed = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params: {limit: number; offset: number; severity?: string} = { limit: 50, offset: 0 };
      if (severity !== 'all') params.severity = severity;
      const result = await api.intelligenceFeed(params);
      setItems(result.items);
      setTotal(result.total);
    } catch (e) {
      // A failed feed load must NOT read as "All clear" — a down pipeline is not
      // a calm, empty inbox. Surface it distinctly.
      setError(e instanceof Error ? e.message : 'Failed to load the intelligence feed');
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

  // Digest grouping
  const digestGroups = useMemo(() => groupEventsForDigest(items), [items]);
  const digestGroupedIds = useMemo(() => {
    const ids = new Set<string>();
    for (const group of digestGroups) {
      for (const item of group.items) {
        ids.add(item.event_id);
      }
    }
    return ids;
  }, [digestGroups]);

  // Items that are NOT part of any digest group (singletons or older than 24h)
  const ungroupedItems = useMemo(() => {
    if (viewMode === 'all') return items;
    return items.filter(i => !digestGroupedIds.has(i.event_id));
  }, [items, digestGroupedIds, viewMode]);

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

        {/* Severity filter + view mode toggle */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
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

          <div style={{ display: 'flex', gap: '2px' }}>
            {(['all', 'digest'] as const).map(mode => (
              <button
                key={mode}
                type="button"
                onClick={() => setViewMode(mode)}
                style={{
                  padding: '4px 10px',
                  borderRadius: '6px',
                  border: 'none',
                  fontSize: '11px',
                  fontWeight: viewMode === mode ? 600 : 400,
                  fontFamily: 'var(--font-body)',
                  cursor: 'pointer',
                  background: viewMode === mode ? 'var(--color-accent-soft)' : 'transparent',
                  color: viewMode === mode ? 'var(--color-accent)' : 'var(--color-ink-3)',
                  transition: 'all 0.15s',
                }}
              >
                {mode === 'all' ? 'All events' : 'Digest'}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Scrollable list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '8px 16px' }}>
        {loading ? (
          <div style={{ padding: '40px 0', textAlign: 'center', color: 'var(--color-ink-4)', fontSize: '13px' }}>
            Loading feed...
          </div>
        ) : error ? (
          <div
            role="alert"
            data-testid="feed-error"
            style={{
              display: 'flex', flexDirection: 'column', alignItems: 'center',
              justifyContent: 'center', padding: '60px 24px', gap: '12px',
            }}
          >
            <Bell size={32} style={{ color: 'var(--color-red)', opacity: 0.7 }} />
            <span style={{ fontSize: '14px', color: 'var(--color-ink-2)', textAlign: 'center' }}>
              Couldn't load the intelligence feed
            </span>
            <span style={{ fontSize: '12px', color: 'var(--color-ink-4)', textAlign: 'center' }}>
              {error}
            </span>
            <button
              type="button"
              onClick={() => void fetchFeed()}
              className="btn btn-xs btn-secondary"
              style={{ borderRadius: '6px', marginTop: '4px' }}
            >
              Retry
            </button>
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
            {/* Digest groups (only in digest mode) */}
            {viewMode === 'digest' && digestGroups.map(group => (
              <DigestCard
                key={group.key}
                group={group}
                onClick={setSelectedEvent}
                onDismiss={handleDismiss}
                onAskInChat={onAskInChat}
              />
            ))}

            {/* Individual cards */}
            {(viewMode === 'all' ? items : ungroupedItems).map(item => (
              <EventCard
                key={item.event_id}
                item={item}
                onClick={setSelectedEvent}
                onDismiss={handleDismiss}
                onAskInChat={onAskInChat}
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
