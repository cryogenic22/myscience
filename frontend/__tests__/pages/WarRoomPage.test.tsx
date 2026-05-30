/**
 * F11 — WarRoomPage tests.
 *
 * Three-mode toggle (Guided / Autonomous / Game-theoretic) sharing one
 * Scenario state. Deep-teal accent via data-warroom="active". Each mode
 * has its own panel; switching is legitimate mid-session.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { WarRoomPage } from '../../src/pages/WarRoomPage';

const SCOPE = { engagementName: 'CagriSema Pre-Launch', focalAsset: 'drug:cagrisema' };

const SCENARIO = {
  id: 'scn-A',
  name: 'Lilly Offensive',
  trigger: {
    event: 'Lilly launches orforglipron at $200 WAC with Tier 2 CVS coverage',
    date: '2026-08-15',
  },
};

const AVAILABLE_MOVES = [
  { id: 'm1', type: 'pricing',     statement: 'Hold WAC at parity with Zepbound' },
  { id: 'm2', type: 'contracting', statement: 'Accelerate OBC framework pre-PDUFA' },
  { id: 'm3', type: 'kol',         statement: 'Specialist field-force mobilisation' },
];

const PAYOFF = {
  rowsLabel: 'Novo',
  colsLabel: 'Lilly',
  rows: ['Hold pricing', 'Match WAC', 'Accelerate OBC'],
  cols: ['Hold', 'Aggressive discount', 'Match'],
  cells: [
    [8.2, 6.1, 7.3],
    [7.4, 6.4, 6.9],
    [9.1, 7.5, 8.0],
  ],
  nash: [2, 0] as [number, number],   // (Accelerate OBC, Lilly Hold) = 9.1
};

function setup(overrides: any = {}) {
  const onModeChange = vi.fn();
  const onPlayMove = vi.fn();
  const onCommitTurn = vi.fn();
  const onAutonomousStart = vi.fn();
  const onAutonomousStep = vi.fn();
  const onAutonomousPause = vi.fn();
  const onAutonomousReset = vi.fn();
  const onMarkComplete = vi.fn();

  const props = {
    scope: SCOPE,
    scenario: SCENARIO,
    mode: 'guided' as const,
    onModeChange,
    onMarkComplete,

    guidedRound: 1,
    availableNovoMoves: AVAILABLE_MOVES,
    guidedLedger: [],
    projectedCounterMoves: [],
    onPlayMove,
    onCommitTurn,

    autonomousState: 'idle' as const,
    autonomousNarration: [],
    onAutonomousStart,
    onAutonomousStep,
    onAutonomousPause,
    onAutonomousReset,

    payoffMatrix: PAYOFF,

    ...overrides,
  };

  const utils = render(<WarRoomPage {...props} />);
  return { ...utils, onModeChange, onPlayMove, onCommitTurn,
           onAutonomousStart, onAutonomousStep, onAutonomousPause,
           onAutonomousReset, onMarkComplete };
}

// ── Shell + mode toggle ────────────────────────────────────────────

describe('WarRoomPage — shell + mode toggle', () => {
  it('renders the engagement header with scenario name and trigger', () => {
    setup();
    expect(screen.getByText(/Lilly Offensive/)).toBeInTheDocument();
    expect(screen.getByText(/Lilly launches orforglipron/)).toBeInTheDocument();
  });

  it('renders three mode tabs in a tablist', () => {
    const { container } = setup();
    const list = container.querySelector('[role="tablist"]');
    expect(list).not.toBeNull();
    const tabs = within(list as HTMLElement).getAllByRole('tab');
    expect(tabs.length).toBe(3);
  });

  it('marks the active mode tab with aria-selected="true"', () => {
    const { container } = setup({ mode: 'game_theoretic' });
    const active = container.querySelector('[role="tab"][aria-selected="true"]');
    expect(active?.textContent?.toLowerCase()).toMatch(/game/);
  });

  it('clicking a tab fires onModeChange with the new mode', () => {
    const { container, onModeChange } = setup();
    const autoTab = container.querySelector('[data-mode="autonomous"]') as HTMLElement;
    fireEvent.click(autoTab);
    expect(onModeChange).toHaveBeenCalledWith('autonomous');
  });

  it('root has data-warroom="active" (deep-teal palette)', () => {
    const { container } = setup();
    expect(container.querySelector('[data-warroom="active"]')).not.toBeNull();
  });
});

// ── Guided panel ──────────────────────────────────────────────────

describe('WarRoomPage — Guided mode', () => {
  it('renders the round counter', () => {
    setup({ mode: 'guided', guidedRound: 3 });
    expect(screen.getByText(/round 3/i)).toBeInTheDocument();
  });

  it('renders available Novo moves as buttons', () => {
    const { container } = setup({ mode: 'guided' });
    AVAILABLE_MOVES.forEach((m) => {
      const btn = container.querySelector(`[data-move-id="${m.id}"]`);
      expect(btn).not.toBeNull();
    });
  });

  it('clicking a move fires onPlayMove(moveId)', () => {
    const { container, onPlayMove } = setup({ mode: 'guided' });
    fireEvent.click(container.querySelector('[data-move-id="m2"]') as HTMLElement);
    expect(onPlayMove).toHaveBeenCalledWith('m2');
  });

  it('renders an empty-ledger placeholder when no moves played', () => {
    setup({ mode: 'guided' });
    expect(screen.getByText(/pick a move to begin/i)).toBeInTheDocument();
  });

  it('renders ledger rows with team + move + round', () => {
    const ledger = [
      { team: 'Novo',  move: 'Hold WAC', round: 1, rationale: 'Defend brand' },
      { team: 'Lilly', move: 'Aggressive WAC parity', round: 1, rationale: 'Capture share' },
    ];
    const { container } = setup({ mode: 'guided', guidedLedger: ledger });
    const rows = container.querySelectorAll('[data-ledger-row]');
    expect(rows.length).toBe(2);
    expect(within(rows[0] as HTMLElement).getByText('Novo')).toBeInTheDocument();
    expect(within(rows[1] as HTMLElement).getByText(/Aggressive WAC parity/)).toBeInTheDocument();
  });

  it('renders projected counter-moves with confidence', () => {
    const counters = [
      { team: 'Lilly', move: 'Match WAC immediately', confidence: 0.78, rationale: 'volume protection' },
      { team: 'Payer', move: 'Step-edit before brand specialty', confidence: 0.62, rationale: 'cost lever' },
    ];
    const { container } = setup({ mode: 'guided', projectedCounterMoves: counters });
    expect(screen.getByText(/Match WAC immediately/)).toBeInTheDocument();
    expect(screen.getByText(/78%/)).toBeInTheDocument();
    expect(screen.getByText(/62%/)).toBeInTheDocument();
  });

  it('Commit turn button fires onCommitTurn', () => {
    const { onCommitTurn } = setup({ mode: 'guided' });
    fireEvent.click(screen.getByRole('button', { name: /commit turn/i }));
    expect(onCommitTurn).toHaveBeenCalled();
  });
});

// ── Autonomous panel ───────────────────────────────────────────────

describe('WarRoomPage — Autonomous mode', () => {
  it('Play button fires onAutonomousStart when idle', () => {
    const { onAutonomousStart } = setup({ mode: 'autonomous', autonomousState: 'idle' });
    fireEvent.click(screen.getByRole('button', { name: /play/i }));
    expect(onAutonomousStart).toHaveBeenCalled();
  });

  it('Pause button fires onAutonomousPause when running', () => {
    const { onAutonomousPause } = setup({ mode: 'autonomous', autonomousState: 'running' });
    fireEvent.click(screen.getByRole('button', { name: /pause/i }));
    expect(onAutonomousPause).toHaveBeenCalled();
  });

  it('Step button fires onAutonomousStep', () => {
    const { onAutonomousStep } = setup({ mode: 'autonomous', autonomousState: 'paused' });
    fireEvent.click(screen.getByRole('button', { name: /step/i }));
    expect(onAutonomousStep).toHaveBeenCalled();
  });

  it('Reset button fires onAutonomousReset', () => {
    const { onAutonomousReset } = setup({ mode: 'autonomous', autonomousState: 'complete' });
    fireEvent.click(screen.getByRole('button', { name: /reset/i }));
    expect(onAutonomousReset).toHaveBeenCalled();
  });

  it('shows "press play to begin" when narration empty + idle', () => {
    setup({ mode: 'autonomous', autonomousState: 'idle', autonomousNarration: [] });
    expect(screen.getByText(/press play to begin/i)).toBeInTheDocument();
  });

  it('renders narration lines when present', () => {
    setup({
      mode: 'autonomous',
      autonomousState: 'running',
      autonomousNarration: [
        'Round 1: Lilly opens with aggressive field activation.',
        'Round 1: Payer signals step-edit consideration.',
        'Round 2: Novo holds pricing; signals OBC framework prep.',
      ],
    });
    expect(screen.getByText(/Lilly opens with aggressive/)).toBeInTheDocument();
    expect(screen.getByText(/Novo holds pricing/)).toBeInTheDocument();
  });
});

// ── Game-theoretic panel ───────────────────────────────────────────

describe('WarRoomPage — Game-theoretic mode', () => {
  it('renders a payoff matrix with all (row, col) cells', () => {
    const { container } = setup({ mode: 'game_theoretic' });
    const cells = container.querySelectorAll('[data-payoff-cell]');
    // 3 rows x 3 cols = 9 cells
    expect(cells.length).toBe(9);
  });

  it('Nash cell has data-nash="true" and the utility value', () => {
    const { container } = setup({ mode: 'game_theoretic' });
    const nashCell = container.querySelector('[data-nash="true"]');
    expect(nashCell).not.toBeNull();
    // PAYOFF.nash = [2, 0] → row 2 (Accelerate OBC), col 0 (Hold) → 9.1
    expect(within(nashCell as HTMLElement).getByText(/9\.1/)).toBeInTheDocument();
  });

  it('shows the Nash equilibrium label', () => {
    setup({ mode: 'game_theoretic' });
    expect(screen.getByText(/nash equilibrium/i)).toBeInTheDocument();
  });

  it('renders strategy labels on rows and columns', () => {
    setup({ mode: 'game_theoretic' });
    expect(screen.getByText('Hold pricing')).toBeInTheDocument();
    expect(screen.getByText('Accelerate OBC')).toBeInTheDocument();
    expect(screen.getByText('Aggressive discount')).toBeInTheDocument();
  });

  it('renders Monte Carlo summary when provided', () => {
    setup({
      mode: 'game_theoretic',
      monteCarlo: { runs: 1000, meanNovoNPV: 7.6, p10: 5.2, p90: 9.4 },
    });
    expect(screen.getByText(/1,000 runs/i)).toBeInTheDocument();
    expect(screen.getByText(/7\.6/)).toBeInTheDocument();
    expect(screen.getByText(/5\.2/)).toBeInTheDocument();
    expect(screen.getByText(/9\.4/)).toBeInTheDocument();
  });

  it('does not render Monte Carlo block when not provided', () => {
    setup({ mode: 'game_theoretic' });
    expect(screen.queryByText(/monte carlo/i)).toBeNull();
  });
});

// ── Footer + ARIA ──────────────────────────────────────────────────

describe('WarRoomPage — footer + ARIA', () => {
  it('Mark stage complete fires onMarkComplete', () => {
    const { onMarkComplete } = setup();
    fireEvent.click(screen.getByRole('button', { name: /mark stage complete/i }));
    expect(onMarkComplete).toHaveBeenCalled();
  });

  it('uses a main landmark named "War Room"', () => {
    setup();
    expect(screen.getByRole('main', { name: /war room/i })).toBeInTheDocument();
  });

  it('mode tabs have role="tab" + aria-controls referencing panels', () => {
    const { container } = setup();
    const tabs = container.querySelectorAll('[role="tab"]');
    tabs.forEach((t) => {
      expect(t.getAttribute('aria-controls')).not.toBeNull();
    });
  });
});
