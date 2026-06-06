import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import ProvenanceCaption, { metricProvenanceCaption, graphEdgeProvenanceCaption } from '../canvas/ProvenanceCaption';
import type { GraphEdge, MetricProvenance } from '../../api';

describe('ProvenanceCaption', () => {
  it('renders source and as-of date', () => {
    render(<ProvenanceCaption source="mv_drug_pipeline_strength" asOf="2026-06-01" />);
    const cap = screen.getByTestId('provenance-caption');
    expect(cap.textContent).toMatch(/mv_drug_pipeline_strength/);
    expect(cap.textContent).toMatch(/as of/i);
    expect(cap.textContent).toMatch(/2026-06-01/);
  });

  it('renders source alone when no date', () => {
    render(<ProvenanceCaption source="entity_links" />);
    expect(screen.getByTestId('provenance-caption').textContent).toMatch(/entity_links/);
  });

  it('surfaces the derivation in the title tooltip', () => {
    render(
      <ProvenanceCaption
        source="mv_evidence_density"
        asOf="2026-06-01"
        derivation="recency-weighted PubMed article count per drug"
      />,
    );
    expect(screen.getByTestId('provenance-caption').getAttribute('title')).toMatch(/recency-weighted/);
  });

  it('renders nothing when there is no source', () => {
    const { container } = render(<ProvenanceCaption source={undefined} />);
    expect(container.firstChild).toBeNull();
  });
});

describe('metricProvenanceCaption', () => {
  it('extracts source/derivation/computed_at from a _provenance block', () => {
    const prov: MetricProvenance = {
      source: 'mv_trial_success_rate',
      derivation: 'completed / (completed + terminated + withdrawn)',
      computed_at: '2026-06-01T12:00:00Z',
      record_basis: 23,
      realtime_fallback: false,
    };
    const c = metricProvenanceCaption(prov)!;
    expect(c.source).toBe('mv_trial_success_rate');
    expect(c.asOf).toBe('2026-06-01T12:00:00Z');
    expect(c.derivation).toMatch(/completed/);
  });

  it('returns null for a row without provenance', () => {
    expect(metricProvenanceCaption(undefined)).toBeNull();
  });
});

describe('graphEdgeProvenanceCaption', () => {
  it('reads provenance_source/as_of off an edge', () => {
    const edge: GraphEdge = {
      source_id: 'a', target_id: 'b', link_type: 'INVESTIGATES', confidence: 0.9, via: 'ctgov',
      provenance_source: 'clinical_trials_gov', as_of: '2026-06-01',
    };
    const c = graphEdgeProvenanceCaption(edge)!;
    expect(c.source).toBe('clinical_trials_gov');
    expect(c.asOf).toBe('2026-06-01');
  });

  it('falls back to edge.source / via when provenance_source is absent', () => {
    const edge: GraphEdge = {
      source_id: 'a', target_id: 'b', link_type: 'OWNS', confidence: 0.8, via: 'sec_edgar',
    };
    expect(graphEdgeProvenanceCaption(edge)?.source).toBe('sec_edgar');
  });

  it('returns null when an edge has no usable provenance', () => {
    const edge: GraphEdge = {
      source_id: 'a', target_id: 'b', link_type: 'OWNS', confidence: 0.8, via: '',
    };
    expect(graphEdgeProvenanceCaption(edge)).toBeNull();
  });
});
