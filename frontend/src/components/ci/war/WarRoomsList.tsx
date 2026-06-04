import { useCallback, useEffect, useMemo, useState } from 'react';
import { Trash2, Search, MessageSquare } from 'lucide-react';
import { warRoomApi, type WarRoom, type WarRoomListFilters } from '../../../api';

interface Props {
  onOpen: (id: string) => void;
}

type FilterTab = 'all' | 'active' | 'closed' | 'archived';

const FILTER_TABS: { key: FilterTab; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'closed', label: 'Closed' },
  { key: 'archived', label: 'Archived' },
];

function hasToken(): boolean {
  if (typeof window === 'undefined') return false;
  return !!window.localStorage.getItem('mz_auth_token');
}

function tabToFilters(tab: FilterTab, q: string): WarRoomListFilters {
  const base: WarRoomListFilters = {};
  if (q.trim()) base.q = q.trim();
  switch (tab) {
    case 'active':
      return { ...base, status: 'active', archived: false };
    case 'closed':
      return { ...base, status: 'closed', archived: false };
    case 'archived':
      return { ...base, archived: true };
    case 'all':
    default:
      return base;
  }
}

export default function WarRoomsList({ onOpen }: Props) {
  const authed = hasToken();
  const [tab, setTab] = useState<FilterTab>('active');
  const [q, setQ] = useState('');
  const [rooms, setRooms] = useState<WarRoom[]>([]);
  const [loading, setLoading] = useState(authed);
  const [error, setError] = useState<string | null>(null);
  // IX04b — standalone war-game launch (no engagement / no scenario needed).
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [createBusy, setCreateBusy] = useState(false);

  const filters = useMemo(() => tabToFilters(tab, q), [tab, q]);

  const reload = useCallback(async () => {
    if (!authed) return;
    setLoading(true);
    try {
      const r = await warRoomApi.list(filters);
      setRooms(r.war_rooms);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [authed, filters]);

  useEffect(() => { void reload(); }, [reload]);

  const submitCreate = async () => {
    const title = newTitle.trim();
    if (!title || createBusy) return;
    setCreateBusy(true);
    setError(null);
    try {
      const room = await warRoomApi.create({ title });
      setShowCreate(false);
      setNewTitle('');
      onOpen(room.id);   // jump straight into the new room (guided default)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCreateBusy(false);
    }
  };

  const handleDelete = async (e: React.MouseEvent, id: string, title: string) => {
    e.stopPropagation();
    if (!window.confirm(`Close war room "${title}"? It stays in the DB but is hidden from active lists.`)) {
      return;
    }
    try {
      await warRoomApi.remove(id);
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
          Log in (viewer or above) to view your war rooms. Or open a signal in
          the Signals tab and click <strong>Simulate in War Room</strong> to
          create your first one.
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto" style={{ padding: '24px 32px' }}>
      <div className="mb-4">
        <div
          className="text-[10px] uppercase font-medium mb-3"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em' }}
        >
          Your war rooms
        </div>

        {/* Filter tabs + search */}
        <div className="flex items-center gap-3 flex-wrap">
          <div className="flex items-center gap-1">
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

          <button
            type="button"
            data-testid="new-war-game"
            onClick={() => setShowCreate((v) => !v)}
            className="text-[11px] uppercase font-medium ml-auto"
            style={{
              padding: '6px 14px',
              borderRadius: '6px',
              border: 'none',
              background: 'var(--color-accent)',
              color: 'var(--color-bg)',
              letterSpacing: '0.06em',
              cursor: 'pointer',
            }}
          >
            + New war game
          </button>

          <div
            className="flex items-center gap-1"
            style={{
              padding: '4px 10px',
              borderRadius: '6px',
              border: '1px solid var(--color-line)',
              background: 'var(--color-surface)',
              minWidth: '220px',
            }}
          >
            <Search size={12} style={{ color: 'var(--color-ink-4)' }} />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search title…"
              className="text-[12px] flex-1 bg-transparent"
              style={{ border: 'none', outline: 'none', color: 'var(--color-ink)' }}
            />
            {q && (
              <button
                type="button"
                onClick={() => setQ('')}
                className="text-[10px]"
                style={{
                  background: 'transparent',
                  color: 'var(--color-ink-4)',
                  border: 'none',
                  cursor: 'pointer',
                  padding: '0 4px',
                }}
                aria-label="Clear search"
              >
                ✕
              </button>
            )}
          </div>
        </div>

        {showCreate && (
          <div
            data-testid="new-war-game-form"
            className="flex items-center gap-2 mt-3"
          >
            <input
              autoFocus
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') void submitCreate(); }}
              placeholder="War game title — e.g. Wegovy vs Zepbound, EU launch"
              className="text-[12px] flex-1"
              style={{
                padding: '7px 12px', borderRadius: '6px',
                border: '1px solid var(--color-line)', background: 'var(--color-surface)',
                color: 'var(--color-ink)', outline: 'none', maxWidth: '420px',
              }}
            />
            <button
              type="button"
              onClick={() => void submitCreate()}
              disabled={createBusy || !newTitle.trim()}
              className="text-[11px] uppercase font-medium"
              style={{
                padding: '7px 14px', borderRadius: '6px', border: 'none',
                background: createBusy || !newTitle.trim() ? 'var(--color-surface-2)' : 'var(--color-ink)',
                color: createBusy || !newTitle.trim() ? 'var(--color-ink-4)' : 'var(--color-bg)',
                letterSpacing: '0.06em',
                cursor: createBusy || !newTitle.trim() ? 'default' : 'pointer',
              }}
            >
              {createBusy ? 'Creating…' : 'Create'}
            </button>
            <button
              type="button"
              onClick={() => { setShowCreate(false); setNewTitle(''); }}
              className="text-[11px]"
              style={{ padding: '7px 10px', background: 'transparent', border: 'none', color: 'var(--color-ink-4)', cursor: 'pointer' }}
            >
              Cancel
            </button>
          </div>
        )}
      </div>

      {loading ? (
        <div className="text-[13px]" style={{ color: 'var(--color-ink-4)' }}>
          Loading…
        </div>
      ) : error ? (
        <div className="text-[13px]" style={{ color: '#B91C1C' }}>
          {error}
        </div>
      ) : rooms.length === 0 ? (
        <div className="text-[13px]" style={{ color: 'var(--color-ink-4)' }}>
          {q || tab !== 'active'
            ? 'No war rooms match this filter.'
            : 'No war rooms yet. Open a signal and click Simulate in War Room to start one.'}
        </div>
      ) : (
        <div className="space-y-2">
          <div
            className="text-[10px] uppercase mb-1"
            style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}
          >
            {rooms.length} room{rooms.length === 1 ? '' : 's'}
          </div>
          {rooms.map((r) => (
            <RoomCard
              key={r.id}
              room={r}
              onOpen={onOpen}
              onDelete={handleDelete}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function RoomCard({
  room,
  onOpen,
  onDelete,
}: {
  room: WarRoom;
  onOpen: (id: string) => void;
  onDelete: (e: React.MouseEvent, id: string, title: string) => void;
}) {
  const r = room;
  const roundCount = r.rounds?.length ?? 0;
  const commentCount = r.comments?.length ?? 0;
  return (
    <div
      className="mz-elevated group relative"
      style={{
        padding: '14px 16px',
        borderRadius: 'var(--radius-card)',
        background: 'var(--color-surface)',
      }}
    >
      <button
        type="button"
        onClick={() => onOpen(r.id)}
        className="w-full text-left"
        style={{ background: 'transparent', border: 'none' }}
      >
        <div className="flex items-center gap-2 mb-1">
          <span
            className="text-[10px] uppercase font-medium"
            style={{
              padding: '2px 7px',
              borderRadius: '4px',
              background: r.status === 'active' ? '#DCFCE7' : 'var(--color-surface-2)',
              color: r.status === 'active' ? '#15803D' : 'var(--color-ink-4)',
              letterSpacing: '0.05em',
            }}
          >
            {r.status}
          </span>
          {r.archived_at && (
            <span
              className="text-[10px] uppercase font-medium"
              style={{
                padding: '2px 7px',
                borderRadius: '4px',
                background: '#F3E8FF',
                color: '#6D28D9',
                letterSpacing: '0.05em',
              }}
              title={`Archived ${new Date(r.archived_at).toLocaleDateString()}`}
            >
              archived
            </span>
          )}
          <span
            className="text-[10px] uppercase"
            style={{ color: 'var(--color-ink-4)', letterSpacing: '0.05em' }}
          >
            {r.game_phase}
          </span>
          <span
            className="ml-auto text-[11px]"
            style={{ color: 'var(--color-ink-4)' }}
          >
            {r.created_at ? new Date(r.created_at).toLocaleDateString() : ''}
          </span>
        </div>
        <div
          className="text-[13px] font-medium"
          style={{ color: 'var(--color-ink)' }}
        >
          {r.title}
        </div>
        {r.primary_entity_name && (
          <div className="text-[11px] mt-1" style={{ color: 'var(--color-ink-4)' }}>
            {r.primary_entity_name}
          </div>
        )}
        {commentCount > 0 && (
          <div
            className="text-[10px] mt-2 inline-flex items-center gap-1"
            style={{ color: 'var(--color-ink-4)' }}
          >
            <MessageSquare size={10} />
            {commentCount} comment{commentCount === 1 ? '' : 's'}
            {roundCount > 0 && ` · ${roundCount} round${roundCount === 1 ? '' : 's'}`}
          </div>
        )}
      </button>
      {r.status === 'active' && !r.archived_at && (
        <button
          type="button"
          onClick={(e) => onDelete(e, r.id, r.title)}
          className="absolute top-3 right-3 opacity-0 group-hover:opacity-100 transition-opacity"
          style={{
            padding: '4px',
            borderRadius: '4px',
            background: 'transparent',
            color: 'var(--color-ink-4)',
          }}
          title="Close war room"
          aria-label="Close war room"
        >
          <Trash2 size={13} />
        </button>
      )}
    </div>
  );
}
