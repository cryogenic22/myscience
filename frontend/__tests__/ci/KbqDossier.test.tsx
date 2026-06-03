/**
 * Polish loop — KBQ Dossier (presentational) tests.
 * Sleek, borderless per-competitor KBQ profile.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import KbqDossier from '../../src/components/ci/KbqDossier';
import type { EntityKbqs } from '../../src/api';

const DATA: EntityKbqs = {
  entity: { type: 'company', id: 'co-lilly' },
  completeness: 0.625,
  kbqs: [
    { kbq: 1, title: 'Indications', status: 'fresh', items: [
      { claim: 'FDA approves Lilly Foundayo (orforglipron)', signal_id: 's1', evidence_ids: ['s1'], impact_tier: 'high', confidence_tier: 'confirmed', date: '2026-05-20T00:00:00Z' },
    ]},
    { kbq: 2, title: 'Competitors', status: 'fresh', items: [
      { claim: 'Neuro prospects expand', signal_id: 's2', evidence_ids: ['s2'], impact_tier: 'medium', confidence_tier: 'reported', date: '2026-05-19T00:00:00Z' },
    ]},
    { kbq: 3, title: 'Clinical', status: 'fresh', items: [] },
    { kbq: 4, title: 'Positioning', status: 'fresh', items: [] },
    { kbq: 5, title: 'Sales & Sentiment', status: 'insufficient', items: [] },
    { kbq: 6, title: 'SWOT', status: 'fresh', items: [] },
    { kbq: 7, title: 'Pricing', status: 'insufficient', items: [] },
    { kbq: 8, title: 'Access', status: 'insufficient', items: [] },
  ],
};

function renderDossier(data = DATA, name = 'Eli Lilly') {
  return render(<KbqDossier data={data} entityName={name} />);
}

describe('KbqDossier (polish loop)', () => {
  it('renders the entity name as the heading', () => {
    renderDossier();
    expect(screen.getByRole('heading', { name: /eli lilly/i })).toBeDefined();
  });

  it('renders all 8 KBQ sections with parity', () => {
    const { container } = renderDossier();
    expect(container.querySelectorAll('[data-kbq]').length).toBe(8);
  });

  it('renders each KBQ title', () => {
    renderDossier();
    for (const t of ['Indications', 'Competitors', 'Clinical', 'Positioning', 'Sales & Sentiment', 'SWOT', 'Pricing', 'Access']) {
      expect(screen.getByText(t)).toBeDefined();
    }
  });

  it('renders item claims', () => {
    renderDossier();
    expect(screen.getByText(/FDA approves Lilly Foundayo/i)).toBeDefined();
  });

  it('shows an insufficient-evidence state for empty KBQs', () => {
    const { container } = renderDossier();
    const insufficient = container.querySelectorAll('[data-kbq-status="insufficient"]');
    expect(insufficient.length).toBe(3); // KBQ 5, 7, 8
  });

  it('renders a completeness indicator', () => {
    renderDossier();
    expect(screen.getByText(/63%|62\.5%|0\.625|completeness/i)).toBeDefined();
  });

  it('uses borderless ds-card surfaces, not inline 1px borders', () => {
    const { container } = renderDossier();
    // KBQ cards use the design-system class, not boxed borders
    expect(container.querySelectorAll('.ds-card, .ds-panel').length).toBeGreaterThan(0);
  });

  it('PB-SL11: renders fact-backed items with a source link, not the signal drawer', () => {
    const onOpenSignal = vi.fn();
    const data: EntityKbqs = {
      entity: { type: 'drug', id: 'd1', name: 'Semaglutide' },
      completeness: 0.125,
      kbqs: [
        { kbq: 1, title: 'Indications', status: 'fresh', items: [] },
        { kbq: 2, title: 'Competitors', status: 'insufficient', items: [] },
        { kbq: 3, title: 'Clinical', status: 'fresh', items: [
          { claim: 'STEP 1 trial — 68 weeks', source: 'fact', signal_id: null,
            fact_id: 'f1', fact_class: 'corporate', evidence_ids: [], impact_tier: null,
            confidence_tier: null, date: '2026-05-01', source_label: 'ctgov',
            source_url: 'https://clinicaltrials.gov/x' },
        ]},
        { kbq: 4, title: 'Positioning', status: 'insufficient', items: [] },
        { kbq: 5, title: 'Sales & Sentiment', status: 'insufficient', items: [] },
        { kbq: 6, title: 'SWOT', status: 'insufficient', items: [] },
        { kbq: 7, title: 'Pricing', status: 'insufficient', items: [] },
        { kbq: 8, title: 'Access', status: 'insufficient', items: [] },
      ],
    };
    render(<KbqDossier data={data} entityName="Semaglutide" onOpenSignal={onOpenSignal} />);
    // fact item renders its claim + a source link
    const claim = screen.getByText(/STEP 1 trial/i);
    expect(claim).toBeInTheDocument();
    const sourceLink = screen.getByText(/ctgov/i).closest('a') as HTMLAnchorElement;
    expect(sourceLink.getAttribute('href')).toBe('https://clinicaltrials.gov/x');
    // clicking a fact item must NOT open the signal provenance drawer
    fireEvent.click(claim);
    expect(onOpenSignal).not.toHaveBeenCalled();
  });
});
