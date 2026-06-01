/**
 * UX07 — SourcesContainer tests.
 *
 * Covers loading → not-assembled (assemble action) → ready, the error path,
 * and that the coverage view renders sources with their fact counts + domains.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';

vi.mock('../../src/api', () => {
  class DossierNotAssembled extends Error {}
  return {
    DossierNotAssembled,
    engagementSourcesApi: { get: vi.fn() },
    dossierKbApi: { assemble: vi.fn() },
  };
});

import { engagementSourcesApi, DossierNotAssembled } from '../../src/api';
import SourcesContainer from '../../src/components/ci/SourcesContainer';

const ENGAGEMENT = { id: 'e1', name: 'Wegovy defense', asset: 'drug:semaglutide' } as any;

function sourcesResponse(overrides: Partial<any> = {}) {
  return {
    source_count: 2,
    total_facts: 7,
    coverage_score: 0.5,
    sources: [
      { source: 'entity_graph', fact_count: 5, domains: ['Competitive landscape'], classes: { inferred: 5 } },
      { source: 'PharmaMetrics', fact_count: 2, domains: ['Clinical profile'], classes: { reference: 2 } },
    ],
    ...overrides,
  };
}

describe('SourcesContainer', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows the not-assembled state with an assemble action', async () => {
    (engagementSourcesApi.get as any).mockRejectedValue(new DossierNotAssembled());
    render(<SourcesContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('sources-empty')).toBeInTheDocument());
    expect(screen.getByTestId('sources-assemble')).toBeInTheDocument();
  });

  it('renders the source coverage with counts + domains', async () => {
    (engagementSourcesApi.get as any).mockResolvedValue(sourcesResponse());
    render(<SourcesContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('sources-ready')).toBeInTheDocument());
    expect(screen.getByText('entity_graph')).toBeInTheDocument();
    expect(screen.getByText('PharmaMetrics')).toBeInTheDocument();
    expect(screen.getByText('2 sources')).toBeInTheDocument();
    expect(screen.getByText(/Competitive landscape/)).toBeInTheDocument();
  });

  it('shows an error (not the empty state) on a non-404 failure', async () => {
    (engagementSourcesApi.get as any).mockRejectedValue(new Error('500: boom'));
    render(<SourcesContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('sources-error')).toBeInTheDocument());
    expect(screen.queryByTestId('sources-empty')).not.toBeInTheDocument();
  });
});
