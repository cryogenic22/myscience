import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import GraphExplorer from '../GraphExplorer';

// Mock the api module
vi.mock('../../api', () => ({
  api: {
    searchSuggest: vi.fn().mockResolvedValue({ suggestions: [] }),
    traverse: vi.fn().mockResolvedValue({ nodes: [], edges: [] }),
    // null is a real return (loadGraph does .catch(() => null)); the component
    // guards every entitySummary read with `entitySummary && …`.
    entitySummary: vi.fn().mockResolvedValue(null),
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

  it('clears a committed path entity when its search box is edited — no stale id submitted (MZ-XR-20260615-001)', async () => {
    const { api } = await import('../../api');
    // Suggestion echoes the query so From/To resolve to distinct, predictable entities.
    vi.mocked(api.searchSuggest).mockImplementation((q: string) =>
      Promise.resolve({ suggestions: [{ entity_id: `${q}-id`, entity_type: 'drug', label: q.toUpperCase(), similarity: 1 }] }),
    );
    const graphPath = vi.mocked(api.graphPath);
    graphPath.mockClear();

    render(<GraphExplorer />);

    // Open the path finder
    fireEvent.click(screen.getByRole('button', { name: /find path/i }));

    // Commit a "From" entity via the suggestion dropdown
    const fromInput = screen.getByPlaceholderText(/search starting entity/i);
    fireEvent.change(fromInput, { target: { value: 'sema' } });
    fireEvent.click(await screen.findByText('SEMA'));

    // Commit a "To" entity
    const toInput = screen.getByPlaceholderText(/search target entity/i);
    fireEvent.change(toInput, { target: { value: 'tirz' } });
    fireEvent.click(await screen.findByText('TIRZ'));

    // Both committed → Show Path is enabled
    const showPath = screen.getByRole('button', { name: /show path/i });
    await waitFor(() => expect(showPath).toBeEnabled());

    // Edit the From box AWAY from the committed selection: the visible text and
    // the committed entity now diverge. The committed entity must be cleared so a
    // path query can NEVER run against the stale, hidden id.
    fireEvent.change(fromInput, { target: { value: 'semaglutide-typo' } });

    expect(showPath).toBeDisabled();
    fireEvent.click(showPath);
    expect(graphPath).not.toHaveBeenCalled();
  });

  it('selecting a lens re-runs traverse with that lens link_types (the control is REAL, not a no-op)', async () => {
    const { api } = await import('../../api');
    const traverse = vi.mocked(api.traverse);
    // initialEntity auto-loads (sets the anchor), so a lens click has an anchor to re-traverse.
    render(<GraphExplorer initialEntity={{ id: 'sema', type: 'drug', label: 'semaglutide' }} />);
    // Initial Neighborhood load fires traverse with no link filter (linkTypes undefined).
    await waitFor(() => expect(traverse).toHaveBeenCalled());
    expect(traverse).toHaveBeenLastCalledWith('drug', 'sema', expect.any(Number), { linkTypes: undefined });
    traverse.mockClear();
    // Clicking the Competitive lens must re-traverse with its real link_types — the
    // guarantee the old decorative objective pills never had.
    fireEvent.click(screen.getByRole('button', { name: 'Competitive' }));
    await waitFor(() =>
      expect(traverse).toHaveBeenCalledWith('drug', 'sema', expect.any(Number), { linkTypes: ['COMPETES_WITH'] }),
    );
  });
});
