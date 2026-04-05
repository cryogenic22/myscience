import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import EntityDossier from '../EntityDossier';
import type { CatalogEntityDetail } from '../../api';

// Mock the api module
vi.mock('../../api', () => ({
  api: {
    catalogRunEnrichment: vi.fn().mockResolvedValue({}),
  },
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
  displayName: (s: string) => s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()),
  isUUID: (s: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s),
  QUALITY_CHECK_LABELS: {
    drug_completeness_core: 'Core field completeness',
    drug_company_link: 'Manufacturer linked',
  },
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

function makeDetail(overrides: Partial<CatalogEntityDetail> = {}): CatalogEntityDetail {
  return {
    entity_type: 'drug',
    entity: {
      id: 'drug-123',
      _label: 'Erlotinib',
      generic_name: 'Erlotinib',
      brand_name: 'Tarceva',
      phase: 'Phase IV',
      supply_status: 'active',
      source_api: 'clinical_trials_gov',
      retrieved_at: '2026-03-20T12:00:00Z',
    },
    quality_results: [
      { rule_name: 'drug_completeness_core', passed: true, details: '' },
      { rule_name: 'drug_company_link', passed: false, details: 'No company link' },
    ],
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
    editable_fields: ['brand_name', 'mechanism_id'],
    change_log: [
      { change_type: 'manual_edit', changed_fields: ['brand_name'], changed_at: '2026-03-20T10:00:00Z' },
    ],
    tags: [],
    ...overrides,
  } as CatalogEntityDetail;
}

describe('EntityDossier', () => {
  const defaultProps = {
    editing: {},
    onEditField: vi.fn(),
    onSave: vi.fn().mockResolvedValue(undefined),
  };

  it('renders entity summary sentence', () => {
    render(<EntityDossier detail={makeDetail()} {...defaultProps} />);
    // The summary sentence includes the drug name in inline text
    expect(screen.getByText(/Erlotinib has supply status/)).toBeInTheDocument();
  });

  it('renders quality result checks', () => {
    render(<EntityDossier detail={makeDetail()} {...defaultProps} />);
    // Quality section shows passed/total — appears in both trust card and quality section
    const matches = screen.getAllByText((_content, element) => {
      return element?.textContent?.includes('1/2 checks passed') ?? false;
    });
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  it('renders connection counts', () => {
    render(<EntityDossier detail={makeDetail()} {...defaultProps} />);
    // Should show connection count header — text includes the count
    expect(screen.getByText((_content, element) => {
      return element?.textContent === 'Connections (2)';
    })).toBeInTheDocument();
  });

  it('renders structured section fields', () => {
    render(<EntityDossier detail={makeDetail()} {...defaultProps} />);
    expect(screen.getByText('Generic Name')).toBeInTheDocument();
    expect(screen.getByText('Brand Name')).toBeInTheDocument();
  });

  it('renders data provenance section', () => {
    render(<EntityDossier detail={makeDetail()} {...defaultProps} />);
    expect(screen.getByText('Data Provenance')).toBeInTheDocument();
  });

  it('renders change history when changes exist', () => {
    render(<EntityDossier detail={makeDetail()} {...defaultProps} />);
    expect(screen.getByText('Change History')).toBeInTheDocument();
  });

  it('renders save button when editing', () => {
    render(
      <EntityDossier
        detail={makeDetail()}
        editing={{ brand_name: 'Updated Name' }}
        onEditField={vi.fn()}
        onSave={vi.fn().mockResolvedValue(undefined)}
      />
    );
    expect(screen.getByText('Save Changes')).toBeInTheDocument();
  });
});
