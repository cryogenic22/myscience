/**
 * DF — ForgeTab: the SME cockpit orchestrator.
 *
 * The Domain Forge surface, reachable from the CI cockpit "Learn" group. It
 * pairs the playable elicitation loop (ForgeRoundView) with the live "I built
 * this" payoff (ForgePackPanel showing the playbook growing), plus a light
 * authoring browse (ForgePlaybooksView: list + version history + rollback).
 *
 * A stable per-tab session id keys the score/streak so a play session
 * accumulates across rounds. House style: design-token CSS variables + inline
 * styles, no dynamic Tailwind class names.
 */
import { useMemo, useState } from 'react';
import { Gamepad2, BookOpen } from 'lucide-react';
import ForgeRoundView from './ForgeRoundView';
import ForgePackPanel from './ForgePackPanel';
import ForgePlaybooksView from './ForgePlaybooksView';
import type { ForgeAnswerResult } from '../../api';

type ForgeView = 'play' | 'authoring';

const DEFAULT_PLAYBOOK = 'compare.drug_x_drug';

function newSessionId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return `forge-${crypto.randomUUID()}`;
  }
  return `forge-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

export default function ForgeTab() {
  const [view, setView] = useState<ForgeView>('play');
  // One session per mount — score/streak accumulate across this tab's rounds.
  const sessionId = useMemo(newSessionId, []);
  // Bump on each answer so the pack panel refetches the grown playbook.
  const [refreshKey, setRefreshKey] = useState(0);

  const onAnswered = (_r: ForgeAnswerResult) => setRefreshKey((k) => k + 1);

  return (
    <div data-testid="forge-tab">
      <div style={{ marginBottom: 'var(--space-4)' }}>
        <h1 style={{
          fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 600,
          color: 'var(--color-ink)', margin: '0 0 4px',
        }}>
          Domain Forge
        </h1>
        <p style={{ margin: 0, fontSize: 13.5, color: 'var(--color-ink-3)', maxWidth: 640 }}>
          Teach the system what matters. Each round you play forges a dimension into an
          answer playbook — quality-gated, versioned, and reused on every future query.
        </p>
      </div>

      {/* sub-nav */}
      <div role="tablist" style={{ display: 'flex', gap: 6, marginBottom: 'var(--space-5)' }}>
        <SubTab active={view === 'play'} onClick={() => setView('play')} icon={Gamepad2} testId="forge-subtab-play">
          Play
        </SubTab>
        <SubTab active={view === 'authoring'} onClick={() => setView('authoring')} icon={BookOpen} testId="forge-subtab-authoring">
          Playbooks
        </SubTab>
      </div>

      {view === 'play' && (
        <div style={{
          display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(280px, 1fr)',
          gap: 'var(--space-5)', alignItems: 'start',
        }}>
          <div data-testid="forge-play-col">
            <ForgeRoundView
              sessionId={sessionId}
              playbookId={DEFAULT_PLAYBOOK}
              onAnswered={onAnswered}
            />
          </div>
          <aside data-testid="forge-pack-col" style={{
            position: 'sticky', top: 'var(--space-4)',
            padding: 'var(--space-4)', borderRadius: 14,
            background: 'var(--color-surface-2)', border: '1px solid var(--color-line)',
          }}>
            <ForgePackPanel playbookId={DEFAULT_PLAYBOOK} refreshKey={refreshKey} />
          </aside>
        </div>
      )}

      {view === 'authoring' && <ForgePlaybooksView />}
    </div>
  );
}

function SubTab({
  active, onClick, icon: Icon, testId, children,
}: {
  active: boolean;
  onClick: () => void;
  icon: any;
  testId: string;
  children: React.ReactNode;
}) {
  return (
    <button
      role="tab"
      aria-selected={active}
      data-testid={testId}
      onClick={onClick}
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '7px 15px', fontSize: 13, fontWeight: 500,
        borderRadius: 'var(--radius-pill)', cursor: 'pointer',
        border: '1px solid', borderColor: active ? 'var(--color-ink)' : 'var(--color-line)',
        background: active ? 'var(--color-ink)' : 'var(--color-surface)',
        color: active ? 'var(--color-bg)' : 'var(--color-ink-3)',
      }}
    >
      <Icon size={14} /> {children}
    </button>
  );
}
