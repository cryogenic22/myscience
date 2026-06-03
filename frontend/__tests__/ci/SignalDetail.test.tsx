/**
 * PB-IX01 — SignalDetail promote bridge tests.
 *
 * The signal detail panel is the "action menu" for a signal: it already had
 * Frame-as-Decision + Simulate-in-War-Room; IX01 adds the dossier + engagement
 * seed links (URL-driven, like the existing "View dossier" link).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';

vi.mock('../../src/api', () => ({
  signalsApi: { review: vi.fn() },
  warRoomApi: { create: vi.fn() },
}));
vi.mock('../../src/hooks/useEvidenceDocuments', () => ({
  useEvidenceDocuments: () => ({ documents: [], loading: false }),
}));
vi.mock('../../src/hooks/useFrameSignal', () => ({
  useFrameSignal: () => ({ frame: vi.fn(), framingId: null, error: null }),
}));

import SignalDetail from '../../src/components/ci/SignalDetail';
import type { Signal } from '../../src/api';

function makeSignal(over: Partial<Signal> = {}): Signal {
  return {
    id: 'sig-1', event_id: null, kbq_tags: ['clinical'],
    headline: 'FDA expands the obesity label', summary: 'Label now includes CV risk reduction.',
    direction: 'positive', confidence_tier: 'confirmed', trust_score: 0.9,
    impact_tier: 'high', impact_score: 0.8, rule_version_id: null,
    primary_entity_type: 'drug', primary_entity_id: 'drug-uuid-1',
    primary_entity_name: 'Semaglutide', related_entity_ids: [],
    evidence_document_ids: [], materiality_factors: null, status: 'shipped',
    superseded_by: null, supersedence_reason: null, created_at: '2026-05-20T00:00:00Z',
    reviewed_by: null, reviewed_at: null, shipped_at: null,
    ...over,
  };
}

describe('SignalDetail — promote bridge (PB-IX01)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('renders Build dossier + Start engagement links seeded with the entity', () => {
    render(<SignalDetail signal={makeSignal()} />);
    const promote = screen.getByTestId('signal-promote');
    expect(promote).toBeInTheDocument();

    const dossier = screen.getByTestId('promote-dossier') as HTMLAnchorElement;
    expect(dossier.getAttribute('href')).toBe(
      '/ci?tab=dossier&asset=drug%3Adrug-uuid-1',
    );

    const engagement = screen.getByTestId('promote-engagement') as HTMLAnchorElement;
    const href = engagement.getAttribute('href') || '';
    expect(href).toContain('/ci?tab=engagements&new=1');
    expect(href).toContain('asset=drug%3Adrug-uuid-1');
    expect(href).toContain('seedName=');
    expect(href).toContain('seedContext=');
    // PB-IX01 provenance — the engagement promote carries the originating signal id.
    expect(href).toContain('seedSignalId=sig-1');
  });

  it('hides the promote bridge for market-wide signals (no entity)', () => {
    render(<SignalDetail signal={makeSignal({ primary_entity_id: 'market', primary_entity_type: null })} />);
    expect(screen.queryByTestId('signal-promote')).not.toBeInTheDocument();
  });
});
