import { useCallback, useEffect, useState } from 'react';
import { Trash2 } from 'lucide-react';
import { warRoomApi, type WarRoom } from '../../../api';

interface Props {
  onOpen: (id: string) => void;
}

function hasToken(): boolean {
  if (typeof window === 'undefined') return false;
  return !!window.localStorage.getItem('mz_auth_token');
}

export default function WarRoomsList({ onOpen }: Props) {
  const authed = hasToken();
  const [rooms, setRooms] = useState<WarRoom[]>([]);
  const [loading, setLoading] = useState(authed);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (!authed) return;
    setLoading(true);
    try {
      const r = await warRoomApi.list();
      setRooms(r.war_rooms);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [authed]);

  useEffect(() => { void reload(); }, [reload]);

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
          className="text-[10px] uppercase font-medium"
          style={{ color: 'var(--color-ink-4)', letterSpacing: '0.06em' }}
        >
          Your war rooms ({rooms.length})
        </div>
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
          No war rooms yet. Open a signal and click <strong>Simulate in War Room</strong> to start one.
        </div>
      ) : (
        <div className="space-y-2">
          {rooms.map((r) => (
            <div
              key={r.id}
              className="group relative"
              style={{
                padding: '14px 16px',
                borderRadius: '6px',
                border: '1px solid var(--color-line)',
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
              </button>
              {r.status === 'active' && (
                <button
                  type="button"
                  onClick={(e) => handleDelete(e, r.id, r.title)}
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
          ))}
        </div>
      )}
    </div>
  );
}
