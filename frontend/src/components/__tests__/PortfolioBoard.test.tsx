import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { PortfolioBoard, type AttentionData, type PortfolioStats } from '../portfolio/PortfolioBoard';

const handlers = {
  onEngagementOpen: vi.fn(),
  onWorkshopOpen: vi.fn(),
  onGapsReview: vi.fn(),
  onStaleEvidenceReview: vi.fn(),
};

const baseStats: PortfolioStats = {
  activeCount: 2,
  archivedCount: 1,
  decisionsCommitted30d: null, // not computed yet
  factsAsserted7d: null,
};

function renderBoard(attention: AttentionData, stats: PortfolioStats = baseStats) {
  return render(
    <PortfolioBoard attention={attention} engagements={[]} stats={stats} {...handlers} />,
  );
}

describe('PortfolioBoard — no fabricated metrics', () => {
  it('shows "—" (not a fake 0) for untracked stats-strip metrics', () => {
    renderBoard({ upcomingWorkshops: [], staleEvidenceCount: null, unresolvedGapsCount: null });
    // Real, computed metrics still render their values...
    expect(screen.getByText('active').closest('div')).toHaveTextContent('2');
    // ...but the un-wired ones render as unavailable, not a confident 0.
    expect(screen.getByText('decisions · 30d').closest('div')).toHaveTextContent('—');
    expect(screen.getByText('facts · 7d').closest('div')).toHaveTextContent('—');
  });

  it('renders untracked attention counts as "not tracked yet", not 0', () => {
    // A real signal (an upcoming workshop) forces the attention section to show.
    renderBoard({
      upcomingWorkshops: [{ engagementId: 'e1', name: 'Alpha', daysUntil: 3, readinessPct: 50 }],
      staleEvidenceCount: null,
      unresolvedGapsCount: null,
    });
    expect(screen.getByText('Stale Evidence')).toBeInTheDocument();
    expect(screen.getByText('Unresolved Gaps')).toBeInTheDocument();
    // Both untracked buckets say so, rather than showing a prominent fake "0".
    expect(screen.getAllByText('not tracked yet')).toHaveLength(2);
  });

  it('untracked (null) counts do NOT fabricate an all-clear or force the attention buckets', () => {
    // With no real workshops and both counts untracked, it must read "All clear"
    // — the old fabricated 0s made `=== 0` always true, so this was accidentally
    // right for the wrong reason; null must not flip it to a false alarm either.
    renderBoard({ upcomingWorkshops: [], staleEvidenceCount: null, unresolvedGapsCount: null });
    expect(screen.getByText('All clear.')).toBeInTheDocument();
    expect(screen.queryByText('Stale Evidence')).not.toBeInTheDocument();
  });

  it('a real positive gap count still raises attention (not masked by the null path)', () => {
    renderBoard({ upcomingWorkshops: [], staleEvidenceCount: null, unresolvedGapsCount: 3 });
    expect(screen.queryByText('All clear.')).not.toBeInTheDocument();
    expect(screen.getByText('Unresolved Gaps')).toBeInTheDocument();
  });
});
