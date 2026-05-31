/**
 * Loop C — EngagementDetailContainer.
 *
 * Fetches a single engagement (with brief) and renders the F4
 * EngagementShell with stage-routed content. Stages without dedicated
 * content yet render a "coming soon" placeholder — those slot in over
 * subsequent loops as each stage's container is built.
 *
 * URL contract:
 *   /ci?tab=engagements&engagement={eid}&stage={stage}
 *
 * Currently rendered "content" per stage:
 *   - brief    → echoes the BCB JSON (raw, until BriefPage container lands)
 *   - sources  → "coming soon"
 *   - dossier  → DossierContainer (live KB-backed 8-domain dossier) [KB3]
 *   - synthesis→ "coming soon"
 *   - gaps     → "coming soon"
 *   - scenarios→ "coming soon"
 *   - workshop → "coming soon"
 *
 * The point of this loop is to make engagement-detail navigation
 * actually work end-to-end; the per-stage content surfaces are their
 * own loops.
 */
import { useEffect, useState } from 'react';
import { engagementsApi, type EngagementDTO } from '../../api';
import {
  EngagementShell,
  LIFECYCLE_STAGES,
  type LifecycleStage,
  type ShellActiveEngagement,
} from '../layout/EngagementShell';
import DossierContainer from './DossierContainer';

interface Props {
  eid: string;
  stage?: LifecycleStage;
  onBackToPortfolio: () => void;
  onStageChange: (eid: string, stage: LifecycleStage) => void;
}

function daysUntil(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return null;
  return Math.ceil((d - Date.now()) / 86_400_000);
}

function toActive(e: EngagementDTO): ShellActiveEngagement {
  const idx = (LIFECYCLE_STAGES as readonly string[]).indexOf(e.stage);
  const completed = idx > 0 ? LIFECYCLE_STAGES.slice(0, idx) : [];
  return {
    id: e.id,
    name: e.name,
    focalAsset: e.asset,
    situation: e.situation,
    workshopDate: e.workshop_date,
    daysUntilWorkshop: daysUntil(e.workshop_date),
    stage: e.stage,
    completedStages: completed,
  };
}

// Per-stage content placeholder. As individual stage containers ship,
// import + render them here.
function StagePlaceholder({ stage }: { stage: LifecycleStage }) {
  const labels: Record<LifecycleStage, string> = {
    brief:     'Brief & Scope — full brief composer arrives in a follow-up loop.',
    sources:   'Sources & Gaps — sources detail coming soon.',
    dossier:   'Dossier — 8-domain dossier surface coming soon.',
    synthesis: 'Synthesis — Insight ledger coming soon.',
    gaps:      'Intelligence Gaps — gap log coming soon.',
    scenarios: 'Scenarios — event-triggered scenarios coming soon.',
    workshop:  'War Room + Decisions — workshop surface coming soon.',
  };
  return (
    <div
      data-testid="stage-placeholder"
      style={{
        padding: 'var(--space-7)',
        background: 'var(--color-surface)',
        borderRadius: 'var(--radius-panel)',
        color: 'var(--color-ink-2)',
        boxShadow: 'var(--shadow-sm)',
      }}
    >
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
        Stage · {stage}
      </div>
      <p style={{ margin: 0, fontSize: 16, lineHeight: 1.5 }}>
        {labels[stage]}
      </p>
    </div>
  );
}

export default function EngagementDetailContainer({
  eid, stage, onBackToPortfolio, onStageChange,
}: Props) {
  const [engagement, setEngagement] = useState<EngagementDTO | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    engagementsApi.get(eid)
      .then((e) => { if (!cancelled) setEngagement(e); })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [eid]);

  if (loading) {
    return (
      <div
        data-testid="engagement-loading"
        style={{
          padding: 'var(--space-7)',
          color: 'var(--color-ink-3)',
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
        }}
      >
        Loading engagement…
      </div>
    );
  }

  if (error || !engagement) {
    return (
      <div
        data-testid="engagement-error"
        style={{
          padding: 'var(--space-7)',
          color: 'var(--color-red)',
          fontFamily: 'var(--font-mono)',
          fontSize: 12,
        }}
      >
        {error
          ? `Engagement load error: ${error}`
          : `Engagement not found: ${eid}`}
        <div style={{ marginTop: 12 }}>
          <button
            onClick={onBackToPortfolio}
            style={{
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              padding: '8px 14px',
              borderRadius: 'var(--radius-pill)',
              background: 'var(--color-surface-2)',
              color: 'var(--color-ink)',
              cursor: 'pointer',
            }}
          >
            ← Back to portfolio
          </button>
        </div>
      </div>
    );
  }

  const active = toActive(engagement);
  const currentStage = (stage ?? engagement.stage) as LifecycleStage;

  return (
    <EngagementShell
      activeEngagement={active}
      currentStage={currentStage}
      onPortfolioSelect={onBackToPortfolio}
      onStageSelect={(engagementId, s) => onStageChange(engagementId, s)}
      sidebar={null}
    >
      {currentStage === 'dossier' ? (
        <DossierContainer
          engagement={engagement}
          onMarkComplete={() => onStageChange(engagement.id, 'synthesis')}
        />
      ) : (
        <StagePlaceholder stage={currentStage} />
      )}
    </EngagementShell>
  );
}
