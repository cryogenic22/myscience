import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import EntityPreview from '../search/EntityPreview';
import type { SearchResult, GraphNode, GraphEdge } from '../../api';

// Mock api module
vi.mock('../../api', () => ({
  api: {},
  SOURCE_LABELS: {
    clinical_trials_gov: 'ClinicalTrials.gov',
    pubmed: 'PubMed',
  },
  ENTITY_TYPE_LABELS: {
    drug: 'Drug',
    company: 'Company',
    trial: 'Trial',
  },
}));

// Mock brand module
vi.mock('../../brand', () => ({
  SOURCE_LABELS: { clinical_trials_gov: 'ClinicalTrials.gov' },
  ENTITY_TYPE_LABELS: {
    drug: 'Drug',
    company: 'Company',
    trial: 'Trial',
    mechanism: 'Mechanism',
    therapeutic_area: 'Therapeutic Area',
  },
}));

// Mock KnowledgeGraph (path relative from search/ dir)
vi.mock('../KnowledgeGraph', () => ({
  default: () => <div data-testid="knowledge-graph"><canvas /></div>,
}));

// Mock search-utils — provide everything the component needs
vi.mock('../search/search-utils', () => ({
  TYPE_CONFIG: {
    drug: { icon: 'pill', color: '#1C6EF7', label: 'Drug', plural: 'Drugs', bgVar: 'rgba(28,110,247,0.08)' },
    company: { icon: 'building', color: '#22C55E', label: 'Company', plural: 'Companies', bgVar: 'rgba(34,197,94,0.08)' },
    trial: { icon: 'flask', color: '#0EA5E9', label: 'Trial', plural: 'Trials', bgVar: 'rgba(14,165,233,0.08)' },
  },
  prettyType: (t: string) => t.charAt(0).toUpperCase() + t.slice(1).replace(/_/g, ' '),
  truncateValue: (v: string) => v.length > 80 ? v.slice(0, 77) + '...' : v,
  getResultSnippet: () => 'Test snippet',
  getSourcePublicationDate: () => '2026-01-15',
  getRelatedDocuments: () => [],
  extractTherapeuticAreasFromResult: () => [],
  formatDate: (d: string) => d,
}));

function makeResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    entity_id: 'drug-123',
    entity_type: 'drug',
    label: 'Erlotinib',
    similarity: 0.92,
    source_api: 'clinical_trials_gov',
    metadata: {
      generic_name: 'Erlotinib',
      brand_name: 'Tarceva',
      phase: 'Phase IV',
      supply_status: 'active',
    },
    ...overrides,
  } as SearchResult;
}

function makeNeighbor() {
  return {
    key: 'trial-1',
    id: 'trial-1',
    type: 'trial',
    label: 'NCT001',
    nodeType: 'trial',
    relation: 'INVESTIGATES',
    confidence: 0.85,
  };
}

const defaultProps = {
  activeResultIndex: 0,
  totalVisibleResults: 5,
  onPrevResult: vi.fn(),
  onNextResult: vi.fn(),
  onAskInChat: vi.fn(),
  onExploreNode: vi.fn(),
  linkedGraphLoading: false,
  linkedGraphError: null,
  linkedNeighbors: [makeNeighbor()],
  linkedGraphNodes: [] as GraphNode[],
  linkedGraphEdges: [] as GraphEdge[],
  graphFocus: null,
  graphTrail: [],
  edgeTypeFilter: 'all',
  edgeTypeOptions: ['all'],
  onEdgeTypeFilterChange: vi.fn(),
  onGraphNodeSelect: vi.fn(),
  onGraphTrailJump: vi.fn(),
  onGraphNeighborFocus: vi.fn(),
  onOpenFocusedNodeInSearch: vi.fn(),
};

describe('EntityPreview', () => {
  it('renders entity type label', () => {
    render(<EntityPreview result={makeResult()} {...defaultProps} />);
    // The component displays entity type somewhere in the preview
    expect(screen.getByText(/Drug/i)).toBeInTheDocument();
  });

  it('renders entity name in the heading', () => {
    render(<EntityPreview result={makeResult()} {...defaultProps} />);
    // Entity name appears as part of heading/title area
    expect(screen.getByText(/Erlotinib/)).toBeInTheDocument();
  });

  it('renders connection neighbor items', () => {
    render(<EntityPreview result={makeResult()} {...defaultProps} />);
    expect(screen.getByText('NCT001')).toBeInTheDocument();
  });

  it('renders empty state when result is null', () => {
    render(<EntityPreview result={null} {...defaultProps} />);
    expect(screen.getByText('Entity Profile')).toBeInTheDocument();
    expect(screen.getByText(/Select a result to view/)).toBeInTheDocument();
  });
});
