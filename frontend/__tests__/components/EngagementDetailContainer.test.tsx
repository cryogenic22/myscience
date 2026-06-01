/**
 * Loop C — EngagementDetailContainer tests.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import EngagementDetailContainer from '../../src/components/ci/EngagementDetailContainer';

vi.mock('../../src/api', () => {
  class DossierNotAssembled extends Error {}
  return {
    engagementsApi: { get: vi.fn() },
    dossierKbApi: { get: vi.fn(), assemble: vi.fn(), gaps: vi.fn() },
    scenariosApi: { get: vi.fn(), assemble: vi.fn() },
    DossierNotAssembled,
  };
});

import { engagementsApi, dossierKbApi, scenariosApi } from '../../src/api';

// gaps() must be hoisted-safe on the mocked dossierKbApi.

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

  it('renders EngagementShell + stage placeholder for a not-yet-built stage', async () => {
    (engagementsApi.get as any).mockResolvedValue(dto({ stage: 'sources' }));
    render(
      <EngagementDetailContainer
        eid="eng-1"
        stage="sources"
        onBackToPortfolio={() => {}}
        onStageChange={() => {}}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('stage-placeholder')).toBeInTheDocument();
    });
    // The placeholder names the current stage.
    expect(screen.getByText(/stage · sources/i)).toBeInTheDocument();
  });

  it('renders the DossierContainer (not a placeholder) at the dossier stage', async () => {
    (engagementsApi.get as any).mockResolvedValue(dto({ stage: 'dossier' }));
    // pending fetch → DossierContainer shows its own loading state.
    (dossierKbApi.get as any).mockReturnValue(new Promise(() => {}));
    render(
      <EngagementDetailContainer
        eid="eng-1"
        stage="dossier"
        onBackToPortfolio={() => {}}
        onStageChange={() => {}}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('dossier-loading')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('stage-placeholder')).not.toBeInTheDocument();
  });

  it('with no explicit stage, lands on the persona default (PB-UX01)', async () => {
    // Default persona is EL → default landing stage 'brief' (a placeholder).
    window.localStorage.removeItem('mz_persona');
    (engagementsApi.get as any).mockResolvedValue(dto({ stage: 'workshop' }));
    render(
      <EngagementDetailContainer
        eid="eng-1"
        onBackToPortfolio={() => {}}
        onStageChange={() => {}}
      />,
    );
    // Persona-driven landing overrides the persisted engagement.stage when no
    // explicit ?stage= is given.
    await waitFor(() => expect(screen.getByText(/stage · brief/i)).toBeInTheDocument());
  });

  it('explicit stage prop overrides engagement.stage', async () => {
    (engagementsApi.get as any).mockResolvedValue(dto({ stage: 'dossier' }));
    render(
      <EngagementDetailContainer
        eid="eng-1"
        stage="synthesis"
        onBackToPortfolio={() => {}}
        onStageChange={() => {}}
      />,
    );
    await waitFor(() => {
      expect(screen.getByText(/stage · synthesis/i)).toBeInTheDocument();
    });
  });

  it('renders the GapsContainer (not a placeholder) at the gaps stage (PB-UX05)', async () => {
    (engagementsApi.get as any).mockResolvedValue(dto({ stage: 'gaps' }));
    // pending fetch → GapsContainer shows its own loading state.
    (dossierKbApi.gaps as any).mockReturnValue(new Promise(() => {}));
    render(
      <EngagementDetailContainer
        eid="eng-1"
        stage="gaps"
        onBackToPortfolio={() => {}}
        onStageChange={() => {}}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('gaps-loading')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('stage-placeholder')).not.toBeInTheDocument();
  });

  it('renders the ScenariosContainer (not a placeholder) at the scenarios stage (PB-UX04)', async () => {
    (engagementsApi.get as any).mockResolvedValue(dto({ stage: 'scenarios' }));
    // pending fetch → ScenariosContainer shows its own loading state.
    (scenariosApi.get as any).mockReturnValue(new Promise(() => {}));
    render(
      <EngagementDetailContainer
        eid="eng-1"
        stage="scenarios"
        onBackToPortfolio={() => {}}
        onStageChange={() => {}}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('scenarios-loading')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('stage-placeholder')).not.toBeInTheDocument();
  });
});
