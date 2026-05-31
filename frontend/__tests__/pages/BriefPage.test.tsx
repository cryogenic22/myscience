/**
 * F5 — BriefPage tests.
 *
 * Renders the Z4 BCB + Z5 priority matrix as the engagement's scoping
 * artifact. Launch-only per Riya. Critical-priority cells use the accent
 * color. Empty competitive set falls back to a research-needed placeholder.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { BriefPage } from '../../src/pages/BriefPage';

const DOMAINS = [
  'disease_and_patient',
  'clinical_profile',
  'competitive',
  'pricing_and_access',
  'commercial_operational',
  'hcp_and_patient',
  'pipeline_and_macro',
  'wargame_specific',
] as const;

const baseBrief = {
  id: 'b1',
  focalAsset: 'drug:cagrisema',
  situation: 'launch' as const,
  strategicDecisions: [
    {
      statement: 'Should Novo pre-launch CagriSema at WAC parity with Zepbound?',
      rationale: 'Pricing decision drives 5-year NPV by >$2B.',
    },
    {
      statement: 'Defend specialist-only launch or accelerate PCP enablement?',
      rationale: 'Trade-off between premium pricing and volume.',
    },
  ],
  competitiveSet: [
    { entityRef: 'drug:zepbound', threatLevel: 'primary' as const,
      note: 'incumbent, SURMOUNT-1 22.5% benchmark' },
    { entityRef: 'drug:wegovy_hd', threatLevel: 'secondary' as const,
      note: 'in-house cannibalisation risk' },
  ],
  successCriteria: ['defensible 5-year NPV', '3 mutually exclusive pricing paths'],
  constraints: ['no MFN reference in messaging', 'workshop in 4 days'],
  signedOff: false,
};

function baseMatrix() {
  return {
    cells: {
      disease_and_patient:    'high',
      clinical_profile:       'high',
      competitive:            'critical',
      pricing_and_access:     'critical',
      commercial_operational: 'medium',
      hcp_and_patient:        'high',
      pipeline_and_macro:     'high',
      wargame_specific:       'high',
    },
  } as const;
}

describe('BriefPage — header and scope', () => {
  it('renders focal asset and the Launch situation pill', () => {
    render(
      <BriefPage brief={baseBrief} matrix={baseMatrix() as any} onSignOff={() => {}} />,
    );
    expect(screen.getByText(/drug:cagrisema/)).toBeInTheDocument();
    expect(screen.getByText(/^launch$/i)).toBeInTheDocument();
  });

  it('renders >= 1 strategic decision', () => {
    render(
      <BriefPage brief={baseBrief} matrix={baseMatrix() as any} onSignOff={() => {}} />,
    );
    expect(
      screen.getByText(/Should Novo pre-launch CagriSema at WAC parity/),
    ).toBeInTheDocument();
  });

  it('renders a "demo supports Launch only" stub when situation != launch', () => {
    const offBrief = { ...baseBrief, situation: 'defense' as any };
    render(
      <BriefPage brief={offBrief} matrix={baseMatrix() as any} onSignOff={() => {}} />,
    );
    expect(screen.getByText(/launch only/i)).toBeInTheDocument();
  });
});

describe('BriefPage — competitive set', () => {
  it('renders threats grouped by level', () => {
    render(
      <BriefPage brief={baseBrief} matrix={baseMatrix() as any} onSignOff={() => {}} />,
    );
    const primarySection = screen.getByText(/primary/i).closest('section');
    expect(primarySection).not.toBeNull();
    expect(within(primarySection as HTMLElement).getByText(/drug:zepbound/)).toBeInTheDocument();
  });

  it('shows "awaiting primary research" placeholder when competitive set is empty', () => {
    const empty = { ...baseBrief, competitiveSet: [] };
    render(
      <BriefPage brief={empty} matrix={baseMatrix() as any} onSignOff={() => {}} />,
    );
    expect(screen.getByText(/awaiting primary research/i)).toBeInTheDocument();
  });
});

describe('BriefPage — priority matrix grid', () => {
  it('renders all 8 ZS dossier domains', () => {
    const { container } = render(
      <BriefPage brief={baseBrief} matrix={baseMatrix() as any} onSignOff={() => {}} />,
    );
    DOMAINS.forEach((d) => {
      const cell = container.querySelector(`[data-domain="${d}"]`);
      expect(cell).not.toBeNull();
    });
  });

  it('critical-priority cells get data-priority="critical"', () => {
    const { container } = render(
      <BriefPage brief={baseBrief} matrix={baseMatrix() as any} onSignOff={() => {}} />,
    );
    const critical = container.querySelectorAll('[data-priority="critical"]');
    // baseMatrix() has 2 criticals: competitive, pricing_and_access
    expect(critical.length).toBe(2);
  });

  it('clicking a cell with onCellEdit cycles the priority', () => {
    const onCellEdit = vi.fn();
    const { container } = render(
      <BriefPage
        brief={baseBrief}
        matrix={baseMatrix() as any}
        onSignOff={() => {}}
        onCellEdit={onCellEdit}
      />,
    );
    const cell = container.querySelector('[data-domain="commercial_operational"]') as HTMLElement;
    // commercial_operational starts at 'medium'; next is 'critical'
    fireEvent.click(cell);
    expect(onCellEdit).toHaveBeenCalledWith('commercial_operational', 'critical');
  });

  it('cell click does not fire when onCellEdit is unset (read-only)', () => {
    const { container } = render(
      <BriefPage brief={baseBrief} matrix={baseMatrix() as any} onSignOff={() => {}} />,
    );
    const cell = container.querySelector('[data-domain="competitive"]') as HTMLElement;
    // No onCellEdit prop; clicking should be a no-op (no spy to assert; this
    // is mostly a smoke test — no crash)
    fireEvent.click(cell);
  });
});

describe('BriefPage — sign-off', () => {
  it('renders draft state when not signed off', () => {
    render(
      <BriefPage brief={baseBrief} matrix={baseMatrix() as any} onSignOff={() => {}} />,
    );
    expect(screen.getByText(/draft/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /sign off/i }),
    ).not.toBeDisabled();
  });

  it('fires onSignOff when sign-off button clicked in draft state', () => {
    const onSignOff = vi.fn();
    render(
      <BriefPage brief={baseBrief} matrix={baseMatrix() as any} onSignOff={onSignOff} />,
    );
    fireEvent.click(screen.getByRole('button', { name: /sign off/i }));
    expect(onSignOff).toHaveBeenCalledTimes(1);
  });

  it('renders signed-off state when signedOff', () => {
    const signed = {
      ...baseBrief,
      signedOff: true,
      signedOffBy: 'anika',
      signedOffAt: '2026-05-29T09:00:00Z',
    };
    render(
      <BriefPage brief={signed} matrix={baseMatrix() as any} onSignOff={() => {}} />,
    );
    expect(screen.getByText(/signed off by anika/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /signed off/i }),
    ).toBeDisabled();
  });
});

describe('BriefPage — accessibility', () => {
  it('uses a main landmark named "Brief and Scope"', () => {
    render(
      <BriefPage brief={baseBrief} matrix={baseMatrix() as any} onSignOff={() => {}} />,
    );
    expect(screen.getByRole('main', { name: /brief and scope/i })).toBeInTheDocument();
  });

  it('renders the priority matrix as a table', () => {
    const { container } = render(
      <BriefPage brief={baseBrief} matrix={baseMatrix() as any} onSignOff={() => {}} />,
    );
    expect(container.querySelector('table[aria-label="Priority matrix"]')).not.toBeNull();
  });
});
