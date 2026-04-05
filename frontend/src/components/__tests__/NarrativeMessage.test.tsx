import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import NarrativeMessage from '../chat/NarrativeMessage';
import type { Message } from '../ChatMessage';
import type { EvidenceItem, GraphNode, GraphEdge } from '../../api';

// Framer-motion minimal mock — renders children without animation
vi.mock('framer-motion', () => ({
  motion: {
    div: ({ children, ...props }: React.PropsWithChildren<Record<string, unknown>>) => {
      const { initial, animate, transition, ...domProps } = props;
      void initial; void animate; void transition;
      return <div {...domProps}>{children}</div>;
    },
  },
}));

function makeMessage(content: string, evidence?: EvidenceItem[]): Message {
  return {
    id: 'msg-1',
    role: 'assistant',
    content,
    timestamp: new Date(),
    data: evidence ? { evidence } as Message['data'] : undefined,
  };
}

const pubmedEvidence: EvidenceItem = {
  source: 'search',
  entity_type: 'literature',
  entity_id: 'lit-001',
  content: 'Aspirin significantly reduces cardiovascular events in high-risk patients according to meta-analysis.',
  relevance: 0.92,
  provenance: { source_api: 'pubmed', source_url: 'https://pubmed.ncbi.nlm.nih.gov/12345678' },
};

const fdaEvidence: EvidenceItem = {
  source: 'search',
  entity_type: 'drug',
  entity_id: 'drug-002',
  content: 'FDA approved atorvastatin for primary prevention of cardiovascular disease.',
  relevance: 0.65,
  provenance: { source_api: 'fda_orange_book' },
};

const lowConfidenceEvidence: EvidenceItem = {
  source: 'search',
  entity_type: 'trial',
  entity_id: 'trial-003',
  content: 'Phase 2 trial showed marginal improvement in endpoint.',
  relevance: 0.35,
  provenance: { source_api: 'clinical_trials_gov' },
};

describe('NarrativeMessage citation chips', () => {
  it('renders citation chips for [1] [2] markers with evidence', () => {
    const msg = makeMessage(
      'Aspirin reduces risk [1] and statins help prevention [2].',
      [pubmedEvidence, fdaEvidence],
    );
    render(<NarrativeMessage message={msg} isUser={false} />);

    const chip1 = screen.getByTestId('citation-chip-1');
    const chip2 = screen.getByTestId('citation-chip-2');
    expect(chip1).toBeInTheDocument();
    expect(chip2).toBeInTheDocument();
  });

  it('shows correct source icon for PubMed evidence', () => {
    const msg = makeMessage('Study found benefit [1].', [pubmedEvidence]);
    render(<NarrativeMessage message={msg} isUser={false} />);

    // The icon wrapper should exist — Flask icon for pubmed
    const iconEl = screen.getByTestId('citation-icon-1');
    expect(iconEl).toBeInTheDocument();
    // Lucide renders an SVG inside
    const svg = iconEl.querySelector('svg');
    expect(svg).toBeTruthy();
  });

  it('shows green confidence dot for high-relevance evidence', () => {
    const msg = makeMessage('Result [1].', [pubmedEvidence]); // relevance 0.92
    render(<NarrativeMessage message={msg} isUser={false} />);

    const dot = screen.getByTestId('citation-dot-1');
    expect(dot.style.background).toBe('rgb(34, 197, 94)'); // #22c55e
  });

  it('shows amber confidence dot for mid-relevance evidence', () => {
    const msg = makeMessage('FDA approved [1].', [fdaEvidence]); // relevance 0.65
    render(<NarrativeMessage message={msg} isUser={false} />);

    const dot = screen.getByTestId('citation-dot-1');
    expect(dot.style.background).toBe('rgb(245, 158, 11)'); // #f59e0b
  });

  it('shows red confidence dot for low-relevance evidence', () => {
    const msg = makeMessage('Trial showed [1].', [lowConfidenceEvidence]); // relevance 0.35
    render(<NarrativeMessage message={msg} isUser={false} />);

    const dot = screen.getByTestId('citation-dot-1');
    expect(dot.style.background).toBe('rgb(239, 68, 68)'); // #ef4444
  });

  it('clicking chip toggles evidence card visibility', () => {
    const msg = makeMessage('Aspirin works [1].', [pubmedEvidence]);
    render(<NarrativeMessage message={msg} isUser={false} />);

    // Evidence card should not be visible initially
    expect(screen.queryByTestId('citation-evidence-1')).toBeNull();

    // Click the chip
    const chip = screen.getByTestId('citation-chip-1');
    const button = chip.querySelector('[role="button"]')!;
    fireEvent.click(button);

    // Evidence card should now be visible
    const card = screen.getByTestId('citation-evidence-1');
    expect(card).toBeInTheDocument();
    expect(card.textContent).toContain('Aspirin significantly reduces');
    expect(card.textContent).toContain('92% relevant');

    // Click again to collapse
    fireEvent.click(button);
    expect(screen.queryByTestId('citation-evidence-1')).toBeNull();
  });

  it('renders plain text fallback when no evidence data provided', () => {
    const msg = makeMessage('Claim without evidence [1] and another [2].');
    render(<NarrativeMessage message={msg} isUser={false} />);

    // Should still render chips (as plain superscript fallback)
    const chip1 = screen.getByTestId('citation-chip-1');
    expect(chip1).toBeInTheDocument();
    expect(chip1.textContent).toContain('[1]');

    // No icon or dot since there is no evidence
    expect(screen.queryByTestId('citation-icon-1')).toBeNull();
    expect(screen.queryByTestId('citation-dot-1')).toBeNull();
  });

  it('renders user messages as plain text without citation processing', () => {
    const msg = makeMessage('What about [1]?');
    msg.role = 'user';
    render(<NarrativeMessage message={msg} isUser={true} />);

    // User messages render raw content, not parsed
    expect(screen.queryByTestId('citation-chip-1')).toBeNull();
    expect(screen.getByText('What about [1]?')).toBeInTheDocument();
  });

  it('shows source URL in expanded evidence card when available', () => {
    const msg = makeMessage('Study [1].', [pubmedEvidence]);
    render(<NarrativeMessage message={msg} isUser={false} />);

    // Expand
    const chip = screen.getByTestId('citation-chip-1');
    const button = chip.querySelector('[role="button"]')!;
    fireEvent.click(button);

    const card = screen.getByTestId('citation-evidence-1');
    const link = card.querySelector('a');
    expect(link).toBeTruthy();
    expect(link!.href).toContain('pubmed.ncbi.nlm.nih.gov');
  });
});

/* ── View in Graph button ── */

const sampleNodes: GraphNode[] = [
  { entity_id: 'drug-1', entity_type: 'drug', label: 'semaglutide', properties: {} },
  { entity_id: 'company-1', entity_type: 'company', label: 'Novo Nordisk', properties: {} },
];

const sampleEdges: GraphEdge[] = [
  { source_id: 'drug-1', target_id: 'company-1', link_type: 'MANUFACTURED_BY', confidence: 0.95, via: 'pipeline' },
];

function makeGraphMessage(hasGraph: boolean): Message {
  return {
    id: 'msg-graph',
    role: 'assistant',
    content: 'Semaglutide is manufactured by Novo Nordisk.',
    timestamp: new Date(),
    data: {
      question: 'test',
      evidence: [],
      graph_context: hasGraph
        ? { nodes: sampleNodes, edges: sampleEdges, node_count: 2, edge_count: 1 }
        : { nodes: [], edges: [], node_count: 0, edge_count: 0 },
      metrics_context: {},
      entity_focus: [],
      provenance_summary: {},
    },
  };
}

describe('NarrativeMessage "View in Graph" button', () => {
  it('renders "View in Graph" button when graph_context has nodes', () => {
    const msg = makeGraphMessage(true);
    const onViewInGraph = vi.fn();
    render(<NarrativeMessage message={msg} isUser={false} onViewInGraph={onViewInGraph} />);

    const btn = screen.getByTestId('view-in-graph-btn');
    expect(btn).toBeInTheDocument();
    expect(btn.textContent).toContain('View in Graph');
  });

  it('does not show button when graph_context has no nodes', () => {
    const msg = makeGraphMessage(false);
    const onViewInGraph = vi.fn();
    render(<NarrativeMessage message={msg} isUser={false} onViewInGraph={onViewInGraph} />);

    expect(screen.queryByTestId('view-in-graph-btn')).toBeNull();
  });

  it('does not show button when no onViewInGraph callback provided', () => {
    const msg = makeGraphMessage(true);
    render(<NarrativeMessage message={msg} isUser={false} />);

    expect(screen.queryByTestId('view-in-graph-btn')).toBeNull();
  });

  it('does not show button when message has no data', () => {
    const msg: Message = {
      id: 'msg-no-data',
      role: 'assistant',
      content: 'A plain response.',
      timestamp: new Date(),
    };
    const onViewInGraph = vi.fn();
    render(<NarrativeMessage message={msg} isUser={false} onViewInGraph={onViewInGraph} />);

    expect(screen.queryByTestId('view-in-graph-btn')).toBeNull();
  });

  it('calls onViewInGraph with correct nodes and edges when clicked', () => {
    const msg = makeGraphMessage(true);
    const onViewInGraph = vi.fn();
    render(<NarrativeMessage message={msg} isUser={false} onViewInGraph={onViewInGraph} />);

    const btn = screen.getByTestId('view-in-graph-btn');
    fireEvent.click(btn);

    expect(onViewInGraph).toHaveBeenCalledTimes(1);
    expect(onViewInGraph).toHaveBeenCalledWith(sampleNodes, sampleEdges);
  });

  it('does not show button for user messages', () => {
    const msg = makeGraphMessage(true);
    msg.role = 'user';
    const onViewInGraph = vi.fn();
    render(<NarrativeMessage message={msg} isUser={true} onViewInGraph={onViewInGraph} />);

    expect(screen.queryByTestId('view-in-graph-btn')).toBeNull();
  });
});
