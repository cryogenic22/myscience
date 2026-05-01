import { useCallback, useEffect, useState } from 'react';
import { Trash2, Plus } from 'lucide-react';
import { watchlistApi, type WatchlistEntry } from '../../api';
import SignalsTab from './SignalsTab';

const ENTITY_TYPES = [
  { value: 'company', label: 'Company' },
  { value: 'drug', label: 'Drug' },
  { value: 'mechanism', label: 'Mechanism' },
  { value: 'therapeutic_area', label: 'Therapeutic area' },
  { value: 'trial', label: 'Trial' },
];

function hasToken(): boolean {
  if (typeof window === 'undefined') return false;
  return !!window.localStorage.getItem('mz_auth_token');
}

export default function WatchlistTab() {
  const authed = hasToken();
  const [entries, setEntries] = useState<WatchlistEntry[]>([]);
  const [loading, setLoading] = useState(authed);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [newEntityType, setNewEntityType] = useState('company');
  const [newEntityId, setNewEntityId] = useState('');
  const [newLabel, setNewLabel] = useState('');

  const reload = useCallback(async () => {
    if (!authed) return;
    setLoading(true);
    try {
      const r = await watchlistApi.list();
      setEntries(r.entries);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [authed]);

  useEffect(() => { void reload(); }, [reload]);

  const handleAdd = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newEntityId.trim()) return;
    try {
      await watchlistApi.add({
        entity_type: newEntityType,
        entity_id: newEntityId.trim(),
        label: newLabel.trim() || undefined,
      });
      setNewEntityId('');
      setNewLabel('');
      setAdding(false);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const handleRemove = async (id: string) => {
    try {
      await watchlistApi.remove(id);
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  if (!authed) {
    return (
      <div className="flex-1 flex items-center justify-center" style={{ padding: '40px' }}>
        <div
          className="text-[13px] text-center max-w-md"
          style={{ color: 'var(--color-ink-3)' }}
        >
          Log in (viewer or above) to manage your watchlist. The watchlist filters
          the Signals view to a specific set of companies, drugs, mechanisms, or
          therapeutic areas you want to track.
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Watchlist management */}
      <div
        className="shrink-0"
        style={{
          padding: '14px 20px',
          borderBottom: '1px solid var(--color-line)',
          background: 'var(--color-surface-2)',
        }}
      >
        <div className="flex items-center justify-between mb-3">
          <div
            className="text-[10px] uppercase font-medium"
            style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em' }}
          >
            Tracked entities ({entries.length})
          </div>
          <button
            type="button"
            onClick={() => setAdding((v) => !v)}
            className="text-[12px] flex items-center gap-1"
            style={{
              padding: '4px 10px',
              borderRadius: '6px',
              background: adding ? 'var(--color-surface)' : 'var(--color-accent)',
              color: adding ? 'var(--color-ink)' : 'white',
              border: adding ? '1px solid var(--color-line)' : 'none',
            }}
          >
            <Plus size={12} />
            {adding ? 'Cancel' : 'Add'}
          </button>
        </div>

        {adding && (
          <form onSubmit={handleAdd} className="flex items-center gap-2 mb-3">
            <select
              value={newEntityType}
              onChange={(e) => setNewEntityType(e.target.value)}
              className="text-[12px]"
              style={{
                padding: '5px 8px',
                borderRadius: '6px',
                border: '1px solid var(--color-line)',
                background: 'var(--color-surface)',
                color: 'var(--color-ink)',
              }}
            >
              {ENTITY_TYPES.map((t) => (
                <option key={t.value} value={t.value}>{t.label}</option>
              ))}
            </select>
            <input
              value={newEntityId}
              onChange={(e) => setNewEntityId(e.target.value)}
              placeholder="entity_id (UUID)"
              className="text-[12px] font-mono"
              style={{
                padding: '5px 8px',
                borderRadius: '6px',
                border: '1px solid var(--color-line)',
                background: 'var(--color-surface)',
                color: 'var(--color-ink)',
                minWidth: '280px',
              }}
              required
            />
            <input
              value={newLabel}
              onChange={(e) => setNewLabel(e.target.value)}
              placeholder="display label"
              className="text-[12px]"
              style={{
                padding: '5px 8px',
                borderRadius: '6px',
                border: '1px solid var(--color-line)',
                background: 'var(--color-surface)',
                color: 'var(--color-ink)',
                flex: 1,
              }}
            />
            <button
              type="submit"
              className="text-[12px] font-medium"
              style={{
                padding: '5px 14px',
                borderRadius: '6px',
                background: 'var(--color-accent)',
                color: 'white',
                border: 'none',
              }}
            >
              Add
            </button>
          </form>
        )}

        {entries.length === 0 ? (
          <div className="text-[12px]" style={{ color: 'var(--color-ink-4)' }}>
            No tracked entities yet. Add a company, drug, or mechanism to filter
            your signals.
          </div>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {entries.map((e) => (
              <span
                key={e.id}
                className="inline-flex items-center gap-1.5 text-[12px]"
                style={{
                  padding: '4px 4px 4px 10px',
                  borderRadius: '14px',
                  background: 'var(--color-surface)',
                  border: '1px solid var(--color-line)',
                  color: 'var(--color-ink)',
                }}
              >
                <span>{e.label || e.entity_id.slice(0, 8)}</span>
                <span
                  className="text-[10px]"
                  style={{ color: 'var(--color-ink-4)' }}
                >
                  {e.entity_type}
                </span>
                <button
                  type="button"
                  onClick={() => handleRemove(e.id)}
                  className="rounded-full"
                  style={{
                    padding: '3px',
                    background: 'transparent',
                    color: 'var(--color-ink-4)',
                  }}
                  title="Remove"
                >
                  <Trash2 size={11} />
                </button>
              </span>
            ))}
          </div>
        )}

        {error && (
          <div className="text-[11px] mt-2" style={{ color: '#B91C1C' }}>
            {error}
          </div>
        )}
      </div>

      {/* Filtered signals */}
      {loading ? (
        <div
          className="flex-1 flex items-center justify-center text-[13px]"
          style={{ color: 'var(--color-ink-4)' }}
        >
          Loading watchlist…
        </div>
      ) : (
        <SignalsTab
          watchlistFilter={entries.map((e) => ({
            entity_type: e.entity_type,
            entity_id: e.entity_id,
          }))}
        />
      )}
    </div>
  );
}
