/**
 * Loop #20 — Materiality factor drawer tests.
 *
 * Surfaces the four factor contributions (source_tier, entity_criticality,
 * claim_type, recency) for any signal whose materiality has been scored.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import MaterialityDrawer from '../../src/components/ci/MaterialityDrawer';
import type { MaterialityFactors } from '../../src/types/materiality';

const FACTORS: MaterialityFactors = {
  source_tier: { input: 1, value: 1.0, weight: 0.3, contribution: 30.0 },
  entity_criticality: { input: 'critical', value: 1.0, weight: 0.3, contribution: 30.0 },
  claim_type: { input: 'trial_readout', value: 1.0, weight: 0.25, contribution: 25.0 },
  recency: { input: 5.0, value: 0.89, weight: 0.15, contribution: 13.3 },
};

describe('MaterialityDrawer (Loop #20)', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <MaterialityDrawer open={false} factors={FACTORS} score={98.3} onClose={() => {}} />,
    );
    expect(container.querySelector('[data-materiality-drawer]')).toBeNull();
  });

  it('renders the composite score in the header', () => {
    render(<MaterialityDrawer open factors={FACTORS} score={98.3} onClose={() => {}} />);
    expect(screen.getByText(/98/)).toBeDefined();
  });

  it('renders all four factor rows', () => {
    render(<MaterialityDrawer open factors={FACTORS} score={98.3} onClose={() => {}} />);
    expect(screen.getByText(/source tier/i)).toBeDefined();
    expect(screen.getByText(/entity criticality/i)).toBeDefined();
    expect(screen.getByText(/claim type/i)).toBeDefined();
    expect(screen.getByText(/recency/i)).toBeDefined();
  });

  it('renders the contribution percentage for each factor', () => {
    render(<MaterialityDrawer open factors={FACTORS} score={98.3} onClose={() => {}} />);
    // Each contribution % can also appear elsewhere (weight label, hint
    // text); we just need at least one match per expected value.
    expect(screen.getAllByText(/30(\.0)?\s*%?/).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/25(\.0)?\s*%?/).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/13/).length).toBeGreaterThanOrEqual(1);
  });

  it('renders the input value for each factor', () => {
    render(<MaterialityDrawer open factors={FACTORS} score={98.3} onClose={() => {}} />);
    // "Tier 1" appears both as the input and inside the hint text;
    // assert presence non-uniquely.
    expect(screen.getAllByText(/tier 1/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/critical/i).length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText(/trial[_ ]readout/i).length).toBeGreaterThanOrEqual(1);
  });

  it('renders a horizontal bar per factor with width proportional to contribution', () => {
    const { container } = render(
      <MaterialityDrawer open factors={FACTORS} score={98.3} onClose={() => {}} />,
    );
    const bars = container.querySelectorAll('[data-factor-bar]');
    expect(bars.length).toBe(4);
    // source_tier contribution = 30 → width 30%
    const sourceTierBar = container.querySelector('[data-factor-bar="source_tier"]') as HTMLElement;
    expect(sourceTierBar.style.width).toMatch(/30/);
  });

  it('renders the formula text near the bottom', () => {
    render(<MaterialityDrawer open factors={FACTORS} score={98.3} onClose={() => {}} />);
    expect(screen.getByText(/score\s*=\s*100\s*×/i)).toBeDefined();
  });

  it('invokes onClose when the close button is clicked', () => {
    const onClose = vi.fn();
    render(<MaterialityDrawer open factors={FACTORS} score={98.3} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', { name: /close/i }));
    expect(onClose).toHaveBeenCalled();
  });

  it('invokes onClose when Escape is pressed', () => {
    const onClose = vi.fn();
    render(<MaterialityDrawer open factors={FACTORS} score={98.3} onClose={onClose} />);
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it('shows an empty-state when factors is null', () => {
    render(<MaterialityDrawer open factors={null} score={null} onClose={() => {}} />);
    expect(screen.getByText(/not yet scored|no breakdown/i)).toBeDefined();
  });
});
