/**
 * Loop B + B2 — EngagementsTab.
 *
 * Container that fetches /engagements (Loop A backend) and renders the
 * F3 PortfolioBoard headless component. Loop B2 added the create flow:
 * a "+ New engagement" button surfaces a NewEngagementModal that posts
 * to the API and on success refreshes the list (or navigates to the
 * newly-created engagement).
 */
import { useEffect, useState } from 'react';
import { Plus } from 'lucide-react';
import { engagementsApi, type EngagementDTO } from '../../api';
import {
  PortfolioBoard,
  type PortfolioEngagement,
  type AttentionData,
  type PortfolioStats,
} from '../portfolio/PortfolioBoard';
import NewEngagementModal from './NewEngagementModal';

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
  /** PB-IX01 — promote bridge: open the create modal pre-seeded from a signal. */
  autoNew?: boolean;
  seedAsset?: string;
  seedName?: string;
  seedContext?: string;
  seedSignalId?: string;
  /** Called once the seed has been consumed so the URL params can be cleared. */
  onSeedConsumed?: () => void;
}

export default function EngagementsTab({
  onEngagementOpen, autoNew, seedAsset, seedName, seedContext, seedSignalId, onSeedConsumed,
}: Props) {
  const [items, setItems] = useState<EngagementDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modalOpen, setModalOpen] = useState(false);
  // Capture the promote seed into local state so it survives the URL-param
  // clear (onSeedConsumed) that fires in the same tick.
  const [seed, setSeed] = useState<
    { asset?: string; name?: string; context?: string; signalId?: string } | null
  >(null);

  // PB-IX01 — auto-open the create modal when arriving via a signal promote
  // (?new=1). Fire once; clear the URL seed so closing the modal stays closed.
  useEffect(() => {
    if (autoNew) {
      setSeed({ asset: seedAsset, name: seedName, context: seedContext, signalId: seedSignalId });
      setModalOpen(true);
      onSeedConsumed?.();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoNew]);

  const load = () => {
    setLoading(true);
    return engagementsApi.list({ limit: 50 })
      .then((r) => setItems(r.engagements))
      .catch((e) => setError(String(e?.message ?? e)))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    let cancelled = false;
    engagementsApi.list({ limit: 50 })
      .then((r) => { if (!cancelled) setItems(r.engagements); })
      .catch((e) => { if (!cancelled) setError(String(e?.message ?? e)); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);

  const open = onEngagementOpen ?? (() => {});

  // Shared header — appears across all states so the "create" CTA is
  // discoverable even when the list is empty.
  const Header = (
    <div
      data-testid="engagements-header"
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: 'var(--space-5) var(--space-6) 0',
      }}
    >
      <div
        style={{
          fontFamily: 'var(--font-mono)',
          fontSize: 10.5,
          letterSpacing: '0.16em',
          textTransform: 'uppercase',
          color: 'var(--color-ink-3)',
        }}
      >
        Engagements · {items.length}
      </div>
      <button
        type="button"
        data-testid="engagements-new-button"
        onClick={() => { setSeed(null); setModalOpen(true); }}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          padding: '8px 14px',
          borderRadius: 'var(--radius-pill)',
          background: 'var(--color-ink)',
          color: 'var(--color-bg)',
          fontSize: 13,
          fontWeight: 500,
          border: 'none',
          cursor: 'pointer',
          transitionDuration: '180ms',
        }}
      >
        <Plus size={14} /> New engagement
      </button>
    </div>
  );

  const Body = (() => {
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
            Click <strong>New engagement</strong> above to scope a structured CI workshop.
          </p>
        </div>
      );
    }

    const portfolioItems = items.map(toPortfolioShape);
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
  })();

  return (
    <>
      {Header}
      {Body}
      <NewEngagementModal
        open={modalOpen}
        initialAsset={seed?.asset}
        initialName={seed?.name}
        initialContext={seed?.context}
        initialSignalId={seed?.signalId}
        onClose={() => setModalOpen(false)}
        onCreated={(eng) => {
          setModalOpen(false);
          // Open the newly-created engagement immediately. Caller may
          // route to the detail page; we also refresh the list in the
          // background so the count + portfolio reflect reality.
          load();
          open(eng.id);
        }}
      />
    </>
  );
}
