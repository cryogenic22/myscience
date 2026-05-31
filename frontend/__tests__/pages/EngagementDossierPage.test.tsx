/**
 * F7 — EngagementDossierPage tests.
 *
 * 8 ZS domains, fact-class glyphs, visual elements for visual-eligible
 * domains (patient journey, competitor table, payer landscape). Each
 * domain shows its priority pill from the Z5 matrix.
 *
 * NOTE: Distinct from the legacy `DossierPage` (PB-301 scaffold) which
 * renders a per-entity dossier at `/dossier/:entityType/:slug`. This is
 * the engagement-stage dossier — the v7 ZS-domain read.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import { EngagementDossierPage } from '../../src/pages/EngagementDossierPage';

const SCOPE = { focalAsset: 'drug:cagrisema', engagementName: 'CagriSema Pre-Launch' };

function domain(
  d: any,
  priority: any,
  state: any,
  factCount: number,
  extras: any = {},
) {
  return {
    domain: d,
    priority,
    state,
    facts: Array.from({ length: factCount }, (_, i) => ({
      id: `${d}-f${i}`,
      claim: `${d} fact ${i}`,
      factClass: (['reference', 'corporate', 'signal', 'inferred'] as const)[i % 4],
      sourceLabel: 'Lilly Q1 PR',
    })),
    ...extras,
  };
}

const FULL_DOMAINS = [
  domain('disease_and_patient', 'high', 'complete', 3, {
    patientJourney: [
      { stage: 'At risk',       count: 65_000_000, note: 'BMI >= 30' },
      { stage: 'Seeking care',  count: 12_000_000, note: 'Discussed weight w/ HCP' },
      { stage: 'Diagnosed',     count:  4_500_000, note: 'Coded obesity dx' },
      { stage: 'On therapy',    count:    900_000, note: 'GLP-1 active' },
    ],
  }),
  domain('clinical_profile', 'high', 'complete', 4),
  domain('competitive', 'critical', 'complete', 5, {
    competitors: [
      { name: 'Zepbound',  benchmark: '-22.5% weight (SURMOUNT-1)', status: 'incumbent' },
      { name: 'Wegovy HD', benchmark: '-20.3% weight',              status: 'in-house' },
      { name: 'Foundayo',  benchmark: 'oral; PDUFA H2 2026',        status: 'imminent' },
    ],
  }),
  domain('pricing_and_access', 'critical', 'in_progress', 2, {
    payers: [
      { name: 'CVS Caremark', tier: 'Tier 2', restriction: 'PA' },
      { name: 'Express Scripts', tier: 'Tier 3', restriction: 'PA + step-edit' },
    ],
  }),
  domain('commercial_operational', 'medium', 'gap', 0),
  domain('hcp_and_patient',     'high',     'complete', 3),
  domain('pipeline_and_macro',  'high',     'complete', 4),
  domain('wargame_specific',    'high',     'in_progress', 1),
];

function setup(overrides: any = {}) {
  const onJumpToDomain = vi.fn();
  const onOpenFact = vi.fn();
  const onMarkComplete = vi.fn();
  const utils = render(
    <EngagementDossierPage
      scope={SCOPE}
      domains={FULL_DOMAINS as any}
      onJumpToDomain={onJumpToDomain}
      onOpenFact={onOpenFact}
      onMarkComplete={onMarkComplete}
      {...overrides}
    />,
  );
  return { ...utils, onJumpToDomain, onOpenFact, onMarkComplete };
}

describe('EngagementDossierPage — domain TOC', () => {
  it('renders 8 TOC chips with data-toc-domain', () => {
    const { container } = setup();
    expect(container.querySelectorAll('[data-toc-domain]').length).toBe(8);
  });

  it('clicking a chip fires onJumpToDomain', () => {
    const { container, onJumpToDomain } = setup();
    fireEvent.click(container.querySelector('[data-toc-domain="competitive"]')!);
    expect(onJumpToDomain).toHaveBeenCalledWith('competitive');
  });
});

describe('EngagementDossierPage — domain sections', () => {
  it('renders 8 domain sections', () => {
    const { container } = setup();
    expect(container.querySelectorAll('section[data-domain]').length).toBe(8);
  });

  it('disease_and_patient renders the patient journey flow', () => {
    const { container } = setup();
    const sec = container.querySelector('section[data-domain="disease_and_patient"]') as HTMLElement;
    expect(within(sec).getByText(/At risk/)).toBeInTheDocument();
    expect(within(sec).getByText(/Seeking care/)).toBeInTheDocument();
    expect(within(sec).getByText(/Diagnosed/)).toBeInTheDocument();
    expect(within(sec).getByText(/On therapy/)).toBeInTheDocument();
  });

  it('competitive renders the competitor table', () => {
    const { container } = setup();
    const sec = container.querySelector('section[data-domain="competitive"]') as HTMLElement;
    expect(within(sec).getByText('Zepbound')).toBeInTheDocument();
    expect(within(sec).getByText(/SURMOUNT-1/)).toBeInTheDocument();
  });

  it('pricing_and_access renders the payer landscape', () => {
    const { container } = setup();
    const sec = container.querySelector('section[data-domain="pricing_and_access"]') as HTMLElement;
    expect(within(sec).getByText('CVS Caremark')).toBeInTheDocument();
    expect(within(sec).getByText(/Tier 2/)).toBeInTheDocument();
  });

  it('empty domain shows the "return to Sources" placeholder', () => {
    const { container } = setup();
    const sec = container.querySelector('section[data-domain="commercial_operational"]') as HTMLElement;
    expect(within(sec).getByText(/return to Sources/i)).toBeInTheDocument();
  });
});

describe('EngagementDossierPage — facts', () => {
  it('each fact carries a fact-class data attribute', () => {
    const { container } = setup();
    const facts = container.querySelectorAll('[data-fact-class]');
    expect(facts.length).toBeGreaterThanOrEqual(20);
    const classes = new Set(
      Array.from(facts).map((f) => f.getAttribute('data-fact-class')),
    );
    expect(classes.has('reference')).toBe(true);
    expect(classes.has('corporate')).toBe(true);
    expect(classes.has('signal')).toBe(true);
    expect(classes.has('inferred')).toBe(true);
  });

  it('clicking a fact fires onOpenFact', () => {
    const { container, onOpenFact } = setup();
    const fact = container.querySelector('[data-fact-id]') as HTMLElement;
    fireEvent.click(fact);
    expect(onOpenFact).toHaveBeenCalled();
    expect(typeof onOpenFact.mock.calls[0][0]).toBe('string');
  });
});

describe('EngagementDossierPage — footer', () => {
  it('fires onMarkComplete when CTA clicked', () => {
    const { onMarkComplete } = setup();
    const btn = screen.getByRole('button', { name: /mark stage complete/i });
    fireEvent.click(btn);
    expect(onMarkComplete).toHaveBeenCalled();
  });
});

describe('EngagementDossierPage — accessibility', () => {
  it('uses a main landmark named "Engagement Dossier"', () => {
    setup();
    expect(screen.getByRole('main', { name: /engagement dossier/i })).toBeInTheDocument();
  });

  it('each section has aria-labelledby', () => {
    const { container } = setup();
    const sections = container.querySelectorAll('section[data-domain]');
    sections.forEach((s) => {
      expect(s.getAttribute('aria-labelledby')).not.toBeNull();
    });
  });
});
