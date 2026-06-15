import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import GraphExplorer from '../GraphExplorer';

// Mock the api module
vi.mock('../../api', () => ({
  api: {
    listEntities: vi.fn().mockResolvedValue({ results: [] }),
    searchSuggest: vi.fn().mockResolvedValue({ suggestions: [] }),
    traverse: vi.fn().mockResolvedValue({ nodes: [], edges: [] }),
    graphNeighborhood: vi.fn().mockResolvedValue({ nodes: [], edges: [] }),
    entitySummary: vi.fn().mockResolvedValue({ summary: '', links: [] }),
    graphPath: vi.fn().mockResolvedValue({ path: [], edges: [] }),
  },
}));

// Mock brand
vi.mock('../../brand', () => ({
  displayName: (s: string) => s.replace(/_/g, ' '),
  LINK_TYPE_LABELS: {},
  SOURCE_LABELS: {},
  isUUID: () => false,
}));

// Mock KnowledgeGraph (canvas-based) — export default
vi.mock('../KnowledgeGraph', () => ({
  default: (_props: Record<string, unknown>) => (
    <div data-testid="knowledge-graph">
      <canvas data-testid="graph-canvas" />
    </div>
  ),
}));

// Mock graph constants
vi.mock('../graph/graph-constants', () => ({
  NODE_COLORS: {
    drug: '#1C6EF7',
    company: '#22C55E',
    trial: '#0EA5E9',
    mechanism: '#F59E0B',
    therapeutic_area: '#8B5CF6',
    literature: '#EF4444',
    unknown: '#64748b',
  },
  GRAPH_LENSES: [
    { id: 'neighborhood', label: 'Neighborhood', description: 'All relationships.', linkTypes: null },
    { id: 'competitive', label: 'Competitive', description: 'Rivals.', linkTypes: ['COMPETES_WITH'] },
    { id: 'evidence', label: 'Evidence', description: 'Trial evidence.', linkTypes: ['INVESTIGATES'] },
    { id: 'regulatory', label: 'Regulatory', description: 'Patents.', linkTypes: ['HAS_PATENT'] },
    { id: 'safety', label: 'Safety', description: 'Adverse events.', linkTypes: ['HAS_ADVERSE_EVENT'] },
  ],
}));

// Mock Drawer
vi.mock('../ui/Drawer', () => ({
  Drawer: ({ children, open }: React.PropsWithChildren<{ open: boolean }>) =>
    open ? <div data-testid="drawer">{children}</div> : null,
}));

describe('GraphExplorer', () => {
  it('renders search input', () => {
    render(<GraphExplorer />);
    const searchInput = screen.getByPlaceholderText(/search/i);
    expect(searchInput).toBeInTheDocument();
  });

  it('renders lens control buttons', () => {
    render(<GraphExplorer />);
    // The objective pills were replaced by a real Lens segmented control whose
    // options map to actual link_type filters forwarded to the traverse call.
    expect(screen.getByRole('button', { name: 'Neighborhood' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Competitive' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Evidence' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Regulatory' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Safety' })).toBeInTheDocument();
  });

  it('renders graph explorer title', () => {
    render(<GraphExplorer />);
    expect(screen.getByText('Graph Explorer')).toBeInTheDocument();
  });

  it('renders hops selector with a 1-4 range', () => {
    render(<GraphExplorer />);
    expect(screen.getByText('Hops')).toBeInTheDocument();
    // API allows le=4 — the UI cap was raised from 3 to 4.
    const hopsOptions = screen.getAllByRole('option').map((o) => o.textContent);
    expect(hopsOptions).toEqual(['1', '2', '3', '4']);
  });
});
