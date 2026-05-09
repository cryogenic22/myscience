/**
 * SPEC_030 Stage 3 — SimulationPanel
 *
 * Center panel. In v1 (this loop) the panel is structural: shows
 * scenario/MC/war-game placeholders with state-aware affordances. The
 * "Start war-game" CTA is disabled-with-tooltip until SPEC_032 lands.
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { makeBrief } from './_fixtures';
import SimulationPanel from '../../../src/components/ci/decisions/SimulationPanel';

describe('SimulationPanel', () => {
  it('renders three sections: Scenario, Monte Carlo, War-game', () => {
    // simulation_pending shows all three (war-game only renders in run states)
    render(<SimulationPanel brief={makeBrief({ state: 'simulation_pending' })} />);
    expect(screen.getAllByText(/scenario/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/monte carlo/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/war.game/i).length).toBeGreaterThan(0);
  });

  it('"Start war-game" button is disabled until SPEC_032', () => {
    render(<SimulationPanel brief={makeBrief({ state: 'simulation_pending' })} />);
    const btn = screen.getByRole('button', { name: /start war.game/i });
    expect(btn).toBeDisabled();
  });

  it('disabled war-game button has a tooltip explaining the SPEC_032 dependency', () => {
    render(<SimulationPanel brief={makeBrief({ state: 'simulation_pending' })} />);
    const btn = screen.getByRole('button', { name: /start war.game/i });
    expect(btn.getAttribute('title') || btn.getAttribute('aria-describedby')).toBeTruthy();
  });

  it('does not render run controls when state is draft / human_review', () => {
    render(<SimulationPanel brief={makeBrief({ state: 'draft' })} />);
    expect(screen.queryByRole('button', { name: /start/i })).not.toBeInTheDocument();
  });

  it.todo('renders war-game run results once SPEC_032 wires the war-games API');
  it.todo('renders Monte Carlo distribution histogram when results land');
});
