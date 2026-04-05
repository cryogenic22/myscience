import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import SearchResults from '../search/SearchResults';
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
});
