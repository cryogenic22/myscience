/**
 * DataHub · Phase 0 · Lens A (L1b) — CatalogPage container tests.
 *
 * The container wires the headless CatalogHomePage to live read-API shapes:
 *   - api.catalogDatasets()      → the source grid (records, FAIR overall, data type)
 *   - api.catalogPipelineStatus() → the per-source status verdict + connector schedule
 *   - api.datasetProfile(key)     → the drill-in source dossier
 *
 * Covers: loading → ready (grid joined from datasets × pipeline-status), the
 * error path, opening a source dossier (datasetProfile), and the graceful
 * source-level-FAIR-absent degrade (fair === null until that endpoint exists).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../src/api', () => ({
  api: {
    catalogDatasets: vi.fn(),
    catalogPipelineStatus: vi.fn(),
    datasetProfile: vi.fn(),
  },
}));

import { api } from '../../src/api';
import CatalogPage from '../../src/pages/CatalogPage';

const DATASETS = {
  datasets: [
    {
      dataset_name: 'ClinicalTrials.gov',
      source_type: 'clinical_trials_gov',
      entity_type: 'trial',
      table_name: 'clinical_trials',
      row_count: 12450,
      last_refreshed_at: '2026-06-12T00:00:00Z',
      refresh_frequency: 'daily',
      license_name: 'free · public domain',
      quality_score_avg: 0.88,
      completeness_pct: 0.9,
      freshness_days: 1,
    },
    {
      dataset_name: 'SEC EDGAR',
      source_type: 'sec_edgar',
      entity_type: 'company',
      table_name: 'companies',
      row_count: 3120,
      last_refreshed_at: '2026-06-02T00:00:00Z',
      refresh_frequency: 'daily',
      license_name: 'free · public domain',
      quality_score_avg: null,
      completeness_pct: 0.7,
      freshness_days: 11,
    },
  ],
  count: 2,
};

const PIPELINE = {
  connectors: [
    {
      source_key: 'clinical_trials_gov',
      label: 'ClinicalTrials.gov',
      schedule: 'daily',
      last_run: '2026-06-12T00:00:00Z',
      days_since: 1,
      records: 12450,
      status: 'fresh',
    },
    {
      source_key: 'sec_edgar',
      label: 'SEC EDGAR',
      schedule: 'daily',
      last_run: '2026-06-02T00:00:00Z',
      days_since: 11,
      records: 3120,
      status: 'stale',
    },
  ],
};

const PROFILE = {
  source_key: 'sec_edgar',
  display_name: 'SEC EDGAR',
  description: 'Corporate filings',
  source_url: 'https://www.sec.gov',
  entity_types: ['company', 'event'],
  refresh_schedule: 'daily',
  collection_method: 'API (EDGAR REST + XBRL)',
  fields_collected: ['cik', 'form', 'filed_at', 'revenue'],
  coverage_notes: 'US public companies',
  records: 3120,
  quality_score: 0.79,
  last_refreshed: '2026-06-02T00:00:00Z',
  freshness: '11 days',
};

describe('CatalogPage container', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows a loading state before data arrives', () => {
    (api.catalogDatasets as any).mockReturnValue(new Promise(() => {}));
    (api.catalogPipelineStatus as any).mockReturnValue(new Promise(() => {}));
    render(<CatalogPage />);
    expect(screen.getByTestId('catalog-loading')).toBeInTheDocument();
  });

  it('renders the grid joined from datasets × pipeline-status', async () => {
    (api.catalogDatasets as any).mockResolvedValue(DATASETS);
    (api.catalogPipelineStatus as any).mockResolvedValue(PIPELINE);
    const { container } = render(<CatalogPage />);
    await waitFor(() =>
      expect(screen.getByRole('main', { name: /data catalog/i })).toBeInTheDocument(),
    );
    // One card per dataset.
    expect(container.querySelectorAll('[data-source-card]').length).toBe(2);
    // The pipeline-status verdict is carried onto the card.
    const sec = container.querySelector('[data-source-card="sec_edgar"]') as HTMLElement;
    expect(sec.querySelector('[data-status-badge="stale"]')).not.toBeNull();
    const ct = container.querySelector('[data-source-card="clinical_trials_gov"]') as HTMLElement;
    expect(ct.querySelector('[data-status-badge="fresh"]')).not.toBeNull();
  });

  it('maps quality_score_avg onto the FAIR ring, degrading to a placeholder when null', async () => {
    (api.catalogDatasets as any).mockResolvedValue(DATASETS);
    (api.catalogPipelineStatus as any).mockResolvedValue(PIPELINE);
    const { container } = render(<CatalogPage />);
    await waitFor(() =>
      expect(screen.getByRole('main', { name: /data catalog/i })).toBeInTheDocument(),
    );
    const ct = container.querySelector('[data-source-card="clinical_trials_gov"]') as HTMLElement;
    expect((ct.querySelector('[data-fair-ring]') as HTMLElement).textContent).toBe('88');
    // SEC has a null quality score → placeholder ring (en-dash), not a fabricated number.
    const sec = container.querySelector('[data-source-card="sec_edgar"]') as HTMLElement;
    expect((sec.querySelector('[data-fair-ring]') as HTMLElement).textContent).toBe('–');
  });

  it('opens a source dossier from datasetProfile and degrades source-level FAIR to null', async () => {
    (api.catalogDatasets as any).mockResolvedValue(DATASETS);
    (api.catalogPipelineStatus as any).mockResolvedValue(PIPELINE);
    (api.datasetProfile as any).mockResolvedValue(PROFILE);
    const { container } = render(<CatalogPage />);
    await waitFor(() =>
      expect(screen.getByRole('main', { name: /data catalog/i })).toBeInTheDocument(),
    );
    fireEvent.click(container.querySelector('[data-source-card="sec_edgar"]') as HTMLElement);
    await waitFor(() =>
      expect(container.querySelector('[data-source-dossier="sec_edgar"]')).not.toBeNull(),
    );
    expect(api.datasetProfile).toHaveBeenCalledWith('sec_edgar');
    // Schema preview is carried from the profile.
    expect(container.querySelector('[data-schema-field="cik"]')).not.toBeNull();
    // Source-level FAIR doesn't exist yet → graceful "profile pending" copy, no fabricated dims.
    expect(screen.getByText(/profile pending/i)).toBeInTheDocument();
    expect(container.querySelector('[data-fair-dim="completeness"]')).toBeNull();
  });

  it('shows an error state when the catalog load fails', async () => {
    (api.catalogDatasets as any).mockRejectedValue(new Error('500: boom'));
    (api.catalogPipelineStatus as any).mockResolvedValue(PIPELINE);
    render(<CatalogPage />);
    await waitFor(() => expect(screen.getByTestId('catalog-error')).toBeInTheDocument());
  });
});
