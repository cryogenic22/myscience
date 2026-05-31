/**
 * F2 — EngagementSidebar tests.
 *
 * Engagement-spine IA. Portfolio at top, active engagement with 7 stages
 * below, other engagements collapsed. Stages are an ordered list with
 * accessible markup (nav > ol > aria-current="step"). Skip-ahead is
 * visually disabled (matches the Z3 FSM); back-track is enabled.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { EngagementSidebar, LIFECYCLE_STAGES } from '../../src/components/layout/EngagementSidebar';

const STAGES = LIFECYCLE_STAGES; // 7 strings, same order as Z3 STAGE_ORDER

describe('EngagementSidebar — IA shape', () => {
  it('renders the Portfolio link at the top', () => {
    render(
      <EngagementSidebar
        activeEngagement={null}
        otherEngagements={[]}
        onPortfolioSelect={() => {}}
        onEngagementSelect={() => {}}
        onStageSelect={() => {}}
      />,
    );
    expect(screen.getByRole('link', { name: /portfolio/i })).toBeInTheDocument();
  });

  it('shows the empty state when no active engagement', () => {
    render(
      <EngagementSidebar
        activeEngagement={null}
        otherEngagements={[]}
        onPortfolioSelect={() => {}}
        onEngagementSelect={() => {}}
        onStageSelect={() => {}}
      />,
    );
    expect(screen.getByText(/open an engagement/i)).toBeInTheDocument();
  });

  it('renders all 7 stages with 01–07 numbering when an engagement is active', () => {
    render(
      <EngagementSidebar
        activeEngagement={{
          id: 'e1', name: 'CagriSema Pre-Launch', stage: 'dossier',
          completedStages: ['brief', 'sources'],
        }}
        otherEngagements={[]}
        onPortfolioSelect={() => {}}
        onEngagementSelect={() => {}}
        onStageSelect={() => {}}
      />,
    );
    STAGES.forEach((stage, i) => {
      const num = String(i + 1).padStart(2, '0');
      expect(screen.getByText(new RegExp(num))).toBeInTheDocument();
    });
  });
});

describe('EngagementSidebar — stage markers', () => {
  function setup(stage: string, completed: string[] = []) {
    const onStageSelect = vi.fn();
    const utils = render(
      <EngagementSidebar
        activeEngagement={{
          id: 'e1', name: 'CagriSema Pre-Launch', stage,
          completedStages: completed,
        }}
        otherEngagements={[]}
        onPortfolioSelect={() => {}}
        onEngagementSelect={() => {}}
        onStageSelect={onStageSelect}
      />,
    );
    return { ...utils, onStageSelect };
  }

  it('marks the current stage with aria-current="step"', () => {
    const { container } = setup('dossier');
    const current = container.querySelector('[aria-current="step"]');
    expect(current).not.toBeNull();
    expect(current?.textContent).toMatch(/dossier/i);
  });

  it('marks completed stages with data-complete', () => {
    const { container } = setup('dossier', ['brief', 'sources']);
    const complete = container.querySelectorAll('[data-complete="true"]');
    expect(complete.length).toBe(2);
  });

  it('disables skip-ahead (stages beyond current+1 do not fire onStageSelect)', () => {
    const { container, onStageSelect } = setup('brief');
    // 'scenarios' is index 5; current 'brief' is 0 → skip-ahead
    const skipTarget = container.querySelector('[data-stage="scenarios"]');
    expect(skipTarget).not.toBeNull();
    fireEvent.click(skipTarget!);
    expect(onStageSelect).not.toHaveBeenCalled();
  });

  it('allows forward-by-one (current+1 fires onStageSelect)', () => {
    const { container, onStageSelect } = setup('brief');
    const fwd = container.querySelector('[data-stage="sources"]');
    expect(fwd).not.toBeNull();
    fireEvent.click(fwd!);
    expect(onStageSelect).toHaveBeenCalledWith('e1', 'sources');
  });

  it('allows back-track (earlier stages fire onStageSelect)', () => {
    const { container, onStageSelect } = setup('dossier', ['brief', 'sources']);
    const back = container.querySelector('[data-stage="brief"]');
    fireEvent.click(back!);
    expect(onStageSelect).toHaveBeenCalledWith('e1', 'brief');
  });

  it('clicking the current stage does NOT fire onStageSelect (already there)', () => {
    const { container, onStageSelect } = setup('dossier');
    const self = container.querySelector('[data-stage="dossier"]');
    fireEvent.click(self!);
    expect(onStageSelect).not.toHaveBeenCalled();
  });
});

describe('EngagementSidebar — other engagements', () => {
  it('renders "Other engagements" header with collapsed state by default', () => {
    render(
      <EngagementSidebar
        activeEngagement={{
          id: 'e1', name: 'CagriSema Pre-Launch', stage: 'brief',
          completedStages: [],
        }}
        otherEngagements={[
          { id: 'e2', name: 'Trulicity Defense Q3', workshopDate: '2026-07-15' },
          { id: 'e3', name: 'Keytruda LCM',         workshopDate: '2026-09-01' },
        ]}
        onPortfolioSelect={() => {}}
        onEngagementSelect={() => {}}
        onStageSelect={() => {}}
      />,
    );
    expect(screen.getByText(/other engagements/i)).toBeInTheDocument();
  });

  it('clicking another engagement fires onEngagementSelect', () => {
    const onEngagementSelect = vi.fn();
    const { container } = render(
      <EngagementSidebar
        activeEngagement={{
          id: 'e1', name: 'CagriSema', stage: 'brief', completedStages: [],
        }}
        otherEngagements={[
          { id: 'e2', name: 'Trulicity Defense', workshopDate: '2026-07-15' },
        ]}
        onPortfolioSelect={() => {}}
        onEngagementSelect={onEngagementSelect}
        onStageSelect={() => {}}
        defaultOtherOpen
      />,
    );
    const other = container.querySelector('[data-engagement-id="e2"]');
    fireEvent.click(other!);
    expect(onEngagementSelect).toHaveBeenCalledWith('e2');
  });
});

describe('EngagementSidebar — accessibility', () => {
  it('uses a nav landmark with a clear aria-label', () => {
    render(
      <EngagementSidebar
        activeEngagement={null}
        otherEngagements={[]}
        onPortfolioSelect={() => {}}
        onEngagementSelect={() => {}}
        onStageSelect={() => {}}
      />,
    );
    expect(
      screen.getByRole('navigation', { name: /engagement navigation/i }),
    ).toBeInTheDocument();
  });

  it('renders stages as an ordered list', () => {
    const { container } = render(
      <EngagementSidebar
        activeEngagement={{
          id: 'e1', name: 'CagriSema', stage: 'brief', completedStages: [],
        }}
        otherEngagements={[]}
        onPortfolioSelect={() => {}}
        onEngagementSelect={() => {}}
        onStageSelect={() => {}}
      />,
    );
    expect(container.querySelector('ol[data-stages]')).not.toBeNull();
  });
});
