/**
 * Loop C — EngagementDetailContainer tests.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import EngagementDetailContainer from '../../src/components/ci/EngagementDetailContainer';

vi.mock('../../src/api', () => ({
  engagementsApi: { get: vi.fn() },
}));

import { engagementsApi } from '../../src/api';

function dto(over: Record<string, any> = {}) {
  return {
    id: 'eng-1', name: 'Wegovy MASH defense', asset: 'drug:wegovy',
    sponsor: null, situation: 'defense', workshop_date: null,
    stage: 'dossier', status: 'active', scope: {},
    created_by: 'u1', created_at: '2026-05-30T00:00:00Z',
    updated_at: '2026-05-30T00:00:00Z', tenant_scope: null,
    ...over,
  };
}

describe('EngagementDetailContainer', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows loading state while fetching', () => {
    (engagementsApi.get as any).mockReturnValue(new Promise(() => {}));
    render(
      <EngagementDetailContainer
        eid="eng-1"
        onBackToPortfolio={() => {}}
        onStageChange={() => {}}
      />,
    );
    expect(screen.getByTestId('engagement-loading')).toBeInTheDocument();
  });

  it('shows error state with back-to-portfolio CTA', async () => {
    (engagementsApi.get as any).mockRejectedValue(new Error('404'));
    const back = vi.fn();
    render(
      <EngagementDetailContainer
        eid="missing"
        onBackToPortfolio={back}
        onStageChange={() => {}}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('engagement-error')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /back to portfolio/i }));
    expect(back).toHaveBeenCalledTimes(1);
  });

  it('renders EngagementShell + stage placeholder when loaded', async () => {
    (engagementsApi.get as any).mockResolvedValue(dto({ stage: 'dossier' }));
    render(
      <EngagementDetailContainer
        eid="eng-1"
        onBackToPortfolio={() => {}}
        onStageChange={() => {}}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('stage-placeholder')).toBeInTheDocument();
    });
    // The placeholder names the current stage.
    expect(screen.getByText(/stage · dossier/i)).toBeInTheDocument();
  });

  it('explicit stage prop overrides engagement.stage', async () => {
    (engagementsApi.get as any).mockResolvedValue(dto({ stage: 'dossier' }));
    render(
      <EngagementDetailContainer
        eid="eng-1"
        stage="scenarios"
        onBackToPortfolio={() => {}}
        onStageChange={() => {}}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText(/stage · scenarios/i)).toBeInTheDocument();
    });
  });
});
