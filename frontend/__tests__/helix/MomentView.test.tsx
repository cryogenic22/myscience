/**
 * Loop #18 — Cinematic Moment overlay tests.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import MomentView from '../../src/components/helix/MomentView';
import { ThemeProvider } from '../../src/hooks/useTheme';
import type { Moment } from '../../src/types/helix';
import type { Signal } from '../../src/api';

const MOMENT: Moment = {
  id: 'm-abc',
  priority: 1,
  ev_at_stake_musd: 340,
  expires_hours: 72,
  title: 'Lilly orforglipron acceleration changes your pricing posture',
  summary: 'Three signals jointly raise P(Lilly launches oral GLP-1 by Q1 27) from 18% to 41%.',
  delta_belief: { from: 0.18, to: 0.41, label: "P(Lilly oral by Q1 '27)" },
  signal_chain: ['s1', 's5'],
  category: 'strategic',
  plays: [
    { id: 'p1', label: 'Defend with semaglutide oral acceleration', ev: 380, ev_var: 90, prob_success: 0.62, kind: 'aggressive' },
    { id: 'p2', label: 'Pivot pricing to capture share before launch', ev: 210, ev_var: 50, prob_success: 0.74, kind: 'balanced' },
    { id: 'p3', label: 'Hold and differentiate on CV outcomes', ev: 140, ev_var: 40, prob_success: 0.81, kind: 'cautious' },
  ],
};

const SIGNALS: Signal[] = [
  {
    id: 's1', event_id: 'e1', kbq_tags: ['clinical'],
    headline: 'SURMOUNT-MMO interim hit CV endpoint',
    summary: 'Tirzepatide reduced MACE 38%.',
    direction: 'positive', confidence_tier: 'confirmed', trust_score: 0.95,
    impact_tier: 'high', impact_score: 9.1, rule_version_id: 'v1',
    primary_entity_type: 'company', primary_entity_id: 'lilly',
    primary_entity_name: 'Eli Lilly', related_entity_ids: [],
    evidence_document_ids: [], status: 'shipped', superseded_by: null,
    supersedence_reason: null, created_at: '2026-05-09T12:00:00Z',
    reviewed_by: null, reviewed_at: null, shipped_at: '2026-05-09T13:00:00Z',
  },
  {
    id: 's5', event_id: 'e2', kbq_tags: ['strategic'],
    headline: "Dr. Aronne at AACE: 'orforglipron is the form factor that wins'",
    summary: 'KOL signals oral preference.',
    direction: 'positive', confidence_tier: 'reviewed', trust_score: 0.82,
    impact_tier: 'medium', impact_score: 6.4, rule_version_id: 'v1',
    primary_entity_type: 'company', primary_entity_id: 'lilly',
    primary_entity_name: 'Eli Lilly', related_entity_ids: [],
    evidence_document_ids: [], status: 'shipped', superseded_by: null,
    supersedence_reason: null, created_at: '2026-05-09T12:00:00Z',
    reviewed_by: null, reviewed_at: null, shipped_at: '2026-05-09T13:00:00Z',
  },
];

function renderView(close = vi.fn(), moment = MOMENT) {
  return render(
    <ThemeProvider>
      <MemoryRouter>
        <MomentView moment={moment} signals={SIGNALS} close={close} />
      </MemoryRouter>
    </ThemeProvider>,
  );
}

describe('MomentView (Loop #18 — cinematic overlay)', () => {
  it('renders the moment title as the hero heading', () => {
    renderView();
    expect(
      screen.getByRole('heading', { level: 1, name: /orforglipron acceleration/i }),
    ).toBeDefined();
  });

  it('renders the moment summary', () => {
    renderView();
    expect(screen.getByText(/three signals jointly raise/i)).toBeDefined();
  });

  it('renders three PlayCards with kind labels', () => {
    renderView();
    expect(screen.getByText(/aggressive/i)).toBeDefined();
    expect(screen.getByText(/balanced/i)).toBeDefined();
    expect(screen.getByText(/cautious/i)).toBeDefined();
  });

  it('marks the middle play (balanced) as selected by default', () => {
    const { container } = renderView();
    const selected = container.querySelector('[data-play-selected="true"]');
    expect(selected).not.toBeNull();
    expect(selected?.textContent).toMatch(/pivot pricing/i);
  });

  it('clicking a different play changes the selected card', () => {
    const { container } = renderView();
    const aggressive = container.querySelector('[data-play-kind="aggressive"]');
    expect(aggressive).not.toBeNull();
    fireEvent.click(aggressive!);
    const selected = container.querySelector('[data-play-selected="true"]');
    expect(selected?.getAttribute('data-play-kind')).toBe('aggressive');
  });

  it('renders the Monte Carlo outcome distribution', () => {
    renderView();
    expect(screen.getByText(/monte carlo/i)).toBeDefined();
    expect(screen.getByText(/10,000 runs/i)).toBeDefined();
  });

  it('renders the signal chain with each referenced signal headline', () => {
    renderView();
    expect(screen.getByText(/SURMOUNT-MMO/i)).toBeDefined();
    expect(screen.getByText(/orforglipron is the form factor/i)).toBeDefined();
  });

  it('renders the belief shift with prior + posterior', () => {
    renderView();
    // PRIOR + POSTERIOR labels are unique to the belief-shift card.
    // Numeric labels (18%, 41%) also appear inside the summary text;
    // assert their presence non-uniquely.
    expect(screen.getByText(/^PRIOR$/i)).toBeDefined();
    expect(screen.getByText(/^POSTERIOR$/i)).toBeDefined();
    expect(screen.getAllByText(/18%/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/41%/).length).toBeGreaterThan(0);
  });

  it('renders the three bottom actions — War Room, Defer, Commit', () => {
    renderView();
    expect(screen.getByRole('button', { name: /open as war room/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /^defer$/i })).toBeDefined();
    expect(screen.getByRole('button', { name: /commit decision/i })).toBeDefined();
  });

  it('clicking the back button calls close()', () => {
    const close = vi.fn();
    renderView(close);
    fireEvent.click(screen.getByRole('button', { name: /^back$/i }));
    expect(close).toHaveBeenCalled();
  });

  it('pressing Escape calls close()', () => {
    const close = vi.fn();
    renderView(close);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(close).toHaveBeenCalled();
  });

  it('applies a light-mode (hybrid) data attribute to the overlay so the editorial register lands even on dark sites', () => {
    const { container } = renderView();
    const overlay = container.querySelector('[data-moment-overlay]');
    expect(overlay).not.toBeNull();
    expect(overlay?.getAttribute('data-theme')).toBe('hybrid-light');
  });
});
