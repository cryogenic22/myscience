/**
 * F4 — EngagementShell tests.
 *
 * Top-level page frame that mounts the sidebar (F2), the engagement
 * header, the 7-stage stepper, and the per-stage content (F5-F12).
 * Sidebar is a slot prop, so the shell stays independent of F2's PR.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EngagementShell, LIFECYCLE_STAGES } from '../../src/components/layout/EngagementShell';

const ACTIVE = {
  id: 'e1',
  name: 'CagriSema Pre-Launch',
  focalAsset: 'drug:cagrisema',
  situation: 'launch' as const,
  workshopDate: '2026-06-03',
  daysUntilWorkshop: 4,
  stage: 'dossier' as const,
  completedStages: ['brief', 'sources'] as const,
};

describe('EngagementShell — frame composition', () => {
  it('renders the sidebar slot + header + stepper + content when active', () => {
    render(
      <EngagementShell
        activeEngagement={ACTIVE}
        currentStage="dossier"
        onPortfolioSelect={() => {}}
        onStageSelect={() => {}}
        sidebar={<aside data-testid="sidebar-slot">sidebar</aside>}
      >
        <div data-testid="stage-content">stage content</div>
      </EngagementShell>,
    );
    expect(screen.getByTestId('sidebar-slot')).toBeInTheDocument();
    expect(screen.getByText(/CagriSema Pre-Launch/)).toBeInTheDocument();
    expect(screen.getByTestId('stage-content')).toBeInTheDocument();
    expect(screen.getByRole('list', { name: /lifecycle progress/i })).toBeInTheDocument();
  });

  it('renders the empty state with a "Return to Portfolio" affordance when no engagement', () => {
    const onPortfolioSelect = vi.fn();
    render(
      <EngagementShell
        activeEngagement={null}
        currentStage="brief"
        onPortfolioSelect={onPortfolioSelect}
        onStageSelect={() => {}}
        sidebar={<aside />}
      >
        <div>should not render</div>
      </EngagementShell>,
    );
    const link = screen.getByRole('link', { name: /return to portfolio/i });
    expect(link).toBeInTheDocument();
    fireEvent.click(link);
    expect(onPortfolioSelect).toHaveBeenCalled();
  });
});

describe('EngagementShell — header status tone', () => {
  it('marks workshop within 7 days as critical', () => {
    const { container } = render(
      <EngagementShell
        activeEngagement={{ ...ACTIVE, daysUntilWorkshop: 4 }}
        currentStage="dossier"
        onPortfolioSelect={() => {}}
        onStageSelect={() => {}}
        sidebar={<aside />}
      >
        <div />
      </EngagementShell>,
    );
    expect(container.querySelector('[data-workshop-window="critical"]')).not.toBeNull();
  });

  it('marks 8–30 days as soon', () => {
    const { container } = render(
      <EngagementShell
        activeEngagement={{ ...ACTIVE, daysUntilWorkshop: 18 }}
        currentStage="dossier"
        onPortfolioSelect={() => {}}
        onStageSelect={() => {}}
        sidebar={<aside />}
      >
        <div />
      </EngagementShell>,
    );
    expect(container.querySelector('[data-workshop-window="soon"]')).not.toBeNull();
  });

  it('marks >30 days as muted', () => {
    const { container } = render(
      <EngagementShell
        activeEngagement={{ ...ACTIVE, daysUntilWorkshop: 90 }}
        currentStage="dossier"
        onPortfolioSelect={() => {}}
        onStageSelect={() => {}}
        sidebar={<aside />}
      >
        <div />
      </EngagementShell>,
    );
    expect(container.querySelector('[data-workshop-window="distant"]')).not.toBeNull();
  });
});

describe('EngagementShell — stepper', () => {
  it('renders 7 dots with stage attributes', () => {
    const { container } = render(
      <EngagementShell
        activeEngagement={ACTIVE}
        currentStage="dossier"
        onPortfolioSelect={() => {}}
        onStageSelect={() => {}}
        sidebar={<aside />}
      >
        <div />
      </EngagementShell>,
    );
    const dots = container.querySelectorAll('[data-stepper-stage]');
    expect(dots.length).toBe(LIFECYCLE_STAGES.length); // 7
  });

  it('marks current stage with aria-current="step"', () => {
    const { container } = render(
      <EngagementShell
        activeEngagement={ACTIVE}
        currentStage="dossier"
        onPortfolioSelect={() => {}}
        onStageSelect={() => {}}
        sidebar={<aside />}
      >
        <div />
      </EngagementShell>,
    );
    const current = container.querySelector('[aria-current="step"]');
    expect(current).not.toBeNull();
    expect(current?.getAttribute('data-stepper-stage')).toBe('dossier');
  });

  it('marks completed stages with data-complete', () => {
    const { container } = render(
      <EngagementShell
        activeEngagement={ACTIVE}
        currentStage="dossier"
        onPortfolioSelect={() => {}}
        onStageSelect={() => {}}
        sidebar={<aside />}
      >
        <div />
      </EngagementShell>,
    );
    const complete = container.querySelectorAll('[data-stepper-stage][data-complete="true"]');
    expect(complete.length).toBe(2); // brief, sources
  });

  it('clicking the next stage in the stepper fires onStageSelect', () => {
    const onStageSelect = vi.fn();
    const { container } = render(
      <EngagementShell
        activeEngagement={ACTIVE}
        currentStage="dossier"
        onPortfolioSelect={() => {}}
        onStageSelect={onStageSelect}
        sidebar={<aside />}
      >
        <div />
      </EngagementShell>,
    );
    const next = container.querySelector('[data-stepper-stage="synthesis"]');
    fireEvent.click(next!);
    expect(onStageSelect).toHaveBeenCalledWith('e1', 'synthesis');
  });

  it('clicking a skip-ahead stage does NOT fire onStageSelect', () => {
    const onStageSelect = vi.fn();
    const { container } = render(
      <EngagementShell
        activeEngagement={ACTIVE}
        currentStage="brief"
        onPortfolioSelect={() => {}}
        onStageSelect={onStageSelect}
        sidebar={<aside />}
      >
        <div />
      </EngagementShell>,
    );
    const skip = container.querySelector('[data-stepper-stage="scenarios"]');
    fireEvent.click(skip!);
    expect(onStageSelect).not.toHaveBeenCalled();
  });

  it('clicking an earlier stage fires onStageSelect (back-track allowed)', () => {
    const onStageSelect = vi.fn();
    const { container } = render(
      <EngagementShell
        activeEngagement={ACTIVE}
        currentStage="dossier"
        onPortfolioSelect={() => {}}
        onStageSelect={onStageSelect}
        sidebar={<aside />}
      >
        <div />
      </EngagementShell>,
    );
    const back = container.querySelector('[data-stepper-stage="brief"]');
    fireEvent.click(back!);
    expect(onStageSelect).toHaveBeenCalledWith('e1', 'brief');
  });
});
