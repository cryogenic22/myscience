/**
 * CIPage — the CI cockpit (home).
 *
 * Refactored in Loop D1 to use the shell primitives + design tokens. The
 * previous version hardcoded `data-theme="dark"` plus eight distinct hex
 * codes, overriding the F1 theme toggle and creating the "boxed-in" feel
 * the user flagged. This version:
 *
 *   - Uses CockpitShell / NavRail / NavRailItem / ContentRegion / CockpitMobileNav
 *   - Honors the user's chosen theme (no `data-theme` override)
 *   - Zero hardcoded hex codes; everything via `var(--color-*)`
 *   - Separation via tone-shifted surfaces, not 1px borders
 *
 * Tab content (DigestTab, SignalsTab, etc.) is unchanged — those live
 * inside ContentRegion and can be migrated in their own loops.
 */
import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft, Activity, LayoutGrid, Database, Target,
  ShieldAlert, LineChart, BrainCircuit, CheckSquare,
} from 'lucide-react';
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

// Loop D1 — shell primitives
import { CockpitShell } from '../components/layout/CockpitShell';
import { NavRail } from '../components/layout/NavRail';
import { NavRailItem } from '../components/layout/NavRailItem';
import { ContentRegion } from '../components/layout/ContentRegion';
import { CockpitMobileNav } from '../components/layout/CockpitMobileNav';

type TabKey =
  | 'inbox' | 'digest' | 'signals' | 'watchlist'
  | 'rooms' | 'decisions' | 'insights' | 'reviewer';

const ALL_TABS: Array<{
  key: TabKey;
  label: string;
  icon: any;
  enterprise?: boolean;
}> = [
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

  const initialTab =
    (params.get('tab') as TabKey) || (getRole() ? 'inbox' : 'digest');
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

  useDemoAutoLogin();

  useEffect(() => {
    const t = (params.get('tab') as TabKey) || (getRole() ? 'inbox' : 'digest');
    if (t !== tab) setTabState(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [params]);

  // ── Slots for the NavRail ─────────────────────────────────────────

  const navHeader = (
    <div
      className="flex items-center w-full"
      style={{ gap: 'var(--space-3)' }}
    >
      <button
        type="button"
        onClick={() => navigate('/')}
        aria-label="Back to landing"
        className="transition-opacity hover:opacity-70"
        style={{ color: 'var(--color-ink-3)' }}
      >
        <ArrowLeft size={16} />
      </button>
      <div className="flex flex-col flex-1">
        <span
          style={{
            color: 'var(--color-ink)',
            fontFamily: 'var(--font-display)',
            fontSize: 19,
            fontWeight: 500,
            letterSpacing: '-0.01em',
          }}
        >
          {PRODUCT_NAME}
        </span>
        <span
          style={{
            color: 'var(--color-ink-4)',
            fontFamily: 'var(--font-mono)',
            fontSize: 'var(--text-xs)',
            textTransform: 'uppercase',
            letterSpacing: '0.16em',
          }}
        >
          Cockpit
        </span>
      </div>
      <ThemeToggle />
    </div>
  );

  const navFooter = (
    <>
      <CIPageAgentSection />
      <div
        className="flex items-center justify-between w-full"
        style={{ fontSize: 'var(--text-xs)' }}
      >
        <a
          href="/connectors"
          className="hover:underline transition-opacity"
          style={{
            color: 'var(--color-ink-4)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          Connectors →
        </a>
        {role && (
          <span
            style={{
              background: 'var(--color-surface-3)',
              color: 'var(--color-ink-3)',
              fontFamily: 'var(--font-mono)',
              fontSize: 'var(--text-xs)',
              textTransform: 'uppercase',
              paddingInline: 'var(--space-2)',
              paddingBlock: 2,
              borderRadius: 'var(--radius-pill)',
            }}
          >
            {role}
          </span>
        )}
      </div>
    </>
  );

  // ── Render ─────────────────────────────────────────────────────────

  return (
    <CockpitShell
      nav={
        <NavRail header={navHeader} footer={navFooter}>
          {tabs.map((t) => (
            <NavRailItem
              key={t.key}
              label={t.label}
              icon={t.icon}
              active={tab === t.key}
              onClick={() => setTab(t.key)}
            />
          ))}
        </NavRail>
      }
      mobileNav={
        <CockpitMobileNav
          items={tabs.slice(0, 4).map((t) => ({
            key: t.key,
            label: t.label,
            icon: t.icon,
          }))}
          active={tab}
          onChange={setTab}
        />
      }
    >
      <ContentRegion>
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
          // mz_legacy_decisions === 'true'. Default routes to BriefsTab.
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
          return (
            <BriefsTab
              onOpen={(briefId) => navigate(`/ci/decisions/${briefId}`)}
            />
          );
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
      </ContentRegion>
    </CockpitShell>
  );
}

function CIPageAgentSection() {
  const { activities, loading, error } = useAgentActivity();
  if (error) {
    return <AgentIdentityStrip />;
  }
  return <AgentActivityFeed activities={activities} loading={loading} />;
}
