/**
 * IX-3 — StandaloneDossierTab tests.
 *
 * The light-path dossier builder: enter an asset → preview → render; promote.
 * The heavy EngagementDossierPage + ProvenancePanel are stubbed (own tests).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../src/api', () => ({
  dossierPreviewApi: { get: vi.fn() },
}));
vi.mock('../../src/pages/EngagementDossierPage', () => ({
  EngagementDossierPage: ({ scope }: any) => <div data-testid="dossier-page">{scope.focalAsset}</div>,
}));
vi.mock('../../src/components/ci/ProvenancePanel', () => ({ default: () => null }));

import { dossierPreviewApi } from '../../src/api';
import StandaloneDossierTab from '../../src/components/ci/StandaloneDossierTab';

function snap(asset = 'drug:semaglutide') {
  return {
    id: null, engagement_id: null, focal_asset: asset, version: null,
    coverage_score: 0.5, readiness: 0.36, fact_count: 5,
    domains: [{ domain: 'competitive', priority: 'critical', state: 'in_progress', readiness: 0.7, facts: [] }],
    assembled_by: 'system', assembled_at: null,
  };
}

describe('StandaloneDossierTab', () => {
  beforeEach(() => vi.clearAllMocks());

  it('builds a dossier for the entered asset and renders it', async () => {
    (dossierPreviewApi.get as any).mockResolvedValue(snap());
    render(<StandaloneDossierTab />);
    fireEvent.change(screen.getByTestId('dossier-asset-input'), { target: { value: 'semaglutide' } });
    fireEvent.click(screen.getByTestId('dossier-build'));
    await waitFor(() => expect(screen.getByTestId('dossier-preview-ready')).toBeInTheDocument());
    expect(dossierPreviewApi.get).toHaveBeenCalledWith('semaglutide');
    expect(screen.getByTestId('dossier-page')).toHaveTextContent('drug:semaglutide');
  });

  it('shows an error when the preview fails', async () => {
    (dossierPreviewApi.get as any).mockRejectedValue(new Error('500: boom'));
    render(<StandaloneDossierTab />);
    fireEvent.click(screen.getByTestId('dossier-build'));
    await waitFor(() => expect(screen.getByTestId('dossier-preview-error')).toBeInTheDocument());
  });

  it('offers Promote to engagement once a dossier is built', async () => {
    (dossierPreviewApi.get as any).mockResolvedValue(snap());
    const onPromote = vi.fn();
    render(<StandaloneDossierTab onPromote={onPromote} />);
    fireEvent.click(screen.getByTestId('dossier-build'));
    await waitFor(() => expect(screen.getByTestId('dossier-promote')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('dossier-promote'));
    expect(onPromote).toHaveBeenCalledWith('semaglutide');
  });
});
