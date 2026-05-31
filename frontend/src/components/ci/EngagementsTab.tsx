/**
 * Loop B — EngagementsTab.
 *
 * Container that fetches /engagements (Loop A backend) and renders the
 * F3 PortfolioBoard headless component. The first concrete demo of the
 * v7 IA inside /ci.
 *
 * Transforms the API DTO shape into PortfolioBoard's prop shape. Attention
 * + stats data come from a couple of simple derivations off the engagement
 * list (no separate endpoint yet — those land in their own loops).
 */
import { useEffect, useState } from 'react';
import { engagementsApi, type EngagementDTO } from '../../api';
import {
  PortfolioBoard,
  type PortfolioEngagement,
  type AttentionData,
  type PortfolioStats,
} from '../portfolio/PortfolioBoard';

const STAGE_ORDER = [
  'brief', 'sources', 'dossier', 'synthesis',
  'gaps', 'scenarios', 'workshop',
] as const;

function daysUntil(iso: string | null): number | null {
  if (!iso) return null;
  const d = new Date(iso).getTime();
  if (Number.isNaN(d)) return null;
  return Math.ceil((d - Date.now()) / 86_400_000);
}

function toPortfolioShape(e: EngagementDTO): PortfolioEngagement {
  const completedIdx = STAGE_ORDER.indexOf(e.stage as typeof STAGE_ORDER[number]);
  return {
    id: e.id,
    name: e.name,
    focalAsset: e.asset,
    situation: e.situation,
    workshopDate: e.workshop_date,
    daysUntilWorkshop: daysUntil(e.workshop_date),
    currentStage: e.stage,
    completedStagesCount: completedIdx < 0 ? 0 : completedIdx,
  };
}

function deriveAttention(items: PortfolioEngagement[]): AttentionData {
  const upcomingWorkshops = items
    .filter((e) =>
      e.daysUntilWorkshop !== null &&
      e.daysUntilWorkshop >= 0 &&
      e.daysUntilWorkshop <= 14,
    )
    .map((e) => ({
      engagementId: e.id,
      name: e.name,
      daysUntil: e.daysUntilWorkshop!,
      readinessPct: Math.round((e.completedStagesCount / 7) * 100),
    }));
  return {
    upcomingWorkshops,
    staleEvidenceCount: 0,
    unresolvedGapsCount: 0,
  };
}

function deriveStats(items: EngagementDTO[]): PortfolioStats {
  return {
    activeCount: items.filter((e) => e.status === 'active').length,
    archivedCount: items.filter((e) => e.status === 'archived').length,
    decisionsCommitted30d: 0,
    factsAsserted7d: 0,
  };
}

interface Props {
  onEngagementOpen?: (id: string) => void;
}

export default function EngagementsTab({ onEngagementOpen }: Props) {
  const [items, setItems] = useState<EngagementDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    engagementsApi.list({ limit: 50 })
      .then((r) => { if (!cancelled) setItems(r.engagements); })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <div style={{
        padding: 'var(--space-7)',
        color: 'var(--color-ink-3)',
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
      }}>
        Loading engagements…
      </div>
    );
  }

  if (error) {
    return (
      <div style={{
        padding: 'var(--space-7)',
        color: 'var(--color-red)',
        fontFamily: 'var(--font-mono)',
        fontSize: 12,
      }}>
        Engagement feed error: {error}
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div
        data-testid="engagements-empty"
        style={{
          padding: 'var(--space-7)',
          textAlign: 'center',
          color: 'var(--color-ink-3)',
        }}
      >
        <p style={{
          fontFamily: 'var(--font-display)',
          fontSize: 24,
          marginBottom: 8,
          color: 'var(--color-ink)',
        }}>
          No engagements yet
        </p>
        <p style={{ fontSize: 14 }}>
          Create one to scope a structured CI workshop.
        </p>
      </div>
    );
  }

  const portfolioItems = items.map(toPortfolioShape);
  const open = onEngagementOpen ?? (() => {});

  return (
    <PortfolioBoard
      attention={deriveAttention(portfolioItems)}
      engagements={portfolioItems}
      stats={deriveStats(items)}
      onEngagementOpen={open}
      onWorkshopOpen={open}
      onGapsReview={() => {}}
      onStaleEvidenceReview={() => {}}
    />
  );
}
