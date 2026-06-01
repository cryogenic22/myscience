/**
 * F9 — GapsPage: intelligence gaps between Dossier and Scenarios.
 *
 * Riya's structural correction: gaps belong here, not on the Decisions
 * page as a post-mortem. The page surfaces what's missing, ranked by the
 * Z5 priority matrix importance, with three remediation options per gap
 * (primary research / accept uncertainty / descope).
 *
 * Workshop-blocking rule: any critical gap with remediation=pending blocks
 * the "Mark stage complete" CTA. The banner reflects readiness honestly.
 *
 * Headless. Theme-aware.
 */
import { ReactNode, useState } from 'react';

// ── Types ──────────────────────────────────────────────────────────

export type Importance = 'critical' | 'high' | 'medium';
export type Remediation = 'primary_research' | 'accept_uncertainty' | 'descope' | 'pending';

export interface Gap {
  id: string;
  domain: string;
  importance: Importance;
  question: string;
  expectedSourceClass?: string;
  /** How to fill the gap (domain-appropriate collection method). */
  fillMethod?: string;
  remediation: Remediation;
  remediationNote?: string;
  blocksScenarios?: string[];
}

export interface GapsPageProps {
  scope: { engagementName: string; focalAsset: string };
  gaps: Gap[];
  onSetRemediation: (gapId: string, remediation: Remediation, note?: string) => void;
  onMarkComplete: () => void;
}

// ── Tones ──────────────────────────────────────────────────────────

const IMPORTANCE_ORDER: Importance[] = ['critical', 'high', 'medium'];

function importanceTone(i: Importance) {
  switch (i) {
    case 'critical': return { fg: 'var(--color-red, #b91c1c)', bg: 'rgba(185,28,28,0.08)', border: 'var(--color-red, #b91c1c)' };
    case 'high':     return { fg: 'var(--color-amber)',         bg: 'var(--color-amber-soft, rgba(180,83,9,0.08))', border: 'var(--color-amber)' };
    case 'medium':   return { fg: 'var(--color-ink-3)',         bg: 'var(--color-surface-2)', border: 'var(--color-line-2)' };
  }
}

const REMEDIATION_LABEL: Record<Remediation, string> = {
  primary_research:   'Primary research',
  accept_uncertainty: 'Accept uncertainty',
  descope:            'Descope',
  pending:            'Pending',
};

function remediationTone(r: Remediation) {
  switch (r) {
    case 'primary_research':   return 'var(--color-accent)';
    case 'accept_uncertainty': return 'var(--color-ink-3)';
    case 'descope':            return 'var(--color-ink-4)';
    case 'pending':            return 'var(--color-amber)';
  }
}

// ── Atoms ──────────────────────────────────────────────────────────

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10.5,
        letterSpacing: '0.16em',
        textTransform: 'uppercase',
        color: 'var(--color-ink-3)',
        marginBottom: 12,
      }}
    >
      {children}
    </div>
  );
}

function ImportanceBadge({ importance }: { importance: Importance }) {
  const t = importanceTone(importance);
  return (
    <span
      style={{
        display: 'inline-block',
        fontFamily: 'var(--font-mono)',
        fontSize: 9.5,
        letterSpacing: '0.16em',
        textTransform: 'uppercase',
        padding: '2px 8px',
        background: t.bg,
        color: t.fg,
        border: `1px solid ${t.border}`,
        fontWeight: 600,
      }}
    >
      {importance}
    </span>
  );
}

// ── Banner ─────────────────────────────────────────────────────────

function ReadinessBanner({ criticalPending }: { criticalPending: number }) {
  if (criticalPending > 0) {
    return (
      <div
        data-banner="blocking"
        style={{
          padding: '14px 18px',
          background: 'rgba(185, 28, 28, 0.08)',
          border: '1px solid var(--color-red, #b91c1c)',
          borderLeft: '3px solid var(--color-red, #b91c1c)',
        }}
      >
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '0.16em',
            textTransform: 'uppercase',
            color: 'var(--color-red, #b91c1c)',
            fontWeight: 600,
            marginBottom: 4,
          }}
        >
          {criticalPending} critical gaps unresolved · workshop readiness blocked
        </div>
        <div style={{ fontSize: 13, color: 'var(--color-ink-2)' }}>
          Resolve or descope each critical gap before scenarios are run. Workshops on
          unresolved critical gaps tend to surface decisions the platform cannot
          defend.
        </div>
      </div>
    );
  }
  return (
    <div
      data-banner="ready"
      style={{
        padding: '14px 18px',
        background: 'var(--color-green-soft, rgba(21,128,61,0.08))',
        border: '1px solid var(--color-green, #15803d)',
        borderLeft: '3px solid var(--color-green, #15803d)',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          letterSpacing: '0.16em',
          textTransform: 'uppercase',
          color: 'var(--color-green, #15803d)',
          fontWeight: 600,
          marginBottom: 4,
        }}
      >
        Critical gaps resolved · workshop-ready
      </div>
      <div style={{ fontSize: 13, color: 'var(--color-ink-2)' }}>
        All critical-importance gaps have a remediation path. Proceed to Scenarios.
      </div>
    </div>
  );
}

// ── Gap card ───────────────────────────────────────────────────────

function GapCard({
  gap,
  onSetRemediation,
}: {
  gap: Gap;
  onSetRemediation: (id: string, r: Remediation, note?: string) => void;
}) {
  const isPending = gap.remediation === 'pending';
  return (
    <li
      data-gap-id={gap.id}
      style={{
        padding: '14px 16px',
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderLeft: `3px solid ${importanceTone(gap.importance).border}`,
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
        <ImportanceBadge importance={gap.importance} />
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            color: 'var(--color-ink-3)',
            letterSpacing: '0.04em',
          }}
        >
          {gap.domain}
        </span>
        <span
          style={{
            marginLeft: 'auto',
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            letterSpacing: '0.14em',
            textTransform: 'uppercase',
            color: remediationTone(gap.remediation),
            fontWeight: 600,
          }}
        >
          {REMEDIATION_LABEL[gap.remediation]}
        </span>
      </div>

      <div
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 16,
          fontWeight: 500,
          color: 'var(--color-ink)',
          lineHeight: 1.4,
        }}
      >
        {gap.question}
      </div>

      {gap.expectedSourceClass && (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            color: 'var(--color-ink-3)',
            letterSpacing: '0.04em',
          }}
        >
          Expected source class: <strong style={{ color: 'var(--color-ink-2)' }}>{gap.expectedSourceClass}</strong>
        </div>
      )}

      {gap.fillMethod && (
        <div style={{ fontSize: 12.5, color: 'var(--color-ink-3)', lineHeight: 1.5 }}>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 10,
              letterSpacing: '0.12em',
              textTransform: 'uppercase',
              color: 'var(--color-ink-4)',
              marginRight: 6,
            }}
          >
            How to fill
          </span>
          {gap.fillMethod}
        </div>
      )}

      {gap.remediationNote && !isPending && (
        <div style={{ fontStyle: 'italic', fontSize: 12.5, color: 'var(--color-ink-3)', lineHeight: 1.5 }}>
          {gap.remediationNote}
        </div>
      )}

      {gap.blocksScenarios && gap.blocksScenarios.length > 0 && (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            color: 'var(--color-amber)',
            letterSpacing: '0.04em',
          }}
        >
          Blocks: {gap.blocksScenarios.join(', ')}
        </div>
      )}

      {isPending && (
        <div
          style={{
            display: 'flex',
            gap: 8,
            flexWrap: 'wrap',
            paddingTop: 6,
            borderTop: '1px dashed var(--color-line-soft, var(--color-line))',
          }}
        >
          {(['primary_research', 'accept_uncertainty', 'descope'] as Remediation[]).map((r) => (
            <button
              type="button"
              key={r}
              onClick={() => onSetRemediation(gap.id, r)}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: 10,
                letterSpacing: '0.12em',
                textTransform: 'uppercase',
                padding: '5px 10px',
                background: 'transparent',
                color: remediationTone(r),
                border: `1px solid ${remediationTone(r)}`,
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              {REMEDIATION_LABEL[r]} →
            </button>
          ))}
        </div>
      )}
    </li>
  );
}

// ── Main component ────────────────────────────────────────────────

export function GapsPage(props: GapsPageProps) {
  const { scope, gaps, onSetRemediation, onMarkComplete } = props;
  const [activeImportance, setActiveImportance] = useState<Set<Importance>>(new Set());

  const toggle = (i: Importance) => {
    setActiveImportance((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  };

  const visible = activeImportance.size === 0
    ? gaps
    : gaps.filter((g) => activeImportance.has(g.importance));

  const total = gaps.length;
  const blocking = gaps.filter((g) => (g.blocksScenarios?.length ?? 0) > 0).length;
  const unresolved = gaps.filter((g) => g.remediation === 'pending').length;
  const criticalPending = gaps.filter(
    (g) => g.importance === 'critical' && g.remediation === 'pending',
  ).length;

  return (
    <main
      role="main"
      aria-label="Intelligence Gaps"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 22,
        padding: '24px 28px 40px',
        background: 'var(--color-bg)',
        color: 'var(--color-ink-2)',
        fontFamily: 'var(--font-body)',
        minHeight: '100%',
      }}
    >
      {/* Header */}
      <header
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          paddingBottom: 18,
          borderBottom: '1px solid var(--color-divider)',
        }}
      >
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: 'var(--color-ink-3)',
          }}
        >
          Stage 05 · Intelligence Gaps
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, flexWrap: 'wrap' }}>
          <h1
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 30,
              fontWeight: 400,
              color: 'var(--color-ink)',
              letterSpacing: '-0.014em',
              margin: 0,
            }}
          >
            What we still don't know.
          </h1>
          <span
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 11.5,
              color: 'var(--color-ink-3)',
              letterSpacing: '0.04em',
            }}
          >
            {scope.engagementName} · {scope.focalAsset}
          </span>
          <span
            style={{
              marginLeft: 'auto',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              color: 'var(--color-ink-2)',
              letterSpacing: '0.04em',
            }}
          >
            <strong style={{ color: 'var(--color-ink)' }}>{total} gaps</strong>
            {' · '}
            <span style={{ color: 'var(--color-amber)' }}>{blocking} blocking</span>
            {' · '}
            <span style={{ color: criticalPending > 0 ? 'var(--color-red, #b91c1c)' : 'var(--color-ink-2)' }}>
              {unresolved} unresolved
            </span>
          </span>
        </div>
      </header>

      {/* Readiness banner */}
      <ReadinessBanner criticalPending={criticalPending} />

      {/* Importance filter */}
      {gaps.length > 0 && (
        <section>
          <SectionLabel>Filter by importance</SectionLabel>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {IMPORTANCE_ORDER.map((i) => {
              const isOn = activeImportance.has(i);
              const t = importanceTone(i);
              return (
                <button
                  type="button"
                  key={i}
                  data-importance={i}
                  aria-pressed={isOn}
                  onClick={() => toggle(i)}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                    letterSpacing: '0.16em',
                    textTransform: 'uppercase',
                    padding: '5px 12px',
                    background: isOn ? t.bg : 'transparent',
                    color: isOn ? t.fg : 'var(--color-ink-3)',
                    border: `1px solid ${isOn ? t.border : 'var(--color-line-2)'}`,
                    cursor: 'pointer',
                    fontWeight: 600,
                  }}
                >
                  {i}
                </button>
              );
            })}
            {activeImportance.size > 0 && (
              <button
                type="button"
                onClick={() => setActiveImportance(new Set())}
                style={{
                  fontFamily: 'var(--font-mono)',
                  fontSize: 10,
                  color: 'var(--color-ink-3)',
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  padding: '5px 6px',
                }}
              >
                clear ×
              </button>
            )}
          </div>
        </section>
      )}

      {/* Gap list */}
      <section>
        <SectionLabel>
          Gaps {activeImportance.size > 0 ? `· ${visible.length} of ${total}` : `· ${total}`}
        </SectionLabel>
        {visible.length === 0 ? (
          <div
            style={{
              padding: 20,
              border: '1px dashed var(--color-line-2)',
              color: 'var(--color-ink-3)',
              fontStyle: 'italic',
              fontSize: 13.5,
              textAlign: 'center',
            }}
          >
            {gaps.length === 0
              ? 'All caught — no unresolved gaps for this engagement.'
              : 'No gaps match the active filter.'}
          </div>
        ) : (
          <ul role="list" style={{ listStyle: 'none', margin: 0, padding: 0, display: 'flex', flexDirection: 'column', gap: 10 }}>
            {visible.map((g) => (
              <GapCard key={g.id} gap={g} onSetRemediation={onSetRemediation} />
            ))}
          </ul>
        )}
      </section>

      {/* Footer */}
      <footer
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          gap: 12,
          paddingTop: 16,
          borderTop: '1px solid var(--color-divider)',
        }}
      >
        <button
          type="button"
          aria-label="Mark stage complete"
          onClick={criticalPending === 0 ? onMarkComplete : undefined}
          disabled={criticalPending > 0}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 11,
            letterSpacing: '0.16em',
            textTransform: 'uppercase',
            padding: '8px 16px',
            background: criticalPending > 0 ? 'var(--color-surface-2)' : 'var(--color-accent)',
            color: criticalPending > 0 ? 'var(--color-ink-3)' : 'var(--color-surface)',
            border: `1px solid ${criticalPending > 0 ? 'var(--color-line-2)' : 'var(--color-accent)'}`,
            cursor: criticalPending > 0 ? 'not-allowed' : 'pointer',
            fontWeight: 600,
          }}
        >
          {criticalPending > 0
            ? `${criticalPending} critical pending — resolve first`
            : 'Mark stage complete →'}
        </button>
      </footer>
    </main>
  );
}
