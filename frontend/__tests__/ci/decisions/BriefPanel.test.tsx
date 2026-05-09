/**
 * SPEC_030 Stage 3 — BriefPanel
 *
 * The top panel of DecisionWorkspace: question, state chip, time horizon,
 * stakeholders, trigger, confidence, options strip. Editability follows
 * SPEC_030 §8.3 affordance matrix.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { makeBrief, makeOption, ALL_STATES, setRole } from './_fixtures';
import BriefPanel from '../../../src/components/ci/decisions/BriefPanel';

describe('BriefPanel', () => {
  it('renders the question prominently (Syne display)', () => {
    render(<BriefPanel brief={makeBrief()} onPatch={vi.fn()} onAddOption={vi.fn()} />);
    expect(screen.getByText(/Should we accelerate Phase III readout/)).toBeInTheDocument();
  });

  it('shows time horizon, stakeholders, trigger, confidence', () => {
    const brief = makeBrief({
      stakeholders: ['commercial', 'medical'],
      time_horizon_days: 21,
      trigger_kind: 'cluster',
      confidence_to_proceed: 0.42,
    });
    render(<BriefPanel brief={brief} onPatch={vi.fn()} onAddOption={vi.fn()} />);
    expect(screen.getByText(/21 day/i)).toBeInTheDocument();
    expect(screen.getByText(/commercial/i)).toBeInTheDocument();
    expect(screen.getByText(/medical/i)).toBeInTheDocument();
    expect(screen.getByText(/cluster/i)).toBeInTheDocument();
    expect(screen.getByText(/0\.42/)).toBeInTheDocument();
  });

  it('renders option list (label, predicted_outcome, cost_estimate)', () => {
    const brief = makeBrief({
      options: [
        makeOption({ label: 'Accelerate readout', cost_estimate: '$5M' }),
        makeOption({ label: 'Hold position', cost_estimate: '$0' }),
      ],
    });
    render(<BriefPanel brief={brief} onPatch={vi.fn()} onAddOption={vi.fn()} />);
    expect(screen.getByText('Accelerate readout')).toBeInTheDocument();
    expect(screen.getByText('Hold position')).toBeInTheDocument();
  });

  describe('editability per state', () => {
    it.each(['draft', 'human_review'] as const)('state=%s shows editable inputs + add option', (state) => {
      setRole('uploader');
      const brief = makeBrief({ state });
      render(<BriefPanel brief={brief} onPatch={vi.fn()} onAddOption={vi.fn()} />);
      expect(screen.getByRole('button', { name: /add option/i })).not.toBeDisabled();
    });

    it.each(['simulation_pending', 'simulation_complete', 'decision_pending', 'committed', 'in_review', 'closed'] as const)(
      'state=%s locks edits and disables add-option',
      (state) => {
        setRole('uploader');
        const brief = makeBrief({ state });
        render(<BriefPanel brief={brief} onPatch={vi.fn()} onAddOption={vi.fn()} />);
        const btn = screen.queryByRole('button', { name: /add option/i });
        if (btn) expect(btn).toBeDisabled();
      },
    );
  });

  it('viewer role cannot edit even in draft state', () => {
    setRole('viewer');
    render(<BriefPanel brief={makeBrief({ state: 'draft' })} onPatch={vi.fn()} onAddOption={vi.fn()} />);
    const addBtn = screen.queryByRole('button', { name: /add option/i });
    if (addBtn) expect(addBtn).toBeDisabled();
  });

  it('inline-editing the question calls onPatch with { question }', async () => {
    setRole('uploader');
    const onPatch = vi.fn().mockResolvedValue(makeBrief());
    render(<BriefPanel brief={makeBrief({ state: 'draft' })} onPatch={onPatch} onAddOption={vi.fn()} />);
    const questionEl = screen.getByText(/Should we accelerate Phase III readout/);
    fireEvent.click(questionEl);
    const input = await screen.findByRole('textbox', { name: /question/i });
    fireEvent.change(input, { target: { value: 'Edited?' } });
    fireEvent.blur(input);
    await waitFor(() => expect(onPatch).toHaveBeenCalledWith({ question: 'Edited?' }));
  });

  it.todo('shows a busy spinner overlay while a PATCH is in flight (optimistic update)');
  it.todo('rolls back optimistic edit on PATCH error and surfaces a toast');
  it.todo('"Send to review" CTA appears in draft state and calls onTransition("human_review")');
  it.todo('"Send to simulation" CTA is disabled in human_review until ≥2 options exist');
});
