import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ConnectWizard } from '../ConnectWizard';

// Drive the 4-step wizard to a complete, valid contract so the Register button
// is enabled, then assert a rejected register() surfaces an honest error banner
// rather than being swallowed (leaving the button silently re-enabled).
async function completeContractAndRegister() {
  // Step 0 — default connector type is API_REST (requires Base URL).
  fireEvent.change(screen.getByLabelText('Source key'), { target: { value: 'ema_chmp' } });
  fireEvent.change(screen.getByLabelText('Display label'), { target: { value: 'EMA CHMP' } });
  fireEvent.change(screen.getByLabelText('Base URL'), { target: { value: 'https://api.example.com/v1' } });
  fireEvent.click(screen.getByRole('button', { name: /next/i })); // → step 1 (mappings, optional)
  fireEvent.click(screen.getByRole('button', { name: /next/i })); // → step 2 (contract)

  fireEvent.click(screen.getByRole('radio', { name: /Tier 1/i }));
  fireEvent.change(screen.getByLabelText('Must-capture field 1'), { target: { value: 'opinion_id' } });
  fireEvent.click(screen.getByRole('button', { name: /next/i })); // → step 3 (review)

  const registerBtn = screen.getByRole('button', { name: /register source/i });
  expect(registerBtn).toBeEnabled();
  fireEvent.click(registerBtn);
}

describe('ConnectWizard', () => {
  it('surfaces a register failure instead of swallowing it', async () => {
    const onRegister = vi.fn().mockRejectedValue(new Error('network boom'));
    render(<ConnectWizard onRegister={onRegister} />);

    await completeContractAndRegister();

    await waitFor(() => expect(onRegister).toHaveBeenCalledTimes(1));
    // The rejection must be shown — not vanish, leaving the user staring at a
    // re-enabled button with no idea the write failed.
    expect(await screen.findByText(/network boom/i)).toBeInTheDocument();
  });
});
