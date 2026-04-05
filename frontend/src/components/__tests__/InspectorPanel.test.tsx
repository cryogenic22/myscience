import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import InspectorPanel from '../v2/InspectorPanel';
import type { GraphNode, CatalogEntityDetail, EntityLink } from '../../api';

// Mock sub-components from v2/
vi.mock('../v2/EntityDot', () => ({
  default: ({ type }: { type: string }) => <span data-testid="entity-dot">{type}</span>,
}));
vi.mock('../v2/Badge', () => ({
  default: ({ label }: { label: string }) => <span data-testid="badge">{label}</span>,
}));
vi.mock('../v2/ConfidenceBar', () => ({
  default: ({ value }: { value: number }) => <div data-testid="confidence-bar">{Math.round(value * 100)}%</div>,
}));
vi.mock('../v2/Button', () => ({
  default: ({ children, onClick, icon, title, 'aria-label': ariaLabel, ...rest }: React.PropsWithChildren<{ onClick?: () => void; icon?: React.ReactNode; title?: string; 'aria-label'?: string }>) => (
    <button onClick={onClick} title={title} aria-label={ariaLabel}>{icon}{children}</button>
  ),
}));
vi.mock('../v2/Skeleton', () => ({
  default: ({ variant, lines }: { variant?: string; lines?: number }) => (
    <div data-testid="skeleton">{variant ?? 'block'} {lines ?? 1}</div>
  ),
}));

// Mock inspector-helpers
vi.mock('../../utils/inspector-helpers', () => ({
  filterProperties: (entity: Record<string, unknown>) => {
    const entries = Object.entries(entity).filter(
      ([k]) => !['id', 'entity_id', 'entity_type', 'quality_score'].includes(k) && !k.endsWith('_embedding')
    );
    return entries.map(([k, v]) => ({
      key: k,
      label: k.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
      value: String(v ?? '--'),
    }));
  },
  groupLinksByType: (links: EntityLink[], entityId: string) => {
    const groups: Record<string, { links: EntityLink[]; sampleLabels: Array<{ entityId: string; entityType: string; label: string }> }> = {};
    for (const link of links) {
      const isSource = link.source_entity_id === entityId;
      const otherType = isSource ? link.target_entity_type : link.source_entity_type;
      if (!groups[otherType]) {
        groups[otherType] = { links: [], sampleLabels: [] };
      }
      groups[otherType].links.push(link);
      if (groups[otherType].sampleLabels.length < 3) {
        groups[otherType].sampleLabels.push({
          entityId: isSource ? link.target_entity_id : link.source_entity_id,
          entityType: otherType,
          label: (isSource ? link.target_label : link.source_label) || 'Unknown',
        });
      }
    }
    return Object.entries(groups).map(([entityType, data]) => ({
      entityType,
      linkTypes: [] as string[],
      links: data.links,
      sampleLabels: data.sampleLabels,
    }));
  },
  extractEvidenceLinks: () => [],
}));

function makeEntity(): GraphNode {
  return {
    entity_id: 'drug-123',
    entity_type: 'drug',
    label: 'Erlotinib',
    properties: {
      generic_name: 'Erlotinib',
      brand_name: 'Tarceva',
      quality_score: 0.85,
    },
  } as GraphNode;
}

function makeDetail(): CatalogEntityDetail {
  return {
    entity_type: 'drug',
    entity: {
      id: 'drug-123',
      generic_name: 'Erlotinib',
      brand_name: 'Tarceva',
      phase: 'Phase IV',
      quality_score: 0.85,
    },
    quality_results: [],
    links: [
      {
        source_entity_id: 'drug-123',
        source_entity_type: 'drug',
        target_entity_id: 'trial-1',
        target_entity_type: 'trial',
        link_type: 'INVESTIGATES',
        provenance_source: 'clinical_trials_gov',
        source_label: 'Erlotinib',
        target_label: 'NCT001',
      },
      {
        source_entity_id: 'company-1',
        source_entity_type: 'company',
        target_entity_id: 'drug-123',
        target_entity_type: 'drug',
        link_type: 'OWNS',
        provenance_source: 'fda_orange_book',
        source_label: 'Roche',
        target_label: 'Erlotinib',
      },
    ],
    editable_fields: [],
    change_log: [],
    tags: [],
  } as CatalogEntityDetail;
}

const defaultProps = {
  onClose: vi.fn(),
  onExplore: vi.fn(),
  onEntityClick: vi.fn(),
};

describe('InspectorPanel', () => {
  it('renders entity header with label', () => {
    render(
      <InspectorPanel
        entity={makeEntity()}
        detail={makeDetail()}
        isLoading={false}
        error={null}
        {...defaultProps}
      />
    );
    // "Erlotinib" appears in both header and properties section
    const matches = screen.getAllByText('Erlotinib');
    expect(matches.length).toBeGreaterThanOrEqual(1);
    // Verify the header span has the title attribute
    const headerSpan = matches.find(el => el.getAttribute('title') === 'Erlotinib');
    expect(headerSpan).toBeTruthy();
  });

  it('renders entity type badge', () => {
    render(
      <InspectorPanel
        entity={makeEntity()}
        detail={makeDetail()}
        isLoading={false}
        error={null}
        {...defaultProps}
      />
    );
    // Badge renders entity_type label
    const badges = screen.getAllByTestId('badge');
    const typeLabels = badges.map(b => b.textContent);
    expect(typeLabels).toContain('drug');
  });

  it('renders connection groups from links', () => {
    render(
      <InspectorPanel
        entity={makeEntity()}
        detail={makeDetail()}
        isLoading={false}
        error={null}
        {...defaultProps}
      />
    );
    // Should show connection count
    expect(screen.getByText('2 connections')).toBeInTheDocument();
  });

  it('shows loading skeleton when isLoading is true', () => {
    render(
      <InspectorPanel
        entity={makeEntity()}
        detail={null}
        isLoading={true}
        error={null}
        {...defaultProps}
      />
    );
    const skeletons = screen.getAllByTestId('skeleton');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('shows error state when error is provided', () => {
    render(
      <InspectorPanel
        entity={makeEntity()}
        detail={null}
        isLoading={false}
        error="Network error"
        {...defaultProps}
      />
    );
    expect(screen.getByText('Failed to load details')).toBeInTheDocument();
  });

  it('renders properties section', () => {
    render(
      <InspectorPanel
        entity={makeEntity()}
        detail={makeDetail()}
        isLoading={false}
        error={null}
        {...defaultProps}
      />
    );
    expect(screen.getByText('Properties')).toBeInTheDocument();
  });

  it('renders relationships section', () => {
    render(
      <InspectorPanel
        entity={makeEntity()}
        detail={makeDetail()}
        isLoading={false}
        error={null}
        {...defaultProps}
      />
    );
    expect(screen.getByText('Relationships')).toBeInTheDocument();
  });
});
