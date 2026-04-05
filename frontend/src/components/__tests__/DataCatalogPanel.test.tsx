import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import DataCatalogPanel from '../DataCatalogPanel';

// Mock the api module
const mockCatalogBrowse = vi.fn();
const mockHealth = vi.fn();
const mockCatalogStats = vi.fn();
const mockCatalogDatasets = vi.fn();
const mockCatalogPipelineStatus = vi.fn();
const mockCatalogGraphSummary = vi.fn();
const mockCatalogChanges = vi.fn();
const mockCatalogHITL = vi.fn();

vi.mock('../../api', () => ({
  api: {
    health: (...args: unknown[]) => mockHealth(...args),
    catalogStats: (...args: unknown[]) => mockCatalogStats(...args),
    catalogDatasets: (...args: unknown[]) => mockCatalogDatasets(...args),
    catalogBrowse: (...args: unknown[]) => mockCatalogBrowse(...args),
    catalogPipelineStatus: (...args: unknown[]) => mockCatalogPipelineStatus(...args),
    catalogGraphSummary: (...args: unknown[]) => mockCatalogGraphSummary(...args),
    catalogChanges: (...args: unknown[]) => mockCatalogChanges(...args),
    catalogHITL: (...args: unknown[]) => mockCatalogHITL(...args),
    catalogEntityDetail: vi.fn().mockResolvedValue({}),
    catalogEntityProfile: vi.fn().mockResolvedValue({}),
    catalogResolveHITL: vi.fn().mockResolvedValue({}),
    sourceProfile: vi.fn().mockResolvedValue({}),
    datasetProfile: vi.fn().mockResolvedValue({}),
    refreshMV: vi.fn().mockResolvedValue({}),
    runEnrichment: vi.fn().mockResolvedValue({}),
  },
  SOURCE_LABELS: {},
  ENTITY_TYPE_LABELS: {},
}));

// Mock child components
vi.mock('../LiteratureExplorer', () => ({ LiteratureExplorer: () => <div /> }));
vi.mock('../ui/ErrorBoundary', () => ({
  ErrorBoundary: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));
vi.mock('../ui/Drawer', () => ({
  Drawer: ({ children, open }: React.PropsWithChildren<{ open: boolean }>) =>
    open ? <div data-testid="drawer">{children}</div> : null,
}));
vi.mock('../EntityDossier', () => ({ default: () => <div data-testid="entity-dossier" /> }));
vi.mock('../EntityProfileCard', () => ({ default: () => <div data-testid="entity-profile" /> }));
vi.mock('../SourceProfileCard', () => ({ default: () => <div data-testid="source-profile" /> }));

beforeEach(() => {
  vi.clearAllMocks();

  mockHealth.mockResolvedValue({
    status: 'ok',
    database: 'connected',
    tables: { entities: 1000 },
    services: ['search'],
    total_records: 606000,
    source_coverage: [],
  });
  mockCatalogStats.mockResolvedValue({
    total_entities: 5000,
    total_links: 50000,
    entity_type_counts: { drug: 1000, company: 500, trial: 2000 },
  });
  mockCatalogDatasets.mockResolvedValue({
    datasets: [],
    count: 0,
  });
  mockCatalogBrowse.mockResolvedValue({
    results: [
      {
        id: 'drug-1',
        _label: 'Erlotinib',
        generic_name: 'Erlotinib',
        entity_type: 'drug',
        quality_score: 0.85,
        source_api: 'clinical_trials_gov',
      },
      {
        id: 'drug-2',
        _label: 'Gefitinib',
        generic_name: 'Gefitinib',
        entity_type: 'drug',
        quality_score: 0.72,
        source_api: 'fda_orange_book',
      },
      {
        id: 'drug-3',
        _label: 'Osimertinib',
        generic_name: 'Osimertinib',
        entity_type: 'drug',
        quality_score: 0.90,
        source_api: 'clinical_trials_gov',
      },
    ],
    total: 3,
    page: 0,
    page_size: 24,
  });
  mockCatalogPipelineStatus.mockResolvedValue({ connectors: [] });
  mockCatalogGraphSummary.mockResolvedValue({
    link_types: [],
    total_links: 50000,
    total_entities: 5000,
    drug_completeness: {},
  });
  mockCatalogChanges.mockResolvedValue({ changes: [] });
  mockCatalogHITL.mockResolvedValue({ items: [] });
});

describe('DataCatalogPanel', () => {
  it('renders entity type filter pills', async () => {
    render(<DataCatalogPanel />);
    await waitFor(() => {
      expect(screen.getByText('All')).toBeInTheDocument();
    });
    expect(screen.getByText('Drugs')).toBeInTheDocument();
    expect(screen.getByText('Companies')).toBeInTheDocument();
    expect(screen.getByText('Trials')).toBeInTheDocument();
    expect(screen.getByText('Mechanisms')).toBeInTheDocument();
    expect(screen.getByText('Therapeutic Areas')).toBeInTheDocument();
    // "Sources" appears as both a filter pill and in the supply chain strip,
    // so use getAllByText to confirm at least one exists
    const sourcesElements = screen.getAllByText('Sources');
    expect(sourcesElements.length).toBeGreaterThanOrEqual(1);
  });

  it('renders entity cards from browse data', async () => {
    render(<DataCatalogPanel />);
    // The component calls catalogBrowse for both featured (top 3) and the browse grid.
    // Wait for entity names to appear.
    await waitFor(() => {
      expect(screen.getAllByText('Erlotinib').length).toBeGreaterThanOrEqual(1);
    });
    expect(screen.getAllByText('Gefitinib').length).toBeGreaterThanOrEqual(1);
  });

  it('shows loading state while fetching', () => {
    // Make the health call hang to keep loading state
    mockHealth.mockReturnValue(new Promise(() => {}));
    mockCatalogStats.mockReturnValue(new Promise(() => {}));
    mockCatalogDatasets.mockReturnValue(new Promise(() => {}));
    mockCatalogBrowse.mockReturnValue(new Promise(() => {}));
    mockCatalogPipelineStatus.mockReturnValue(new Promise(() => {}));
    mockCatalogGraphSummary.mockReturnValue(new Promise(() => {}));

    const { container } = render(<DataCatalogPanel />);
    // The component renders Skeleton loaders when loading
    const skeletons = container.querySelectorAll('[style*="skeleton-pulse"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });
});
