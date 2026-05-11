/**
 * Loop #17 — Helix Bridge MVP regression tests.
 *
 * Verifies the new /bridge surface renders all four critical pieces:
 * sidebar shell, hero strip, three zones (Pulse / Twin / Moments),
 * and the Decision Ledger pin.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import BridgePage from '../../src/pages/BridgePage';
import { ThemeProvider } from '../../src/hooks/useTheme';

// Mock the API hooks so tests don't hit the network.
vi.mock('../../src/api', async () => {
  const actual = await vi.importActual<typeof import('../../src/api')>('../../src/api');
  return {
    ...actual,
    signalsApi: {
      list: vi.fn().mockResolvedValue({
        signals: [
          {
            id: 's1', event_id: 'e1', kbq_tags: ['clinical'],
            headline: 'SURMOUNT-MMO interim hit cardiovascular endpoint',
            summary: 'Tirzepatide reduced MACE 38% vs placebo.',
            direction: 'positive', confidence_tier: 'confirmed', trust_score: 0.95,
            impact_tier: 'high', impact_score: 9.1, rule_version_id: 'v1',
            primary_entity_type: 'company', primary_entity_id: 'lilly',
            primary_entity_name: 'Eli Lilly', related_entity_ids: [],
            evidence_document_ids: [], status: 'shipped', superseded_by: null,
            supersedence_reason: null, created_at: '2026-05-09T12:00:00Z',
            reviewed_by: null, reviewed_at: null, shipped_at: '2026-05-09T13:00:00Z',
          },
        ],
        count: 1, limit: 100, offset: 0,
      }),
      detail: vi.fn(),
      review: vi.fn(),
    },
    decisionBriefsApi: {
      list: vi.fn().mockResolvedValue({ briefs: [], count: 0 }),
    },
    bridgeApi: {
      moments: vi.fn().mockResolvedValue({
        moments: [
          {
            id: 'm1', priority: 1, ev_at_stake_musd: 340, expires_hours: 72,
            title: 'Lilly orforglipron acceleration changes your pricing posture',
            summary: 'Three signals jointly raise P(Lilly launches oral GLP-1 by Q1 27) from 18% to 41%.',
            delta_belief: { from: 0.18, to: 0.41, label: "P(Lilly oral by Q1 '27)" },
            signal_chain: ['s1'], category: 'strategic',
            plays: [
              { id: 'p1a', label: 'Defend with semaglutide oral acceleration', ev: 380, ev_var: 90, prob_success: 0.62, kind: 'aggressive' },
              { id: 'p1b', label: 'Pivot pricing to capture share before launch', ev: 210, ev_var: 50, prob_success: 0.74, kind: 'balanced' },
              { id: 'p1c', label: 'Hold and differentiate on CV outcomes', ev: 140, ev_var: 40, prob_success: 0.81, kind: 'cautious' },
            ],
          },
        ],
      }),
    },
  };
});

function renderAt(path: string) {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/bridge" element={<BridgePage />} />
        </Routes>
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('BridgePage (Loop #17 — Helix Bridge MVP)', () => {
  beforeEach(() => {
    window.localStorage.setItem('mz_auth_token', 'test-token');
    window.localStorage.setItem('mz_auth_role', 'enterprise');
  });

  it('renders the MarketZero · Helix brand line in the sidebar', async () => {
    renderAt('/bridge');
    expect(screen.getByText(/MarketZero/i)).toBeDefined();
    expect(screen.getByText(/Helix/i)).toBeDefined();
  });

  it('renders the 6 primary navigation items in the sidebar', async () => {
    renderAt('/bridge');
    for (const label of ['Bridge', 'Watchlist', 'KBQ Workspace', 'War Game', 'Knowledge', 'Replay']) {
      expect(screen.getByRole('link', { name: new RegExp(label, 'i') })).toBeDefined();
    }
  });

  it('renders the 2 oversight navigation items in the sidebar', async () => {
    renderAt('/bridge');
    expect(screen.getByRole('link', { name: /reviewer/i })).toBeDefined();
    expect(screen.getByRole('link', { name: /^agents$/i })).toBeDefined();
  });

  it('renders all three Bridge zones (Pulse, Twin, AI Moments)', async () => {
    renderAt('/bridge');
    expect(screen.getByRole('region', { name: /pulse/i })).toBeDefined();
    expect(screen.getByRole('region', { name: /digital twin/i })).toBeDefined();
    expect(screen.getByRole('region', { name: /ai moments/i })).toBeDefined();
  });

  it('shows the bridge-mode toggle (Live / Today / This Week)', async () => {
    renderAt('/bridge');
    expect(screen.getByRole('button', { name: /^live$/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /today/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /this week/i })).toBeDefined();
  });

  it('renders the Decision Ledger pin in the header', async () => {
    renderAt('/bridge');
    expect(screen.getByRole('button', { name: /decisions/i })).toBeDefined();
  });

  it('fetches and renders real signals in the Pulse zone', async () => {
    renderAt('/bridge');
    await waitFor(() => {
      expect(screen.getByText(/SURMOUNT-MMO/i)).toBeDefined();
    });
  });

  it('renders the impact-category filter chips in the Pulse zone', async () => {
    renderAt('/bridge');
    // 10 impact categories + "All"
    expect(screen.getByRole('button', { name: /^all$/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /^financial$/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /^clinical$/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /^regulatory$/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /pricing.*access/i })).toBeDefined();
  });

  it('renders the hero strip with the top moment + EV at stake', async () => {
    renderAt('/bridge');
    await waitFor(() => {
      expect(screen.getByText(/orforglipron/i)).toBeDefined();
    });
    expect(screen.getByText(/MOST URGENT/i)).toBeDefined();
    // $340M appears in both hero strip and moment card — getAllByText asserts ≥1.
    expect(screen.getAllByText(/\$340M/).length).toBeGreaterThan(0);
  });
});
