/**
 * DataHub · Phase 0 · Lens A (L1b) — CatalogPage container tests.
 *
 * The container wires the headless CatalogHomePage to live read-API shapes:
 *   - api.catalogDatasets()      → the source grid (records, quality overall, data type)
 *   - api.catalogPipelineStatus() → the per-source status verdict + connector schedule
 *   - api.datasetProfile(key)     → the drill-in source dossier
 *   - api.datasetFair(key)        → the D-API-2 source-level quality breakdown
 *
 * Covers: loading → ready (grid joined from datasets × pipeline-status), the
 * error path, opening a source dossier (profile + D-API-2 quality breakdown),
 * the explicit profile-load-failure error state, and honest "Quality" (not FAIR)
 * language (cross-lane review MZ-XR-20260613-004).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../src/api', () => ({
  api: {
    catalogDatasets: vi.fn(),
    catalogPipelineStatus: vi.fn(),
    datasetProfile: vi.fn(),
    datasetFair: vi.fn(),
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
      fair_overall: 0.94, // D-API-2 composite — preferred over the raw quality score
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

const FAIR = {
  source_key: 'sec_edgar',
  fair_overall: 0.63,
  by_dimension: {
    completeness: { value: 0.7, weight: 0.35, explanation: 'fields populated' },
    quality: { value: 0.45, weight: 0.3, explanation: 'mean score' },
    accessibility: { value: 1.0, weight: 0.2, explanation: 'data landed' },
    license_openness: { value: 1.0, weight: 0.15, explanation: 'open license' },
  },
  freshness_days: 11,
  note: 'derived ingest-health composite — not a formal FAIR audit',
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

  it('prefers the D-API-2 fair_overall composite for the ring, degrading to a placeholder when absent', async () => {
    (api.catalogDatasets as any).mockResolvedValue(DATASETS);
    (api.catalogPipelineStatus as any).mockResolvedValue(PIPELINE);
    const { container } = render(<CatalogPage />);
    await waitFor(() =>
      expect(screen.getByRole('main', { name: /data catalog/i })).toBeInTheDocument(),
    );
    const ct = container.querySelector('[data-source-card="clinical_trials_gov"]') as HTMLElement;
    // 0.94 (fair_overall) preferred over 0.88 (quality_score_avg).
    expect((ct.querySelector('[data-quality-ring]') as HTMLElement).textContent).toBe('94');
    // SEC has neither → placeholder ring (en-dash), not a fabricated number.
    const sec = container.querySelector('[data-source-card="sec_edgar"]') as HTMLElement;
    expect((sec.querySelector('[data-quality-ring]') as HTMLElement).textContent).toBe('–');
  });

  it('opens a dossier with the D-API-2 quality breakdown (labelled Quality, not FAIR)', async () => {
    (api.catalogDatasets as any).mockResolvedValue(DATASETS);
    (api.catalogPipelineStatus as any).mockResolvedValue(PIPELINE);
    (api.datasetProfile as any).mockResolvedValue(PROFILE);
    (api.datasetFair as any).mockResolvedValue(FAIR);
    const { container } = render(<CatalogPage />);
    await waitFor(() =>
      expect(screen.getByRole('main', { name: /data catalog/i })).toBeInTheDocument(),
    );
    fireEvent.click(container.querySelector('[data-source-card="sec_edgar"]') as HTMLElement);
    await waitFor(() =>
      expect(container.querySelector('[data-source-dossier="sec_edgar"]')).not.toBeNull(),
    );
    expect(api.datasetProfile).toHaveBeenCalledWith('sec_edgar');
    expect(api.datasetFair).toHaveBeenCalledWith('sec_edgar');
    expect(container.querySelector('[data-schema-field="cik"]')).not.toBeNull();
    // The real D-API-2 dimensions render; no "FAIR" language.
    expect(container.querySelector('[data-quality-dim="completeness"]')).not.toBeNull();
    expect(container.querySelector('[data-quality-dim="accessibility"]')).not.toBeNull();
    expect(screen.getByText(/Quality profile/i)).toBeInTheDocument();
    expect(screen.queryByText(/FAIR profile/i)).toBeNull();
  });

  it('shows an explicit error+retry dossier when the profile load fails (not a silent empty card)', async () => {
    (api.catalogDatasets as any).mockResolvedValue(DATASETS);
    (api.catalogPipelineStatus as any).mockResolvedValue(PIPELINE);
    (api.datasetProfile as any).mockRejectedValue(new Error('HTTP 500'));
    (api.datasetFair as any).mockRejectedValue(new Error('HTTP 500'));
    const { container } = render(<CatalogPage />);
    await waitFor(() =>
      expect(screen.getByRole('main', { name: /data catalog/i })).toBeInTheDocument(),
    );
    fireEvent.click(container.querySelector('[data-source-card="sec_edgar"]') as HTMLElement);
    await waitFor(() =>
      expect(container.querySelector('[data-dossier-error="sec_edgar"]')).not.toBeNull(),
    );
    // It's a real error state, not an empty-but-valid dossier.
    expect(container.querySelector('[data-quality-dim]')).toBeNull();
    expect(screen.getByText(/HTTP 500/)).toBeInTheDocument();
    // Retry re-requests the profile.
    fireEvent.click(container.querySelector('[data-action="retry-dossier"]') as HTMLElement);
    expect((api.datasetProfile as any).mock.calls.length).toBe(2);
  });

  it('shows an error state when the catalog load fails', async () => {
    (api.catalogDatasets as any).mockRejectedValue(new Error('500: boom'));
    (api.catalogPipelineStatus as any).mockResolvedValue(PIPELINE);
    render(<CatalogPage />);
    await waitFor(() => expect(screen.getByTestId('catalog-error')).toBeInTheDocument());
  });
});
