/**
 * KB3 — DossierContainer tests.
 *
 * Covers the four states: loading → not-assembled (with assemble action) →
 * ready, plus the error path. The api module is mocked; EngagementDossierPage
 * renders for real (verifies the DTO→DomainView mapping doesn't throw).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// The factory is hoisted, so DossierNotAssembled is defined inside it and
// imported back — both the container and the test then share one class, so
// `instanceof` works.
vi.mock('../../src/api', () => {
  class DossierNotAssembled extends Error {}
  return {
    DossierNotAssembled,
    dossierKbApi: { get: vi.fn(), assemble: vi.fn() },
  };
});

import { dossierKbApi, DossierNotAssembled } from '../../src/api';
import DossierContainer from '../../src/components/ci/DossierContainer';

const DOMAINS = [
  'disease_and_patient', 'clinical_profile', 'competitive', 'pricing_and_access',
  'commercial_operational', 'hcp_and_patient', 'pipeline_and_macro', 'wargame_specific',
];

function makeSnapshot(overrides: Partial<any> = {}) {
  return {
    id: 'snap-1', engagement_id: 'e1', focal_asset: 'drug:wegovy',
    version: 1, coverage_score: 0.25, fact_count: 2,
    assembled_by: 'analyst', assembled_at: '2026-05-31T00:00:00Z',
    domains: DOMAINS.map((d) => ({
      domain: d,
      priority: d === 'competitive' || d === 'pricing_and_access' ? 'critical' : 'medium',
      state: d === 'pricing_and_access' ? 'in_progress' : 'gap',
      facts: d === 'pricing_and_access'
        ? [{ id: 'f1', claim: 'Wac usd monthly: 675', factClass: 'corporate', sourceLabel: 'sec' }]
        : [],
    })),
    ...overrides,
  };
}

const ENGAGEMENT = { id: 'e1', name: 'Wegovy defense', asset: 'drug:wegovy' } as any;

describe('DossierContainer', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows the empty state with an assemble action when no dossier exists', async () => {
    (dossierKbApi.get as any).mockRejectedValue(new DossierNotAssembled());
    render(<DossierContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('dossier-empty')).toBeInTheDocument());
    expect(screen.getByTestId('dossier-assemble')).toBeInTheDocument();
  });

  it('assembles on click and renders the dossier', async () => {
    (dossierKbApi.get as any).mockRejectedValue(new DossierNotAssembled());
    (dossierKbApi.assemble as any).mockResolvedValue(makeSnapshot());
    render(<DossierContainer engagement={ENGAGEMENT} />);

    await waitFor(() => expect(screen.getByTestId('dossier-assemble')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('dossier-assemble'));

    await waitFor(() => expect(screen.getByTestId('dossier-ready')).toBeInTheDocument());
    expect(dossierKbApi.assemble).toHaveBeenCalledWith('e1');
    // KB header shows the version + coverage.
    expect(screen.getByText('v1')).toBeInTheDocument();
    expect(screen.getByText('25%')).toBeInTheDocument();
  });

  it('renders the existing dossier on load', async () => {
    (dossierKbApi.get as any).mockResolvedValue(makeSnapshot({ version: 3, coverage_score: 0.5 }));
    render(<DossierContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('dossier-ready')).toBeInTheDocument());
    expect(screen.getByText('v3')).toBeInTheDocument();
    expect(screen.getByText('50%')).toBeInTheDocument();
  });

  it('renders per-domain readiness and opens the provenance panel on fact click (PB-UX03)', async () => {
    const snap = makeSnapshot({ readiness: 0.42 });
    // give the in_progress domain a fact with a source url + readiness
    const pa = snap.domains.find((d: any) => d.domain === 'pricing_and_access');
    pa.readiness = 0.6;
    pa.facts = [{ id: 'f1', claim: 'WAC $675/mo', factClass: 'corporate', sourceLabel: 'sec', sourceUrl: 'https://sec.gov/x' }];
    (dossierKbApi.get as any).mockResolvedValue(snap);
    render(<DossierContainer engagement={ENGAGEMENT} />);

    await waitFor(() => expect(screen.getByTestId('dossier-ready')).toBeInTheDocument());
    // engagement readiness surfaced (KB header stat + page-header readiness bar)
    expect(screen.getAllByText('42%').length).toBeGreaterThan(0);
    // panel closed initially, then opens when the fact is clicked
    expect(screen.queryByTestId('provenance-panel')).not.toBeInTheDocument();
    fireEvent.click(screen.getByText('WAC $675/mo'));
    await waitFor(() => expect(screen.getByTestId('provenance-panel')).toBeInTheDocument());
    expect(screen.getByTestId('provenance-source-link')).toBeInTheDocument();
  });

  it('shows an error (not the empty state) on a non-404 failure', async () => {
    (dossierKbApi.get as any).mockRejectedValue(new Error('500: boom'));
    render(<DossierContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('dossier-error')).toBeInTheDocument());
    expect(screen.queryByTestId('dossier-empty')).not.toBeInTheDocument();
  });
});
