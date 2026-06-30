import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import CanvasPanel from '../canvas/CanvasPanel';
import type { QueryResponse, TableData, VisualizationSpec, PersonaAnalysis } from '../../api';

// Mock framer-motion to render plain divs
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => {
      const { initial, animate, transition, ...rest } = props;
      return <div {...rest}>{children}</div>;
    },
  },
  AnimatePresence: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));

// Mock recharts
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

// Mock DataTable sub-component
vi.mock('../ui/DataTable', () => ({
  DataTable: ({ rows }: { rows: unknown[] }) => (
    <table data-testid="data-table">
      <tbody>
        {(rows as Record<string, unknown>[]).map((r, i) => (
          <tr key={i}>
            <td>{String(r.name ?? '')}</td>
          </tr>
        ))}
      </tbody>
    </table>
  ),
}));

function makeTableData(overrides: Partial<TableData> = {}): TableData {
  return {
    title: 'Test Table',
    columns: [
      { key: 'name', label: 'Name', type: 'text' },
      { key: 'score', label: 'Score', type: 'number' },
    ],
    rows: [
      { name: 'Erlotinib', score: 85 },
      { name: 'Gefitinib', score: 72 },
    ],
    ...overrides,
  };
}

function makeViz(): VisualizationSpec[] {
  return [{
    id: 'viz-1',
    type: 'bar',
    title: 'Pipeline Strength',
    data: [{ label: 'Phase I', value: 10 }, { label: 'Phase II', value: 5 }],
  }];
}

function makeQueryResponse(overrides: Partial<QueryResponse> = {}): QueryResponse {
  return {
    question: 'test query',
    narrative: 'Test narrative',
    evidence: [
      { source: 'pubmed', entity_type: 'literature', entity_id: 'e1', content: 'Evidence text', relevance: 0.9, provenance: {} },
    ],
    graph_context: { nodes: [], edges: [], node_count: 0, edge_count: 0 },
    metrics_context: {},
    entity_focus: [
      { entity_id: 'drug-1', entity_type: 'drug', title: 'Semaglutide', total_connections: 42 },
      { entity_id: 'drug-2', entity_type: 'drug', title: 'Tirzepatide', total_connections: 28 },
    ],
    provenance_summary: {},
    ...overrides,
  } as QueryResponse;
}

describe('CanvasPanel', () => {
  it('renders tab buttons when content is available', () => {
    render(
      <CanvasPanel
        intent="landscape"
        data={makeQueryResponse()}
        tableData={makeTableData()}
        visualizations={makeViz()}
        confidence={0.85}
        loading={false}
      />
    );
    expect(screen.getByText('Summary')).toBeInTheDocument();
    // "Data" appears as both tab button and section label, so use getAllByText
    expect(screen.getAllByText('Data').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Entities')).toBeInTheDocument();
  });

  it('shows empty state when no content is provided', () => {
    render(
      <CanvasPanel
        intent={null}
        data={null}
        tableData={null}
        visualizations={null}
        loading={false}
      />
    );
    expect(screen.getByText('Data Canvas')).toBeInTheDocument();
    expect(screen.getByText(/Tables, charts, and entities will appear here/)).toBeInTheDocument();
  });

  it('shows loading skeleton when loading=true', () => {
    const { container } = render(
      <CanvasPanel
        intent="landscape"
        data={null}
        tableData={null}
        visualizations={null}
        loading={true}
      />
    );
    // Loading state renders animated skeleton bars
    const skeletons = container.querySelectorAll('[style*="pulse-dot"]');
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('renders entity list in summary tab when entities data provided', () => {
    render(
      <CanvasPanel
        intent="dossier"
        data={makeQueryResponse()}
        tableData={null}
        visualizations={null}
        loading={false}
      />
    );
    expect(screen.getByText('Semaglutide')).toBeInTheDocument();
    expect(screen.getByText('Tirzepatide')).toBeInTheDocument();
  });

  it('renders evidence without crashing when entity_type / relevance are missing', () => {
    // Evidence is assembled from mixed db/web sources; a malformed item (no
    // entity_type, no relevance) must not throw — the only ErrorBoundary is at
    // the app root, so a throw here would unmount the whole page.
    const data = makeQueryResponse({
      entity_focus: [],
      evidence: [
        // no entity_type; null relevance (must NOT render a fabricated "0%")
        { source: 'web', entity_id: 'x', content: 'partial web evidence', relevance: null, provenance: {} },
      ] as unknown as QueryResponse['evidence'],
    });
    render(
      <CanvasPanel
        intent="landscape"
        data={data}
        tableData={null}
        visualizations={null}
        loading={false}
      />
    );
    // Navigate to the Entities tab (visible because there is evidence) — this
    // mounts EvidenceSection, which renders ev.entity_type / ev.relevance.
    fireEvent.click(screen.getByText('Entities'));
    expect(screen.getByText('partial web evidence')).toBeInTheDocument();
    // null relevance must be omitted, not coerced to a fabricated 0%
    expect(screen.queryByText('0%')).not.toBeInTheDocument();
  });

  it('renders confidence badge', () => {
    render(
      <CanvasPanel
        intent="landscape"
        data={makeQueryResponse()}
        tableData={makeTableData()}
        visualizations={null}
        confidence={0.85}
        loading={false}
      />
    );
    expect(screen.getByText('85% confidence')).toBeInTheDocument();
  });

  it('renders intent label in header', () => {
    render(
      <CanvasPanel
        intent="landscape"
        data={makeQueryResponse()}
        tableData={makeTableData()}
        visualizations={null}
        loading={false}
      />
    );
    expect(screen.getByText('Competitive Landscape')).toBeInTheDocument();
  });

  it('renders context tab with persona analyses', () => {
    const personas: PersonaAnalysis[] = [
      {
        persona: 'analyst',
        display_name: 'Market Analyst',
        analysis: 'Test narrative',
        confidence: 0.82,
        key_findings: ['Strong pipeline', 'Growing market share'],
        data_gaps: [],
      },
    ];
    render(
      <CanvasPanel
        intent="landscape"
        data={makeQueryResponse()}
        tableData={makeTableData()}
        visualizations={null}
        loading={false}
        personaAnalyses={personas}
      />
    );
    // Context tab should be visible
    expect(screen.getByText('Context')).toBeInTheDocument();
  });

  it('renders the decomposition matrix when data carries one', () => {
    const data = makeQueryResponse({
      decomposition_matrix: {
        playbook_id: 'glp1',
        intent: 'compare',
        entities: [
          { entity_id: 'sema', entity_type: 'drug', label: 'Semaglutide' },
          { entity_id: 'tirz', entity_type: 'drug', label: 'Tirzepatide' },
        ],
        dimensions: [
          { key: 'efficacy', label: 'Efficacy', sub_question: 'How effective?', routes: [], required: true, weight: 0.8 },
        ],
        cells: [
          { dimension: 'efficacy', entity_id: 'sema', sub_question: 'How effective?', coverage: 'covered',
            facts: [{ id: 'f1', predicate: 'clinical_trial', claim: 'STEP 1: 14.9%', fact_class: 'corporate', source_label: 'fact_emitter', source_url: null, confidence: 0.9 }],
            routes_executed: [], routes_skipped: [] },
          { dimension: 'efficacy', entity_id: 'tirz', sub_question: 'How effective?', coverage: 'gap',
            facts: [], routes_executed: [], routes_skipped: [] },
        ],
        coverage_summary: { efficacy: 'covered' },
        gaps: ['efficacy'],
        synthesis: {},
      },
    });
    render(
      <CanvasPanel intent="compare" data={data} tableData={null} visualizations={null} loading={false} />
    );
    expect(screen.getByTestId('decomposition-matrix')).toBeInTheDocument();
    expect(screen.getByText(/STEP 1: 14.9%/)).toBeInTheDocument();
    expect(screen.getByText(/gap — no facts in KB/i)).toBeInTheDocument();
  });

  it('surfaces metric provenance caption when rows carry _provenance', () => {
    const tableData = makeTableData({
      rows: [
        { name: 'Semaglutide', score: 85, _provenance: { source: 'mv_drug_pipeline_strength', derivation: 'phase-weighted', computed_at: '2026-06-01T00:00:00Z', record_basis: 12, realtime_fallback: false } },
      ],
    });
    render(
      <CanvasPanel intent="pipeline" data={makeQueryResponse()} tableData={tableData} visualizations={null} loading={false} />
    );
    const caps = screen.getAllByTestId('provenance-caption');
    expect(caps.length).toBeGreaterThan(0);
    expect(caps[0].textContent).toMatch(/as of/i);
    expect(caps[0].textContent).toMatch(/2026-06-01/);
  });
});
