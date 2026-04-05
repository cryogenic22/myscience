import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import CurateView from '../v2/CurateView';
import type { PipelineConnector, GraphSummary } from '../../types/newui';

// Mock FAIRSparkline sub-component
vi.mock('../v2/FAIRSparkline', () => ({
  default: ({ score }: { score: number }) => (
    <div data-testid="fair-sparkline">{Math.round(score * 100)}%</div>
  ),
}));

function makeConnectors(): PipelineConnector[] {
  return [
    {
      source_key: 'clinical_trials_gov',
      label: 'ClinicalTrials.gov',
      schedule: 'Daily at 06:00 UTC',
      last_run: '2026-03-28T06:00:00Z',
      days_since: 1,
      records: 45000,
      status: 'fresh',
    },
    {
      source_key: 'pubmed',
      label: 'PubMed',
      schedule: 'Daily at 08:00 UTC',
      last_run: '2026-03-27T08:00:00Z',
      days_since: 2,
      records: 32000,
      status: 'ok',
    },
    {
      source_key: 'fda_orange_book',
      label: 'FDA Orange Book',
      schedule: 'Weekly',
      last_run: null,
      days_since: null,
      records: 0,
      status: 'never',
    },
  ];
}

function makeGraphSummary(): GraphSummary {
  return {
    link_types: [
      { type: 'INVESTIGATES', count: 25000 },
      { type: 'EVIDENCE_FOR', count: 18000 },
      { type: 'OWNS', count: 5000 },
    ],
    total_links: 48000,
    total_entities: 12000,
    drug_completeness: {
      generic_name: 100,
      company_id: 97,
      mechanism_id: 37,
      brand_name: 5,
    },
  };
}

describe('CurateView', () => {
  it('renders header with Data Supply Chain title', () => {
    render(
      <CurateView
        pipelineStatus={makeConnectors()}
        graphSummary={makeGraphSummary()}
        onRefreshSource={vi.fn()}
      />
    );
    expect(screen.getByText('Data Supply Chain')).toBeInTheDocument();
  });

  it('renders connector cards with labels', () => {
    render(
      <CurateView
        pipelineStatus={makeConnectors()}
        graphSummary={makeGraphSummary()}
        onRefreshSource={vi.fn()}
      />
    );
    expect(screen.getByText('ClinicalTrials.gov')).toBeInTheDocument();
    expect(screen.getByText('PubMed')).toBeInTheDocument();
    expect(screen.getByText('FDA Orange Book')).toBeInTheDocument();
  });

  it('renders drug completeness bars', () => {
    render(
      <CurateView
        pipelineStatus={makeConnectors()}
        graphSummary={makeGraphSummary()}
        onRefreshSource={vi.fn()}
      />
    );
    expect(screen.getByText('Drug Completeness')).toBeInTheDocument();
    expect(screen.getByText(/generic name/i)).toBeInTheDocument();
  });

  it('renders skeleton when pipeline status is null', () => {
    const { container } = render(
      <CurateView
        pipelineStatus={null}
        graphSummary={null}
        onRefreshSource={vi.fn()}
      />
    );
    // When null, the component renders shimmer skeleton divs
    const shimmerElements = container.querySelectorAll('[style*="shimmer"]');
    expect(shimmerElements.length).toBeGreaterThan(0);
  });

  it('renders graph summary stats', () => {
    render(
      <CurateView
        pipelineStatus={makeConnectors()}
        graphSummary={makeGraphSummary()}
        onRefreshSource={vi.fn()}
      />
    );
    expect(screen.getByText('Knowledge Graph')).toBeInTheDocument();
  });
});
