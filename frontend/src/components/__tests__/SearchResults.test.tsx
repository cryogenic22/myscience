import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import SearchResults from '../search/SearchResults';
import { resultsToGraphNodes } from '../search/SearchResults';
import type { SearchResult } from '../../api';

function makeResult(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    entity_id: 'drug-1',
    entity_type: 'drug',
    title: 'Erlotinib',
    snippet: 'An EGFR tyrosine kinase inhibitor used in oncology.',
    similarity: 0.92,
    metadata: {},
    provenance: { source_api: 'clinical_trials_gov', retrieved_at: '2026-03-20' },
    quality_score: 0.85,
    ...overrides,
  };
}

const defaultProps = {
  viewMode: 'cards' as const,
  activeResultKey: null,
  onEntityClick: vi.fn(),
  isLoading: false,
  hasSearched: true,
  query: 'EGFR inhibitors',
  totalResults: 0,
  visibleCount: 0,
};

describe('SearchResults', () => {
  it('renders search result items', () => {
    const results = [
      makeResult({ entity_id: 'drug-1', title: 'Erlotinib', entity_type: 'drug' }),
      makeResult({ entity_id: 'drug-2', title: 'Gefitinib', entity_type: 'drug' }),
      makeResult({ entity_id: 'trial-1', title: 'NCT00446225', entity_type: 'trial' }),
    ];
    render(
      <SearchResults
        {...defaultProps}
        results={results}
        totalResults={3}
        visibleCount={3}
      />
    );
    expect(screen.getByText('Erlotinib')).toBeInTheDocument();
    expect(screen.getByText('Gefitinib')).toBeInTheDocument();
    expect(screen.getByText('NCT00446225')).toBeInTheDocument();
  });

  it('shows empty state when no results', () => {
    render(
      <SearchResults
        {...defaultProps}
        results={[]}
        totalResults={0}
        visibleCount={0}
      />
    );
    expect(screen.getByText(/No results found/)).toBeInTheDocument();
  });

  it('displays entity type badges', () => {
    const results = [
      makeResult({ entity_id: 'drug-1', title: 'Erlotinib', entity_type: 'drug' }),
      makeResult({ entity_id: 'comp-1', title: 'Pfizer', entity_type: 'company' }),
    ];
    render(
      <SearchResults
        {...defaultProps}
        results={results}
        totalResults={2}
        visibleCount={2}
      />
    );
    expect(screen.getByText('Drug')).toBeInTheDocument();
    expect(screen.getByText('Company')).toBeInTheDocument();
  });

  it('renders graph view container when viewMode is graph', () => {
    const results = [
      makeResult({ entity_id: 'drug-1', title: 'Erlotinib', entity_type: 'drug' }),
      makeResult({ entity_id: 'comp-1', title: 'Roche', entity_type: 'company' }),
    ];
    render(
      <SearchResults
        {...defaultProps}
        viewMode="graph"
        results={results}
        totalResults={2}
        visibleCount={2}
      />
    );
    expect(screen.getByTestId('search-graph-view')).toBeInTheDocument();
    expect(screen.getByText('Results shown as a graph. Click a node to explore.')).toBeInTheDocument();
  });

  it('renders KnowledgeGraph canvas when viewMode is graph', () => {
    const results = [
      makeResult({ entity_id: 'drug-1', title: 'Erlotinib', entity_type: 'drug' }),
    ];
    const { container } = render(
      <SearchResults
        {...defaultProps}
        viewMode="graph"
        results={results}
        totalResults={1}
        visibleCount={1}
      />
    );
    const canvas = container.querySelector('canvas');
    expect(canvas).toBeInTheDocument();
  });
});

describe('resultsToGraphNodes', () => {
  it('converts SearchResult[] to GraphNode[]', () => {
    const results: SearchResult[] = [
      {
        entity_id: 'drug-1',
        entity_type: 'drug',
        title: 'Erlotinib',
        snippet: 'EGFR inhibitor',
        similarity: 0.92,
        metadata: { mechanism: 'EGFR' },
        influence_score: 0.75,
      },
      {
        entity_id: 'comp-1',
        entity_type: 'company',
        title: 'Roche',
        snippet: 'Pharma company',
        similarity: 0.88,
        metadata: { country: 'Switzerland' },
      },
    ];
    const nodes = resultsToGraphNodes(results);
    expect(nodes).toHaveLength(2);
    expect(nodes[0].entity_id).toBe('drug-1');
    expect(nodes[0].entity_type).toBe('drug');
    expect(nodes[0].label).toBe('Erlotinib');
    expect(nodes[0].properties.similarity).toBe(0.92);
    expect(nodes[0].properties.influence_score).toBe(0.75);
    expect(nodes[0].properties.mechanism).toBe('EGFR');
    expect(nodes[1].entity_id).toBe('comp-1');
    expect(nodes[1].label).toBe('Roche');
    expect(nodes[1].properties.country).toBe('Switzerland');
  });
});
