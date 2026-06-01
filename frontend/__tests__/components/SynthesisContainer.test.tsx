/**
 * UX06 — SynthesisContainer tests.
 *
 * Covers loading → not-derived (derive action) → ready, the error path, and
 * the citation drill-through (ProvenancePanel reuse). The api module is
 * mocked; SynthesisPage renders for real (verifies the live shape flows
 * through without reshaping).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';

vi.mock('../../src/api', () => ({
  synthesisApi: { get: vi.fn(), assemble: vi.fn() },
}));

import { synthesisApi } from '../../src/api';
import SynthesisContainer from '../../src/components/ci/SynthesisContainer';

const ENGAGEMENT = { id: 'e1', name: 'Wegovy defense', asset: 'drug:semaglutide' } as any;

function makeResponse(overrides: Partial<any> = {}) {
  return {
    passRate: 100,
    count: 1,
    insights: [{
      id: 'i1',
      statement: 'Competitive exposure: semaglutide contends with 4 in-class rivals.',
      strategicFrame: 'risk',
      domain: 'competitive',
      derivedFrom: [{ factId: 'fact-9', predicate: 'competes_with', contribution: 'drug:Dulaglutide competes_with' }],
      synthesisTestRationale: 'grounded in 1 fact',
    }],
    rejectedInsights: [],
    ...overrides,
  };
}

describe('SynthesisContainer', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows the not-derived state with a derive action when empty', async () => {
    (synthesisApi.get as any).mockResolvedValue({ insights: [], rejectedInsights: [], passRate: 0, count: 0 });
    render(<SynthesisContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('synthesis-empty')).toBeInTheDocument());
    expect(screen.getByTestId('synthesis-derive')).toBeInTheDocument();
  });

  it('derives on click and renders the insight set', async () => {
    (synthesisApi.get as any).mockResolvedValue({ insights: [], rejectedInsights: [], passRate: 0, count: 0 });
    (synthesisApi.assemble as any).mockResolvedValue(makeResponse());
    render(<SynthesisContainer engagement={ENGAGEMENT} />);

    await waitFor(() => expect(screen.getByTestId('synthesis-derive')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('synthesis-derive'));

    await waitFor(() => expect(screen.getByTestId('synthesis-ready')).toBeInTheDocument());
    expect(synthesisApi.assemble).toHaveBeenCalledWith('e1');
    expect(screen.getByText(/Competitive exposure: semaglutide/)).toBeInTheDocument();
  });

  it('renders the existing synthesis on load with pass-rate header', async () => {
    (synthesisApi.get as any).mockResolvedValue(makeResponse());
    render(<SynthesisContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('synthesis-ready')).toBeInTheDocument());
    expect(screen.getByTestId('synthesis-rederive')).toBeInTheDocument();
    expect(screen.getAllByText('100%').length).toBeGreaterThan(0);   // header + page pass-rate
  });

  it('opens the provenance panel with the citation contribution when a fact is clicked', async () => {
    (synthesisApi.get as any).mockResolvedValue(makeResponse());
    render(<SynthesisContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('synthesis-ready')).toBeInTheDocument());

    expect(screen.queryByTestId('provenance-panel')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('fact-9'));   // citation fact id is clickable
    const panel = await screen.findByTestId('provenance-panel');
    // the panel renders the citation's contribution as the claim (also shown in
    // the citation row, hence scope the lookup to the panel).
    expect(within(panel).getByText('drug:Dulaglutide competes_with')).toBeInTheDocument();
  });

  it('shows an error with retry on load failure', async () => {
    (synthesisApi.get as any).mockRejectedValue(new Error('500: boom'));
    render(<SynthesisContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('synthesis-error')).toBeInTheDocument());
    expect(screen.queryByTestId('synthesis-empty')).not.toBeInTheDocument();
  });
});
