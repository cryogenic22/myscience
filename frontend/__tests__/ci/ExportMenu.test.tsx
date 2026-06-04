/**
 * UX12/UX13 — ExportMenu tests. Mocks engagementExportApi.open.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ExportMenu from '../../src/components/ci/ExportMenu';
import { engagementExportApi } from '../../src/api';

describe('ExportMenu (UX12/UX13)', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('reveals the three deliverables on click', () => {
    render(<ExportMenu engagementId="e1" />);
    fireEvent.click(screen.getByTestId('export-menu-trigger'));
    expect(screen.getByText('Executive Brief')).toBeInTheDocument();
    expect(screen.getByText('Intelligence Dossier')).toBeInTheDocument();
    expect(screen.getByText('Strategy Deck')).toBeInTheDocument();
  });

  it('opens the chosen deliverable via the auth-aware export api', async () => {
    const spy = vi.spyOn(engagementExportApi, 'open').mockResolvedValue(undefined);
    render(<ExportMenu engagementId="e1" />);
    fireEvent.click(screen.getByTestId('export-menu-trigger'));
    fireEvent.click(screen.getByText('Strategy Deck'));
    await waitFor(() => expect(spy).toHaveBeenCalledWith('e1', 'deck'));
  });

  it('surfaces an error when export fails', async () => {
    vi.spyOn(engagementExportApi, 'open').mockRejectedValue(new Error('403'));
    render(<ExportMenu engagementId="e1" />);
    fireEvent.click(screen.getByTestId('export-menu-trigger'));
    fireEvent.click(screen.getByText('Executive Brief'));
    await waitFor(() => expect(screen.getByText(/403/)).toBeInTheDocument());
  });
});
