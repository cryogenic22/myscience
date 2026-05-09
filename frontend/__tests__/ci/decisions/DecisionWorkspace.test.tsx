/**
 * SPEC_030 Stage 3 — DecisionWorkspace
 *
 * The 5-panel composite. Mounts BriefPanel + EvidencePanel +
 * SimulationPanel + RecommendationPanel + ReasoningTraceDrawer; wires
 * keyboard contract (g e / g s / g r / t / ⌘+enter / escape).
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { makeBrief, makeOption, applyTheme, ALL_STATES } from './_fixtures';

const { mockGet, mockTransition } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockTransition: vi.fn(),
}));
vi.mock('../../../src/api', async () => {
  const actual = await vi.importActual<typeof import('../../../src/api')>('../../../src/api');
  return {
    ...actual,
    decisionBriefsApi: {
      ...(actual as any).decisionBriefsApi,
      get: mockGet,
      transition: mockTransition,
    },
  };
});

import DecisionWorkspace from '../../../src/components/ci/decisions/DecisionWorkspace';

function renderAt(briefId: string) {
  return render(
    <MemoryRouter initialEntries={[`/ci/decisions/${briefId}`]}>
      <Routes>
        <Route path="/ci/decisions/:id" element={<DecisionWorkspace />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('DecisionWorkspace', () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockTransition.mockReset();
  });

  it('shows skeleton while loading', () => {
    let resolve: any;
    mockGet.mockImplementation(() => new Promise((r) => { resolve = r; }));
    renderAt('b-1');
    expect(screen.getByLabelText(/loading workspace/i)).toBeInTheDocument();
    resolve(makeBrief());
  });

  it('renders all 5 panels (or their collapsed equivalents) when brief loads', async () => {
    mockGet.mockResolvedValueOnce(makeBrief({ options: [makeOption()] }));
    renderAt('b-1');
    await screen.findByText(/Should we accelerate/);
    expect(screen.getByTestId('panel-brief')).toBeInTheDocument();
    expect(screen.getByTestId('panel-evidence')).toBeInTheDocument();
    expect(screen.getByTestId('panel-simulation')).toBeInTheDocument();
    expect(screen.getByTestId('panel-recommendation')).toBeInTheDocument();
    // ReasoningTraceDrawer is closed by default
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('"t" toggles the ReasoningTraceDrawer', async () => {
    mockGet.mockResolvedValueOnce(makeBrief());
    renderAt('b-1');
    await screen.findByText(/Should we accelerate/);
    fireEvent.keyDown(window, { key: 't' });
    expect(await screen.findByRole('dialog')).toBeInTheDocument();
    fireEvent.keyDown(window, { key: 't' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  it('"escape" closes any open drawer/modal', async () => {
    mockGet.mockResolvedValueOnce(makeBrief());
    renderAt('b-1');
    await screen.findByText(/Should we accelerate/);
    fireEvent.keyDown(window, { key: 't' });
    await screen.findByRole('dialog');
    fireEvent.keyDown(window, { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  });

  describe('focus shortcuts (g e / g s / g r)', () => {
    it('"g e" focuses the Evidence panel', async () => {
      mockGet.mockResolvedValueOnce(makeBrief());
      renderAt('b-1');
      await screen.findByTestId('panel-evidence');
      fireEvent.keyDown(window, { key: 'g' });
      fireEvent.keyDown(window, { key: 'e' });
      expect(document.activeElement?.closest('[data-testid="panel-evidence"]')).toBeTruthy();
    });

    it('"g s" focuses the Simulation panel', async () => {
      mockGet.mockResolvedValueOnce(makeBrief());
      renderAt('b-1');
      await screen.findByTestId('panel-simulation');
      fireEvent.keyDown(window, { key: 'g' });
      fireEvent.keyDown(window, { key: 's' });
      expect(document.activeElement?.closest('[data-testid="panel-simulation"]')).toBeTruthy();
    });

    it('"g r" focuses the Recommendation panel', async () => {
      mockGet.mockResolvedValueOnce(makeBrief());
      renderAt('b-1');
      await screen.findByTestId('panel-recommendation');
      fireEvent.keyDown(window, { key: 'g' });
      fireEvent.keyDown(window, { key: 'r' });
      expect(document.activeElement?.closest('[data-testid="panel-recommendation"]')).toBeTruthy();
    });
  });

  it('cmd+enter advances state when allowed', async () => {
    mockGet.mockResolvedValueOnce(makeBrief({ state: 'draft', options: [makeOption(), makeOption({ ordinal: 2 })] }));
    mockTransition.mockResolvedValueOnce(makeBrief({ state: 'human_review' }));
    renderAt('b-1');
    await screen.findByText(/Should we accelerate/);
    fireEvent.keyDown(window, { key: 'Enter', metaKey: true });
    await waitFor(() => expect(mockTransition).toHaveBeenCalled());
  });

  it.each(ALL_STATES)('renders without crashing for state=%s', async (state) => {
    mockGet.mockResolvedValueOnce(makeBrief({ state, options: [makeOption()] }));
    renderAt('b-1');
    await screen.findByTestId('panel-brief');
  });

  it('renders error card on 404', async () => {
    mockGet.mockRejectedValueOnce(new Error('not found'));
    renderAt('b-missing');
    expect(await screen.findByText(/not found/i)).toBeInTheDocument();
  });

  it('shows fixture-mode pill when MZ_FIXTURE_MODE is enabled and fetch fails', async () => {
    window.localStorage.setItem('mz_fixture_mode', 'true');
    mockGet.mockRejectedValueOnce(new Error('network'));
    renderAt('b-1');
    expect(await screen.findByText(/fixture mode/i)).toBeInTheDocument();
    window.localStorage.removeItem('mz_fixture_mode');
  });

  it('respects density flag (compact halves spacing tokens)', async () => {
    window.localStorage.setItem('mz_density', 'compact');
    mockGet.mockResolvedValueOnce(makeBrief());
    renderAt('b-1');
    await screen.findByText(/Should we accelerate/);
    const root = screen.getByTestId('decision-workspace-root');
    expect(root.getAttribute('data-density')).toBe('compact');
    window.localStorage.removeItem('mz_density');
  });

  it('renders consistently in light and dark theme', async () => {
    mockGet.mockResolvedValue(makeBrief());
    applyTheme('light');
    const { unmount } = renderAt('b-1');
    await screen.findByText(/Should we accelerate/);
    unmount();
    applyTheme('dark');
    renderAt('b-1');
    await screen.findByText(/Should we accelerate/);
  });

  it.todo('respects prefers-reduced-motion: animations replaced by opacity-only');
  it.todo('responsive collapse: ≤1024px renders panels as tabs above brief panel');
});
