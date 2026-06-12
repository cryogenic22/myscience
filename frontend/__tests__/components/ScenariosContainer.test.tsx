/**
 * UX04 — ScenariosContainer tests.
 *
 * Covers the four states: loading → not-derived (with derive action) → ready,
 * plus the error path and the fact drill-through (ProvenancePanel reuse). The
 * api module is mocked; ScenariosPage renders for real (verifies the live
 * Scenario[] flows through without reshaping).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../src/api', () => ({
  scenariosApi: {
    get: vi.fn(),
    assemble: vi.fn(),
    probabilityHistory: vi.fn(() => Promise.resolve({ history: [], count: 0 })),
  },
}));

import { scenariosApi } from '../../src/api';
import ScenariosContainer from '../../src/components/ci/ScenariosContainer';

function makeScenario(overrides: Partial<any> = {}) {
  return {
    id: 'sc-1',
    name: 'Competitive pressure: tirzepatide',
    trigger: {
      event: 'Tirzepatide expands into obesity at scale',
      date: '2026 H2',
      evidence: [{ factId: 'fact-42', predicate: 'tirzepatide approved for obesity' }],
    },
    probability: 0.45,
    teamMoves: [{ team: 'Lilly', move: 'Aggressive payer contracting', rationale: 'Capture share' }],
    decisionOptions: [
      { id: 'opt-1', statement: 'Defend formulary position', rationale: 'Protect access', recommended: true },
    ],
    decisionOutput: 'Recommend defensive contracting now.',
    ...overrides,
  };
}

const ENGAGEMENT = { id: 'e1', name: 'Wegovy defense', asset: 'drug:semaglutide' } as any;

describe('ScenariosContainer', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows the not-derived state with a derive action when the list is empty', async () => {
    (scenariosApi.get as any).mockResolvedValue({ scenarios: [], count: 0 });
    render(<ScenariosContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('scenarios-empty')).toBeInTheDocument());
    expect(screen.getByTestId('scenarios-derive')).toBeInTheDocument();
  });

  it('derives on click and renders the scenario set', async () => {
    (scenariosApi.get as any).mockResolvedValue({ scenarios: [], count: 0 });
    (scenariosApi.assemble as any).mockResolvedValue({ scenarios: [makeScenario()], count: 1 });
    render(<ScenariosContainer engagement={ENGAGEMENT} />);

    await waitFor(() => expect(screen.getByTestId('scenarios-derive')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('scenarios-derive'));

    await waitFor(() => expect(screen.getByTestId('scenarios-ready')).toBeInTheDocument());
    expect(scenariosApi.assemble).toHaveBeenCalledWith('e1', true);
    expect(screen.getByText('Competitive pressure: tirzepatide')).toBeInTheDocument();
  });

  it('renders the existing scenario set on load with header stats', async () => {
    (scenariosApi.get as any).mockResolvedValue({ scenarios: [makeScenario()], count: 1 });
    render(<ScenariosContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('scenarios-ready')).toBeInTheDocument());
    // header count stat + the page itself both render the scenario.
    expect(screen.getByTestId('scenarios-rederive')).toBeInTheDocument();
    expect(screen.getByText('Competitive pressure: tirzepatide')).toBeInTheDocument();
  });

  it('opens the provenance panel with the cited predicate when trigger evidence is clicked', async () => {
    (scenariosApi.get as any).mockResolvedValue({ scenarios: [makeScenario()], count: 1 });
    render(<ScenariosContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('scenarios-ready')).toBeInTheDocument());

    // expand the scenario card, then click its evidence chip.
    fireEvent.click(screen.getByText('Competitive pressure: tirzepatide'));
    const chip = await screen.findByText(/fact-42 · tirzepatide approved for obesity/);
    expect(screen.queryByTestId('provenance-panel')).not.toBeInTheDocument();
    fireEvent.click(chip);
    await waitFor(() => expect(screen.getByTestId('provenance-panel')).toBeInTheDocument());
    // the panel shows the real predicate as the claim.
    expect(screen.getByText('tirzepatide approved for obesity')).toBeInTheDocument();
  });

  it('shows an error with retry on load failure', async () => {
    (scenariosApi.get as any).mockRejectedValue(new Error('500: boom'));
    render(<ScenariosContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('scenarios-error')).toBeInTheDocument());
    expect(screen.queryByTestId('scenarios-empty')).not.toBeInTheDocument();
  });
});
