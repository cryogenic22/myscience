import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import SourceProfileCard from '../SourceProfileCard';
import type { SourceProfileData } from '../../api';

// Mock brand module
vi.mock('../../brand', () => ({
  displayName: (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
  SOURCE_LABELS: {
    clinical_trials_gov: 'ClinicalTrials.gov',
    pubmed: 'PubMed',
    mesh_ontology: 'MeSH Ontology',
  },
  ENTITY_TYPE_LABELS: {
    drug: 'Drug',
    company: 'Company',
    trial: 'Trial',
    therapeutic_area: 'Therapeutic Area',
  },
}));

// Mock api module — factory must not reference top-level variables
vi.mock('../../api', () => ({
  api: {
    sourceRecords: vi.fn().mockResolvedValue({
      source_key: 'clinical_trials_gov',
      entity_type: 'trial',
      table: 'clinical_trials',
      columns: [
        { name: 'id', type: 'uuid' },
        { name: 'official_title', type: 'text' },
        { name: 'phase', type: 'text' },
      ],
      records: [
        { id: 'abc12345-1234-1234-1234-abcdef123456', official_title: 'A Phase 3 Study of Semaglutide', phase: 'Phase 3' },
        { id: 'def12345-1234-1234-1234-abcdef123456', official_title: 'A Phase 2 Study of Tirzepatide', phase: 'Phase 2' },
      ],
      total: 12000,
      limit: 20,
      offset: 0,
    }),
    sourceConnections: vi.fn().mockResolvedValue({
      source_key: 'clinical_trials_gov',
      connections: [
        { target_source: 'mesh_ontology', link_type: 'IN_THERAPEUTIC_AREA', count: 8200, sample_entities: ['Diabetes', 'Oncology'] },
        { target_source: 'pubmed', link_type: 'EVIDENCE_FOR', count: 5300 },
      ],
      total_outgoing: 13500,
      total_incoming: 9200,
    }),
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

  it('renders Sample Records section header', () => {
    render(
      <SourceProfileCard data={makeProfileData()} isLoading={false} error={null} {...defaultProps} />
    );
    expect(screen.getByText('Sample Records')).toBeInTheDocument();
  });

  it('renders Cross-Source Connections section header', () => {
    render(
      <SourceProfileCard data={makeProfileData()} isLoading={false} error={null} {...defaultProps} />
    );
    expect(screen.getByText('Cross-Source Connections')).toBeInTheDocument();
  });

  it('sample records table renders with data after expand', async () => {
    render(
      <SourceProfileCard data={makeProfileData()} isLoading={false} error={null} {...defaultProps} />
    );

    // Click the "Sample Records" section to expand it
    const sampleBtn = screen.getByText('Sample Records');
    sampleBtn.click();

    // Wait for async records fetch to complete
    await waitFor(() => {
      expect(screen.getByText(/Phase/i)).toBeInTheDocument();
    });

    // Should show records table with column headers
    await waitFor(() => {
      expect(screen.getByText('A Phase 3 Study of Semaglutide')).toBeInTheDocument();
    });
  });

  it('connection flow renders source-target pairs after expand', async () => {
    render(
      <SourceProfileCard data={makeProfileData()} isLoading={false} error={null} {...defaultProps} />
    );

    // Click "Cross-Source Connections" section to expand it
    const connBtn = screen.getByText('Cross-Source Connections');
    connBtn.click();

    // Wait for async connections fetch
    await waitFor(() => {
      expect(screen.getByText('MeSH Ontology')).toBeInTheDocument();
    });

    // Should show counts
    await waitFor(() => {
      expect(screen.getByText('8,200')).toBeInTheDocument();
    });
  });
});
