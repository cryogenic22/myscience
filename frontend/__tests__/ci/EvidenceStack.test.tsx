/**
 * Loop #19 — EvidenceStack rich card rendering.
 *
 * Replaces opaque doc_id hex strings with source name + tier + date + snippet.
 * EvidenceStack now accepts an optional `documents` prop with rich metadata
 * and falls back to id-only rendering when documents are unresolved.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import EvidenceStack from '../../src/components/ci/EvidenceStack';
import type { Signal } from '../../src/api';
import type { EvidenceDocument } from '../../src/types/evidence';

const BASE_SIGNAL: Signal = {
  id: 's-1',
  event_id: 'e-1',
  kbq_tags: ['clinical'],
  headline: 'Phase 3 readout positive',
  summary: 'Met primary endpoint with p<0.001.',
  direction: 'positive',
  confidence_tier: 'confirmed',
  trust_score: 0.95,
  impact_tier: 'high',
  impact_score: 9.1,
  rule_version_id: 'v1',
  primary_entity_type: 'drug',
  primary_entity_id: 'drug-1',
  primary_entity_name: 'Drug X',
  related_entity_ids: [],
  evidence_document_ids: [
    '11111111-1111-1111-1111-111111111111',
    '22222222-2222-2222-2222-222222222222',
  ],
  status: 'shipped',
  superseded_by: null,
  supersedence_reason: null,
  created_at: '2026-05-09T12:00:00Z',
  reviewed_by: null,
  reviewed_at: null,
  shipped_at: '2026-05-09T13:00:00Z',
};

const DOCS: EvidenceDocument[] = [
  {
    evidence_id: '11111111-1111-1111-1111-111111111111',
    source_id: 'clinicaltrials.gov',
    source_url: 'https://clinicaltrials.gov/study/NCT0123',
    source_tier: 'tier_1',
    retrieved_at: '2026-05-09T10:00:00Z',
    snippet:
      'The trial met its primary endpoint with a statistically significant reduction in major adverse cardiovascular events.',
    confidence: 0.95,
  },
  {
    evidence_id: '22222222-2222-2222-2222-222222222222',
    source_id: 'pubmed',
    source_url: 'https://pubmed.ncbi.nlm.nih.gov/12345',
    source_tier: 'tier_1',
    retrieved_at: '2026-05-08T08:00:00Z',
    snippet: 'Peer-reviewed analysis confirms the primary endpoint result.',
    confidence: 0.92,
  },
];

describe('EvidenceStack (Loop #19 — rich cards)', () => {
  it('renders empty state when no evidence ids', () => {
    const s = { ...BASE_SIGNAL, evidence_document_ids: [] };
    render(<EvidenceStack signal={s} />);
    expect(screen.getByText(/no evidence documents linked/i)).toBeDefined();
  });

  it('falls back to id-only chips when no documents prop is provided', () => {
    const { container } = render(<EvidenceStack signal={BASE_SIGNAL} />);
    // Two unresolved cards rendered
    const unresolved = container.querySelectorAll('[data-evidence-card="unresolved"]');
    expect(unresolved.length).toBe(2);
  });

  it('renders source name when documents are provided', () => {
    render(<EvidenceStack signal={BASE_SIGNAL} documents={DOCS} />);
    expect(screen.getByText(/clinicaltrials\.gov/i)).toBeDefined();
    expect(screen.getByText(/pubmed/i)).toBeDefined();
  });

  it('renders the source tier as a visible badge', () => {
    const { container } = render(<EvidenceStack signal={BASE_SIGNAL} documents={DOCS} />);
    const tierBadges = container.querySelectorAll('[data-tier]');
    expect(tierBadges.length).toBe(2);
    expect(tierBadges[0]?.getAttribute('data-tier')).toBe('tier_1');
  });

  it('renders a retrieval date (human-formatted)', () => {
    render(<EvidenceStack signal={BASE_SIGNAL} documents={DOCS} />);
    // Either ISO date fragment or a human-readable form; assert the year shows.
    const matches = screen.getAllByText(/2026/);
    expect(matches.length).toBeGreaterThan(0);
  });

  it('renders the snippet text (truncated or full)', () => {
    render(<EvidenceStack signal={BASE_SIGNAL} documents={DOCS} />);
    expect(screen.getByText(/met its primary endpoint/i)).toBeDefined();
    expect(screen.getByText(/peer-reviewed analysis confirms/i)).toBeDefined();
  });

  it('renders the source URL as an anchor (when present)', () => {
    const { container } = render(<EvidenceStack signal={BASE_SIGNAL} documents={DOCS} />);
    const anchors = container.querySelectorAll('a[href]');
    const hrefs = Array.from(anchors).map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('https://clinicaltrials.gov/study/NCT0123');
    expect(hrefs).toContain('https://pubmed.ncbi.nlm.nih.gov/12345');
  });

  it('renders one resolved card per matched document and one unresolved card per unmatched id', () => {
    const partial = [DOCS[0]]; // only first id resolves
    const { container } = render(
      <EvidenceStack signal={BASE_SIGNAL} documents={partial} />,
    );
    const resolved = container.querySelectorAll('[data-evidence-card="resolved"]');
    const unresolved = container.querySelectorAll('[data-evidence-card="unresolved"]');
    expect(resolved.length).toBe(1);
    expect(unresolved.length).toBe(1);
  });
});
