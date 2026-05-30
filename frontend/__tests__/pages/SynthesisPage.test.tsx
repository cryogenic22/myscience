/**
 * F8 — SynthesisPage tests.
 *
 * Surfaces Z2's Insight type + rejected_insights. The fact-citation chain
 * is the load-bearing artifact: every insight has at least one citation
 * rendered with `data-fact-id`. Rejected insights are visible as the
 * audit artifact (Priya's procurement-grade point made UI-real).
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { SynthesisPage } from '../../src/pages/SynthesisPage';

const SCOPE = { engagementName: 'CagriSema Pre-Launch', focalAsset: 'drug:cagrisema' };

const INSIGHTS = [
  {
    id: 'i1',
    statement: "CagriSema's REDEFINE 4 miss compresses its differentiation window",
    strategicFrame: 'risk' as const,
    domain: 'competitive',
    derivedFrom: [
      { factId: 'f1', predicate: 'trial_result', contribution: 'REDEFINE 4 missed non-inferiority vs Zepbound' },
      { factId: 'f2', predicate: 'corporate_event', contribution: 'Lilly Q1 revenue +56% YoY' },
    ],
    synthesisTestRationale: 'Changes pricing-strategy decision in the wargame',
  },
  {
    id: 'i2',
    statement: 'OBC framework pre-PDUFA opens a defensible Tier-2 path',
    strategicFrame: 'opportunity' as const,
    domain: 'pricing_and_access',
    derivedFrom: [
      { factId: 'f3', predicate: 'payer_policy', contribution: 'CVS OBC pilot signals' },
    ],
    synthesisTestRationale: 'Identifies an unclaimed strategic move',
  },
  {
    id: 'i3',
    statement: 'Assumes specialist-first launch holds payer leverage',
    strategicFrame: 'assumption' as const,
    domain: 'commercial_operational',
    derivedFrom: [
      { factId: 'f4', predicate: 'channel_signal', contribution: 'Specialist channel mix 78%' },
    ],
    synthesisTestRationale: 'Names an assumption requiring stress-test',
  },
];

const REJECTED = [
  {
    id: 'r1',
    candidateStatement: 'KOLs and specialists are the natural CagriSema audience',
    rejectionReason: 'rejected: insight has no derived_from facts (cannot trace claim to evidence)',
    derivedFrom: [],
  },
  {
    id: 'r2',
    candidateStatement: 'Some claim without a frame',
    rejectionReason: 'rejected: strategic_frame must be one of [\'risk\', \'opportunity\', \'assumption\', \'trigger\']',
    derivedFrom: [{ factId: 'fX', predicate: 'p', contribution: 'c' }],
  },
];

function setup(overrides: any = {}) {
  const onOpenFact = vi.fn();
  const onMarkComplete = vi.fn();
  const utils = render(
    <SynthesisPage
      scope={SCOPE}
      insights={INSIGHTS as any}
      rejectedInsights={REJECTED as any}
      onOpenFact={onOpenFact}
      onMarkComplete={onMarkComplete}
      {...overrides}
    />,
  );
  return { ...utils, onOpenFact, onMarkComplete };
}

describe('SynthesisPage — header counts', () => {
  it('shows insights count, rejected count, pass-rate', () => {
    setup();
    // 3 insights, 2 rejected → pass-rate 3/(3+2) = 60%
    expect(screen.getByText(/3 insights/i)).toBeInTheDocument();
    expect(screen.getByText(/2 rejected/i)).toBeInTheDocument();
    expect(screen.getByText(/60%/)).toBeInTheDocument();
  });

  it('shows engagement scope', () => {
    setup();
    expect(screen.getByText(/CagriSema Pre-Launch/)).toBeInTheDocument();
  });
});

describe('SynthesisPage — frame filter', () => {
  it('renders 4 frame pills', () => {
    const { container } = setup();
    expect(container.querySelector('[data-frame="risk"]')).not.toBeNull();
    expect(container.querySelector('[data-frame="opportunity"]')).not.toBeNull();
    expect(container.querySelector('[data-frame="assumption"]')).not.toBeNull();
    expect(container.querySelector('[data-frame="trigger"]')).not.toBeNull();
  });

  it('clicking a pill toggles selection and filters the list', () => {
    const { container } = setup();
    const riskPill = container.querySelector('[data-frame="risk"]') as HTMLElement;
    fireEvent.click(riskPill);
    // Only i1 (risk) should be visible; i2/i3 hidden.
    // "REDEFINE 4 miss" appears in both the statement and a citation —
    // multiple matches is the correct behaviour; assert >=1 match instead.
    expect(screen.getAllByText(/REDEFINE 4 miss/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/OBC framework/)).toBeNull();
    expect(screen.queryByText(/specialist-first launch/)).toBeNull();
  });

  it('clicking the same pill again clears the filter', () => {
    const { container } = setup();
    const pill = container.querySelector('[data-frame="risk"]') as HTMLElement;
    fireEvent.click(pill);
    fireEvent.click(pill);
    expect(screen.getByText(/OBC framework/)).toBeInTheDocument();
  });

  it('frame pills have aria-pressed', () => {
    const { container } = setup();
    const pill = container.querySelector('[data-frame="risk"]') as HTMLElement;
    expect(pill.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(pill);
    expect(pill.getAttribute('aria-pressed')).toBe('true');
  });
});

describe('SynthesisPage — insight cards', () => {
  it('each insight renders statement, frame badge, domain, citations', () => {
    const { container } = setup();
    const card = container.querySelector('[data-insight-id="i1"]') as HTMLElement;
    // "REDEFINE 4 miss" appears in statement AND citation; getAllByText handles both.
    expect(within(card).getAllByText(/REDEFINE 4 miss/).length).toBeGreaterThan(0);
    expect(within(card).getByText(/^risk$/i)).toBeInTheDocument();
    expect(within(card).getByText(/competitive/i)).toBeInTheDocument();
    expect(container.querySelectorAll('[data-insight-id="i1"] [data-fact-id]').length).toBe(2);
  });

  it('clicking a citation fires onOpenFact', () => {
    const { container, onOpenFact } = setup();
    const cite = container.querySelector('[data-insight-id="i1"] [data-fact-id="f1"]') as HTMLElement;
    fireEvent.click(cite);
    expect(onOpenFact).toHaveBeenCalledWith('f1');
  });

  it('renders the synthesis_test rationale', () => {
    setup();
    expect(screen.getByText(/Changes pricing-strategy decision/)).toBeInTheDocument();
  });

  it('renders integrity error marker when an insight has zero citations (defence in depth)', () => {
    const broken = [{
      ...INSIGHTS[0],
      derivedFrom: [],
    }];
    setup({ insights: broken });
    expect(screen.getByText(/integrity error/i)).toBeInTheDocument();
  });
});

describe('SynthesisPage — rejected disclosure', () => {
  it('renders a <details> disclosure for rejected insights', () => {
    const { container } = setup();
    const details = container.querySelector('details[data-rejected]');
    expect(details).not.toBeNull();
  });

  it('expanding shows rejected candidates with rejection reason', () => {
    const { container } = setup();
    const details = container.querySelector('details[data-rejected]') as HTMLDetailsElement;
    details.open = true;
    // Re-render approximation: just check the markup is there in the DOM
    expect(within(details).getByText(/no derived_from facts/i)).toBeInTheDocument();
    expect(within(details).getByText(/strategic_frame must be one of/i)).toBeInTheDocument();
  });

  it('empty rejected list shows "No rejected candidates"', () => {
    setup({ rejectedInsights: [] });
    expect(screen.getByText(/no rejected candidates/i)).toBeInTheDocument();
  });
});

describe('SynthesisPage — empty insights', () => {
  it('shows placeholder when no insights', () => {
    setup({ insights: [] });
    expect(screen.getByText(/return to Dossier/i)).toBeInTheDocument();
  });
});

describe('SynthesisPage — footer', () => {
  it('fires onMarkComplete', () => {
    const { onMarkComplete } = setup();
    fireEvent.click(screen.getByRole('button', { name: /mark stage complete/i }));
    expect(onMarkComplete).toHaveBeenCalled();
  });
});

describe('SynthesisPage — accessibility', () => {
  it('uses a main landmark', () => {
    setup();
    expect(screen.getByRole('main', { name: /synthesis/i })).toBeInTheDocument();
  });
});
