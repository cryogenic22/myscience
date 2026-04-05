import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import ChatMessage, { type Message } from '../ChatMessage';

// Mock framer-motion to render plain divs
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => {
      const { initial, animate, transition, ...rest } = props;
      return <div {...rest}>{children}</div>;
    },
  },
}));

// Mock api module
vi.mock('../../api', () => ({
  api: {
    exportReport: vi.fn(),
  },
}));

// Mock child components that are not under test
vi.mock('../EntityCard', () => ({ default: () => <div data-testid="entity-card" /> }));
vi.mock('../MetricCard', () => ({ default: () => <div data-testid="metric-card" /> }));
vi.mock('../EvidenceCard', () => ({ default: () => <div data-testid="evidence-card" /> }));
vi.mock('../GraphMini', () => ({ default: () => <div data-testid="graph-mini" /> }));

// Mock recharts to avoid rendering canvas/SVG in jsdom
vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  BarChart: () => <div data-testid="bar-chart" />,
  Bar: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  Legend: () => null,
  PieChart: () => <div data-testid="pie-chart" />,
  Pie: () => null,
  Cell: () => null,
}));

function makeMessage(overrides: Partial<Message> = {}): Message {
  return {
    id: 'msg-1',
    role: 'user',
    content: 'Hello world',
    timestamp: new Date('2026-03-28T12:00:00Z'),
    ...overrides,
  };
}

describe('ChatMessage', () => {
  it('renders user message with content', () => {
    const msg = makeMessage({ role: 'user', content: 'What drugs target EGFR?' });
    render(<ChatMessage message={msg} />);
    expect(screen.getByText('What drugs target EGFR?')).toBeInTheDocument();
  });

  it('renders assistant message with narrative', () => {
    const msg = makeMessage({
      role: 'assistant',
      content: 'Erlotinib and gefitinib are two well-known EGFR inhibitors.',
    });
    render(<ChatMessage message={msg} />);
    expect(screen.getByText(/Erlotinib and gefitinib/)).toBeInTheDocument();
  });

  it('renders loading state', () => {
    const msg = makeMessage({ role: 'assistant', content: '', loading: true });
    render(<ChatMessage message={msg} />);
    expect(screen.getByText('Analyzing knowledge graph...')).toBeInTheDocument();
  });

  it('renders citation markers', () => {
    const msg = makeMessage({
      role: 'assistant',
      content: 'EGFR inhibitors show efficacy [1] across multiple indications [2].',
      data: {
        question: 'test',
        evidence: [
          { source: 'pubmed', entity_type: 'literature', entity_id: 'e1', content: 'Study about EGFR', relevance: 0.9, provenance: {} },
          { source: 'clinical_trials_gov', entity_type: 'trial', entity_id: 'e2', content: 'Trial data for EGFR', relevance: 0.85, provenance: {} },
        ],
        graph_context: { nodes: [], edges: [], node_count: 0, edge_count: 0 },
        metrics_context: {},
        entity_focus: [],
        provenance_summary: {},
      },
    });
    render(<ChatMessage message={msg} />);
    expect(screen.getByText('[1]')).toBeInTheDocument();
    expect(screen.getByText('[2]')).toBeInTheDocument();
  });
});
