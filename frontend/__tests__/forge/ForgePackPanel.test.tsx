/**
 * DF — ForgePackPanel tests.
 *
 * Covers the live pack payoff: the playbook's dimensions render (the "I built
 * this" view), the version badge shows, a 404 surfaces the honest "not authored
 * yet" empty state, and a supplied matrix reuses DecompositionMatrix.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../../src/api', () => ({
  playbooksApi: { get: vi.fn() },
}));

import { playbooksApi } from '../../src/api';
import ForgePackPanel from '../../src/components/forge/ForgePackPanel';

function makeDetail(overrides: Partial<any> = {}) {
  return {
    playbook: {
      id: 'compare.drug_x_drug',
      pack: 'pharma',
      trigger: { intent: 'compare', entities: 'drug x drug' },
      synthesis: { shape: 'matrix' },
      dimensions: [
        { key: 'efficacy', label: 'Efficacy / endpoints', sub_question: '', routes: ['predicate:trial_result'], required: false, weight: 0.7 },
      ],
    },
    meta: { version: 4, author: 'sme-1', active: true },
    ...overrides,
  };
}

const MATRIX = {
  playbook_id: 'compare.drug_x_drug',
  intent: 'compare',
  entities: [{ entity_id: 'd1', label: 'semaglutide', entity_type: 'drug' }],
  dimensions: [{ key: 'efficacy', label: 'Efficacy', sub_question: 'q', routes: [], required: false, weight: 0.7 }],
  cells: [{ dimension: 'efficacy', entity_id: 'd1', sub_question: 'q', coverage: 'covered', facts: [], routes_executed: [], routes_skipped: [] }],
  coverage_summary: { efficacy: 'covered' },
  gaps: [],
  synthesis: {},
} as any;

describe('ForgePackPanel', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders the playbook dimensions and version', async () => {
    (playbooksApi.get as any).mockResolvedValue(makeDetail());
    render(<ForgePackPanel playbookId="compare.drug_x_drug" />);

    await waitFor(() => expect(screen.getByTestId('forge-pack-dim-efficacy')).toBeInTheDocument());
    expect(screen.getByTestId('forge-pack-version')).toHaveTextContent('v4');
  });

  it('shows the not-authored empty state on a 404', async () => {
    (playbooksApi.get as any).mockRejectedValue(new Error('404: playbook not found in DB'));
    render(<ForgePackPanel playbookId="compare.drug_x_drug" />);
    await waitFor(() => expect(screen.getByTestId('forge-pack-empty')).toBeInTheDocument());
  });

  it('renders the DecompositionMatrix preview when a matrix is supplied', async () => {
    (playbooksApi.get as any).mockResolvedValue(makeDetail());
    render(<ForgePackPanel playbookId="compare.drug_x_drug" matrix={MATRIX} />);
    await waitFor(() => expect(screen.getByTestId('forge-pack-dim-efficacy')).toBeInTheDocument());
    expect(screen.getByTestId('decomposition-matrix')).toBeInTheDocument();
  });

  it('surfaces a non-404 error', async () => {
    (playbooksApi.get as any).mockRejectedValue(new Error('500: boom'));
    render(<ForgePackPanel playbookId="compare.drug_x_drug" />);
    await waitFor(() => expect(screen.getByTestId('forge-pack-error')).toBeInTheDocument());
  });
});
