import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { ArrowLeft, Activity, LayoutGrid, Database, Target, ShieldAlert, LineChart, BrainCircuit, CheckSquare } from 'lucide-react';
import { PRODUCT_NAME } from '../brand';
import DigestTab from '../components/ci/DigestTab';
import SignalsTab from '../components/ci/SignalsTab';
import WatchlistTab from '../components/ci/WatchlistTab';
import WarRoomView from '../components/ci/war/WarRoomView';
import WarRoomsList from '../components/ci/war/WarRoomsList';
import DecisionsTab from '../components/ci/decisions/DecisionsTab';
import BriefsTab from '../components/ci/decisions/BriefsTab';
import InboxTab from '../components/ci/InboxTab';
import InsightsTab from '../components/ci/InsightsTab';
import AgentIdentityStrip from '../components/primitives/AgentIdentityStrip';
import AgentActivityFeed from '../components/primitives/AgentActivityFeed';
import { useAgentActivity } from '../hooks/useAgentActivity';
import { ThemeToggle } from '../components/primitives/ThemeToggle';
import { useDemoAutoLogin } from '../hooks/useDemoAutoLogin';

type TabKey = 'inbox' | 'digest' | 'signals' | 'watchlist' | 'rooms' | 'decisions' | 'insights' | 'reviewer';

const ALL_TABS: Array<{ key: TabKey; label: string; icon: any; enterprise?: boolean }> = [
  { key: 'inbox',     label: 'Sensing Feed', icon: Activity },
  { key: 'digest',    label: 'Daily Digest', icon: LayoutGrid },
  { key: 'signals',   label: 'Signals DB', icon: Database },
  { key: 'watchlist', label: 'Watchlist', icon: Target },
  { key: 'rooms',     label: 'War Rooms', icon: ShieldAlert },
  { key: 'decisions', label: 'Decisions', icon: CheckSquare },
  { key: 'insights',  label: 'Insights', icon: LineChart },
  { key: 'reviewer',  label: 'Reviewer', icon: BrainCircuit, enterprise: true },
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

  const initialTab = (params.get('tab') as TabKey) || (getRole() ? 'inbox' : 'digest');
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

  // Loop #16 — real JWT against the seeded enterprise demo account
  // (replaces the fake `'demo-token'` literal that was causing 401
  // cycles on every protected fetch).
  useDemoAutoLogin();

  useEffect(() => {
    const t = (params.get('tab') as TabKey) || (getRole() ? 'inbox' : 'digest');
    if (t !== tab) setTabState(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  return (
    <div className="flex h-screen w-full overflow-hidden flex-col md:flex-row" style={{ background: 'var(--color-bg)' }}>
      
      {/* Sidebar Navigation (Desktop) */}
      <aside className="hidden md:flex w-64 flex-col shrink-0 border-r" style={{ borderColor: 'var(--color-line)', background: 'var(--color-surface)' }}>
        
        {/* Header Branding */}
        <div className="flex items-center gap-3 h-16 px-6 border-b shrink-0" style={{ borderColor: 'var(--color-line)' }}>
          <button
            type="button"
            onClick={() => navigate('/')}
            className="text-[var(--color-ink-3)] hover:text-[var(--color-ink)] transition-colors"
          >
            <ArrowLeft size={16} />
          </button>
          <div className="flex flex-col flex-1">
            <span className="font-display mz-text-md font-medium tracking-tight" style={{ color: 'var(--color-ink)' }}>
              {PRODUCT_NAME}
            </span>
            <span className="mz-text-xs font-mono uppercase tracking-widest" style={{ color: 'var(--color-ink-4)' }}>
              Cockpit
            </span>
          </div>
          <ThemeToggle />
        </div>

        {/* Navigation Tabs */}
        <nav className="flex-1 overflow-y-auto py-6 px-4 flex flex-col gap-1">
          {tabs.map((t) => {
            const isActive = tab === t.key;
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => setTab(t.key)}
                className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition-all"
                style={{
                  background: isActive ? 'var(--color-surface-3)' : 'transparent',
                  color: isActive ? 'var(--color-ink)' : 'var(--color-ink-3)',
                  fontWeight: isActive ? 500 : 400,
                  boxShadow: isActive ? 'var(--shadow-sm)' : 'none'
                }}
              >
                <t.icon size={16} style={{ color: isActive ? 'var(--color-accent)' : 'inherit' }} />
                {t.label}
              </button>
            );
          })}
        </nav>

        {/* Global Telemetry & Footer */}
        <div className="p-4 border-t flex flex-col gap-4 shrink-0" style={{ borderColor: 'var(--color-line-2)' }}>
          {/* Loop #21 — live agent activity feed (polls /agents/activity).
              Falls back to the static identity strip if the API errors. */}
          <CIPageAgentSection />
          
          <div className="flex items-center justify-between">
            <a href="/connectors" className="mz-text-xs font-mono hover:underline transition-colors" style={{ color: 'var(--color-ink-4)' }}>
              Connectors →
            </a>
            {role && (
              <span className="mz-text-xs uppercase font-mono px-2 py-0.5 rounded" style={{ background: 'var(--color-surface-2)', color: 'var(--color-ink-3)' }}>
                {role}
              </span>
            )}
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <main className="flex-1 relative flex flex-col min-w-0 overflow-y-auto" style={{ background: 'var(--color-bg)' }}>
        <div className="w-full max-w-6xl mx-auto py-6 px-4 md:px-10 flex flex-col flex-1">
          {tab === 'inbox' && (
            <InboxTab
              onOpenDecision={(id) => navigate(`/ci/decisions/${id}`)}
              onOpenWarRoom={openWarRoom}
              onOpenSignals={() => setTab('signals')}
              onOpenInsights={() => setTab('insights')}
            />
          )}
          {tab === 'digest' && <DigestTab />}
          {tab === 'signals' && <SignalsTab onOpenWarRoom={openWarRoom} />}
          {tab === 'watchlist' && <WatchlistTab onOpenWarRoom={openWarRoom} />}
          {tab === 'rooms' && (
            activeRoom
              ? <WarRoomView roomId={activeRoom} onClose={closeWarRoom} />
              : <WarRoomsList onOpen={openWarRoom} />
          )}
          {tab === 'decisions' && (() => {
            // SPEC_030 Q1 sign-off — flag-gated escape hatch keeps the legacy
            // SPEC-021 DecisionsTab visible at `/ci?tab=decisions` when
            // mz_legacy_decisions === 'true'. Default routes to BriefsTab
            // (SPEC-023 contract).
            const useLegacy =
              typeof window !== 'undefined' &&
              window.localStorage.getItem('mz_legacy_decisions') === 'true';
            if (useLegacy) {
              return (
                <DecisionsTab
                  onOpenWarRoom={openWarRoom}
                  onOpenDecision={(id) => navigate(`/ci/legacy-decisions/${id}`)}
                />
              );
            }
            return <BriefsTab onOpen={(briefId) => navigate(`/ci/decisions/${briefId}`)} />;
          })()}
          {tab === 'insights' && (
            <InsightsTab onOpenDecision={(id) => navigate(`/ci/decisions/${id}`)} />
          )}
          {tab === 'reviewer' && isEnterprise && (
            <SignalsTab
              reviewerMode
              initialStatus="candidate"
              onOpenWarRoom={openWarRoom}
            />
          )}
        </div>
      </main>

      {/* Bottom Navigation (Mobile Only) */}
      <nav className="flex md:hidden shrink-0 border-t items-center justify-around px-2 py-3" style={{ borderColor: 'var(--color-line)', background: 'var(--color-surface)' }}>
        {tabs.slice(0, 4).map((t) => {
          const isActive = tab === t.key;
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className="flex flex-col items-center gap-1"
              style={{ color: isActive ? 'var(--color-accent)' : 'var(--color-ink-3)' }}
            >
              <t.icon size={20} />
              <span className="mz-text-xs font-medium">{t.label}</span>
            </button>
          );
        })}
      </nav>

    </div>
  );
}

function CIPageAgentSection() {
  const { activities, loading, error } = useAgentActivity();
  if (error) {
    // Hard-fail fallback: never break the sidebar — show the static
    // identity strip instead.
    return <AgentIdentityStrip />;
  }
  return <AgentActivityFeed activities={activities} loading={loading} />;
}
