/**
 * LandingPage refresh — behavioural render test.
 *
 * Mocks useHealthStats so the page renders deterministically without network.
 * Pins: the value story renders, the three CTA handlers fire, real/honest
 * metric labels appear, and the fabricated "Agent Tasks" metric is gone.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../../src/components/primitives/ThemeToggle', () => ({
  ThemeToggle: () => null,  // needs a ThemeProvider; irrelevant to this test
}));

vi.mock('../../src/hooks/useHealthStats', () => ({
  useHealthStats: () => ({
    drugs: 1470, trials: 4201, articles: 1098, companies: 320,
    events: 1518, entityLinks: 11747, totalRecords: 9679, connectors: 9,
    services: [], sourceCoverage: [], competitiveSegments: 0,
    topDrug: '', topCompany: '', loading: false, error: null, refreshedAt: null,
  }),
}));

import LandingPage from '../../src/pages/LandingPage';

// jsdom has no IntersectionObserver; framer-motion's whileInView needs it.
class IO {
  observe() {}
  unobserve() {}
  disconnect() {}
  takeRecords() { return []; }
}

describe('LandingPage (refresh)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.stubGlobal('IntersectionObserver', IO);
  });

  it('renders the value proposition + microsite themes', () => {
    render(<LandingPage onEnter={() => {}} onSearch={() => {}} />);
    // hero: intelligence substrate
    expect(screen.getByText(/for pharma decisions/i)).toBeInTheDocument();
    // theme 1 — AI-ready / AI-led (appears in hero + a shift card)
    expect(screen.getAllByText(/AI-led, not AI-assist/i).length).toBeGreaterThan(0);
    // theme 2 — the substrate stack + SDAL flywheel
    expect(screen.getByText(/one substrate/i)).toBeInTheDocument();
    expect(screen.getByText(/Sense → Decide → Act → Learn, on autopilot\./i)).toBeInTheDocument();
    // Beta framing (appears in multiple places)
    expect(screen.getAllByText(/Beta/i).length).toBeGreaterThan(0);
  });

  it('wires the three CTA actions', () => {
    const onEnter = vi.fn();
    const onSearch = vi.fn();
    const onCI = vi.fn();
    render(<LandingPage onEnter={onEnter} onSearch={onSearch} onCI={onCI} />);

    fireEvent.click(screen.getByRole('button', { name: /Enter workspace/i }));
    expect(onEnter).toHaveBeenCalled();

    fireEvent.click(screen.getAllByRole('button', { name: /Launch CI Cockpit/i })[0]);
    expect(onCI).toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: /Browse the data catalog/i }));
    expect(onSearch).toHaveBeenCalled();
  });

  it('shows honest metric labels (and not the fabricated ones)', () => {
    render(<LandingPage onEnter={() => {}} onSearch={() => {}} />);
    expect(screen.getByText('Drugs tracked')).toBeInTheDocument();
    expect(screen.getByText('Clinical trials')).toBeInTheDocument();
    expect(screen.getByText('Publications')).toBeInTheDocument();
    // the previous page invented these — they must not return
    expect(screen.queryByText('Agent Tasks')).not.toBeInTheDocument();
    expect(screen.queryByText('Simulated Scenarios')).not.toBeInTheDocument();
  });
});
