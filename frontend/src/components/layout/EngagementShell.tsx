/**
 * F4 — EngagementShell: the top-level page frame for engagement work.
 *
 * Mounts (via slot) the sidebar (F2), the engagement header, the 7-stage
 * horizontal stepper, and the stage content (F5-F12 each provide a stage
 * page).
 *
 * Sidebar is a slot prop, so this shell does not import EngagementSidebar
 * directly — the two can ship in different PRs. The routing layer wires
 * the EngagementSidebar instance into the sidebar slot.
 *
 * Stepper navigation mirrors the Z3 FSM:
 *   - back-track: enabled
 *   - forward-by-one: enabled
 *   - current: noop
 *   - skip-ahead: disabled (no click handler fires)
 */
import type { ReactNode } from 'react';

// Mirrors services/engagement.py STAGE_ORDER exactly.
export const LIFECYCLE_STAGES = [
  'brief',
  'sources',
  'dossier',
  'synthesis',
  'gaps',
  'scenarios',
  'workshop',
] as const;

export type LifecycleStage = (typeof LIFECYCLE_STAGES)[number];

export interface ShellActiveEngagement {
  id: string;
  name: string;
  focalAsset: string;
  situation: 'launch' | 'defense' | 'lcm';
  workshopDate?: string | null;
  daysUntilWorkshop: number | null;
  stage: LifecycleStage | string;
  completedStages: readonly (LifecycleStage | string)[];
}

export interface EngagementShellProps {
  activeEngagement: ShellActiveEngagement | null;
  currentStage: LifecycleStage;
  onPortfolioSelect: () => void;
  onStageSelect: (engagementId: string, stage: LifecycleStage) => void;
  sidebar: ReactNode;
  children: ReactNode;
}

const STAGE_LABEL: Record<LifecycleStage, string> = {
  brief:     'Brief & Scope',
  sources:   'Sources & Gaps',
  dossier:   'Dossier',
  synthesis: 'Synthesis',
  gaps:      'Intelligence Gaps',
  scenarios: 'Scenarios',
  workshop:  'War Room + Decisions',
};

function indexOf(stage: string): number {
  return (LIFECYCLE_STAGES as readonly string[]).indexOf(stage);
}

function workshopWindow(days: number | null): 'critical' | 'soon' | 'distant' | 'none' {
  if (days === null || days === undefined) return 'none';
  if (days <= 7) return 'critical';
  if (days <= 30) return 'soon';
  return 'distant';
}

function windowAccent(window: ReturnType<typeof workshopWindow>): string {
  switch (window) {
    case 'critical': return 'var(--color-accent)';
    case 'soon':     return 'var(--color-teal, var(--color-accent))';
    case 'distant':  return 'var(--color-line-2)';
    default:         return 'var(--color-line-2)';
  }
}

// ── Empty state ────────────────────────────────────────────────────

function EmptyState({ onPortfolioSelect, sidebar }: {
  onPortfolioSelect: () => void;
  sidebar: ReactNode;
}) {
  return (
    <div
      role="region"
      aria-label="Engagement workspace"
      style={{
        display: 'grid',
        gridTemplateColumns: 'auto 1fr',
        height: '100%',
        background: 'var(--color-bg)',
        fontFamily: 'var(--font-body)',
        color: 'var(--color-ink)',
      }}
    >
      <div>{sidebar}</div>
      <main
        style={{
          display: 'grid',
          placeItems: 'center',
          padding: '48px',
        }}
      >
        <div style={{ textAlign: 'center', maxWidth: 480 }}>
          <div
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10.5,
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
              color: 'var(--color-ink-3)',
              marginBottom: 8,
            }}
          >
            No engagement open
          </div>
          <h2
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 28,
              fontWeight: 400,
              color: 'var(--color-ink)',
              margin: '0 0 14px',
              letterSpacing: '-0.01em',
            }}
          >
            Pick where to work.
          </h2>
          <p style={{ fontSize: 14, color: 'var(--color-ink-3)', marginBottom: 20 }}>
            The engagement is the unit of work. Return to the portfolio to
            open one — or create a new one from there.
          </p>
          <a
            href="#portfolio"
            onClick={(e) => {
              e.preventDefault();
              onPortfolioSelect();
            }}
            style={{
              display: 'inline-block',
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              padding: '8px 14px',
              border: '1px solid var(--color-accent)',
              color: 'var(--color-accent)',
              background: 'var(--color-surface)',
              textDecoration: 'none',
            }}
          >
            Return to Portfolio →
          </a>
        </div>
      </main>
    </div>
  );
}

// ── Header ─────────────────────────────────────────────────────────

function EngagementHeader({ engagement }: { engagement: ShellActiveEngagement }) {
  const window = workshopWindow(engagement.daysUntilWorkshop);
  const accent = windowAccent(window);
  return (
    <header
      data-workshop-window={window}
      style={{
        padding: '20px 28px 16px',
        borderBottom: '1px solid var(--color-divider)',
        background: 'var(--color-surface)',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          letterSpacing: '0.16em',
          textTransform: 'uppercase',
          color: 'var(--color-ink-3)',
          marginBottom: 6,
        }}
      >
        Active Engagement · {engagement.situation}
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 28,
            fontWeight: 400,
            letterSpacing: '-0.012em',
            color: 'var(--color-ink)',
            margin: 0,
          }}
        >
          {engagement.name}
        </h1>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            color: 'var(--color-ink-3)',
            letterSpacing: '0.04em',
          }}
        >
          {engagement.focalAsset}
        </span>
        {engagement.daysUntilWorkshop !== null && (
          <span
            style={{
              marginLeft: 'auto',
              fontFamily: 'var(--font-mono)',
              fontSize: 11,
              letterSpacing: '0.08em',
              textTransform: 'uppercase',
              padding: '4px 10px',
              border: `1px solid ${accent}`,
              color: window === 'critical' ? accent : 'var(--color-ink-2)',
              background: window === 'critical' ? 'var(--color-accent-soft)' : 'transparent',
            }}
          >
            Workshop in {engagement.daysUntilWorkshop} days
            {engagement.workshopDate && (
              <span style={{ opacity: 0.55, marginLeft: 8 }}>
                {engagement.workshopDate}
              </span>
            )}
          </span>
        )}
      </div>
    </header>
  );
}

// ── Stepper ────────────────────────────────────────────────────────

function Stepper({
  engagement,
  currentStage,
  onStageSelect,
}: {
  engagement: ShellActiveEngagement;
  currentStage: LifecycleStage;
  onStageSelect: (engagementId: string, stage: LifecycleStage) => void;
}) {
  const currentIdx = indexOf(currentStage);

  return (
    <ol
      aria-label="Lifecycle progress"
      style={{
        listStyle: 'none',
        margin: 0,
        padding: '14px 28px',
        display: 'flex',
        gap: 0,
        alignItems: 'center',
        background: 'var(--color-surface-2)',
        borderBottom: '1px solid var(--color-divider)',
        overflowX: 'auto',
      }}
    >
      {LIFECYCLE_STAGES.map((stage, i) => {
        const isCurrent = stage === currentStage;
        const isComplete = engagement.completedStages.includes(stage);
        const canNavigate =
          !isCurrent && (i < currentIdx || i === currentIdx + 1);
        const num = String(i + 1).padStart(2, '0');

        const click = () => {
          if (canNavigate) onStageSelect(engagement.id, stage);
        };

        return (
          <li
            key={stage}
            data-stepper-stage={stage}
            data-current={isCurrent || undefined}
            data-complete={isComplete || undefined}
            aria-current={isCurrent ? 'step' : undefined}
            onClick={click}
            title={STAGE_LABEL[stage]}
            style={{
              display: 'grid',
              gridTemplateColumns: 'auto 1fr',
              gap: 8,
              alignItems: 'center',
              padding: '6px 14px 6px 8px',
              cursor: canNavigate ? 'pointer' : 'default',
              opacity: !isCurrent && !canNavigate ? 0.4 : 1,
              borderBottom: isCurrent
                ? '2px solid var(--color-accent)'
                : '2px solid transparent',
              transition: 'opacity 80ms ease',
            }}
          >
            <span
              aria-hidden
              style={{
                width: 18,
                height: 18,
                borderRadius: '50%',
                display: 'grid',
                placeItems: 'center',
                fontFamily: 'var(--font-mono)',
                fontSize: 9.5,
                fontWeight: 600,
                color: isCurrent
                  ? 'var(--color-bg)'
                  : isComplete
                  ? 'var(--color-ok, var(--color-green, #15803d))'
                  : 'var(--color-ink-3)',
                background: isCurrent
                  ? 'var(--color-accent)'
                  : isComplete
                  ? 'var(--color-green-soft, transparent)'
                  : 'transparent',
                border: isCurrent
                  ? '1px solid var(--color-accent)'
                  : isComplete
                  ? '1px solid var(--color-green, #15803d)'
                  : '1px solid var(--color-line-2)',
              }}
            >
              {isComplete && !isCurrent ? '✓' : num}
            </span>
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10.5,
                letterSpacing: '0.06em',
                color: isCurrent
                  ? 'var(--color-ink)'
                  : 'var(--color-ink-3)',
                fontWeight: isCurrent ? 600 : 400,
                whiteSpace: 'nowrap',
              }}
            >
              {STAGE_LABEL[stage]}
            </span>
            {i < LIFECYCLE_STAGES.length - 1 && (
              <span
                aria-hidden
                style={{
                  display: 'inline-block',
                  width: 12,
                  height: 1,
                  background: 'var(--color-line-2)',
                  margin: '0 4px',
                  gridColumn: 'span 2',
                }}
              />
            )}
          </li>
        );
      })}
    </ol>
  );
}

// ── Main shell ─────────────────────────────────────────────────────

export function EngagementShell(props: EngagementShellProps) {
  const { activeEngagement, currentStage, onPortfolioSelect, onStageSelect,
          sidebar, children } = props;

  if (!activeEngagement) {
    return <EmptyState onPortfolioSelect={onPortfolioSelect} sidebar={sidebar} />;
  }

  return (
    <div
      role="region"
      aria-label="Engagement workspace"
      style={{
        display: 'grid',
        gridTemplateColumns: 'auto 1fr',
        height: '100%',
        background: 'var(--color-bg)',
        fontFamily: 'var(--font-body)',
        color: 'var(--color-ink)',
        overflow: 'hidden',
      }}
    >
      {sidebar}
      <main
        style={{
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        <EngagementHeader engagement={activeEngagement} />
        <Stepper
          engagement={activeEngagement}
          currentStage={currentStage}
          onStageSelect={onStageSelect}
        />
        <section
          style={{
            flex: '1 1 auto',
            overflow: 'auto',
            padding: '24px 28px 40px',
            background: 'var(--color-bg)',
          }}
        >
          {children}
        </section>
      </main>
    </div>
  );
}
