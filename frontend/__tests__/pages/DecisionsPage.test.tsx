/**
 * F12 — DecisionsPage tests.
 *
 * Closes the v7 IA spine. Committed-decisions ledger + gap log + 3-session
 * facilitator guide. Close-engagement gated on no pending gaps.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { DecisionsPage } from '../../src/pages/DecisionsPage';

const SCOPE = { engagementName: 'CagriSema Pre-Launch', focalAsset: 'drug:cagrisema' };

const DECISIONS = [
  {
    id: 'd1',
    statement: 'Begin OBC framework work pre-PDUFA',
    owner: 'Riya · Strategy',
    timing: 'pre-PDUFA',
    scenarioId: 'scn-A',
    scenarioName: 'Lilly Offensive',
    evidenceChain: [
      { factId: 'f1', predicate: 'trial_result' },
      { factId: 'f2', predicate: 'payer_policy' },
    ],
    disposition: 'committed' as const,
    rationale: 'OBC opens a defensible Tier-2 path before Lilly responds.',
  },
  {
    id: 'd2',
    statement: 'Specialist-only launch in first 90 days',
    owner: 'Anika · CI',
    timing: 'first 90 days',
    scenarioId: 'scn-A',
    scenarioName: 'Lilly Offensive',
    evidenceChain: [{ factId: 'f3', predicate: 'channel_signal' }],
    disposition: 'committed' as const,
    rationale: 'Preserves premium pricing while access stabilises.',
  },
  {
    id: 'd3',
    statement: 'Hold pricing 90 days',
    owner: 'Pricing committee',
    timing: 'first 90 days',
    scenarioId: 'scn-A',
    scenarioName: 'Lilly Offensive',
    evidenceChain: [],
    disposition: 'contingent' as const,
    rationale: 'Pending payer formulary signals.',
  },
  {
    id: 'd4',
    statement: 'Direct-to-consumer cash channel',
    owner: 'Commercial',
    timing: 'H2 2027',
    scenarioId: 'scn-B',
    scenarioName: 'Payer Coalition',
    evidenceChain: [],
    disposition: 'parked' as const,
    rationale: 'Park unless payer landscape deteriorates.',
  },
];

const GAPS_RESOLVED = [
  { id: 'g1', importance: 'critical' as const,
    question: 'Projected CVS Caremark tier for CagriSema?',
    disposition: 'primary_research' as const,
    remediationNote: 'reach out to MMIT' },
  { id: 'g2', importance: 'high' as const,
    question: 'Specialist channel mix?',
    disposition: 'accept_uncertainty' as const },
  { id: 'g3', importance: 'medium' as const,
    question: 'KOL sentiment shift YoY?',
    disposition: 'descope' as const,
    remediationNote: 'not material to launch decisions' },
];

const GAPS_WITH_PENDING = [
  ...GAPS_RESOLVED,
  { id: 'g4', importance: 'critical' as const,
    question: 'Is Foundayo PDUFA confirmed for H2 2026?',
    disposition: 'pending' as const },
];

const SESSIONS = [
  {
    id: 'think_like_competitor' as const,
    title: 'Think Like Competitor',
    duration: '90 min',
    agenda: ['Open with Lilly Offensive scenario', 'Each team roleplays counter-moves', 'Capture rationale'],
    outputs: ['Move ledger Round 1-3', 'Counter-move confidence map'],
    escalationTriggers: ['Two consecutive low-confidence projections'],
  },
  {
    id: 'prioritise_implications' as const,
    title: 'Prioritise Implications',
    duration: '60 min',
    agenda: ['Cluster moves by NPV impact', 'Vote on top 5'],
    outputs: ['Prioritised implications list'],
  },
  {
    id: 'risk_mitigation' as const,
    title: 'Risk Mitigation',
    duration: '90 min',
    agenda: ['Each prioritised implication gets a mitigation plan', 'Identify decision owner + timing'],
    outputs: ['Committed decision ledger', 'Gap log'],
  },
];

function setup(overrides: any = {}) {
  const onOpenFact = vi.fn();
  const onExportArtifact = vi.fn();
  const onCloseEngagement = vi.fn();
  const utils = render(
    <DecisionsPage
      scope={SCOPE}
      decisions={DECISIONS as any}
      gaps={GAPS_RESOLVED as any}
      sessions={SESSIONS as any}
      onOpenFact={onOpenFact}
      onExportArtifact={onExportArtifact}
      onCloseEngagement={onCloseEngagement}
      {...overrides}
    />,
  );
  return { ...utils, onOpenFact, onExportArtifact, onCloseEngagement };
}

describe('DecisionsPage — header', () => {
  it('shows engagement scope', () => {
    setup();
    expect(screen.getByText(/CagriSema Pre-Launch/)).toBeInTheDocument();
  });

  it('shows disposition counts (committed/contingent/parked)', () => {
    setup();
    expect(screen.getByText(/2 committed/i)).toBeInTheDocument();
    expect(screen.getByText(/1 contingent/i)).toBeInTheDocument();
    expect(screen.getByText(/1 parked/i)).toBeInTheDocument();
  });
});

describe('DecisionsPage — decision ledger', () => {
  it('renders each decision with statement, owner, timing, scenario', () => {
    const { container } = setup();
    const row = container.querySelector('[data-decision-id="d1"]') as HTMLElement;
    expect(within(row).getByText(/Begin OBC framework/)).toBeInTheDocument();
    expect(within(row).getByText(/Riya · Strategy/)).toBeInTheDocument();
    // "pre-PDUFA" appears in both statement and timing field — getAllByText
    expect(within(row).getAllByText(/pre-PDUFA/).length).toBeGreaterThanOrEqual(1);
    expect(within(row).getByText(/Lilly Offensive/)).toBeInTheDocument();
  });

  it('renders evidence chips that fire onOpenFact', () => {
    const { container, onOpenFact } = setup();
    const chip = container.querySelector('[data-decision-id="d1"] [data-fact-id="f1"]') as HTMLElement;
    expect(chip).not.toBeNull();
    fireEvent.click(chip);
    expect(onOpenFact).toHaveBeenCalledWith('f1');
  });

  it('groups decisions by disposition with data-disposition attribute', () => {
    const { container } = setup();
    expect(container.querySelector('[data-decision-id="d1"][data-disposition="committed"]')).not.toBeNull();
    expect(container.querySelector('[data-decision-id="d3"][data-disposition="contingent"]')).not.toBeNull();
    expect(container.querySelector('[data-decision-id="d4"][data-disposition="parked"]')).not.toBeNull();
  });
});

describe('DecisionsPage — gap log', () => {
  it('renders gap rows with disposition badges', () => {
    const { container } = setup();
    const row = container.querySelector('[data-gap-id="g1"]') as HTMLElement;
    expect(within(row).getByText(/primary research/i)).toBeInTheDocument();
  });

  it('renders pending gap row with red warning style', () => {
    const { container } = setup({ gaps: GAPS_WITH_PENDING });
    const pending = container.querySelector('[data-gap-id="g4"][data-pending="true"]');
    expect(pending).not.toBeNull();
  });

  it('shows "no gaps" placeholder when empty', () => {
    setup({ gaps: [] });
    expect(screen.getByText(/no gaps recorded/i)).toBeInTheDocument();
  });
});

describe('DecisionsPage — facilitator guide', () => {
  it('renders all 3 sessions', () => {
    const { container } = setup();
    expect(container.querySelector('[data-session="think_like_competitor"]')).not.toBeNull();
    expect(container.querySelector('[data-session="prioritise_implications"]')).not.toBeNull();
    expect(container.querySelector('[data-session="risk_mitigation"]')).not.toBeNull();
  });

  it('each session shows title, duration, and agenda items', () => {
    const { container } = setup();
    const sec = container.querySelector('[data-session="think_like_competitor"]') as HTMLElement;
    expect(within(sec).getByText(/Think Like Competitor/)).toBeInTheDocument();
    expect(within(sec).getByText(/90 min/)).toBeInTheDocument();
    expect(within(sec).getByText(/Open with Lilly Offensive/)).toBeInTheDocument();
  });

  it('escalation triggers shown when present', () => {
    setup();
    expect(screen.getByText(/two consecutive low-confidence/i)).toBeInTheDocument();
  });
});

describe('DecisionsPage — footer + gating', () => {
  it('Export button fires onExportArtifact', () => {
    const { onExportArtifact } = setup();
    fireEvent.click(screen.getByRole('button', { name: /export pdf/i }));
    expect(onExportArtifact).toHaveBeenCalled();
  });

  it('Close engagement disabled when any gap is pending', () => {
    setup({ gaps: GAPS_WITH_PENDING });
    expect(screen.getByRole('button', { name: /close engagement/i })).toBeDisabled();
  });

  it('Close engagement enabled when all gaps resolved', () => {
    setup();
    expect(screen.getByRole('button', { name: /close engagement/i })).not.toBeDisabled();
  });

  it('clicking Close fires onCloseEngagement when enabled', () => {
    const { onCloseEngagement } = setup();
    fireEvent.click(screen.getByRole('button', { name: /close engagement/i }));
    expect(onCloseEngagement).toHaveBeenCalled();
  });
});

describe('DecisionsPage — accessibility', () => {
  it('uses a main landmark named "Decisions"', () => {
    setup();
    expect(screen.getByRole('main', { name: /decisions/i })).toBeInTheDocument();
  });

  it('each session has aria-labelledby', () => {
    const { container } = setup();
    const sessions = container.querySelectorAll('[data-session]');
    sessions.forEach((s) => {
      expect(s.getAttribute('aria-labelledby')).not.toBeNull();
    });
  });
});
