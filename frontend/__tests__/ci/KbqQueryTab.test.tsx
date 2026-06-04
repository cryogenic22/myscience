/**
 * PB-SL10 — KBQ query surface tests.
 *
 * Type an asset → the 8 KBQs answered (parity), each item drillable to its
 * signal → fact → evidence provenance. The KbqDossier renderer + the signal
 * detail call are exercised through the public api client (mocked).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../src/api', () => ({
  kbqApi: { byAsset: vi.fn() },
  signalsApi: { detail: vi.fn() },
}));

import { kbqApi, signalsApi } from '../../src/api';
import KbqQueryTab from '../../src/components/ci/KbqQueryTab';

function kbqs(asset = 'semaglutide') {
  return {
    entity: { type: 'drug', id: 'drug-uuid-1', name: 'Semaglutide' },
    completeness: 0.25,
    asset,
    kbqs: [
      { kbq: 1, title: 'Indications', status: 'fresh', items: [
        { claim: 'Approved for obesity', signal_id: 'sig-1', evidence_ids: ['e1'], impact_tier: 'high', confidence_tier: 'confirmed', date: '2026-05-01T00:00:00Z' },
      ]},
      { kbq: 2, title: 'Competitors', status: 'insufficient', items: [] },
      { kbq: 3, title: 'Clinical', status: 'insufficient', items: [] },
      { kbq: 4, title: 'Positioning', status: 'insufficient', items: [] },
      { kbq: 5, title: 'Sales & Sentiment', status: 'insufficient', items: [] },
      { kbq: 6, title: 'SWOT', status: 'insufficient', items: [] },
      { kbq: 7, title: 'Pricing', status: 'insufficient', items: [] },
      { kbq: 8, title: 'Access', status: 'insufficient', items: [] },
    ],
  };
}

function signalDetail() {
  return {
    id: 'sig-1', headline: 'Approved for obesity', summary: 'FDA approval.',
    confidence_tier: 'confirmed', impact_tier: 'high', kbq_tags: [],
    linked_facts: [
      { role: 'feeds', fact_id: 'f1', predicate: 'label_indication', fact_class: 'corporate', claim: 'Indicated for chronic weight management', confidence: 0.9, source_id: 'fda', source_url: 'https://x' },
    ],
  };
}

describe('KbqQueryTab (PB-SL10)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('asks the KBQs for the entered asset and renders all 8 with parity', async () => {
    (kbqApi.byAsset as any).mockResolvedValue(kbqs());
    render(<KbqQueryTab />);
    fireEvent.change(screen.getByTestId('kbq-asset-input'), { target: { value: 'semaglutide' } });
    fireEvent.click(screen.getByTestId('kbq-ask'));
    await waitFor(() => expect(screen.getByTestId('kbq-ready')).toBeInTheDocument());
    expect(kbqApi.byAsset).toHaveBeenCalledWith('semaglutide');
    expect(screen.getByRole('heading', { name: /semaglutide/i })).toBeDefined();
    expect(document.querySelectorAll('[data-kbq]').length).toBe(8);
  });

  it('opens the provenance drawer with linked facts when an item is clicked', async () => {
    (kbqApi.byAsset as any).mockResolvedValue(kbqs());
    (signalsApi.detail as any).mockResolvedValue(signalDetail());
    render(<KbqQueryTab />);
    fireEvent.change(screen.getByTestId('kbq-asset-input'), { target: { value: 'semaglutide' } });
    fireEvent.click(screen.getByTestId('kbq-ask'));
    await waitFor(() => expect(screen.getByTestId('kbq-ready')).toBeInTheDocument());
    fireEvent.click(screen.getByText(/Approved for obesity/i));
    await waitFor(() => expect(signalsApi.detail).toHaveBeenCalledWith('sig-1'));
    await waitFor(() =>
      expect(screen.getByText(/Indicated for chronic weight management/i)).toBeInTheDocument(),
    );
    expect(screen.getByText(/Feeds 1 fact/i)).toBeInTheDocument();
  });

  it('shows an error when the query fails', async () => {
    (kbqApi.byAsset as any).mockRejectedValue(new Error('500: boom'));
    render(<KbqQueryTab />);
    fireEvent.change(screen.getByTestId('kbq-asset-input'), { target: { value: 'x' } });
    fireEvent.click(screen.getByTestId('kbq-ask'));
    await waitFor(() => expect(screen.getByTestId('kbq-error')).toBeInTheDocument());
  });
});
