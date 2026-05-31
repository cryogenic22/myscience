/**
 * F9 — GapsPage tests.
 *
 * Sits between Dossier and Scenarios (Riya's structural correction). The
 * "Mark stage complete" CTA is workshop-blocking when any critical gap is
 * pending — that's the actual gate before scenarios are run.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { GapsPage } from '../../src/pages/GapsPage';

const SCOPE = { engagementName: 'CagriSema Pre-Launch', focalAsset: 'drug:cagrisema' };

const GAPS_WITH_CRITICAL_PENDING = [
  {
    id: 'g1',
    domain: 'pricing_and_access',
    importance: 'critical',
    question: 'What is the projected CVS Caremark tier for CagriSema at launch?',
    expectedSourceClass: 'payer_pricing',
    remediation: 'pending',
    blocksScenarios: ['scn-A', 'scn-B'],
  },
  {
    id: 'g2',
    domain: 'competitive',
    importance: 'critical',
    question: 'Is Foundayo PDUFA still on track for H2 2026?',
    expectedSourceClass: 'regulatory_api',
    remediation: 'primary_research',
    remediationNote: 'reach out to FDA contact',
  },
  {
    id: 'g3',
    domain: 'commercial_operational',
    importance: 'high',
    question: 'Specialist channel mix in obesity 2025?',
    expectedSourceClass: 'internal_documents',
    remediation: 'pending',
  },
  {
    id: 'g4',
    domain: 'hcp_and_patient',
    importance: 'medium',
    question: 'KOL sentiment shift YoY?',
    remediation: 'accept_uncertainty',
    remediationNote: 'will not move decisions',
  },
];

const NO_CRITICAL_PENDING = GAPS_WITH_CRITICAL_PENDING.map((g) =>
  g.importance === 'critical' && g.remediation === 'pending'
    ? { ...g, remediation: 'primary_research' as const }
    : g,
);

function setup(overrides: any = {}) {
  const onSetRemediation = vi.fn();
  const onMarkComplete = vi.fn();
  const utils = render(
    <GapsPage
      scope={SCOPE}
      gaps={GAPS_WITH_CRITICAL_PENDING as any}
      onSetRemediation={onSetRemediation}
      onMarkComplete={onMarkComplete}
      {...overrides}
    />,
  );
  return { ...utils, onSetRemediation, onMarkComplete };
}

describe('GapsPage — header', () => {
  it('shows total / blocking / unresolved counts', () => {
    setup();
    // total=4, blocking=1 (g1 blocks scenarios), unresolved=2 (g1, g3 pending)
    expect(screen.getByText(/4 gaps/i)).toBeInTheDocument();
    expect(screen.getByText(/1 blocking/i)).toBeInTheDocument();
    expect(screen.getByText(/2 unresolved/i)).toBeInTheDocument();
  });
});

describe('GapsPage — importance filter', () => {
  it('renders 3 importance pills', () => {
    const { container } = setup();
    expect(container.querySelector('[data-importance="critical"]')).not.toBeNull();
    expect(container.querySelector('[data-importance="high"]')).not.toBeNull();
    expect(container.querySelector('[data-importance="medium"]')).not.toBeNull();
  });

  it('clicking a pill filters the list', () => {
    const { container } = setup();
    fireEvent.click(container.querySelector('[data-importance="critical"]') as HTMLElement);
    expect(screen.getByText(/CVS Caremark tier/)).toBeInTheDocument();
    expect(screen.queryByText(/Specialist channel mix/)).toBeNull();
  });

  it('pills have aria-pressed', () => {
    const { container } = setup();
    const pill = container.querySelector('[data-importance="critical"]') as HTMLElement;
    expect(pill.getAttribute('aria-pressed')).toBe('false');
    fireEvent.click(pill);
    expect(pill.getAttribute('aria-pressed')).toBe('true');
  });
});

describe('GapsPage — gap cards', () => {
  it('each gap shows importance badge, domain, question, remediation', () => {
    const { container } = setup();
    const card = container.querySelector('[data-gap-id="g1"]') as HTMLElement;
    expect(within(card).getByText(/^critical$/i)).toBeInTheDocument();
    expect(within(card).getByText(/pricing_and_access/i)).toBeInTheDocument();
    expect(within(card).getByText(/CVS Caremark tier/)).toBeInTheDocument();
    expect(within(card).getByText(/pending/i)).toBeInTheDocument();
  });

  it('pending gap shows 3 remediation action buttons', () => {
    const { container } = setup();
    const card = container.querySelector('[data-gap-id="g1"]') as HTMLElement;
    expect(within(card).getByRole('button', { name: /primary research/i })).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: /accept uncertainty/i })).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: /descope/i })).toBeInTheDocument();
  });

  it('clicking a remediation action fires onSetRemediation', () => {
    const { container, onSetRemediation } = setup();
    const card = container.querySelector('[data-gap-id="g1"]') as HTMLElement;
    fireEvent.click(within(card).getByRole('button', { name: /accept uncertainty/i }));
    expect(onSetRemediation).toHaveBeenCalledWith('g1', 'accept_uncertainty');
  });

  it('non-pending gap does NOT show action buttons', () => {
    const { container } = setup();
    const card = container.querySelector('[data-gap-id="g2"]') as HTMLElement;
    expect(within(card).queryByRole('button', { name: /primary research/i })).toBeNull();
    expect(within(card).queryByRole('button', { name: /descope/i })).toBeNull();
  });

  it('gap with blocksScenarios shows the "blocks" line', () => {
    const { container } = setup();
    const card = container.querySelector('[data-gap-id="g1"]') as HTMLElement;
    expect(within(card).getByText(/blocks/i)).toBeInTheDocument();
    expect(within(card).getByText(/scn-A/)).toBeInTheDocument();
  });
});

describe('GapsPage — readiness banner', () => {
  it('shows blocking banner when any critical gap is pending', () => {
    const { container } = setup();
    const banner = container.querySelector('[data-banner="blocking"]');
    expect(banner).not.toBeNull();
    expect(within(banner as HTMLElement).getByText(/critical gaps unresolved/i)).toBeInTheDocument();
  });

  it('shows ready banner when no critical gap is pending', () => {
    const { container } = setup({ gaps: NO_CRITICAL_PENDING });
    expect(container.querySelector('[data-banner="ready"]')).not.toBeNull();
  });
});

describe('GapsPage — workshop blocking', () => {
  it('"Mark stage complete" is disabled when any critical gap is pending', () => {
    setup();
    expect(screen.getByRole('button', { name: /mark stage complete/i })).toBeDisabled();
  });

  it('"Mark stage complete" is enabled when no critical pending', () => {
    setup({ gaps: NO_CRITICAL_PENDING });
    expect(screen.getByRole('button', { name: /mark stage complete/i })).not.toBeDisabled();
  });
});

describe('GapsPage — empty gaps', () => {
  it('shows "All caught" calm state when no gaps', () => {
    setup({ gaps: [] });
    expect(screen.getByText(/all caught/i)).toBeInTheDocument();
  });
});

describe('GapsPage — accessibility', () => {
  it('uses a main landmark', () => {
    setup();
    expect(screen.getByRole('main', { name: /intelligence gaps/i })).toBeInTheDocument();
  });
});
