import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import GraphExplorer from '../GraphExplorer';

// Mock the api module
vi.mock('../../api', () => ({
  api: {
    listEntities: vi.fn().mockResolvedValue({ results: [] }),
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
  },
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

  it('renders objective buttons', () => {
    render(<GraphExplorer />);
    // The objectives are rendered as button text
    expect(screen.getByRole('button', { name: 'Entity Neighborhood' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Trial Evidence Map' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Portfolio Network' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mechanism Landscape' })).toBeInTheDocument();
  });

  it('renders graph explorer title', () => {
    render(<GraphExplorer />);
    expect(screen.getByText('Graph Explorer')).toBeInTheDocument();
  });

  it('renders hops selector', () => {
    render(<GraphExplorer />);
    expect(screen.getByText('Hops')).toBeInTheDocument();
  });
});
