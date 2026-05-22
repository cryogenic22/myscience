import { describe, it, expect, vi } from 'vitest';
import { render as rtlRender, screen, waitFor, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { SensingFeed } from '../../src/components/ci/SensingFeed';
import { signalsApi, decisionBriefsApi } from '../../src/api';

vi.mock('../../src/api', () => ({
  signalsApi: { list: vi.fn() },
  decisionBriefsApi: { create: vi.fn() },
}));

// SensingFeed uses useFrameSignal → useNavigate, which needs a Router.
const render = (ui: React.ReactElement) => rtlRender(<MemoryRouter>{ui}</MemoryRouter>);

function sig(over = {}) {
  return {
    id: 's1', event_id: 'e1', kbq_tags: ['clinical'],
    headline: 'Phase 3 readout is positive',
    summary: null, direction: 'positive', confidence_tier: 'confirmed',
    trust_score: 0.9, impact_tier: 'high', impact_score: 0.9,
    rule_version_id: 'v1', primary_entity_type: 'company',
    primary_entity_id: 'co-lilly', primary_entity_name: 'Eli Lilly',
    related_entity_ids: [], evidence_document_ids: ['e1'], status: 'shipped',
    superseded_by: null, supersedence_reason: null,
    created_at: '2026-05-20T00:00:00Z', reviewed_by: null,
    reviewed_at: null, shipped_at: '2026-05-20T01:00:00Z',
    ...over,
  };
}

describe('SensingFeed (Helix reskin)', () => {
  it('renders loading state initially', () => {
    vi.mocked(signalsApi.list).mockImplementation(() => new Promise(() => {}));
    render(<SensingFeed />);
    expect(screen.getByText(/sensing the market/i)).toBeDefined();
  });

  it('renders entity-resolved signals (not SIGNAL: MARKET)', async () => {
    vi.mocked(signalsApi.list).mockResolvedValue({
      signals: [sig()], count: 1, limit: 40, offset: 0,
    });
    render(<SensingFeed />);
    await waitFor(() => {
      expect(screen.getByText('Phase 3 readout is positive')).toBeDefined();
      // real entity name appears, not "MARKET"
      expect(screen.getByText('Eli Lilly')).toBeDefined();
    });
  });

  it('encodes impact as a tier word, not a 1% ring', async () => {
    vi.mocked(signalsApi.list).mockResolvedValue({
      signals: [sig({ impact_tier: 'high' })], count: 1, limit: 40, offset: 0,
    });
    render(<SensingFeed />);
    await waitFor(() => expect(screen.getByText('ACT')).toBeDefined()); // high → ACT
  });

  it('renders the category label from the kbq tag', async () => {
    vi.mocked(signalsApi.list).mockResolvedValue({
      signals: [sig({ kbq_tags: ['pricing_access'] })], count: 1, limit: 40, offset: 0,
    });
    render(<SensingFeed />);
    await waitFor(() => expect(screen.getByText('Pricing & Access')).toBeDefined());
  });

  it('clicking Frame creates a decision brief from the signal (was a dead button)', async () => {
    vi.mocked(signalsApi.list).mockResolvedValue({
      signals: [sig()], count: 1, limit: 40, offset: 0,
    });
    vi.mocked(decisionBriefsApi.create).mockResolvedValue({ brief_id: 'b-1' } as never);
    render(<SensingFeed />);
    const btn = await screen.findByRole('button', { name: /frame/i });
    fireEvent.click(btn);
    await waitFor(() => {
      expect(decisionBriefsApi.create).toHaveBeenCalled();
      const arg = vi.mocked(decisionBriefsApi.create).mock.calls[0][0];
      expect(arg.trigger_signal_ids).toContain('s1');
      expect(arg.question).toMatch(/how should we respond/i);
    });
  });

  it('falls back to "Market" only when entity is the market bucket', async () => {
    vi.mocked(signalsApi.list).mockResolvedValue({
      signals: [sig({ primary_entity_id: 'market', primary_entity_name: null })],
      count: 1, limit: 40, offset: 0,
    });
    render(<SensingFeed />);
    await waitFor(() => expect(screen.getByText('Market')).toBeDefined());
  });
});
