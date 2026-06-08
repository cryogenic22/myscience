/**
 * F3 — PortfolioBoard: attention-this-week, not vanity KPIs.
 *
 * Information priority:
 *   1. Attention-this-week (upcoming workshops, stale evidence, gaps) leads.
 *   2. Engagement cards (one per active engagement) sit below.
 *   3. Numbers strip (small, terminal-style) at the bottom — reference only.
 *
 * When the three attention buckets are all empty, the panel renders a
 * calm "all clear" state rather than three empty boxes. This keeps the
 * page from screaming "nothing to do" — it explicitly says "nothing this
 * week, review the portfolio below."
 *
 * Headless: takes data via props, calls back via the on* handlers. The
 * page-level component wires it.
 */
import type { ReactNode } from 'react';

// ── Types ──────────────────────────────────────────────────────────

export interface AttentionData {
  upcomingWorkshops: {
    engagementId: string;
    name: string;
    daysUntil: number;
    readinessPct: number;
  }[];
  staleEvidenceCount: number;
  unresolvedGapsCount: number;
}

export interface PortfolioEngagement {
  id: string;
  name: string;
  focalAsset: string;
  situation: 'launch' | 'defense' | 'lcm';
  workshopDate: string | null;
  daysUntilWorkshop: number | null;
  currentStage: string;
  completedStagesCount: number; // 0–7
}

export interface PortfolioStats {
  activeCount: number;
  archivedCount: number;
  decisionsCommitted30d: number;
  factsAsserted7d: number;
}

export interface PortfolioBoardProps {
  attention: AttentionData;
  engagements: PortfolioEngagement[];
  stats: PortfolioStats;
  onEngagementOpen: (id: string) => void;
  onWorkshopOpen: (id: string) => void;
  onGapsReview: () => void;
  onStaleEvidenceReview: () => void;
}

// ── Shared atoms ───────────────────────────────────────────────────

function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        fontFamily: 'var(--font-mono)',
        fontSize: 10,
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

function SituationPill({ situation }: { situation: PortfolioEngagement['situation'] }) {
  return (
    <span
      data-situation={situation}
      style={{
        display: 'inline-block',
        fontFamily: 'var(--font-mono)',
        fontSize: 9.5,
        letterSpacing: '0.14em',
        textTransform: 'uppercase',
        padding: '2px 7px',
        border: '1px solid var(--color-line-2)',
        color: 'var(--color-ink-3)',
        background: 'var(--color-surface-2)',
      }}
    >
      {situation}
    </span>
  );
}

// ── Attention bucket ───────────────────────────────────────────────

function AttentionBucket({
  attention,
  onWorkshopOpen,
  onGapsReview,
  onStaleEvidenceReview,
}: {
  attention: AttentionData;
  onWorkshopOpen: (id: string) => void;
  onGapsReview: () => void;
  onStaleEvidenceReview: () => void;
}) {
  const allClear =
    attention.upcomingWorkshops.length === 0 &&
    attention.staleEvidenceCount === 0 &&
    attention.unresolvedGapsCount === 0;

  if (allClear) {
    return (
      <section
        aria-label="Attention this week"
        style={{
          padding: '20px 24px',
          background: 'var(--color-surface)',
          border: '1px solid var(--color-line)',
          color: 'var(--color-ink-2)',
        }}
      >
        <SectionLabel>Attention this week</SectionLabel>
        <div
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 20,
            fontWeight: 400,
            color: 'var(--color-ink)',
            marginBottom: 6,
          }}
        >
          All clear.
        </div>
        <div style={{ fontSize: 13, color: 'var(--color-ink-3)' }}>
          Nothing demands action this week. Review the portfolio below.
        </div>
      </section>
    );
  }

  return (
    <section
      aria-label="Attention this week"
      style={{
        display: 'grid',
        gridTemplateColumns: '2fr 1fr 1fr',
        gap: 12,
      }}
    >
      {/* Upcoming workshops */}
      <div
        style={{
          padding: '16px 18px',
          background: 'var(--color-surface)',
          border: '1px solid var(--color-line)',
        }}
      >
        <SectionLabel>Upcoming Workshops · {attention.upcomingWorkshops.length}</SectionLabel>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {attention.upcomingWorkshops.map((w) => {
            const critical = w.daysUntil <= 7;
            return (
              <div
                key={w.engagementId}
                data-critical={critical || undefined}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr auto',
                  alignItems: 'center',
                  gap: 12,
                  padding: '10px 12px',
                  borderLeft: critical
                    ? '3px solid var(--color-accent)'
                    : '3px solid var(--color-line-2)',
                  background: critical
                    ? 'var(--color-accent-soft)'
                    : 'var(--color-surface-2)',
                }}
              >
                <div>
                  <div
                    style={{
                      fontFamily: 'var(--font-display)',
                      fontWeight: 500,
                      fontSize: 14,
                      color: 'var(--color-ink)',
                      marginBottom: 2,
                    }}
                  >
                    {w.name}
                  </div>
                  <div
                    style={{
                      fontFamily: 'var(--font-mono)',
                      fontSize: 10.5,
                      color: 'var(--color-ink-3)',
                      letterSpacing: '0.04em',
                    }}
                  >
                    {w.daysUntil} days · readiness {w.readinessPct}%
                  </div>
                </div>
                <button
                  type="button"
                  data-action="open-workshop"
                  data-engagement-id={w.engagementId}
                  onClick={() => onWorkshopOpen(w.engagementId)}
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 10,
                    letterSpacing: '0.12em',
                    textTransform: 'uppercase',
                    padding: '5px 10px',
                    border: '1px solid var(--color-line-2)',
                    background: 'transparent',
                    color: critical ? 'var(--color-accent)' : 'var(--color-ink-2)',
                    cursor: 'pointer',
                  }}
                >
                  Open →
                </button>
              </div>
            );
          })}
        </div>
      </div>

      {/* Stale evidence */}
      <div
        onClick={() => onStaleEvidenceReview()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') onStaleEvidenceReview();
        }}
        style={{
          padding: '16px 18px',
          background: 'var(--color-surface)',
          border: '1px solid var(--color-line)',
          cursor: 'pointer',
        }}
      >
        <SectionLabel>Stale Evidence</SectionLabel>
        <div
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 32,
            fontWeight: 300,
            lineHeight: 1,
            color: attention.staleEvidenceCount > 0 ? 'var(--color-amber)' : 'var(--color-ink-3)',
            marginBottom: 4,
          }}
        >
          {attention.staleEvidenceCount}
        </div>
        <div style={{ fontSize: 12, color: 'var(--color-ink-3)' }}>
          across committed decisions
        </div>
      </div>

      {/* Unresolved gaps */}
      <div
        onClick={() => onGapsReview()}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') onGapsReview();
        }}
        style={{
          padding: '16px 18px',
          background: 'var(--color-surface)',
          border: '1px solid var(--color-line)',
          cursor: 'pointer',
        }}
      >
        <SectionLabel>Unresolved Gaps</SectionLabel>
        <div
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 32,
            fontWeight: 300,
            lineHeight: 1,
            color: attention.unresolvedGapsCount > 0 ? 'var(--color-red)' : 'var(--color-ink-3)',
            marginBottom: 4,
          }}
        >
          {attention.unresolvedGapsCount}
        </div>
        <div style={{ fontSize: 12, color: 'var(--color-ink-3)' }}>
          high importance, awaiting remediation
        </div>
      </div>
    </section>
  );
}

// ── Engagement card ────────────────────────────────────────────────

function EngagementCard({
  engagement,
  onOpen,
}: {
  engagement: PortfolioEngagement;
  onOpen: (id: string) => void;
}) {
  const readinessFraction = `${engagement.completedStagesCount}/7`;
  const readinessPct = (engagement.completedStagesCount / 7) * 100;
  const accent =
    engagement.daysUntilWorkshop !== null && engagement.daysUntilWorkshop <= 7
      ? 'var(--color-accent)'
      : engagement.daysUntilWorkshop !== null && engagement.daysUntilWorkshop <= 30
      ? 'var(--color-teal, var(--color-accent))'
      : 'var(--color-line-2)';
  return (
    <article
      data-engagement-id={engagement.id}
      onClick={() => onOpen(engagement.id)}
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-line)',
        borderLeft: `3px solid ${accent}`,
        padding: '16px 18px',
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12 }}>
        <div
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 17,
            fontWeight: 500,
            color: 'var(--color-ink)',
          }}
        >
          {engagement.name}
        </div>
        <SituationPill situation={engagement.situation} />
      </div>
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 11,
          color: 'var(--color-ink-3)',
          letterSpacing: '0.04em',
        }}
      >
        {engagement.focalAsset}
        {engagement.workshopDate ? ` · workshop ${engagement.workshopDate}` : ''}
        {engagement.daysUntilWorkshop !== null
          ? ` · in ${engagement.daysUntilWorkshop}d`
          : ''}
      </div>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto', alignItems: 'center', gap: 12 }}>
        <div
          data-readiness={readinessFraction}
          style={{
            height: 4,
            background: 'var(--color-surface-3)',
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          <div
            style={{
              position: 'absolute',
              left: 0,
              top: 0,
              bottom: 0,
              width: `${readinessPct}%`,
              background: accent,
            }}
          />
        </div>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            color: 'var(--color-ink-3)',
            letterSpacing: '0.06em',
          }}
        >
          {readinessFraction} · {engagement.currentStage}
        </span>
      </div>
    </article>
  );
}

// ── Stats strip ────────────────────────────────────────────────────

function StatsStrip({ stats }: { stats: PortfolioStats }) {
  const items: Array<[string, number]> = [
    ['active', stats.activeCount],
    ['archived', stats.archivedCount],
    ['decisions · 30d', stats.decisionsCommitted30d],
    ['facts · 7d', stats.factsAsserted7d],
  ];
  return (
    <div
      style={{
        display: 'flex',
        gap: 24,
        padding: '12px 18px',
        background: 'var(--color-surface-2)',
        border: '1px solid var(--color-line)',
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        color: 'var(--color-ink-3)',
        letterSpacing: '0.06em',
        flexWrap: 'wrap',
      }}
    >
      {items.map(([label, value]) => (
        <div key={label} style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
          <span
            style={{
              fontSize: 16,
              color: 'var(--color-ink)',
              fontWeight: 500,
              letterSpacing: 0,
            }}
          >
            {value}
          </span>
          <span style={{ textTransform: 'uppercase' }}>{label}</span>
        </div>
      ))}
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────

export function PortfolioBoard(props: PortfolioBoardProps) {
  const { attention, engagements, stats, onEngagementOpen, onWorkshopOpen,
          onGapsReview, onStaleEvidenceReview } = props;
  return (
    <main
      aria-label="Portfolio"
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 20,
        padding: '24px 28px 32px',
        background: 'var(--color-bg)',
        color: 'var(--color-ink-2)',
        fontFamily: 'var(--font-body)',
        minHeight: '100%',
      }}
    >
      <header>
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            color: 'var(--color-ink-3)',
            marginBottom: 6,
          }}
        >
          Portfolio
        </div>
        <h1
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 32,
            fontWeight: 400,
            color: 'var(--color-ink)',
            letterSpacing: '-0.012em',
            margin: 0,
          }}
        >
          What needs your attention this week.
        </h1>
      </header>

      <AttentionBucket
        attention={attention}
        onWorkshopOpen={onWorkshopOpen}
        onGapsReview={onGapsReview}
        onStaleEvidenceReview={onStaleEvidenceReview}
      />

      <section aria-label="Engagements">
        <SectionLabel>Engagements · {engagements.length}</SectionLabel>
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))',
            gap: 12,
          }}
        >
          {engagements.map((e) => (
            <EngagementCard key={e.id} engagement={e} onOpen={onEngagementOpen} />
          ))}
        </div>
      </section>

      <StatsStrip stats={stats} />
    </main>
  );
}
