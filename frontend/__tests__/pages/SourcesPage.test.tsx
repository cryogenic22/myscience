/**
 * F6 — SourcesPage tests.
 *
 * Riya's catch: named outlets with real article URLs, not abstract classes.
 * Each outlet is clickable; gap outlets surface a "Plan primary research"
 * affordance inline. Class tiles cycle a filter on the outlets table.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { SourcesPage } from '../../src/pages/SourcesPage';

const SCOPE = { focalAsset: 'drug:cagrisema', engagementName: 'CagriSema Pre-Launch' };

const CLASSES = [
  { id: 'regulatory_api',           label: 'Regulatory APIs',            connected: 4, total: 5 },
  { id: 'scientific_literature',    label: 'Scientific Literature',      connected: 3, total: 4 },
  { id: 'corporate_filings',        label: 'Corporate Filings',          connected: 2, total: 2 },
  { id: 'corporate_communications', label: 'Corporate Communications',   connected: 6, total: 8 },
  { id: 'scientific_presentations', label: 'Scientific Presentations',   connected: 0, total: 3 },
  { id: 'payer_pricing',            label: 'Payer / Pricing Intel',      connected: 1, total: 4 },
  { id: 'internal_documents',       label: 'Internal Documents',         connected: 0, total: 0 },
];

const OUTLETS = [
  { id: 'fierce_pharma', name: 'Fierce Pharma', classId: 'corporate_communications',
    access: 'free' as const, cadence: 'daily', status: 'connected' as const,
    latestArticle: {
      title: 'Lilly Q1 2026 beats consensus on Zepbound demand',
      url: 'https://fiercepharma.com/lilly-q1-2026',
      publishedAt: '2026-04-30',
    }},
  { id: 'biopharma_dive', name: 'BioPharma Dive', classId: 'corporate_communications',
    access: 'free' as const, cadence: 'daily', status: 'connected' as const,
    latestArticle: {
      title: 'Novo trims CagriSema guidance after REDEFINE 4 miss',
      url: 'https://biopharmadive.com/novo-cagrisema-redefine4',
      publishedAt: '2026-05-12',
    }},
  { id: 'aace_2026', name: 'AACE 2026 abstracts', classId: 'scientific_presentations',
    access: 'free' as const, cadence: 'on event', status: 'gap' as const,
    latestArticle: null },
  { id: 'mmit_formulary', name: 'MMIT formulary', classId: 'payer_pricing',
    access: 'paid' as const, cadence: 'daily', status: 'partial' as const,
    latestArticle: null },
];

function setup(overrides: Partial<Parameters<typeof SourcesPage>[0]> = {}) {
  const onPlanResearch = vi.fn();
  const onOpenArticle = vi.fn();
  const utils = render(
    <SourcesPage
      scope={SCOPE}
      classes={CLASSES as any}
      outlets={OUTLETS as any}
      onPlanResearch={onPlanResearch}
      onOpenArticle={onOpenArticle}
      {...overrides}
    />,
  );
  return { ...utils, onPlanResearch, onOpenArticle };
}

describe('SourcesPage — header', () => {
  it('shows the engagement name and completeness ratio', () => {
    setup();
    expect(screen.getByText(/CagriSema Pre-Launch/)).toBeInTheDocument();
    // covered = 4+3+2+6+0+1+0 = 16; total = 5+4+2+8+3+4+0 = 26
    expect(screen.getByText(/16\s*\/\s*26/)).toBeInTheDocument();
  });
});

describe('SourcesPage — class tiles', () => {
  it('renders 7 class tiles with data-class', () => {
    const { container } = setup();
    const tiles = container.querySelectorAll('[data-class]');
    expect(tiles.length).toBe(CLASSES.length);
  });

  it('class with 0 connected gets a gap or empty-state tone', () => {
    const { container } = setup();
    const empty = container.querySelector('[data-class="internal_documents"]');
    expect(empty?.getAttribute('data-status')).toMatch(/empty|gap/i);
  });

  it('clicking a class tile filters the outlets table', () => {
    const { container } = setup();
    const tile = container.querySelector('[data-class="corporate_communications"]') as HTMLElement;
    fireEvent.click(tile);
    // Only outlets of this class should be visible; AACE 2026 + MMIT should
    // be filtered out.
    expect(screen.getByText('Fierce Pharma')).toBeInTheDocument();
    expect(screen.queryByText('AACE 2026 abstracts')).toBeNull();
    expect(screen.queryByText('MMIT formulary')).toBeNull();
  });

  it('clicking the same class tile again clears the filter', () => {
    const { container } = setup();
    const tile = container.querySelector('[data-class="corporate_communications"]') as HTMLElement;
    fireEvent.click(tile);
    fireEvent.click(tile);
    expect(screen.getByText('AACE 2026 abstracts')).toBeInTheDocument();
  });
});

describe('SourcesPage — outlets table', () => {
  it('renders all outlets with name, class label, access, cadence, status', () => {
    setup();
    expect(screen.getByText('Fierce Pharma')).toBeInTheDocument();
    expect(screen.getByText('BioPharma Dive')).toBeInTheDocument();
    expect(screen.getByText('AACE 2026 abstracts')).toBeInTheDocument();
    expect(screen.getByText('MMIT formulary')).toBeInTheDocument();
  });

  it('outlet with latestArticle renders a clickable link', () => {
    const { onOpenArticle, container } = setup();
    const link = container.querySelector('[data-action="open-article"][data-outlet="fierce_pharma"]') as HTMLElement;
    expect(link).not.toBeNull();
    fireEvent.click(link);
    expect(onOpenArticle).toHaveBeenCalledWith('fierce_pharma', 'https://fiercepharma.com/lilly-q1-2026');
  });

  it('outlet without latestArticle renders a muted placeholder', () => {
    const { container } = setup();
    const row = container.querySelector('[data-outlet="aace_2026"]') as HTMLElement;
    expect(within(row).getByText('—')).toBeInTheDocument();
  });

  it('gap outlet shows a "Plan primary research" button that fires onPlanResearch', () => {
    const { container, onPlanResearch } = setup();
    const btn = container.querySelector('[data-outlet="aace_2026"] [data-action="plan-research"]') as HTMLElement;
    expect(btn).not.toBeNull();
    fireEvent.click(btn);
    expect(onPlanResearch).toHaveBeenCalledWith('aace_2026');
  });

  it('non-gap outlets do not show the plan-research CTA', () => {
    const { container } = setup();
    const row = container.querySelector('[data-outlet="fierce_pharma"]') as HTMLElement;
    expect(within(row).queryByText(/plan primary research/i)).toBeNull();
  });
});

describe('SourcesPage — empty class', () => {
  it('shows "No outlets configured" when a class has zero outlets', () => {
    const { container } = setup();
    const tile = container.querySelector('[data-class="internal_documents"]') as HTMLElement;
    fireEvent.click(tile);
    expect(screen.getByText(/no outlets configured/i)).toBeInTheDocument();
  });
});

describe('SourcesPage — accessibility', () => {
  it('uses a main landmark named "Sources and Gaps"', () => {
    setup();
    expect(screen.getByRole('main', { name: /sources and gaps/i })).toBeInTheDocument();
  });

  it('outlets table has accessible column headers', () => {
    const { container } = setup();
    const table = container.querySelector('table[aria-label="Named outlets"]');
    expect(table).not.toBeNull();
    expect(within(table as HTMLElement).getByText(/outlet/i)).toBeInTheDocument();
    expect(within(table as HTMLElement).getByText(/access/i)).toBeInTheDocument();
  });
});
