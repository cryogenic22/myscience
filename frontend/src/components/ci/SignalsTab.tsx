import { useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { signalsApi, type ImpactTier, type Signal } from '../../api';
import KBQFilter from './KBQFilter';
import SignalsListPanel from './SignalsListPanel';
import SignalDetail from './SignalDetail';

interface Props {
  reviewerMode?: boolean;
  initialStatus?: 'candidate' | 'reviewed' | 'shipped';
  watchlistFilter?: Array<{ entity_type: string; entity_id: string }>;
  onOpenWarRoom?: (roomId: string, signalKbq?: string) => void;
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

  // PB-104 — kbq is multi-select, mirrored to `?kbq=financial,clinical` in the URL
  const [searchParams, setSearchParams] = useSearchParams();
  const kbq = useMemo<string[]>(() => {
    const raw = searchParams.get('kbq');
    if (!raw) return [];
    return Array.from(new Set(
      raw.split(',').map((s) => s.trim()).filter(Boolean),
    ));
  }, [searchParams]);

  const setKbq = (next: string[]) => {
    const dedup = Array.from(new Set(next.filter(Boolean)));
    setSearchParams(
      (prev) => {
        const sp = new URLSearchParams(prev);
        if (dedup.length === 0) sp.delete('kbq');
        else sp.set('kbq', dedup.join(','));
        return sp;
      },
      { replace: true },
    );
  };

  const reload = async () => {
    setLoading(true);
    setError(null);
    try {
      const params: Parameters<typeof signalsApi.list>[0] = { limit: 100 };
      if (initialStatus) params.status = initialStatus;
      if (impact !== 'all') params.impact = impact;
      if (kbq.length > 0) params.kbq = kbq;
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

  // Reload on filter changes (kbq comparison via stable serialized key)
  const kbqKey = kbq.join(',');
  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [impact, kbqKey, initialStatus]);

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
    <div className="flex-1 flex flex-col overflow-hidden" style={{ background: '#0a0b0e' }}>
      {/* Filter bar */}
      <div
        className="shrink-0 flex items-center gap-3 flex-wrap"
        style={{
          padding: '10px 16px',
          borderBottom: '1px solid #23262d',
          background: '#0a0b0e',
        }}
      >
        <select
          value={impact}
          onChange={(e) => setImpact(e.target.value as ImpactTier | 'all')}
          className="text-[12px]"
          style={{
            padding: '4px 8px',
            borderRadius: '6px',
            border: '1px solid #2c3038',
            background: '#12141a',
            color: '#e8eaed',
            fontFamily: "'JetBrains Mono', ui-monospace, monospace",
          }}
        >
          {IMPACT_OPTIONS.map((o) => (
            <option key={o.key} value={o.key}>{o.label}</option>
          ))}
        </select>
        <KBQFilter selected={kbq} onSelect={setKbq} />
        <span className="ml-auto" style={{ color: '#8a8f99', fontFamily: "'JetBrains Mono', ui-monospace, monospace", fontSize: 11, letterSpacing: '0.04em' }}>
          {loading ? 'LOADING…' : `${filtered.length} SIGNAL${filtered.length === 1 ? '' : 'S'}`}
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
            style={{ color: '#5a5f69', background: '#0a0b0e' }}
          >
            {filtered.length === 0 ? '' : 'Select a signal'}
          </div>
        )}
      </div>
    </div>
  );
}
