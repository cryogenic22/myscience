import { useCallback, useEffect, useMemo, useState } from 'react';
import { decisionsApi, type Decision, type DecisionStatus, type DecisionListFilters } from '../../../api';
import DecisionCard from './DecisionCard';

interface Props {
  onOpenWarRoom?: (roomId: string) => void;
  onOpenDecision?: (decisionId: string) => void;
}

type FilterTab = 'open' | 'in_progress' | 'verified' | 'overdue' | 'all';

const FILTER_TABS: { key: FilterTab; label: string }[] = [
  { key: 'open',        label: 'Open' },
  { key: 'in_progress', label: 'In progress' },
  { key: 'overdue',     label: 'Overdue' },
  { key: 'verified',    label: 'Verified' },
  { key: 'all',         label: 'All' },
];

function hasToken(): boolean {
  if (typeof window === 'undefined') return false;
  return !!window.localStorage.getItem('mz_auth_token');
}

function tabToFilters(tab: FilterTab): DecisionListFilters {
  switch (tab) {
    case 'open':        return { status: 'open' as DecisionStatus };
    case 'in_progress': return { status: 'in_progress' as DecisionStatus };
    case 'verified':    return { status: 'verified' as DecisionStatus };
    case 'overdue':     return { overdue: true };
    case 'all':
    default:            return {};
  }
}

export default function DecisionsTab({ onOpenWarRoom, onOpenDecision }: Props) {
  const authed = hasToken();
  const [tab, setTab] = useState<FilterTab>('open');
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(authed);
  const [error, setError] = useState<string | null>(null);

  const filters = useMemo(() => tabToFilters(tab), [tab]);

  const reload = useCallback(async () => {
    if (!authed) return;
    setLoading(true);
    setError(null);
    try {
      const r = await decisionsApi.list(filters);
      setDecisions(r.decisions);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [authed, filters]);

  useEffect(() => { void reload(); }, [reload]);

  const handleChange = (updated: Decision) => {
    setDecisions((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
    // If the updated status no longer matches the filter, refresh from server
    if (filters.status && updated.status !== filters.status) {
      void reload();
    }
  };

  if (!authed) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ padding: '40px' }}>
        <div
          className="text-[13px] text-center max-w-md"
          style={{ color: 'var(--color-ink-3)' }}
        >
          Log in (viewer or above) to view your decisions. Promote a war-room
          round to commit your first decision.
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto" style={{ padding: '24px 32px' }}>
      <div className="mb-4">
        <div
          className="text-[10px] uppercase font-medium mb-1"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em' }}
        >
          Decision Ledger
        </div>
        <div
          className="text-[12px] mb-3"
          style={{ color: 'var(--color-ink-4)', fontStyle: 'italic' }}
        >
          Every committed decision is here, anchored to its source war room
          and waiting for outcome capture (Phase D).
        </div>

        <div className="flex items-center gap-1 flex-wrap">
          {FILTER_TABS.map((t) => {
            const active = tab === t.key;
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => setTab(t.key)}
                className="text-[11px]"
                style={{
                  padding: '5px 12px',
                  borderRadius: '6px',
                  border: `1px solid ${active ? 'var(--color-accent)' : 'var(--color-line)'}`,
                  background: active ? 'var(--color-accent)' : 'transparent',
                  color: active ? 'white' : 'var(--color-ink-3)',
                  cursor: 'pointer',
                }}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      {loading ? (
        <div className="text-[13px]" style={{ color: 'var(--color-ink-4)' }}>
          Loading decisions…
        </div>
      ) : error ? (
        <div className="text-[13px]" style={{ color: '#B91C1C' }}>
          {error}
        </div>
      ) : decisions.length === 0 ? (
        <div className="text-[13px]" style={{ color: 'var(--color-ink-4)' }}>
          {tab === 'all'
            ? 'No decisions yet. Open a war room, run a simulation, then promote a round to commit your first decision.'
            : `No ${tab.replace('_', ' ')} decisions.`}
        </div>
      ) : (
        <div className="space-y-2">
          <div
            className="text-[10px] uppercase mb-1"
            style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}
          >
            {decisions.length} decision{decisions.length === 1 ? '' : 's'}
          </div>
          {decisions.map((d) => (
            <DecisionCard
              key={d.id}
              decision={d}
              onChange={handleChange}
              onOpenWarRoom={onOpenWarRoom}
              onOpenDetail={onOpenDecision}
            />
          ))}
        </div>
      )}
    </div>
  );
}
