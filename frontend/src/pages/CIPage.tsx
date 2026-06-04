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
  ArrowLeft, Activity, Target, BookOpen,
  ShieldAlert, LineChart, BrainCircuit, CheckSquare, Briefcase, HelpCircle,
} from 'lucide-react';
import { PRODUCT_NAME } from '../brand';
import IntelligenceTab, { type IntelView } from '../components/ci/IntelligenceTab';
import StandaloneDossierTab from '../components/ci/StandaloneDossierTab';
import KbqQueryTab from '../components/ci/KbqQueryTab';
import AgentsDrawer from '../components/ci/AgentsDrawer';
import SignalsTab from '../components/ci/SignalsTab';
import WatchlistTab from '../components/ci/WatchlistTab';
import WarRoomView from '../components/ci/war/WarRoomView';
import WarRoomsList from '../components/ci/war/WarRoomsList';
import DecisionsTab from '../components/ci/decisions/DecisionsTab';
import BriefsTab from '../components/ci/decisions/BriefsTab';
import InsightsTab from '../components/ci/InsightsTab';
import EngagementsTab from '../components/ci/EngagementsTab';
import EngagementDetailContainer from '../components/ci/EngagementDetailContainer';
import { ThemeToggle } from '../components/primitives/ThemeToggle';
import type { LifecycleStage } from '../components/layout/EngagementShell';
import { useDemoAutoLogin } from '../hooks/useDemoAutoLogin';

// Loop D1 — shell primitives
import { CockpitShell } from '../components/layout/CockpitShell';
import { NavRail } from '../components/layout/NavRail';
import { NavRailItem } from '../components/layout/NavRailItem';
import { ContentRegion } from '../components/layout/ContentRegion';
import { CockpitMobileNav } from '../components/layout/CockpitMobileNav';

type TabKey =
  | 'inbox' | 'digest' | 'signals' | 'watchlist' | 'kbq' | 'dossier' | 'engagements'
  | 'rooms' | 'decisions' | 'insights' | 'reviewer';

// IX-2 — map a legacy feed tab key to the consolidated Intelligence view.
function viewFromTab(tab: TabKey): IntelView {
  if (tab === 'inbox') return 'stream';
  if (tab === 'signals') return 'signals';
  return 'digest';
}

const ALL_TABS: Array<{
  key: TabKey;
  label: string;
  icon: any;
  enterprise?: boolean;
}> = [
  // IX-2 — three former feed tabs → one Intelligence surface ('digest' is the
  // canonical key; 'inbox'/'signals' still route here via viewFromTab).
  { key: 'digest',      label: 'Intelligence', icon: Activity },
  { key: 'watchlist',   label: 'Watchlist', icon: Target },
  // PB-SL10 — KBQ query surface: ask the 8 key business questions of any asset.
  { key: 'kbq',         label: 'KBQ', icon: HelpCircle },
  // IX-3/IX-5 — Dossier (light path) + War Game (its own section) + the full
  // Engagement flow are the "Engage" building blocks.
  { key: 'dossier',     label: 'Dossier', icon: BookOpen },
  { key: 'rooms',       label: 'War Game', icon: ShieldAlert },
  { key: 'engagements', label: 'Engagements', icon: Briefcase },
  { key: 'decisions',   label: 'Decisions', icon: CheckSquare },
  { key: 'insights',    label: 'Insights', icon: LineChart },
  { key: 'reviewer',    label: 'Reviewer', icon: BrainCircuit, enterprise: true },
];

// IX-5 — group the nav around the flywheel (sense → engage → act → learn),
// instead of nine flat artifact tabs. Each group renders a label + its
// available items; an empty group (e.g. Admin when not enterprise) is skipped.
const NAV_GROUPS: Array<{ label: string; keys: TabKey[] }> = [
  { label: 'Sense',  keys: ['digest', 'watchlist', 'kbq'] },
  { label: 'Engage', keys: ['dossier', 'rooms', 'engagements'] },
  { label: 'Act',    keys: ['decisions'] },
  { label: 'Learn',  keys: ['insights'] },
  { label: 'Admin',  keys: ['reviewer'] },
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
  const activeEngagement = params.get('engagement');
  const activeStage = (params.get('stage') || undefined) as LifecycleStage | undefined;

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

  // D1.5 — agent activity feed removed from the sidebar per user
  // feedback. Sentinel/Strategist/Curator status lived here but
  // dominated the navigation visually. They'll resurface elsewhere
  // (e.g. an "Agents" tab or a status drawer) once we know where
  // they earn their square footage.
  const navFooter = (
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
  );

  // ── Render ─────────────────────────────────────────────────────────

  return (
    <>
    <CockpitShell
      nav={
        <NavRail header={navHeader} footer={navFooter}>
          {NAV_GROUPS.map((group) => {
            const items = group.keys
              .map((k) => tabs.find((t) => t.key === k))
              .filter((t): t is (typeof tabs)[number] => Boolean(t));
            if (items.length === 0) return null;
            return (
              <div key={group.label} data-nav-group={group.label}>
                <div
                  style={{
                    fontFamily: 'var(--font-mono)', fontSize: 9.5, letterSpacing: '0.16em',
                    textTransform: 'uppercase', color: 'var(--color-ink-4)',
                    padding: '12px 11px 5px',
                  }}
                >
                  {group.label}
                </div>
                {items.map((t) => (
                  <NavRailItem
                    key={t.key}
                    label={t.label}
                    icon={t.icon}
                    active={tab === t.key}
                    onClick={() => setTab(t.key)}
                  />
                ))}
              </div>
            );
          })}
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
        {(tab === 'digest' || tab === 'inbox' || tab === 'signals') && (
          <IntelligenceTab
            initialView={viewFromTab(tab)}
            onOpenDecision={(id) => navigate(`/ci/decisions/${id}`)}
            onOpenWarRoom={openWarRoom}
            onOpenInsights={() => setTab('insights')}
          />
        )}
        {tab === 'watchlist' && <WatchlistTab onOpenWarRoom={openWarRoom} />}
        {tab === 'kbq' && <KbqQueryTab />}
        {tab === 'dossier' && (
          <StandaloneDossierTab
            initialAsset={params.get('asset') ?? undefined}
            onPromote={(asset) => {
              // PB-IX01 — carry the asset into the engagement create flow.
              const next = new URLSearchParams(params);
              next.set('tab', 'engagements');
              next.set('new', '1');
              if (asset) next.set('asset', asset);
              next.delete('stage');
              setParams(next, { replace: false });
            }}
          />
        )}
        {tab === 'engagements' && (
          activeEngagement
            ? <EngagementDetailContainer
                eid={activeEngagement}
                stage={activeStage}
                onBackToPortfolio={() => {
                  const next = new URLSearchParams(params);
                  next.delete('engagement');
                  next.delete('stage');
                  setParams(next, { replace: false });
                }}
                onStageChange={(id, s) => {
                  const next = new URLSearchParams(params);
                  next.set('tab', 'engagements');
                  next.set('engagement', id);
                  next.set('stage', s);
                  setParams(next, { replace: false });
                }}
              />
            : <EngagementsTab
                autoNew={params.get('new') === '1'}
                seedAsset={params.get('asset') ?? undefined}
                seedName={params.get('seedName') ?? undefined}
                seedContext={params.get('seedContext') ?? undefined}
                seedSignalId={params.get('seedSignalId') ?? undefined}
                onSeedConsumed={() => {
                  // PB-IX01 — clear the promote seed so closing the modal stays
                  // closed (and a refresh doesn't reopen it).
                  const next = new URLSearchParams(params);
                  next.delete('new');
                  next.delete('asset');
                  next.delete('seedName');
                  next.delete('seedContext');
                  next.delete('seedSignalId');
                  setParams(next, { replace: true });
                }}
                onEngagementOpen={(id) => {
                  const next = new URLSearchParams(params);
                  next.set('tab', 'engagements');
                  next.set('engagement', id);
                  setParams(next, { replace: false });
                }}
              />
        )}
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
    <AgentsDrawer />
    </>
  );
}

