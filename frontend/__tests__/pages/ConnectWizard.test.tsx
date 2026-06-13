/**
 * DataHub · F5 — Connect wizard tests.
 *
 * The differentiator: a curator can onboard a source end-to-end through the UI.
 * Covers the headline acceptance criteria from SPEC_DATA_HUB_FRONTEND §5:
 *   - all five automated connector kinds are offered
 *   - the lifecycle (draft→test→staged→prod) is visible
 *   - the contract gate BLOCKS register without trust tier + must-capture
 *   - a complete contract registers and reports the draft lifecycle status
 * Plus the pure `validateContract` helper (the gate logic, network-free).
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { ConnectWizard } from '../../src/pages/ConnectWizard';
import {
  validateContract,
  type OnboardingDraft,
  type RegisterResult,
} from '../../src/lib/datahubOnboarding';

function completeDraft(): OnboardingDraft {
  return {
    source_key: 'ema_chmp',
    label: 'EMA CHMP',
    connector_type: 'API_REST',
    config: { base_url: 'https://api.ema.europa.eu' },
    mappings: [{ source_field: 'title', target_field: 'name' }],
    contract: { trust_tier: 1, must_capture: ['source_doc_id'], license: null },
  };
}

describe('validateContract (the gate)', () => {
  it('blocks when trust tier is missing', () => {
    const d = completeDraft();
    d.contract.trust_tier = null;
    expect(validateContract(d).some((e) => /trust tier/i.test(e))).toBe(true);
  });

  it('blocks when no must-capture field is declared', () => {
    const d = completeDraft();
    d.contract.must_capture = ['', '  '];
    expect(validateContract(d).some((e) => /must-capture/i.test(e))).toBe(true);
  });

  it('blocks when a required connector config field is empty', () => {
    const d = completeDraft();
    d.config = {}; // base_url required for API_REST
    expect(validateContract(d).some((e) => /base url/i.test(e))).toBe(true);
  });

  it('passes a complete draft', () => {
    expect(validateContract(completeDraft())).toEqual([]);
  });
});

describe('ConnectWizard', () => {
  it('offers all five automated connector kinds', () => {
    render(<ConnectWizard />);
    for (const kind of ['API_REST', 'RSS', 'CSV_FILE', 'WEB_SCRAPE', 'WAREHOUSE']) {
      expect(document.querySelector(`[data-connector-option="${kind}"]`)).toBeInTheDocument();
    }
  });

  it('shows the draft→test→staged→prod lifecycle on the review step', () => {
    render(<ConnectWizard />);
    // advance to the review step (step 4)
    fireEvent.click(screen.getByText('Next →'));
    fireEvent.click(screen.getByText('Next →'));
    fireEvent.click(screen.getByText('Next →'));
    expect(document.querySelector('[data-lifecycle-strip]')).toBeInTheDocument();
    expect(document.querySelector('[data-lifecycle-stage="draft"]')).toBeInTheDocument();
    expect(document.querySelector('[data-lifecycle-stage="prod"]')).toBeInTheDocument();
  });

  it('keeps Register disabled until the contract is declared (the gate)', () => {
    render(<ConnectWizard />);
    fireEvent.click(screen.getByText('Next →'));
    fireEvent.click(screen.getByText('Next →'));
    fireEvent.click(screen.getByText('Next →'));
    const register = screen.getByRole('button', { name: /register source/i });
    expect(register).toBeDisabled();
    expect(document.querySelector('[data-contract-block]')).toBeInTheDocument();
  });

  it('registers a complete source and reports the draft lifecycle status', async () => {
    const onRegister = vi.fn(
      async (): Promise<RegisterResult> => ({
        ok: true,
        errors: [],
        record: {
          source_id: 'ema_chmp',
          status: 'draft',
          owner: null,
          contact: null,
          go_live_date: null,
          escalation: null,
          created_at: '2026-06-13T00:00:00Z',
          updated_at: '2026-06-13T00:00:00Z',
        },
      }),
    );
    const onDone = vi.fn();
    render(<ConnectWizard onRegister={onRegister} onDone={onDone} />);

    // Step 0 — identity + config
    fireEvent.change(screen.getByLabelText('Source key'), { target: { value: 'ema_chmp' } });
    fireEvent.change(screen.getByLabelText('Display label'), { target: { value: 'EMA CHMP' } });
    fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'https://api.ema.europa.eu' } });
    fireEvent.click(screen.getByText('Next →')); // → mapping
    fireEvent.click(screen.getByText('Next →')); // → contract

    // Step 2 — contract: trust tier + must-capture
    fireEvent.click(document.querySelector('[data-trust-tier="1"]')!);
    fireEvent.change(screen.getByLabelText('Must-capture field 1'), { target: { value: 'source_doc_id' } });
    fireEvent.click(screen.getByText('Next →')); // → review

    const register = screen.getByRole('button', { name: /register source/i });
    expect(register).not.toBeDisabled();
    fireEvent.click(register);

    await waitFor(() => expect(onRegister).toHaveBeenCalledTimes(1));
    expect(onDone).toHaveBeenCalledWith('ema_chmp');
    await waitFor(() =>
      expect(document.querySelector('[data-register-success]')).toBeInTheDocument(),
    );
  });
});
