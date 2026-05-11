import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import DossierPage from '../../src/pages/DossierPage';
import { ThemeProvider } from '../../src/hooks/useTheme';

// Mock the hook so we control the dossier payload per test.
vi.mock('../../src/hooks/useDossier', () => ({
  useDossier: vi.fn(),
}));

import { useDossier } from '../../src/hooks/useDossier';

function renderAt(path: string) {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/dossier/:entityType/:slug" element={<DossierPage />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

const MOCK_DRUG = {
  entity: {
    id: 'ent-tirzepatide',
    slug: 'tirzepatide',
    type: 'drug' as const,
    canonical_name: 'tirzepatide',
    aliases: ['Mounjaro', 'Zepbound', 'LY3298176'],
    external_ids: { rxnorm: '2589007', chembl: 'CHEMBL4297535' },
    primary_attributes: {
      mechanism: 'GIP/GLP-1 dual agonist',
      company: 'Eli Lilly',
      approval_date: '2022-05-13',
    },
    updated_at: '2026-05-09T12:00:00Z',
  },
  synthesis: {
    summary: 'Tirzepatide is a dual GIP/GLP-1 receptor agonist approved in 2022 for type 2 diabetes (Mounjaro) and chronic weight management (Zepbound).',
    citations: [],
  },
  recent_moves: [],
  evidence: [
    { id: 'ev-1', source_name: 'ClinicalTrials.gov', tier: 'T1' as const, published_at: '2026-04-15', snippet: 'SURPASS-PEDS Phase 3 trial primary endpoint met.' },
    { id: 'ev-2', source_name: 'FDA Orange Book', tier: 'T1' as const, published_at: '2026-03-10', snippet: 'Patent expiry 2036.' },
    { id: 'ev-3', source_name: 'PubMed', tier: 'T3' as const, published_at: '2026-02-20', snippet: 'NEJM publication — SURPASS-1 5-year follow-up.' },
    { id: 'ev-4', source_name: 'SEC EDGAR', tier: 'T2' as const, published_at: '2026-01-30', snippet: 'Lilly Q1 8-K — Mounjaro $5.4B revenue.' },
  ],
  watchers: [],
  watcher_count: 0,
};

describe('DossierPage (PB-301 scaffold)', () => {
  beforeEach(() => {
    vi.mocked(useDossier).mockReset();
  });

  it('renders the loading state while the dossier is fetching', () => {
    vi.mocked(useDossier).mockReturnValue({ data: null, error: null, isLoading: true });
    renderAt('/dossier/drug/tirzepatide');
    expect(screen.getByText(/loading dossier/i)).toBeDefined();
  });

  it('renders an error state when the fetch fails', () => {
    vi.mocked(useDossier).mockReturnValue({ data: null, error: new Error('boom'), isLoading: false });
    renderAt('/dossier/drug/tirzepatide');
    expect(screen.getByText(/could not load dossier/i)).toBeDefined();
  });

  it('renders a 404-style state when the entity does not exist', () => {
    vi.mocked(useDossier).mockReturnValue({
      data: null,
      error: Object.assign(new Error('not found'), { status: 404 }),
      isLoading: false,
    });
    renderAt('/dossier/drug/unknown');
    expect(screen.getByText(/no dossier for/i)).toBeDefined();
  });

  it('renders the entity name and type badge in the header', () => {
    vi.mocked(useDossier).mockReturnValue({ data: MOCK_DRUG, error: null, isLoading: false });
    renderAt('/dossier/drug/tirzepatide');
    expect(screen.getByRole('heading', { name: /tirzepatide/i })).toBeDefined();
    expect(screen.getByText(/^drug$/i)).toBeDefined();
  });

  it('renders aliases and external IDs in the identity rail', () => {
    vi.mocked(useDossier).mockReturnValue({ data: MOCK_DRUG, error: null, isLoading: false });
    renderAt('/dossier/drug/tirzepatide');
    expect(screen.getByText('Mounjaro')).toBeDefined();
    expect(screen.getByText('LY3298176')).toBeDefined();
    expect(screen.getByText('rxnorm')).toBeDefined();
    expect(screen.getByText('2589007')).toBeDefined();
  });

  it('renders the synthesis summary in the centre column', () => {
    vi.mocked(useDossier).mockReturnValue({ data: MOCK_DRUG, error: null, isLoading: false });
    renderAt('/dossier/drug/tirzepatide');
    expect(screen.getByText(/dual GIP\/GLP-1 receptor agonist/i)).toBeDefined();
  });

  it('renders up to 3 evidence rows and a "+N more" affordance in the evidence pile', () => {
    vi.mocked(useDossier).mockReturnValue({ data: MOCK_DRUG, error: null, isLoading: false });
    renderAt('/dossier/drug/tirzepatide');
    expect(screen.getByText(/ClinicalTrials\.gov/)).toBeDefined();
    expect(screen.getByText(/FDA Orange Book/)).toBeDefined();
    expect(screen.getByText(/PubMed/)).toBeDefined();
    // 4th item is hidden behind +N more
    expect(screen.queryByText(/SEC EDGAR/)).toBeNull();
    expect(screen.getByText(/\+1 more/i)).toBeDefined();
  });

  it('renders synthesis-pending copy when the entity has no synthesis yet', () => {
    vi.mocked(useDossier).mockReturnValue({
      data: { ...MOCK_DRUG, synthesis: null },
      error: null,
      isLoading: false,
    });
    renderAt('/dossier/drug/tirzepatide');
    expect(screen.getByText(/synthesis pending/i)).toBeDefined();
  });
});
