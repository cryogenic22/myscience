import { useEffect, useMemo, useState } from 'react';
import { signalsApi, type ImpactTier, type Signal } from '../../api';
import KBQFilter from './KBQFilter';
import SignalsListPanel from './SignalsListPanel';
import SignalDetail from './SignalDetail';

interface Props {
  reviewerMode?: boolean;
  initialStatus?: 'candidate' | 'reviewed' | 'shipped';
  watchlistFilter?: Array<{ entity_type: string; entity_id: string }>;
  onOpenWarRoom?: (roomId: string) => void;
}

const IMPACT_OPTIONS: Array<{ key: ImpactTier | 'all'; label: string }> = [
  { key: 'all', label: 'All impact' },
  { key: 'high', label: 'High' },
  { key: 'medium', label: 'Medium' },
  { key: 'low', label: 'Low' },
];

export default function SignalsTab({
  reviewerMode = false,
  initialStatus,
  watchlistFilter,
  onOpenWarRoom,
}: Props) {
  const [signals, setSignals] = useState<Signal[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<Signal | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [impact, setImpact] = useState<ImpactTier | 'all'>('all');
  const [kbq, setKbq] = useState<string | null>(null);

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Parameters<typeof signalsApi.list>[0] = { limit: 100 };
      if (initialStatus) params.status = initialStatus;
      if (impact !== 'all') params.impact = impact;
      if (kbq) params.kbq = kbq;
      const r = await signalsApi.list(params);
      setSignals(r.signals);
      if (r.signals.length > 0 && !selectedId) {
        setSelectedId(r.signals[0].id);
      } else if (r.signals.length === 0) {
        setSelectedId(null);
        setDetail(null);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  // Reload on filter changes
  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [impact, kbq, initialStatus]);

  // Load detail when selection changes
  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      return;
    }
    void signalsApi.detail(selectedId).then(setDetail).catch(() => setDetail(null));
  }, [selectedId]);

  const filtered = useMemo(() => {
    if (!watchlistFilter || watchlistFilter.length === 0) return signals;
    const set = new Set(watchlistFilter.map((w) => `${w.entity_type}:${w.entity_id}`));
    return signals.filter(
      (s) => s.primary_entity_type && s.primary_entity_id
        && set.has(`${s.primary_entity_type}:${s.primary_entity_id}`),
    );
  }, [signals, watchlistFilter]);

  const emptyMessage = (
    <div className="space-y-3">
      <div className="text-[13px]" style={{ color: 'var(--color-ink-2)' }}>
        {reviewerMode
          ? 'No candidates awaiting review.'
          : watchlistFilter && watchlistFilter.length > 0
          ? 'No signals match your watchlist filter.'
          : 'No signals yet.'}
      </div>
      <div className="text-[12px]" style={{ color: 'var(--color-ink-4)' }}>
        The SPEC-015 signal pipeline (clustering, KBQ scoring, 8-K parser) is
        still being built. Once it lands, dedup&apos;d signals will appear here.
        Until then the <strong>Digest</strong> tab shows raw market events from{' '}
        <a
          href="/connectors"
          className="underline"
          style={{ color: 'var(--color-accent)' }}
        >
          connected sources
        </a>
        .
      </div>
    </div>
  );

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Filter bar */}
      <div
        className="shrink-0 flex items-center gap-3 flex-wrap"
        style={{
          padding: '10px 16px',
          borderBottom: '1px solid var(--color-line)',
          background: 'var(--color-surface)',
        }}
      >
        <select
          value={impact}
          onChange={(e) => setImpact(e.target.value as ImpactTier | 'all')}
          className="text-[12px]"
          style={{
            padding: '4px 8px',
            borderRadius: '6px',
            border: '1px solid var(--color-line)',
            background: 'var(--color-surface)',
            color: 'var(--color-ink)',
          }}
        >
          {IMPACT_OPTIONS.map((o) => (
            <option key={o.key} value={o.key}>{o.label}</option>
          ))}
        </select>
        <KBQFilter selected={kbq} onSelect={setKbq} />
        <span className="ml-auto text-[11px]" style={{ color: 'var(--color-ink-4)' }}>
          {loading ? 'Loading…' : `${filtered.length} signal${filtered.length === 1 ? '' : 's'}`}
        </span>
      </div>

      {error && (
        <div
          className="text-[12px]"
          style={{ padding: '10px 16px', color: '#B91C1C' }}
        >
          {error}
        </div>
      )}

      <div className="flex flex-1 overflow-hidden">
        <SignalsListPanel
          signals={filtered}
          selectedId={selectedId}
          onSelect={setSelectedId}
          emptyMessage={emptyMessage}
        />
        {detail ? (
          <SignalDetail
            signal={detail}
            reviewerMode={reviewerMode}
            onReviewed={() => void reload()}
            onOpenWarRoom={onOpenWarRoom}
          />
        ) : (
          <div
            className="flex-1 flex items-center justify-center text-[13px]"
            style={{ color: 'var(--color-ink-4)' }}
          >
            {filtered.length === 0 ? '' : 'Select a signal'}
          </div>
        )}
      </div>
    </div>
  );
}
