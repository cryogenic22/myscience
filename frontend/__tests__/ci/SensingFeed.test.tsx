import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { SensingFeed } from '../../src/components/ci/SensingFeed';
import { api } from '../../src/api';
import React from 'react';

vi.mock('../../src/api', () => ({
  api: {
    intelligenceFeed: vi.fn(),
    intelligenceFeedSummary: vi.fn(),
  }
}));

describe('SensingFeed', () => {
  it('renders loading state initially', () => {
    vi.mocked(api.intelligenceFeed).mockImplementation(() => new Promise(() => {}));
    vi.mocked(api.intelligenceFeedSummary).mockImplementation(() => new Promise(() => {}));
    
    render(<SensingFeed />);
    expect(screen.getByText('Sensing the market...')).toBeDefined();
  });

  it('renders feed items when data is loaded', async () => {
    vi.mocked(api.intelligenceFeedSummary).mockResolvedValue({
      total_unread: 5,
      critical_count: 1,
      high_count: 2,
      since_hours: 24,
    });
    vi.mocked(api.intelligenceFeed).mockResolvedValue({
      items: [
        {
          event_id: 'ev1',
          event_type: 'trial_readout',
          event_date: '2026-05-09',
          description: 'Phase 3 readout is positive.',
          source_url: null,
          source_tier: 'Tier 1',
          trust_score: 95,
          primary_entity_name: 'Drug X',
          primary_entity_type: 'drug',
          severity: 'high',
          impact_count: 1,
          max_impact_magnitude: 85,
          status: 'unread',
          created_at: '2026-05-09T00:00:00Z',
        }
      ],
      total: 1
    });

    render(<SensingFeed />);

    await waitFor(() => {
      expect(screen.getByText('Phase 3 readout is positive.')).toBeDefined();
      expect(screen.getByText('SIGNAL: Drug X')).toBeDefined();
    });
  });
});
