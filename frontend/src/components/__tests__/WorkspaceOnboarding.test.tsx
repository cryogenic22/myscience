import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import WorkspaceOnboarding from '../chat/WorkspaceOnboarding';

const mockCatalogStats = vi.fn();
vi.mock('../../api', () => ({
  api: { catalogStats: (...args: unknown[]) => mockCatalogStats(...args) },
}));

describe('WorkspaceOnboarding KG metric strip', () => {
  beforeEach(() => {
    mockCatalogStats.mockReset();
  });

  it('shows a loading skeleton and NO fabricated counts before stats resolve', () => {
    mockCatalogStats.mockReturnValue(new Promise(() => {})); // never resolves
    const { container } = render(<WorkspaceOnboarding onSendQuery={() => {}} />);

    expect(container.querySelectorAll('[data-testid="kg-metric-skeleton"]').length).toBe(4);
    // the old hardcoded FALLBACK_METRICS (1.7K drugs / 5.3K trials) must not render
    expect(screen.queryByText('1.7K')).not.toBeInTheDocument();
    expect(screen.queryByText('5.3K')).not.toBeInTheDocument();
  });

  it('renders the LIVE counts once stats resolve', async () => {
    mockCatalogStats.mockResolvedValue({
      entity_counts: { drug: 2000, trial: 6000, company: 1200, mechanism: 30 },
    });
    render(<WorkspaceOnboarding onSendQuery={() => {}} />);

    expect(await screen.findByText('2K')).toBeInTheDocument();
    expect(screen.getByText('6K')).toBeInTheDocument();
    expect(screen.getByText('1.2K')).toBeInTheDocument();
    expect(screen.getByText('30')).toBeInTheDocument();
  });

  it('shows an honest "unavailable" message (not fabricated counts) on failure', async () => {
    mockCatalogStats.mockRejectedValue(new Error('network'));
    render(<WorkspaceOnboarding onSendQuery={() => {}} />);

    expect(await screen.findByText(/counts unavailable/i)).toBeInTheDocument();
    expect(screen.queryByText('1.7K')).not.toBeInTheDocument();
    expect(screen.queryByText('5.3K')).not.toBeInTheDocument();
  });
});
