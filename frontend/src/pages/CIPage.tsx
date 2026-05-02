import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { PRODUCT_NAME } from '../brand';
import DigestTab from '../components/ci/DigestTab';
import SignalsTab from '../components/ci/SignalsTab';
import WatchlistTab from '../components/ci/WatchlistTab';
import WarRoomView from '../components/ci/war/WarRoomView';
import WarRoomsList from '../components/ci/war/WarRoomsList';

type TabKey = 'digest' | 'signals' | 'watchlist' | 'rooms' | 'reviewer';

const ALL_TABS: Array<{ key: TabKey; label: string; enterprise?: boolean }> = [
  { key: 'digest',    label: 'Digest' },
  { key: 'signals',   label: 'Signals' },
  { key: 'watchlist', label: 'Watchlist' },
  { key: 'rooms',     label: 'War Rooms' },
  { key: 'reviewer',  label: 'Reviewer', enterprise: true },
];

function getRole(): string | null {
  if (typeof window === 'undefined') return null;
  return window.localStorage.getItem('mz_auth_role');
}

export default function CIPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const role = getRole();
  const isEnterprise = role === 'enterprise';
  const tabs = ALL_TABS.filter((t) => !t.enterprise || isEnterprise);

  const initialTab = (params.get('tab') as TabKey) || 'digest';
  const [tab, setTabState] = useState<TabKey>(initialTab);
  const activeRoom = params.get('room');

  // Sync tab to URL
  const setTab = (t: TabKey) => {
    setTabState(t);
    const next = new URLSearchParams(params);
    next.set('tab', t);
    next.delete('room');
    setParams(next, { replace: true });
  };

  const openWarRoom = (id: string, signalKbq?: string) => {
    const next = new URLSearchParams(params);
    next.set('tab', 'rooms');
    next.set('room', id);
    if (signalKbq) {
      next.set('signal_kbq', signalKbq);
    } else {
      next.delete('signal_kbq');
    }
    setParams(next, { replace: false });
    setTabState('rooms');
  };

  const closeWarRoom = () => {
    const next = new URLSearchParams(params);
    next.delete('room');
    next.set('tab', 'rooms');
    setParams(next, { replace: false });
  };

  // If room param disappears (back button), no-op — body already conditions on it
  useEffect(() => {
    const t = (params.get('tab') as TabKey) || 'digest';
    if (t !== tab) setTabState(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  return (
    <div className="flex flex-col h-screen" style={{ background: 'var(--color-surface)' }}>
      {/* Header */}
      <header
        className="shrink-0 flex items-center gap-4"
        style={{
          height: '52px',
          padding: '0 20px',
          borderBottom: '1px solid var(--color-line)',
          background: 'var(--color-surface)',
        }}
      >
        <button
          type="button"
          onClick={() => navigate('/')}
          className="btn-icon"
          aria-label="Back"
          title="Back"
        >
          <ArrowLeft size={15} />
        </button>
        <span
          className="font-display text-[15px] font-light"
          style={{ color: 'var(--color-ink-3)', letterSpacing: '-0.01em' }}
        >
          {PRODUCT_NAME}
        </span>
        <div className="h-4 w-px" style={{ background: 'var(--color-line)' }} />
        <span className="font-display text-[15px]" style={{ color: 'var(--color-ink)' }}>
          Competitive Intelligence
        </span>

        <nav
          className="ml-6 flex items-center gap-0.5 rounded-[10px]"
          style={{ padding: '4px', background: 'var(--color-surface-2)' }}
        >
          {tabs.map((t) => (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className="text-[12px] font-medium"
              style={{
                padding: '5px 12px',
                borderRadius: '6px',
                background: tab === t.key ? 'var(--color-surface)' : 'transparent',
                color: tab === t.key ? 'var(--color-ink)' : 'var(--color-ink-3)',
                boxShadow: tab === t.key ? 'var(--shadow-xs)' : 'none',
              }}
            >
              {t.label}
            </button>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-3">
          <a
            href="/connectors"
            className="text-[11px]"
            style={{ color: 'var(--color-ink-4)' }}
          >
            Connectors →
          </a>
          {role && (
            <span
              className="text-[10px] uppercase font-medium"
              style={{
                padding: '3px 8px',
                borderRadius: '4px',
                background: 'var(--color-surface-2)',
                color: 'var(--color-ink-3)',
                letterSpacing: '0.06em',
              }}
            >
              {role}
            </span>
          )}
        </div>
      </header>

      {/* Body */}
      <div className="flex-1 overflow-hidden flex flex-col">
        {tab === 'digest' && <DigestTab />}
        {tab === 'signals' && <SignalsTab onOpenWarRoom={openWarRoom} />}
        {tab === 'watchlist' && <WatchlistTab onOpenWarRoom={openWarRoom} />}
        {tab === 'rooms' && (
          activeRoom
            ? <WarRoomView roomId={activeRoom} onClose={closeWarRoom} />
            : <WarRoomsList onOpen={openWarRoom} />
        )}
        {tab === 'reviewer' && isEnterprise && (
          <SignalsTab
            reviewerMode
            initialStatus="candidate"
            onOpenWarRoom={openWarRoom}
          />
        )}
      </div>
    </div>
  );
}
