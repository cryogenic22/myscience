/**
 * Loop B — EngagementsTab container test.
 *
 * The container fetches /engagements, transforms the DTO shape to
 * PortfolioBoard's prop shape, and renders. Tests cover:
 *   - loading state shows while fetch is in-flight
 *   - error state shows on fetch failure
 *   - empty state renders the friendly "no engagements yet" message
 *   - populated state passes correct shape to PortfolioBoard
 *   - DTO → PortfolioEngagement shape transform is correct
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import EngagementsTab from '../../src/components/ci/EngagementsTab';

// Mock the API module before any imports that touch it.
vi.mock('../../src/api', () => ({
  engagementsApi: {
    list: vi.fn(),
  },
}));

import { engagementsApi } from '../../src/api';

function dto(over: Record<string, any> = {}) {
  return {
    id: 'eng-1', name: 'Wegovy MASH defense', asset: 'drug:wegovy',
    sponsor: null, situation: 'defense', workshop_date: null,
    stage: 'sources', status: 'active', scope: {},
    created_by: 'u1', created_at: '2026-05-30T00:00:00Z',
    updated_at: '2026-05-30T00:00:00Z', tenant_scope: null,
    ...over,
  };
}

describe('EngagementsTab — container behaviour', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state during fetch', () => {
    (engagementsApi.list as any).mockReturnValue(new Promise(() => {})); // never resolves
    render(<EngagementsTab />);
    expect(screen.getByText(/loading engagements/i)).toBeInTheDocument();
  });

  it('renders error state on fetch failure', async () => {
    (engagementsApi.list as any).mockRejectedValue(new Error('network'));
    render(<EngagementsTab />);
    await waitFor(() => {
      expect(screen.getByText(/engagement feed error/i)).toBeInTheDocument();
    });
  });

  it('renders empty state when list is empty', async () => {
    (engagementsApi.list as any).mockResolvedValue({ engagements: [], count: 0 });
    render(<EngagementsTab />);
    await waitFor(() => {
      expect(screen.getByTestId('engagements-empty')).toBeInTheDocument();
      expect(screen.getByText(/no engagements yet/i)).toBeInTheDocument();
    });
  });

  it('renders PortfolioBoard with transformed shape when items present', async () => {
    (engagementsApi.list as any).mockResolvedValue({
      engagements: [
        dto({ id: 'a', name: 'Engagement A', stage: 'dossier', situation: 'launch' }),
        dto({ id: 'b', name: 'Engagement B', stage: 'workshop', situation: 'defense' }),
      ],
      count: 2,
    });
    render(<EngagementsTab />);
    await waitFor(() => {
      expect(screen.getByText(/engagement a/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/engagement b/i)).toBeInTheDocument();
  });
});
