/**
 * F3 — PortfolioBoard tests.
 *
 * Attention-this-week leads (not vanity KPIs). When all three attention
 * buckets are empty, render a calm "all clear" rather than empty buckets.
 * Critical countdowns get the accent color rail.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { PortfolioBoard } from '../../src/components/portfolio/PortfolioBoard';

const baseEngagements = [
  {
    id: 'e1', name: 'CagriSema Pre-Launch', focalAsset: 'drug:cagrisema',
    situation: 'launch', workshopDate: '2026-06-03', daysUntilWorkshop: 4,
    currentStage: 'dossier', completedStagesCount: 2,
  },
  {
    id: 'e2', name: 'Trulicity Defense Q3', focalAsset: 'drug:trulicity',
    situation: 'defense', workshopDate: '2026-08-10', daysUntilWorkshop: 72,
    currentStage: 'sources', completedStagesCount: 1,
  },
];

const baseStats = {
  activeCount: 2,
  archivedCount: 1,
  decisionsCommitted30d: 5,
  factsAsserted7d: 47,
};

describe('PortfolioBoard — attention this week', () => {
  it('renders three attention buckets when populated', () => {
    render(
      <PortfolioBoard
        attention={{
          upcomingWorkshops: [
            { engagementId: 'e1', name: 'CagriSema Pre-Launch', daysUntil: 4, readinessPct: 78 },
          ],
          staleEvidenceCount: 2,
          unresolvedGapsCount: 3,
        }}
        engagements={baseEngagements}
        stats={baseStats}
        onEngagementOpen={() => {}}
        onWorkshopOpen={() => {}}
        onGapsReview={() => {}}
        onStaleEvidenceReview={() => {}}
      />,
    );
    expect(screen.getByText(/upcoming workshop/i)).toBeInTheDocument();
    expect(screen.getByText(/stale evidence/i)).toBeInTheDocument();
    expect(screen.getByText(/unresolved gap/i)).toBeInTheDocument();
  });

  it('renders calm "all clear" state when nothing needs attention', () => {
    render(
      <PortfolioBoard
        attention={{
          upcomingWorkshops: [],
          staleEvidenceCount: 0,
          unresolvedGapsCount: 0,
        }}
        engagements={baseEngagements}
        stats={baseStats}
        onEngagementOpen={() => {}}
        onWorkshopOpen={() => {}}
        onGapsReview={() => {}}
        onStaleEvidenceReview={() => {}}
      />,
    );
    expect(screen.getByText(/all clear/i)).toBeInTheDocument();
  });

  it('critical-window workshop card uses the accent color rail', () => {
    const { container } = render(
      <PortfolioBoard
        attention={{
          upcomingWorkshops: [
            { engagementId: 'e1', name: 'CagriSema Pre-Launch', daysUntil: 4, readinessPct: 78 },
          ],
          staleEvidenceCount: 0,
          unresolvedGapsCount: 0,
        }}
        engagements={baseEngagements}
        stats={baseStats}
        onEngagementOpen={() => {}}
        onWorkshopOpen={() => {}}
        onGapsReview={() => {}}
        onStaleEvidenceReview={() => {}}
      />,
    );
    const critical = container.querySelector('[data-critical="true"]');
    expect(critical).not.toBeNull();
  });

  it('clicking the workshop open button fires onWorkshopOpen', () => {
    const onWorkshopOpen = vi.fn();
    const { container } = render(
      <PortfolioBoard
        attention={{
          upcomingWorkshops: [
            { engagementId: 'e1', name: 'CagriSema Pre-Launch', daysUntil: 4, readinessPct: 78 },
          ],
          staleEvidenceCount: 0,
          unresolvedGapsCount: 0,
        }}
        engagements={baseEngagements}
        stats={baseStats}
        onEngagementOpen={() => {}}
        onWorkshopOpen={onWorkshopOpen}
        onGapsReview={() => {}}
        onStaleEvidenceReview={() => {}}
      />,
    );
    const btn = container.querySelector('[data-action="open-workshop"][data-engagement-id="e1"]');
    expect(btn).not.toBeNull();
    fireEvent.click(btn!);
    expect(onWorkshopOpen).toHaveBeenCalledWith('e1');
  });
});

describe('PortfolioBoard — engagement cards', () => {
  function setup(onEngagementOpen = vi.fn()) {
    const utils = render(
      <PortfolioBoard
        attention={{ upcomingWorkshops: [], staleEvidenceCount: 0, unresolvedGapsCount: 0 }}
        engagements={baseEngagements}
        stats={baseStats}
        onEngagementOpen={onEngagementOpen}
        onWorkshopOpen={() => {}}
        onGapsReview={() => {}}
        onStaleEvidenceReview={() => {}}
      />,
    );
    return { ...utils, onEngagementOpen };
  }

  it('renders one card per engagement with data-engagement-id', () => {
    const { container } = setup();
    expect(container.querySelectorAll('[data-engagement-id]').length).toBeGreaterThanOrEqual(2);
  });

  it('clicking a card fires onEngagementOpen with the right id', () => {
    const { container, onEngagementOpen } = setup();
    const card = container.querySelector('article[data-engagement-id="e2"]');
    expect(card).not.toBeNull();
    fireEvent.click(card!);
    expect(onEngagementOpen).toHaveBeenCalledWith('e2');
  });

  it('readiness bar reflects completed stages / 7', () => {
    const { container } = setup();
    const bar = container.querySelector('[data-engagement-id="e1"] [data-readiness]');
    expect(bar).not.toBeNull();
    // CagriSema has 2 completed of 7 → ~29% width
    const width = bar?.getAttribute('data-readiness');
    expect(width).toBe('2/7');
  });

  it('renders situation pill (launch/defense/lcm)', () => {
    const { container } = setup();
    const pill = container.querySelector('[data-engagement-id="e1"] [data-situation="launch"]');
    expect(pill).not.toBeNull();
  });
});

describe('PortfolioBoard — stats strip', () => {
  it('renders all 4 numbers', () => {
    render(
      <PortfolioBoard
        attention={{ upcomingWorkshops: [], staleEvidenceCount: 0, unresolvedGapsCount: 0 }}
        engagements={baseEngagements}
        stats={baseStats}
        onEngagementOpen={() => {}}
        onWorkshopOpen={() => {}}
        onGapsReview={() => {}}
        onStaleEvidenceReview={() => {}}
      />,
    );
    expect(screen.getByText('2')).toBeInTheDocument();   // active
    expect(screen.getByText('1')).toBeInTheDocument();   // archived
    expect(screen.getByText('5')).toBeInTheDocument();   // decisions 30d
    expect(screen.getByText('47')).toBeInTheDocument();  // facts 7d
  });
});

describe('PortfolioBoard — accessibility', () => {
  it('uses a main landmark', () => {
    render(
      <PortfolioBoard
        attention={{ upcomingWorkshops: [], staleEvidenceCount: 0, unresolvedGapsCount: 0 }}
        engagements={baseEngagements}
        stats={baseStats}
        onEngagementOpen={() => {}}
        onWorkshopOpen={() => {}}
        onGapsReview={() => {}}
        onStaleEvidenceReview={() => {}}
      />,
    );
    expect(screen.getByRole('main', { name: /portfolio/i })).toBeInTheDocument();
  });
});
