/**
 * F2 — EngagementSidebar: the engagement-spine IA.
 *
 * v7 design canon: Portfolio → Active Engagement (7 stages) → Other
 * Engagements. The sidebar makes the spine legible at every page load —
 * the user always knows what stage of which engagement they're in.
 *
 * Stage navigation mirrors the Z3 FSM:
 *   - back-track to earlier stages: enabled
 *   - current stage: noop (already there)
 *   - forward-by-one: enabled
 *   - skip-ahead (current+2 or beyond): visually disabled
 *
 * Headless: takes data + callbacks via props; no API calls. F3 wires it.
 *
 * Themed: uses CSS variables so it renders correctly under any of the
 * three themes (zs / dark / light) without per-theme branching.
 */
import { useState } from 'react';

// Mirrors services/engagement.py STAGE_ORDER exactly. Order matters — used
// to compute skip-ahead.
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

const STAGE_LABEL: Record<LifecycleStage, string> = {
  brief:     'Brief & Scope',
  sources:   'Sources & Gaps',
  dossier:   'Dossier',
  synthesis: 'Synthesis',
  gaps:      'Intelligence Gaps',
  scenarios: 'Scenarios',
  workshop:  'War Room + Decisions',
};

export interface ActiveEngagement {
  id: string;
  name: string;
  stage: LifecycleStage | string;
  completedStages: (LifecycleStage | string)[];
}

export interface OtherEngagement {
  id: string;
  name: string;
  workshopDate?: string | null;
}

export interface EngagementSidebarProps {
  activeEngagement: ActiveEngagement | null;
  otherEngagements: OtherEngagement[];
  onPortfolioSelect: () => void;
  onEngagementSelect: (id: string) => void;
  onStageSelect: (engagementId: string, stage: LifecycleStage) => void;
  /** For tests + dense displays: start with the "other engagements"
   *  disclosure open. */
  defaultOtherOpen?: boolean;
}

function stageNumber(stage: LifecycleStage): string {
  const i = LIFECYCLE_STAGES.indexOf(stage);
  return String(i + 1).padStart(2, '0');
}

/** Stage indices in LIFECYCLE_STAGES, falling back to -1 if unknown. */
function indexOf(stage: string): number {
  return (LIFECYCLE_STAGES as readonly string[]).indexOf(stage);
}

export function EngagementSidebar({
  activeEngagement,
  otherEngagements,
  onPortfolioSelect,
  onEngagementSelect,
  onStageSelect,
  defaultOtherOpen = false,
}: EngagementSidebarProps) {
  const [otherOpen, setOtherOpen] = useState(defaultOtherOpen);
  const currentIdx = activeEngagement ? indexOf(String(activeEngagement.stage)) : -1;

  return (
    <nav
      aria-label="Engagement navigation"
      data-engagement-sidebar
      style={{
        width: 260,
        height: '100%',
        display: 'flex',
        flexDirection: 'column',
        background: 'var(--color-surface)',
        borderRight: '1px solid var(--color-line)',
        fontFamily: 'var(--font-body)',
        color: 'var(--color-ink)',
        overflow: 'hidden',
      }}
    >
      {/* ── Portfolio (pinned) ─── */}
      <div
        style={{
          padding: '14px 16px',
          borderBottom: '1px solid var(--color-divider)',
        }}
      >
        <a
          href="#portfolio"
          onClick={(e) => {
            e.preventDefault();
            onPortfolioSelect();
          }}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            color: 'var(--color-ink-2)',
            textDecoration: 'none',
            fontSize: 13,
            fontWeight: 500,
          }}
        >
          <span aria-hidden style={{ fontSize: 14 }}>📊</span>
          <span>Portfolio</span>
          <span style={{
            marginLeft: 'auto',
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            color: 'var(--color-ink-3)',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}>
            Home
          </span>
        </a>
      </div>

      {/* ── Active Engagement ─── */}
      <div style={{ flex: '0 0 auto', padding: '14px 16px 8px' }}>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            color: 'var(--color-ink-3)',
            marginBottom: 10,
          }}
        >
          Active Engagement
        </div>

        {!activeEngagement && (
          <div
            style={{
              padding: '14px 12px',
              fontSize: 13,
              color: 'var(--color-ink-3)',
              fontStyle: 'italic',
              border: '1px dashed var(--color-line-2)',
            }}
          >
            Open an engagement to begin the lifecycle.
          </div>
        )}

        {activeEngagement && (
          <>
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                marginBottom: 12,
                fontFamily: 'var(--font-display)',
                fontSize: 15,
                fontWeight: 500,
                lineHeight: 1.25,
                color: 'var(--color-ink)',
              }}
            >
              <span
                aria-hidden
                style={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  background: 'var(--color-accent)',
                  flexShrink: 0,
                }}
              />
              <span>{activeEngagement.name}</span>
            </div>

            <ol
              data-stages
              style={{
                listStyle: 'none',
                margin: 0,
                padding: 0,
                display: 'flex',
                flexDirection: 'column',
                gap: 0,
              }}
            >
              {LIFECYCLE_STAGES.map((stage, i) => {
                const isCurrent = activeEngagement.stage === stage;
                const isComplete = activeEngagement.completedStages.includes(stage);
                const targetIdx = i;
                const canNavigate =
                  !isCurrent && (targetIdx < currentIdx || targetIdx === currentIdx + 1);

                const click = () => {
                  if (canNavigate) onStageSelect(activeEngagement.id, stage);
                };

                return (
                  <li
                    key={stage}
                    data-stage={stage}
                    data-current={isCurrent || undefined}
                    data-complete={isComplete || undefined}
                    aria-current={isCurrent ? 'step' : undefined}
                    onClick={click}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '20px 22px 1fr',
                      gap: 8,
                      alignItems: 'center',
                      padding: '7px 8px',
                      borderLeft: isCurrent
                        ? '2px solid var(--color-accent)'
                        : '2px solid transparent',
                      cursor: canNavigate ? 'pointer' : 'default',
                      opacity: !isCurrent && !canNavigate ? 0.45 : 1,
                      background: isCurrent ? 'var(--color-accent-soft)' : 'transparent',
                      color: isCurrent
                        ? 'var(--color-ink)'
                        : 'var(--color-ink-2)',
                      transition: 'background 80ms ease',
                    }}
                  >
                    <span
                      aria-hidden
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 11,
                        color: 'var(--color-ink-3)',
                      }}
                    >
                      {isComplete ? '✓' : isCurrent ? '▶' : ''}
                    </span>
                    <span
                      style={{
                        fontFamily: 'var(--font-mono)',
                        fontSize: 10.5,
                        color: 'var(--color-ink-3)',
                        letterSpacing: '0.06em',
                      }}
                    >
                      {stageNumber(stage)}
                    </span>
                    <span style={{ fontSize: 12.5, fontWeight: isCurrent ? 600 : 400 }}>
                      {STAGE_LABEL[stage]}
                    </span>
                  </li>
                );
              })}
            </ol>
          </>
        )}
      </div>

      {/* ── Other Engagements (collapsible) ─── */}
      <div
        style={{
          marginTop: 'auto',
          borderTop: '1px solid var(--color-divider)',
          padding: '10px 16px 12px',
        }}
      >
        <button
          type="button"
          onClick={() => setOtherOpen((v) => !v)}
          aria-expanded={otherOpen}
          style={{
            width: '100%',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            background: 'transparent',
            border: 'none',
            padding: '4px 0',
            cursor: 'pointer',
            color: 'var(--color-ink-3)',
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
          }}
        >
          <span>Other Engagements · {otherEngagements.length}</span>
          <span aria-hidden>{otherOpen ? '▾' : '▸'}</span>
        </button>

        {otherOpen && (
          <ul
            style={{
              listStyle: 'none',
              margin: '8px 0 0',
              padding: 0,
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
            }}
          >
            {otherEngagements.map((e) => (
              <li
                key={e.id}
                data-engagement-id={e.id}
                onClick={() => onEngagementSelect(e.id)}
                style={{
                  padding: '8px 10px',
                  cursor: 'pointer',
                  fontSize: 12.5,
                  color: 'var(--color-ink-2)',
                  borderLeft: '2px solid transparent',
                  transition: 'background 80ms ease',
                }}
              >
                <div style={{ fontWeight: 500, color: 'var(--color-ink)' }}>{e.name}</div>
                {e.workshopDate && (
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10,
                      color: 'var(--color-ink-3)',
                      letterSpacing: '0.04em',
                      marginTop: 2,
                    }}
                  >
                    {e.workshopDate}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </nav>
  );
}
