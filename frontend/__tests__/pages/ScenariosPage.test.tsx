/**
 * F10 — ScenariosPage tests.
 *
 * Scenarios are event-triggered with team-moves and decision-options.
 * Each scenario carries an inline blocked-by-gaps banner when relevant.
 * The probability dial shows prior vs current (the learn-loop in operation).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';

// FS-1: the expanded card lazily fetches the probability-history tape.
vi.mock('../../src/api', () => ({
  scenariosApi: {
    probabilityHistory: vi.fn(() => Promise.resolve({ history: [], count: 0 })),
  },
}));
import { scenariosApi } from '../../src/api';
import { ScenariosPage } from '../../src/pages/ScenariosPage';

const mockHistory = scenariosApi.probabilityHistory as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockHistory.mockReset();
  mockHistory.mockResolvedValue({ history: [], count: 0 });
});

const SCOPE = { engagementName: 'CagriSema Pre-Launch', focalAsset: 'drug:cagrisema' };

const SCENARIOS = [
  {
    id: 'scn-A',
    name: 'Lilly Offensive',
    trigger: {
      event: 'Lilly launches orforglipron at $200 WAC with Tier 2 CVS coverage',
      date: '2026-08-15',
      evidence: [
        { factId: 'f10', predicate: 'pricing_intent' },
        { factId: 'f11', predicate: 'corporate_event' },
      ],
    },
    probability: 0.55,
    probabilityCurrent: 0.62,
    calibrationNote: '3 signals on cagrisema since derivation re-weighted this scenario (prior 0.55 -> 0.62). Latest: "Lilly readout positive" (confirmed, 2026-05-20).',
    teamMoves: [
      { team: 'Lilly',  move: 'Aggressive WAC parity + premium specialist rebates',
        rationale: 'Maximises early-market lock-in given orforglipron oral advantage',
        impact: { Lilly: 0.6, Novo: -0.4, Payer: 0.1 } },
      { team: 'Payer',  move: 'Step-edit to Foundayo before brand specialty access',
        rationale: 'Cost-containment lever opens with multiple options' },
      { team: 'HCP',    move: 'Hedge prescribing to oral options first',
        rationale: 'Adherence + access conjugate' },
    ],
    decisionOptions: [
      { id: 'do1', statement: 'Hold pricing 90 days',
        rationale: 'Defend brand value; let mfg signals settle',
        npv5yDkkBn: 8.2 },
      { id: 'do2', statement: 'Match WAC immediately',
        rationale: 'Capture volume; protect Tier 2 access',
        npv5yDkkBn: 6.4 },
      { id: 'do3', statement: 'Accelerate OBC framework',
        rationale: 'Open new commercial primitive ahead of Lilly response',
        npv5yDkkBn: 9.1, recommended: true },
    ],
    decisionOutput: 'Begin Option 3 work now, execute Option 2 at launch, hold pricing in first 90 days',
  },
  {
    id: 'scn-B',
    name: 'Payer Coalition',
    trigger: {
      event: 'CVS + Express Scripts joint formulary policy: Tier 3 + step-edit for all new GLP-1 brand entries',
      date: '2026-10-01',
      evidence: [{ factId: 'f20', predicate: 'payer_policy' }],
    },
    probability: 0.30,
    teamMoves: [
      { team: 'Payer', move: 'Coordinated Tier 3 + step-edit', rationale: 'cost control' },
    ],
    decisionOptions: [
      { id: 'do4', statement: 'Aggressive value contracts', rationale: 'unlock access' },
      { id: 'do5', statement: 'Direct-to-consumer cash channel', rationale: 'sidestep formulary' },
    ],
    blockedByGaps: ['gap-payer-tier'],
  },
];

function setup(overrides: any = {}) {
  const onSelectScenario = vi.fn();
  const onPlayScenario = vi.fn();
  const onOpenFact = vi.fn();
  const onMarkComplete = vi.fn();
  const utils = render(
    <ScenariosPage
      eid="eng-1"
      scope={SCOPE}
      scenarios={SCENARIOS as any}
      activeScenarioId={null}
      onSelectScenario={onSelectScenario}
      onPlayScenario={onPlayScenario}
      onOpenFact={onOpenFact}
      onMarkComplete={onMarkComplete}
      {...overrides}
    />,
  );
  return { ...utils, onSelectScenario, onPlayScenario, onOpenFact, onMarkComplete };
}

describe('ScenariosPage — header', () => {
  it('shows total scenarios count and recommended-output count', () => {
    setup();
    // 2 scenarios; scn-A has decisionOutput → 1 recommended
    expect(screen.getByText(/2 scenarios/i)).toBeInTheDocument();
    expect(screen.getByText(/1 recommended/i)).toBeInTheDocument();
  });
});

describe('ScenariosPage — scenario cards', () => {
  it('renders one card per scenario with name + trigger snippet', () => {
    const { container } = setup();
    expect(container.querySelectorAll('[data-scenario-id]').length).toBe(2);
    expect(screen.getByText(/Lilly Offensive/)).toBeInTheDocument();
    expect(screen.getByText(/Lilly launches orforglipron/)).toBeInTheDocument();
  });

  it('renders per-team impact chips on team moves when expanded (PB-H11)', () => {
    const { container } = setup({ activeScenarioId: 'scn-A' });
    const chip = container.querySelector('[data-impact-team="Lilly"]');
    expect(chip).toBeTruthy();
    expect(chip).toHaveTextContent('Lilly +0.6');
    // a negative impact renders too
    expect(container.querySelector('[data-impact-team="Novo"]')).toHaveTextContent('Novo -0.4');
  });

  it('shows probability dial — prior + current when both present', () => {
    const { container } = setup();
    const card = container.querySelector('[data-scenario-id="scn-A"]') as HTMLElement;
    // 55% prior, 62% current
    expect(within(card).getByText(/55%/)).toBeInTheDocument();
    expect(within(card).getByText(/62%/)).toBeInTheDocument();
  });

  it('shows prior only when no current calibration', () => {
    const { container } = setup();
    const card = container.querySelector('[data-scenario-id="scn-B"]') as HTMLElement;
    expect(within(card).getByText(/30%/)).toBeInTheDocument();
  });

  it('shows the calibration note when current_prob was re-weighted (PB-H14)', () => {
    const { container } = setup();
    const card = container.querySelector('[data-scenario-id="scn-A"]') as HTMLElement;
    const note = within(card).getByTestId('scenario-calibration-note');
    expect(note).toBeInTheDocument();
    expect(note.textContent).toMatch(/re-weighted this scenario/i);
    expect(note.textContent).toMatch(/Lilly readout positive/);
  });

  it('shows no calibration note for an uncalibrated scenario', () => {
    const { container } = setup();
    const card = container.querySelector('[data-scenario-id="scn-B"]') as HTMLElement;
    expect(within(card).queryByTestId('scenario-calibration-note')).not.toBeInTheDocument();
  });

  it('clicking a card header fires onSelectScenario', () => {
    const { container, onSelectScenario } = setup();
    const header = container.querySelector('[data-scenario-id="scn-A"] [data-card-header]') as HTMLElement;
    fireEvent.click(header);
    expect(onSelectScenario).toHaveBeenCalledWith('scn-A');
  });

  it('blocked scenario renders blocked banner', () => {
    const { container } = setup();
    const card = container.querySelector('[data-scenario-id="scn-B"]') as HTMLElement;
    expect(within(card).getByText(/blocked/i)).toBeInTheDocument();
  });
});

describe('ScenariosPage — expanded scenario', () => {
  it('shows trigger evidence chips when active', () => {
    const { container, onOpenFact } = setup({ activeScenarioId: 'scn-A' });
    const expanded = container.querySelector('[data-scenario-id="scn-A"][data-expanded="true"]') as HTMLElement;
    expect(expanded).not.toBeNull();
    const chip = within(expanded).getByText(/f10/);
    expect(chip).toBeInTheDocument();
    fireEvent.click(chip);
    expect(onOpenFact).toHaveBeenCalledWith('f10');
  });

  it('shows team moves when expanded', () => {
    const { container } = setup({ activeScenarioId: 'scn-A' });
    const expanded = container.querySelector('[data-scenario-id="scn-A"][data-expanded="true"]') as HTMLElement;
    expect(within(expanded).getByText(/Aggressive WAC parity/)).toBeInTheDocument();
    expect(within(expanded).getByText(/Step-edit to Foundayo/)).toBeInTheDocument();
  });

  it('shows decision options with recommended badge', () => {
    const { container } = setup({ activeScenarioId: 'scn-A' });
    const expanded = container.querySelector('[data-scenario-id="scn-A"][data-expanded="true"]') as HTMLElement;
    expect(within(expanded).getByText(/Hold pricing 90 days/)).toBeInTheDocument();
    expect(within(expanded).getByText(/Match WAC immediately/)).toBeInTheDocument();
    expect(within(expanded).getByText(/Accelerate OBC framework/)).toBeInTheDocument();
    expect(within(expanded).getByText(/recommended/i)).toBeInTheDocument();
  });

  it('shows decision output narrative when expanded', () => {
    setup({ activeScenarioId: 'scn-A' });
    expect(screen.getByText(/Begin Option 3 work now/)).toBeInTheDocument();
  });

  it('"Play in War Room" fires onPlayScenario for unblocked scenarios', () => {
    const { container, onPlayScenario } = setup({ activeScenarioId: 'scn-A' });
    const btn = within(container.querySelector('[data-scenario-id="scn-A"]') as HTMLElement)
      .getByRole('button', { name: /play in war room/i });
    fireEvent.click(btn);
    expect(onPlayScenario).toHaveBeenCalledWith('scn-A');
  });

  it('"Play in War Room" disabled for blocked scenarios', () => {
    const { container } = setup({ activeScenarioId: 'scn-B' });
    const btn = within(container.querySelector('[data-scenario-id="scn-B"]') as HTMLElement)
      .getByRole('button', { name: /play in war room/i });
    expect(btn).toBeDisabled();
  });
});

describe('ScenariosPage — workshop gate', () => {
  it('"Mark stage complete" disabled when any scenario is blocked', () => {
    setup();
    expect(screen.getByRole('button', { name: /mark stage complete/i })).toBeDisabled();
  });

  it('"Mark stage complete" enabled when no scenario is blocked', () => {
    setup({ scenarios: [SCENARIOS[0]] });
    expect(screen.getByRole('button', { name: /mark stage complete/i })).not.toBeDisabled();
  });
});

describe('ScenariosPage — empty', () => {
  it('shows placeholder when no scenarios', () => {
    setup({ scenarios: [] });
    expect(screen.getByText(/no scenarios/i)).toBeInTheDocument();
  });
});

describe('ScenariosPage — accessibility', () => {
  it('uses a main landmark', () => {
    setup();
    expect(screen.getByRole('main', { name: /scenarios/i })).toBeInTheDocument();
  });
});

describe('ScenariosPage — probability history timeline (FS-1 / OQ2)', () => {
  const STEPS = [
    { id: 'h1', scenarioId: 'scn-A', prevProb: 0.55, newProb: 0.62, delta: 0.07,
      nSupporting: 3, nContradicting: 0, triggeringSignalId: 's1',
      method: 'ewma_stance', note: 'corroborated', createdAt: '2026-05-20T00:00:00Z' },
    { id: 'h2', scenarioId: 'scn-A', prevProb: 0.62, newProb: 0.50, delta: -0.12,
      nSupporting: 0, nContradicting: 1, triggeringSignalId: 's2',
      method: 'ewma_stance', note: 'rival readout missed', createdAt: '2026-06-01T00:00:00Z' },
  ];

  it('fetches the tape with the engagement + scenario id when a card expands', async () => {
    setup({ activeScenarioId: 'scn-A' });
    await screen.findByTestId('probability-timeline-empty');
    expect(mockHistory).toHaveBeenCalledWith('eng-1', 'scn-A');
  });

  it('renders an honest empty state when no calibration has happened', async () => {
    setup({ activeScenarioId: 'scn-A' });
    expect(await screen.findByTestId('probability-timeline-empty')).toBeInTheDocument();
    expect(screen.getByText(/No calibration yet/i)).toBeInTheDocument();
  });

  it('renders up and down moves with deltas (the audit tape)', async () => {
    mockHistory.mockResolvedValue({ history: STEPS, count: 2 });
    const { container } = setup({ activeScenarioId: 'scn-A' });
    const tape = await screen.findByTestId('probability-timeline');
    const steps = within(tape).getAllByTestId('calibration-step');
    expect(steps).toHaveLength(2);
    // a contradiction-driven downward move is visibly flagged
    expect(container.querySelector('[data-testid="calibration-step"][data-direction="down"]'))
      .toBeInTheDocument();
    expect(within(tape).getByText(/55%/)).toBeInTheDocument();   // step1 prev
    expect(within(tape).getByText(/50%/)).toBeInTheDocument();   // step2 new
    expect(within(tape).getByText(/1 contradict/i)).toBeInTheDocument();
  });

  it('does not fetch history for a collapsed (inactive) card', () => {
    setup(); // activeScenarioId null → no card expanded
    expect(mockHistory).not.toHaveBeenCalled();
  });
});
