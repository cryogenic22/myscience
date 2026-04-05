import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import KnowledgeGraph from '../KnowledgeGraph';
import type { GraphNode, GraphEdge } from '../../api';

const sampleNodes: GraphNode[] = [
  { entity_id: 'drug-1', entity_type: 'drug', label: 'Erlotinib', properties: {} },
  { entity_id: 'comp-1', entity_type: 'company', label: 'Roche', properties: {} },
];

const sampleEdges: GraphEdge[] = [
  { source_id: 'drug-1', target_id: 'comp-1', link_type: 'OWNS', confidence: 0.95, via: 'fda' },
];

describe('KnowledgeGraph', () => {
  it('renders canvas element', () => {
    const { container } = render(
      <KnowledgeGraph nodes={sampleNodes} edges={sampleEdges} height={400} />
    );
    const canvas = container.querySelector('canvas');
    expect(canvas).toBeInTheDocument();
  });

  it('renders with compact mode (no legend)', () => {
    const { container } = render(
      <KnowledgeGraph nodes={sampleNodes} edges={sampleEdges} height={300} compact={true} />
    );
    const canvas = container.querySelector('canvas');
    expect(canvas).toBeInTheDocument();
    // In compact mode the edge category legend should not be rendered
    // The legend renders category labels like "Ownership", "Research", etc.
    expect(screen.queryByText('Ownership')).toBeNull();
    expect(screen.queryByText('Research')).toBeNull();
  });
});
