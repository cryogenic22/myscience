import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { EntityProfileData } from '../../api';

const { mockEntityEvents } = vi.hoisted(() => ({
  mockEntityEvents: vi.fn(),
}));

vi.mock('../../api', async () => {
  const actual = await vi.importActual<typeof import('../../api')>('../../api');
  return {
    ...actual,
    api: {
      ...actual.api,
      entityEvents: mockEntityEvents,
    },
  };
});

import EntityProfileCard from '../EntityProfileCard';

function makeProfileData(overrides: Partial<EntityProfileData> = {}): EntityProfileData {
  return {
    entity_type: 'drug',
    identity: {
      id: 'drug-123',
      _label: 'Erlotinib',
      generic_name: 'Erlotinib',
      entity_type: 'drug',
      brand_name: 'Tarceva',
    },
    fair_scores: {
      overall: 0.78,
      completeness: 0.85,
      link_density: 0.72,
      source_diversity: 0.65,
      freshness: 0.9,
      resolution: 0.8,
    },
    ai_readiness: {
      has_embedding: true,
      is_linked: true,
      is_resolved: true,
    },
    connections: [
      { entity_type: 'trial', count: 15, sample_labels: ['NCT001', 'NCT002'] },
      { entity_type: 'literature', count: 10, sample_labels: ['Study A'] },
      { entity_type: 'mechanism', count: 3, sample_labels: ['EGFR'] },
    ],
    evidence: [
      { title: 'Phase III trial results', type: 'literature', date: '2026-01-15', entity_id: 'lit-1' },
    ],
    provenance: ['clinical_trials_gov', 'pubmed'],
    recent_changes: [],
    stats: {
      total_connections: 28,
      influence_score: 0.67,
    },
    ...overrides,
  };
}

const defaultProps = {
  onClose: vi.fn(),
  onAskInChat: vi.fn(),
  onExploreGraph: vi.fn(),
};

describe('EntityProfileCard', () => {
  beforeEach(() => {
    mockEntityEvents.mockReset();
    // Default: return empty events
    mockEntityEvents.mockResolvedValue({ events: [], total: 0 });
  });

  it('renders FAIR score dimension labels', () => {
    render(
      <EntityProfileCard
        data={makeProfileData()}
        isLoading={false}
        error={null}
        {...defaultProps}
      />
    );
    expect(screen.getByText('Completeness')).toBeInTheDocument();
    expect(screen.getByText('Link Density')).toBeInTheDocument();
    expect(screen.getByText('Source Diversity')).toBeInTheDocument();
    expect(screen.getByText('Freshness')).toBeInTheDocument();
    expect(screen.getByText('Resolution')).toBeInTheDocument();
  });

  it('renders connection groups', () => {
    render(
      <EntityProfileCard
        data={makeProfileData()}
        isLoading={false}
        error={null}
        {...defaultProps}
      />
    );
    expect(screen.getByText('Connections')).toBeInTheDocument();
    // Connection entity type labels
    expect(screen.getByText('Clinical Trial')).toBeInTheDocument();
    expect(screen.getByText('Publication')).toBeInTheDocument();
    expect(screen.getByText('Mechanism of Action')).toBeInTheDocument();
  });

  it('shows loading state', () => {
    const { container } = render(
      <EntityProfileCard
        data={null}
        isLoading={true}
        error={null}
        {...defaultProps}
      />
    );
    // Loading state renders Skeleton components with skeleton-pulse animation
    const skeletons = container.querySelectorAll('[style*="skeleton-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('renders activity section when events present', async () => {
    mockEntityEvents.mockResolvedValue({
      events: [
        {
          event_type: 'field_change',
          description: 'Brand name updated to Tarceva',
          source: 'auto_curate',
          timestamp: new Date().toISOString(),
          details: { changed_fields: ['brand_name'] },
        },
        {
          event_type: 'new_connection',
          description: 'New TREATS connection to therapeutic_area',
          source: 'cross_linker',
          timestamp: new Date().toISOString(),
          details: { link_type: 'TREATS' },
        },
      ],
      total: 2,
    });

    render(
      <EntityProfileCard
        data={makeProfileData()}
        isLoading={false}
        error={null}
        {...defaultProps}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Recent Activity')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText('Brand name updated to Tarceva')).toBeInTheDocument();
    });
  });

  it('shows "No recent activity" when empty', async () => {
    mockEntityEvents.mockResolvedValue({
      events: [],
      total: 0,
    });

    render(
      <EntityProfileCard
        data={makeProfileData()}
        isLoading={false}
        error={null}
        {...defaultProps}
      />
    );

    await waitFor(() => {
      expect(screen.getByText('Recent Activity')).toBeInTheDocument();
    });
    await waitFor(() => {
      expect(screen.getByText('No recent activity')).toBeInTheDocument();
    });
  });
});
