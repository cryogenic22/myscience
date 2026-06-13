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
    label: 'ClinicalTrials.gov',
    connector_type: 'regulatory_api',
    data_type: 'trial',
    status: 'fresh',
    records: 12450,
    fair_overall: 0.88,
    freshness_days: 1,
  },
  {
    source_key: 'sec_edgar',
    label: 'SEC EDGAR',
    connector_type: 'corporate_filing',
    data_type: 'company',
    status: 'stale',
    records: 3120,
    fair_overall: 0.61,
    freshness_days: 11,
  },
  {
    source_key: 'pubmed',
    label: 'PubMed',
    connector_type: 'scientific_literature',
    data_type: 'article',
    status: 'ok',
    records: 90210,
    fair_overall: 0.79,
    freshness_days: 3,
  },
  {
    source_key: 'nadac_pricing',
    label: 'NADAC pricing',
    connector_type: 'csv',
    data_type: null,
    status: 'never',
    records: 0,
    fair_overall: null,
    freshness_days: null,
  },
];

const SEC_DETAIL: SourceDetail = {
  source_key: 'sec_edgar',
  label: 'SEC EDGAR',
  connector_type: 'corporate_filing',
  schedule: 'daily',
  license: 'free · public domain',
  fair: {
    completeness: 0.84,
    source_diversity: 0.71,
    freshness: 0.66,
    link_density: 0.8,
    resolution: 0.92,
    overall: 0.79,
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
    const sec = container.querySelector('[data-source-card="sec_edgar"]') as HTMLElement;
    expect(within(sec).getByText('SEC EDGAR')).toBeInTheDocument();
    expect(within(sec).getByText(/corporate filing/i)).toBeInTheDocument();
    expect(sec.querySelector('[data-status-badge="stale"]')).not.toBeNull();
    expect(within(sec).getByText(/3,120 rows/)).toBeInTheDocument();
  });

  it('renders a FAIR ring with the rounded overall score', () => {
    const { container } = setup();
    const ct = container.querySelector('[data-source-card="clinical_trials_gov"]') as HTMLElement;
    const ring = ct.querySelector('[data-fair-ring]') as HTMLElement;
    expect(ring).not.toBeNull();
    expect(ring.textContent).toBe('88');
  });

  it('shows a placeholder ring for a source still profiling (null FAIR)', () => {
    const { container } = setup();
    const nadac = container.querySelector('[data-source-card="nadac_pricing"]') as HTMLElement;
    const ring = nadac.querySelector('[data-fair-ring]') as HTMLElement;
    expect(ring.textContent).toBe('–'); // en-dash placeholder
  });

  it('clicking a card fires onSelectSource with the source key', () => {
    const { container, onSelectSource } = setup();
    const card = container.querySelector('[data-source-card="pubmed"]') as HTMLElement;
    fireEvent.click(card);
    expect(onSelectSource).toHaveBeenCalledWith('pubmed');
  });
});

describe('CatalogHomePage — search + filter', () => {
  it('search narrows the grid by label', () => {
    const { container } = setup();
    const input = screen.getByLabelText(/search sources/i);
    fireEvent.change(input, { target: { value: 'edgar' } });
    const cards = container.querySelectorAll('[data-source-card]');
    expect(cards.length).toBe(1);
    expect(container.querySelector('[data-source-card="sec_edgar"]')).not.toBeNull();
  });

  it('connector-type filter shows only matching sources', () => {
    const { container } = setup();
    const select = screen.getByLabelText(/filter by connector type/i);
    fireEvent.change(select, { target: { value: 'csv' } });
    const cards = container.querySelectorAll('[data-source-card]');
    expect(cards.length).toBe(1);
    expect(container.querySelector('[data-source-card="nadac_pricing"]')).not.toBeNull();
  });

  it('status filter shows only matching sources', () => {
    const { container } = setup();
    const select = screen.getByLabelText(/filter by status/i);
    fireEvent.change(select, { target: { value: 'fresh' } });
    const cards = container.querySelectorAll('[data-source-card]');
    expect(cards.length).toBe(1);
    expect(container.querySelector('[data-source-card="clinical_trials_gov"]')).not.toBeNull();
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

  it('renders all 5 FAIR dimensions with their scores', () => {
    const { container } = setup({ selected: SEC_DETAIL });
    expect(container.querySelector('[data-fair-dim="completeness"]')).not.toBeNull();
    expect(container.querySelector('[data-fair-dim="source_diversity"]')).not.toBeNull();
    expect(container.querySelector('[data-fair-dim="freshness"]')).not.toBeNull();
    expect(container.querySelector('[data-fair-dim="link_density"]')).not.toBeNull();
    expect(container.querySelector('[data-fair-dim="resolution"]')).not.toBeNull();
    const completeness = container.querySelector('[data-fair-dim="completeness"]') as HTMLElement;
    expect(within(completeness).getByText('0.84')).toBeInTheDocument();
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
