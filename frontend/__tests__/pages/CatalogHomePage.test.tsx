/**
 * DataHub · Phase 0 · Lens A (L1) — Catalog Home + Source dossier tests.
 *
 * Screen 1: searchable / filterable grid of connected sources (connector
 * type, status verdict, data type, FAIR ring). Screen 2: source dossier with
 * the 5-dim FAIR breakdown, schema preview, and coverage.
 *
 * Headless component — props in, callbacks out, mirroring SourcesPage.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import {
  CatalogHomePage,
  type CatalogSource,
  type SourceDetail,
} from '../../src/pages/CatalogHomePage';

const SOURCES: CatalogSource[] = [
  {
    source_key: 'clinical_trials_gov',
    dataset_name: 'clinical_trials_gov.trials',
    label: 'ClinicalTrials.gov',
    connector_type: 'regulatory_api',
    data_type: 'trial',
    status: 'fresh',
    records: 12450,
    quality_overall: 0.88,
    freshness_days: 1,
  },
  {
    source_key: 'sec_edgar',
    dataset_name: 'sec_edgar.filings',
    label: 'SEC EDGAR',
    connector_type: 'corporate_filing',
    data_type: 'company',
    status: 'stale',
    records: 3120,
    quality_overall: 0.61,
    freshness_days: 11,
  },
  {
    source_key: 'pubmed',
    dataset_name: 'pubmed.articles',
    label: 'PubMed',
    connector_type: 'scientific_literature',
    data_type: 'article',
    status: 'ok',
    records: 90210,
    quality_overall: 0.79,
    freshness_days: 3,
  },
  {
    source_key: 'nadac_pricing',
    dataset_name: 'nadac_pricing.prices',
    label: 'NADAC pricing',
    connector_type: 'csv',
    data_type: null,
    status: 'never',
    records: 0,
    quality_overall: null,
    freshness_days: null,
  },
];

const SEC_DETAIL: SourceDetail = {
  source_key: 'sec_edgar',
  dataset_name: 'sec_edgar.filings',
  label: 'SEC EDGAR',
  connector_type: 'corporate_filing',
  schedule: 'daily',
  license: 'free · public domain',
  quality: {
    overall: 0.79,
    dimensions: [
      { key: 'completeness', label: 'Completeness', value: 0.84, explanation: 'fields populated' },
      { key: 'quality', label: 'Data quality', value: 0.71, explanation: 'mean score' },
      { key: 'accessibility', label: 'Accessibility', value: 1.0, explanation: 'data landed' },
      { key: 'license_openness', label: 'License openness', value: 0.7, explanation: 'reuse terms' },
    ],
  },
  fields_collected: ['cik', 'form', 'filed_at', 'revenue'],
  records: 3120,
  freshness_days: 11,
  coverage: [
    { entity_type: 'company', count: 3000 },
    { entity_type: 'event', count: 120 },
  ],
};

function setup(overrides: Partial<Parameters<typeof CatalogHomePage>[0]> = {}) {
  const onSelectSource = vi.fn();
  const onCloseDetail = vi.fn();
  const onRefresh = vi.fn();
  const utils = render(
    <CatalogHomePage
      sources={SOURCES}
      selected={null}
      onSelectSource={onSelectSource}
      onCloseDetail={onCloseDetail}
      onRefresh={onRefresh}
      {...overrides}
    />,
  );
  return { ...utils, onSelectSource, onCloseDetail, onRefresh };
}

describe('CatalogHomePage — catalog home grid', () => {
  it('renders a card for every connected source', () => {
    const { container } = setup();
    const cards = container.querySelectorAll('[data-source-card]');
    expect(cards.length).toBe(SOURCES.length);
  });

  it('shows connector type, status verdict, and rows on each card', () => {
    const { container } = setup();
    const sec = container.querySelector('[data-source-card="sec_edgar.filings"]') as HTMLElement;
    expect(within(sec).getByText('SEC EDGAR')).toBeInTheDocument();
    expect(within(sec).getByText(/corporate filing/i)).toBeInTheDocument();
    expect(sec.querySelector('[data-status-badge="stale"]')).not.toBeNull();
    expect(within(sec).getByText(/3,120 rows/)).toBeInTheDocument();
  });

  it('renders a Quality ring with the rounded overall score', () => {
    const { container } = setup();
    const ct = container.querySelector('[data-source-card="clinical_trials_gov.trials"]') as HTMLElement;
    const ring = ct.querySelector('[data-quality-ring]') as HTMLElement;
    expect(ring).not.toBeNull();
    expect(ring.textContent).toBe('88');
    // Honesty: the ring is labelled Quality, never "FAIR".
    expect(ring.getAttribute('title')).toMatch(/Quality/);
    expect(ring.getAttribute('title')).not.toMatch(/FAIR/);
  });

  it('shows a placeholder ring for a source still profiling (null quality)', () => {
    const { container } = setup();
    const nadac = container.querySelector('[data-source-card="nadac_pricing.prices"]') as HTMLElement;
    const ring = nadac.querySelector('[data-quality-ring]') as HTMLElement;
    expect(ring.textContent).toBe('–'); // en-dash placeholder
  });

  it('clicking a card fires onSelectSource with BOTH the source_type and the dataset_name', () => {
    const { container, onSelectSource } = setup();
    const card = container.querySelector('[data-source-card="pubmed.articles"]') as HTMLElement;
    fireEvent.click(card);
    // The container needs both: source_type → /profile, composite dataset_name → /fair.
    expect(onSelectSource).toHaveBeenCalledWith('pubmed', 'pubmed.articles');
  });

  it('renders distinct cards for two datasets of the SAME source (no key collision)', () => {
    const twoOfOne: CatalogSource[] = [
      { ...SOURCES[0], source_key: 'clinical_trials_gov', dataset_name: 'clinical_trials_gov.trials' },
      { ...SOURCES[0], source_key: 'clinical_trials_gov', dataset_name: 'clinical_trials_gov.sponsors', data_type: 'company' },
    ];
    const { container } = setup({ sources: twoOfOne });
    const cards = container.querySelectorAll('[data-source-card]');
    expect(cards.length).toBe(2); // two distinct cards, not collapsed to one
    expect(container.querySelector('[data-source-card="clinical_trials_gov.trials"]')).not.toBeNull();
    expect(container.querySelector('[data-source-card="clinical_trials_gov.sponsors"]')).not.toBeNull();
  });

  it('renders a "Connect a source" entry that fires onConnect (F5 discoverability)', () => {
    const onConnect = vi.fn();
    const { container } = setup({ onConnect });
    const btn = container.querySelector('[data-action="connect-source"]') as HTMLElement;
    expect(btn).not.toBeNull();
    fireEvent.click(btn);
    expect(onConnect).toHaveBeenCalled();
  });

  it('omits the Connect entry when no onConnect is provided', () => {
    const { container } = setup();
    expect(container.querySelector('[data-action="connect-source"]')).toBeNull();
  });
});

describe('CatalogHomePage — search + filter', () => {
  it('search narrows the grid by label', () => {
    const { container } = setup();
    const input = screen.getByLabelText(/search sources/i);
    fireEvent.change(input, { target: { value: 'edgar' } });
    const cards = container.querySelectorAll('[data-source-card]');
    expect(cards.length).toBe(1);
    expect(container.querySelector('[data-source-card="sec_edgar.filings"]')).not.toBeNull();
  });

  it('connector-type filter shows only matching sources', () => {
    const { container } = setup();
    const select = screen.getByLabelText(/filter by connector type/i);
    fireEvent.change(select, { target: { value: 'csv' } });
    const cards = container.querySelectorAll('[data-source-card]');
    expect(cards.length).toBe(1);
    expect(container.querySelector('[data-source-card="nadac_pricing.prices"]')).not.toBeNull();
  });

  it('status filter shows only matching sources', () => {
    const { container } = setup();
    const select = screen.getByLabelText(/filter by status/i);
    fireEvent.change(select, { target: { value: 'fresh' } });
    const cards = container.querySelectorAll('[data-source-card]');
    expect(cards.length).toBe(1);
    expect(container.querySelector('[data-source-card="clinical_trials_gov.trials"]')).not.toBeNull();
  });

  it('shows an empty state when no source matches', () => {
    const { container } = setup();
    const input = screen.getByLabelText(/search sources/i);
    fireEvent.change(input, { target: { value: 'zzzznope' } });
    expect(container.querySelector('[data-empty-state]')).not.toBeNull();
    expect(container.querySelectorAll('[data-source-card]').length).toBe(0);
  });
});

describe('CatalogHomePage — source dossier (Screen 2)', () => {
  it('renders the dossier when a source is selected', () => {
    const { container } = setup({ selected: SEC_DETAIL });
    expect(container.querySelector('[data-source-dossier="sec_edgar"]')).not.toBeNull();
    // The grid is replaced by the dossier.
    expect(container.querySelectorAll('[data-source-card]').length).toBe(0);
  });

  it('renders the quality dimensions (D-API-2) with their scores, labelled Quality not FAIR', () => {
    const { container } = setup({ selected: SEC_DETAIL });
    expect(container.querySelector('[data-quality-dim="completeness"]')).not.toBeNull();
    expect(container.querySelector('[data-quality-dim="quality"]')).not.toBeNull();
    expect(container.querySelector('[data-quality-dim="accessibility"]')).not.toBeNull();
    expect(container.querySelector('[data-quality-dim="license_openness"]')).not.toBeNull();
    const completeness = container.querySelector('[data-quality-dim="completeness"]') as HTMLElement;
    expect(within(completeness).getByText('0.84')).toBeInTheDocument();
    // No "FAIR" language in the dossier body (it's a derived composite, not a FAIR audit).
    expect(screen.queryByText(/FAIR profile/i)).toBeNull();
    expect(screen.getByText(/Quality profile/i)).toBeInTheDocument();
  });

  it('renders a null dimension as "n/a", never fabricated', () => {
    const partial: SourceDetail = {
      ...SEC_DETAIL,
      quality: {
        overall: 0.5,
        dimensions: [
          { key: 'completeness', label: 'Completeness', value: 0.5, explanation: '' },
          { key: 'quality', label: 'Data quality', value: null, explanation: 'not scored' },
        ],
      },
    };
    const { container } = setup({ selected: partial });
    const q = container.querySelector('[data-quality-dim="quality"]') as HTMLElement;
    expect(within(q).getByText('n/a')).toBeInTheDocument();
  });

  it('shows an explicit error+retry dossier when the profile failed to load', () => {
    const errored: SourceDetail = {
      ...SEC_DETAIL,
      loadError: 'HTTP 500',
    };
    const { container, onSelectSource } = setup({ selected: errored });
    const errBox = container.querySelector('[data-dossier-error="sec_edgar"]') as HTMLElement;
    expect(errBox).not.toBeNull();
    expect(within(errBox).getByText(/sec_edgar/)).toBeInTheDocument();
    // It is NOT a normal (empty-but-valid) dossier — no quality dims rendered.
    expect(container.querySelector('[data-quality-dim]')).toBeNull();
    const retry = container.querySelector('[data-action="retry-dossier"]') as HTMLElement;
    fireEvent.click(retry);
    // Retry re-drives the same drill-in: both grains, so /fair can re-resolve.
    expect(onSelectSource).toHaveBeenCalledWith('sec_edgar', 'sec_edgar.filings');
  });

  it('renders a schema preview of the fields collected', () => {
    const { container } = setup({ selected: SEC_DETAIL });
    expect(container.querySelector('[data-schema-field="cik"]')).not.toBeNull();
    expect(container.querySelector('[data-schema-field="revenue"]')).not.toBeNull();
  });

  it('renders coverage rows by entity type', () => {
    const { container } = setup({ selected: SEC_DETAIL });
    const company = container.querySelector('[data-coverage-row="company"]') as HTMLElement;
    expect(company).not.toBeNull();
    expect(within(company).getByText(/3,000/)).toBeInTheDocument();
  });

  it('the back button fires onCloseDetail', () => {
    const { container, onCloseDetail } = setup({ selected: SEC_DETAIL });
    const btn = container.querySelector('[data-action="close-dossier"]') as HTMLElement;
    fireEvent.click(btn);
    expect(onCloseDetail).toHaveBeenCalled();
  });

  it('shows a loading dossier while the profile is fetching', () => {
    const { container } = setup({ selected: null, selectedLoading: true });
    expect(container.querySelector('[data-source-dossier]')).not.toBeNull();
    expect(screen.getByText(/loading profile/i)).toBeInTheDocument();
  });
});

describe('CatalogHomePage — accessibility', () => {
  it('uses a main landmark named "Data catalog"', () => {
    setup();
    expect(screen.getByRole('main', { name: /data catalog/i })).toBeInTheDocument();
  });
});
