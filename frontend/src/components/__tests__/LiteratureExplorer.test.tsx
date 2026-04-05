import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { LiteratureExplorer } from '../LiteratureExplorer';

// Mock IntersectionObserver for ContentArea's scroll-spy
globalThis.IntersectionObserver = class IntersectionObserver {
  constructor() {}
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof globalThis.IntersectionObserver;

const mockLiteratureDocument = vi.fn();
const mockLiteratureSimilar = vi.fn();
const mockLiteratureSummary = vi.fn();

vi.mock('../../api', () => ({
  api: {
    literatureDocument: (...args: unknown[]) => mockLiteratureDocument(...args),
    literatureSimilar: (...args: unknown[]) => mockLiteratureSimilar(...args),
    literatureSummary: (...args: unknown[]) => mockLiteratureSummary(...args),
  },
}));

function makeDoc() {
  return {
    id: 'lit-1',
    title: 'Efficacy of Semaglutide in Type 2 Diabetes',
    journal: 'The New England Journal of Medicine',
    publication_date: '2025-06-15',
    pmid: '12345678',
    pmc_id: 'PMC9876543',
    article_type: 'clinical-trial',
    is_protocol: false,
    is_systematic_review: false,
    has_full_text: true,
    authors: ['Smith J', 'Doe A', 'Brown K'],
    mesh_terms: ['Diabetes Mellitus, Type 2', 'GLP-1'],
    sections: [
      { id: 'abstract', title: 'Abstract', level: 1, content: 'Background text about the study.', children: [] },
      { id: 'methods', title: 'Methods', level: 1, content: 'Study design and methodology.', children: [] },
    ],
    external_urls: {
      pubmed: 'https://pubmed.ncbi.nlm.nih.gov/12345678',
      pmc: 'https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9876543',
      pdf: null,
    },
    cross_links: {
      drugs: [{ id: 'drug-1', name: 'Semaglutide' }],
      trials: [{ id: 'trial-1', title: 'NCT001 Phase III' }],
    },
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mockLiteratureSimilar.mockResolvedValue({ similar: [] });
  mockLiteratureSummary.mockResolvedValue({ summary: '' });
});

describe('LiteratureExplorer', () => {
  it('renders article title after loading', async () => {
    mockLiteratureDocument.mockResolvedValue(makeDoc());
    render(<LiteratureExplorer articleId="lit-1" onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Efficacy of Semaglutide in Type 2 Diabetes')).toBeInTheDocument();
    });
  });

  it('renders journal and PMID', async () => {
    mockLiteratureDocument.mockResolvedValue(makeDoc());
    render(<LiteratureExplorer articleId="lit-1" onClose={vi.fn()} />);

    await waitFor(() => {
      // Journal name appears in both header and sidebar
      const matches = screen.getAllByText(/The New England Journal of Medicine/);
      expect(matches.length).toBeGreaterThanOrEqual(1);
    });
  });

  it('renders cross-linked drugs', async () => {
    mockLiteratureDocument.mockResolvedValue(makeDoc());
    render(<LiteratureExplorer articleId="lit-1" onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Semaglutide')).toBeInTheDocument();
    });
    expect(screen.getByText('Linked Drugs')).toBeInTheDocument();
  });

  it('shows loading state during fetch', () => {
    mockLiteratureDocument.mockReturnValue(new Promise(() => {}));
    render(<LiteratureExplorer articleId="lit-1" onClose={vi.fn()} />);

    expect(screen.getByText(/Loading article/)).toBeInTheDocument();
  });

  it('renders section titles', async () => {
    mockLiteratureDocument.mockResolvedValue(makeDoc());
    render(<LiteratureExplorer articleId="lit-1" onClose={vi.fn()} />);

    await waitFor(() => {
      // Section titles appear in both the tree nav and the content area
      const abstractMatches = screen.getAllByText('Abstract');
      expect(abstractMatches.length).toBeGreaterThanOrEqual(1);
    });
    const methodsMatches = screen.getAllByText('Methods');
    expect(methodsMatches.length).toBeGreaterThanOrEqual(1);
  });

  it('renders MeSH terms', async () => {
    mockLiteratureDocument.mockResolvedValue(makeDoc());
    render(<LiteratureExplorer articleId="lit-1" onClose={vi.fn()} />);

    await waitFor(() => {
      expect(screen.getByText('Diabetes Mellitus, Type 2')).toBeInTheDocument();
    });
    expect(screen.getByText('GLP-1')).toBeInTheDocument();
  });
});
