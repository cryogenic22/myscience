/**
 * Loop C — EngagementDetailContainer tests.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import EngagementDetailContainer from '../../src/components/ci/EngagementDetailContainer';

// WorkshopContainer pulls in the heavy, self-contained WarRoomView (which has
// its own api imports). Stub it — the workshop wiring is what's under test here.
vi.mock('../../src/components/ci/war/WarRoomView', () => ({
  default: () => <div data-testid="warroom-stub" />,
}));

vi.mock('../../src/api', () => {
  class DossierNotAssembled extends Error {}
  return {
    engagementsApi: { get: vi.fn() },
    dossierKbApi: { get: vi.fn(), assemble: vi.fn(), gaps: vi.fn() },
    scenariosApi: { get: vi.fn(), assemble: vi.fn() },
    synthesisApi: { get: vi.fn(), assemble: vi.fn() },
    engagementSourcesApi: { get: vi.fn() },
    engagementBriefApi: { get: vi.fn() },
    warRoomApi: { list: vi.fn(), create: vi.fn(), detail: vi.fn() },
    DossierNotAssembled,
  };
});

import { engagementsApi, dossierKbApi, scenariosApi, synthesisApi, engagementSourcesApi, engagementBriefApi, warRoomApi } from '../../src/api';

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

  it('renders the WorkshopContainer (not a placeholder) at the workshop stage (PB-UX-Workshop)', async () => {
    // All 7 stages are now wired — workshop renders the WorkshopContainer.
    (engagementsApi.get as any).mockResolvedValue(dto({ stage: 'workshop' }));
    (scenariosApi.get as any).mockReturnValue(new Promise(() => {}));
    (warRoomApi.list as any).mockReturnValue(new Promise(() => {}));
    render(
      <EngagementDetailContainer
        eid="eng-1"
        stage="workshop"
        onBackToPortfolio={() => {}}
        onStageChange={() => {}}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('workshop-loading')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('stage-placeholder')).not.toBeInTheDocument();
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
    // Default persona is EL → default landing stage 'brief' (now wired to the
    // BriefContainer). Persona-driven landing overrides the persisted
    // engagement.stage when no explicit ?stage= is given.
    window.localStorage.removeItem('mz_persona');
    (engagementsApi.get as any).mockResolvedValue(dto({ stage: 'workshop' }));
    (engagementBriefApi.get as any).mockReturnValue(new Promise(() => {}));
    render(
      <EngagementDetailContainer
        eid="eng-1"
        onBackToPortfolio={() => {}}
        onStageChange={() => {}}
      />,
    );
    await waitFor(() => expect(screen.getByTestId('brief-loading')).toBeInTheDocument());
  });

  it('explicit stage prop overrides engagement.stage', async () => {
    // engagement says dossier, but the URL asks for gaps → gaps wins.
    (engagementsApi.get as any).mockResolvedValue(dto({ stage: 'dossier' }));
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
  });

  it('renders the BriefContainer (not a placeholder) at the brief stage (PB-UX-Brief)', async () => {
    (engagementsApi.get as any).mockResolvedValue(dto({ stage: 'brief' }));
    (engagementBriefApi.get as any).mockReturnValue(new Promise(() => {}));
    render(
      <EngagementDetailContainer
        eid="eng-1"
        stage="brief"
        onBackToPortfolio={() => {}}
        onStageChange={() => {}}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('brief-loading')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('stage-placeholder')).not.toBeInTheDocument();
  });

  it('renders the SourcesContainer (not a placeholder) at the sources stage (PB-UX07)', async () => {
    (engagementsApi.get as any).mockResolvedValue(dto({ stage: 'sources' }));
    (engagementSourcesApi.get as any).mockReturnValue(new Promise(() => {}));
    render(
      <EngagementDetailContainer
        eid="eng-1"
        stage="sources"
        onBackToPortfolio={() => {}}
        onStageChange={() => {}}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('sources-loading')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('stage-placeholder')).not.toBeInTheDocument();
  });

  it('renders the SynthesisContainer (not a placeholder) at the synthesis stage (PB-UX06)', async () => {
    (engagementsApi.get as any).mockResolvedValue(dto({ stage: 'synthesis' }));
    (synthesisApi.get as any).mockReturnValue(new Promise(() => {}));
    render(
      <EngagementDetailContainer
        eid="eng-1"
        stage="synthesis"
        onBackToPortfolio={() => {}}
        onStageChange={() => {}}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId('synthesis-loading')).toBeInTheDocument();
    });
    expect(screen.queryByTestId('stage-placeholder')).not.toBeInTheDocument();
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
