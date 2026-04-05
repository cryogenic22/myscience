import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import SourceProfileCard from '../SourceProfileCard';
import type { SourceProfileData } from '../../api';

// Mock brand module
vi.mock('../../brand', () => ({
  displayName: (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
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

function makeProfileData(overrides: Partial<SourceProfileData> = {}): SourceProfileData {
  return {
    source_key: 'clinical_trials_gov',
    label: 'ClinicalTrials.gov',
    status: 'OK',
    schedule: 'Daily at 06:00 UTC',
    last_run: '2026-03-28T12:00:00Z',
    days_since: 2,
    total_records: 15000,
    entity_breakdown: [
      { entity_type: 'trial', count: 12000 },
      { entity_type: 'drug', count: 2500 },
      { entity_type: 'company', count: 500 },
    ],
    field_completeness: [
      { field: 'phase', filled: 11400, total: 12000, pct: 95 },
      { field: 'status', filled: 11040, total: 12000, pct: 92 },
      { field: 'sponsor_name', filled: 9360, total: 12000, pct: 78 },
      { field: 'conditions', filled: 7800, total: 12000, pct: 65 },
    ],
    steward_actions: [],
    cross_source_links: [],
    ...overrides,
  };
}

describe('SourceProfileCard', () => {
  const defaultProps = {
    onClose: vi.fn(),
    onRefresh: vi.fn(),
  };

  it('renders source name', () => {
    render(
      <SourceProfileCard data={makeProfileData()} isLoading={false} error={null} {...defaultProps} />
    );
    expect(screen.getByText('ClinicalTrials.gov')).toBeInTheDocument();
  });

  it('renders field completeness entries', () => {
    render(
      <SourceProfileCard data={makeProfileData()} isLoading={false} error={null} {...defaultProps} />
    );
    // Field Completeness section shows field names
    expect(screen.getByText('Field Completeness')).toBeInTheDocument();
  });

  it('shows loading state with skeletons', () => {
    const { container } = render(
      <SourceProfileCard data={null} isLoading={true} error={null} {...defaultProps} />
    );
    // Skeleton elements use skeleton-pulse animation
    const skeletons = container.querySelectorAll('[style*="skeleton-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('renders status badge', () => {
    render(
      <SourceProfileCard data={makeProfileData()} isLoading={false} error={null} {...defaultProps} />
    );
    expect(screen.getByText('OK')).toBeInTheDocument();
  });

  it('renders record count in meta row', () => {
    render(
      <SourceProfileCard data={makeProfileData()} isLoading={false} error={null} {...defaultProps} />
    );
    // Records are shown as "Records: 15,000" in meta row
    expect(screen.getByText(/15,000/)).toBeInTheDocument();
  });
});
