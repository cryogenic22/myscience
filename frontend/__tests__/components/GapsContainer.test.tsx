/**
 * UX05 — GapsContainer tests.
 *
 * Covers loading → not-assembled (assemble action) → ready, the error path,
 * and the client-side remediation flow (a pending remediation resolves and
 * unblocks the readiness banner). The api module is mocked; GapsPage renders
 * for real (verifies the DTO→Gap mapping + the fillMethod render).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../src/api', () => {
  class DossierNotAssembled extends Error {}
  return {
    DossierNotAssembled,
    dossierKbApi: { gaps: vi.fn(), assemble: vi.fn() },
    gapRemediationApi: { list: vi.fn(), set: vi.fn() },
  };
});

import { dossierKbApi, gapRemediationApi, DossierNotAssembled } from '../../src/api';
import GapsContainer from '../../src/components/ci/GapsContainer';

const ENGAGEMENT = { id: 'e1', name: 'Wegovy defense', asset: 'drug:semaglutide' } as any;

function gapsDTO(overrides: Partial<any> = {}) {
  return {
    coverage_score: 0.25,
    gaps: [
      { domain: 'pricing_and_access', priority: 'critical', importance: 'high',
        text: 'No evidence collected yet for payer & access.', method: 'Pull NADAC + formulary tiers.' },
      { domain: 'clinical_profile', priority: 'medium', importance: 'medium',
        text: 'No evidence collected yet for clinical profile.', method: 'Pull trial readouts.' },
    ],
    ...overrides,
  };
}

describe('GapsContainer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // default: no persisted remediations, set succeeds.
    (gapRemediationApi.list as any).mockResolvedValue({});
    (gapRemediationApi.set as any).mockResolvedValue({ gap_domain: 'x', remediation: 'descope', note: null });
  });

  it('shows the not-assembled state with an assemble action', async () => {
    (dossierKbApi.gaps as any).mockRejectedValue(new DossierNotAssembled());
    render(<GapsContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('gaps-empty')).toBeInTheDocument());
    expect(screen.getByTestId('gaps-assemble')).toBeInTheDocument();
  });

  it('renders the gaps with coverage header + fill method', async () => {
    (dossierKbApi.gaps as any).mockResolvedValue(gapsDTO());
    render(<GapsContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('gaps-ready')).toBeInTheDocument());
    expect(screen.getByText('25%')).toBeInTheDocument();                 // coverage stat
    expect(screen.getByText(/No evidence collected yet for payer & access/)).toBeInTheDocument();
    expect(screen.getByText(/Pull NADAC \+ formulary tiers/)).toBeInTheDocument();  // fillMethod
  });

  it('blocks completion on a critical pending gap, then unblocks after remediation', async () => {
    (dossierKbApi.gaps as any).mockResolvedValue(gapsDTO());
    render(<GapsContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('gaps-ready')).toBeInTheDocument());

    // critical (pricing) gap pending → blocking banner present.
    expect(document.querySelector('[data-banner="blocking"]')).toBeTruthy();

    // resolve the critical gap via "Primary research".
    const card = document.querySelector('[data-gap-id="gap-pricing_and_access"]')!;
    const btn = Array.from(card.querySelectorAll('button'))
      .find((b) => /primary research/i.test(b.textContent || ''))!;
    fireEvent.click(btn);

    await waitFor(() => expect(document.querySelector('[data-banner="ready"]')).toBeTruthy());
    // PB-UX05b: the choice is persisted by raw gap domain.
    expect(gapRemediationApi.set).toHaveBeenCalledWith('e1', 'pricing_and_access', 'primary_research');
  });

  it('seeds remediation from the persisted store on load (PB-UX05b)', async () => {
    (dossierKbApi.gaps as any).mockResolvedValue(gapsDTO());
    (gapRemediationApi.list as any).mockResolvedValue({
      pricing_and_access: { gap_domain: 'pricing_and_access', remediation: 'descope', note: null },
    });
    render(<GapsContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('gaps-ready')).toBeInTheDocument());
    // critical gap already resolved (descope) → not blocking → workshop-ready.
    expect(document.querySelector('[data-banner="ready"]')).toBeTruthy();
  });

  it('shows an error (not the empty state) on a non-404 failure', async () => {
    (dossierKbApi.gaps as any).mockRejectedValue(new Error('500: boom'));
    render(<GapsContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('gaps-error')).toBeInTheDocument());
    expect(screen.queryByTestId('gaps-empty')).not.toBeInTheDocument();
  });
});
