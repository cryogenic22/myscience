/**
 * SPEC_030 Stage 3 — RecommendationPanel
 *
 * Right panel. Shows ranked options + dissent (the "unanimous AI is
 * suspicious AI" rule). Commit CTA appears in `decision_pending`.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { makeBrief, makeOption } from './_fixtures';
import RecommendationPanel from '../../../src/components/ci/decisions/RecommendationPanel';

describe('RecommendationPanel', () => {
  it('shows "awaiting simulation" when state is pre-simulation_complete', () => {
    render(<RecommendationPanel brief={makeBrief({ state: 'human_review' })} onCommit={vi.fn()} />);
    expect(screen.getByText(/awaiting simulation/i)).toBeInTheDocument();
  });

  it('renders ranked options when state is simulation_complete', () => {
    const brief = makeBrief({
      state: 'simulation_complete',
      options: [
        makeOption({ ordinal: 1, label: 'Accelerate' }),
        makeOption({ ordinal: 2, label: 'Hold' }),
      ],
    });
    render(<RecommendationPanel brief={brief} onCommit={vi.fn()} />);
    expect(screen.getByText('Accelerate')).toBeInTheDocument();
    expect(screen.getByText('Hold')).toBeInTheDocument();
  });

  it('shows dissent block when more than one option exists', () => {
    const brief = makeBrief({
      state: 'simulation_complete',
      options: [
        makeOption({ ordinal: 1, label: 'Accelerate' }),
        makeOption({ ordinal: 2, label: 'Hold' }),
      ],
    });
    render(<RecommendationPanel brief={brief} onCommit={vi.fn()} />);
    expect(screen.getByText(/dissent|counter/i)).toBeInTheDocument();
  });

  it('"Commit decision" button appears in decision_pending and is disabled until backend endpoint ships', () => {
    const brief = makeBrief({ state: 'decision_pending', options: [makeOption(), makeOption({ ordinal: 2 })] });
    render(<RecommendationPanel brief={brief} onCommit={vi.fn()} />);
    const btn = screen.getByRole('button', { name: /commit decision/i });
    expect(btn).toBeDisabled();
  });

  it('committed state renders a link/chip back to the linked decision', () => {
    const brief = makeBrief({
      state: 'committed',
      decision_id: 'd-001',
      options: [makeOption()],
    });
    render(<RecommendationPanel brief={brief} onCommit={vi.fn()} />);
    expect(screen.getByText(/d-001/)).toBeInTheDocument();
  });

  it.todo('"Commit decision" enables once /decisions/from-brief backend lands and calls onCommit(brief_id)');
  it.todo('option cards show predicted_outcome ranges via RangeReadout primitive');
});
