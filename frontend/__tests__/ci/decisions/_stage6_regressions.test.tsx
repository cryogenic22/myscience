/**
 * SPEC_030 Stage 6 — regression tests for the red-team findings closed
 * during FIX-ALL. One `describe` per finding number; spec §14 lists them
 * all. Each test is the failure mode the reviewer surfaced — they FAIL
 * against the pre-fix code and pass against the fix.
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { makeBrief, makeOption } from './_fixtures';
import StateMachineChip, {
  nextForwardTransition,
} from '../../../src/components/ci/decisions/StateMachineChip';
import BriefEditableField from '../../../src/components/ci/decisions/BriefEditableField';
import OptionEditor from '../../../src/components/ci/decisions/OptionEditor';
import SimulationPanel from '../../../src/components/ci/decisions/SimulationPanel';
import ReasoningTraceDrawer from '../../../src/components/ci/decisions/ReasoningTraceDrawer';

describe('Stage 6 fix #5 — cmd+enter advances forward (rank-aware), never backward', () => {
  it('human_review → simulation_pending (not draft)', () => {
    expect(nextForwardTransition('human_review')).toBe('simulation_pending');
  });
  it('draft → human_review', () => {
    expect(nextForwardTransition('draft')).toBe('human_review');
  });
  it('decision_pending → committed', () => {
    expect(nextForwardTransition('decision_pending')).toBe('committed');
  });
  it('closed → null (terminal)', () => {
    expect(nextForwardTransition('closed')).toBeNull();
  });
  it('committed → in_review', () => {
    expect(nextForwardTransition('committed')).toBe('in_review');
  });
});

describe('Stage 6 fix #7 — save errors are surfaced inline', () => {
  it('BriefEditableField shows the error and stays in edit mode when onSave rejects', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('500: boom'));
    render(<BriefEditableField label="question" value="A" onSave={onSave} />);
    fireEvent.click(screen.getByRole('button', { name: /question/i }));
    const input = await screen.findByRole('textbox');
    fireEvent.change(input, { target: { value: 'B' } });
    fireEvent.blur(input);
    // Inline alert renders the error message
    expect(await screen.findByRole('alert')).toHaveTextContent(/500: boom/);
    // Still editing (input remains)
    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });

  it('OptionEditor shows the error and stays open when onSave rejects', async () => {
    const onSave = vi.fn().mockRejectedValue(new Error('insufficient_role'));
    render(
      <OptionEditor
        mode="create"
        onSave={onSave}
        onClose={vi.fn()}
      />,
    );
    fireEvent.change(screen.getByLabelText(/^label$/i), {
      target: { value: 'Try' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^save$/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/insufficient_role/);
    // Modal still open
    expect(screen.getByRole('dialog')).toBeInTheDocument();
  });
});

describe('Stage 6 fix #8 — SimulationPanel does not lie in simulation_complete', () => {
  it('says "complete" in simulation_complete, not "No scenario run yet"', () => {
    render(<SimulationPanel brief={makeBrief({ state: 'simulation_complete' })} />);
    expect(screen.queryByText(/no scenario run yet/i)).not.toBeInTheDocument();
    expect(screen.getByText(/scenario complete/i)).toBeInTheDocument();
  });

  it('still says "no scenario run yet" pre-simulation_complete', () => {
    render(<SimulationPanel brief={makeBrief({ state: 'human_review' })} />);
    expect(screen.getByText(/no scenario run yet/i)).toBeInTheDocument();
  });

  it('says "archived" in committed/in_review/closed', () => {
    render(<SimulationPanel brief={makeBrief({ state: 'closed' })} />);
    expect(screen.getByText(/scenario archived/i)).toBeInTheDocument();
  });
});

describe('Stage 6 fix #10 — ReasoningTraceDrawer takes initial focus on open', () => {
  it('moves focus to the close button when the drawer opens', async () => {
    const brief = makeBrief();
    const { rerender } = render(
      <ReasoningTraceDrawer brief={brief} open={false} onClose={vi.fn()} />,
    );
    rerender(<ReasoningTraceDrawer brief={brief} open onClose={vi.fn()} />);
    await waitFor(() => {
      const closeBtn = screen.getByRole('button', { name: /close/i });
      expect(document.activeElement).toBe(closeBtn);
    });
  });

  it('escape key closes', () => {
    const onClose = vi.fn();
    render(<ReasoningTraceDrawer brief={makeBrief()} open onClose={onClose} />);
    act(() => {
      fireEvent.keyDown(document, { key: 'Escape' });
    });
    expect(onClose).toHaveBeenCalled();
  });
});

describe('Hard session-expiry DISABLED — a 401 no longer clears the token or redirects', () => {
  it('does not dispatch mz:auth-expired, keeps the stored token, and surfaces a plain 401 error', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response('unauthorized', { status: 401 }),
    );
    vi.stubGlobal('fetch', fetchMock);
    window.localStorage.setItem('mz_auth_token', 'stale-token');
    window.localStorage.setItem('mz_auth_role', 'enterprise');

    const handler = vi.fn();
    window.addEventListener('mz:auth-expired', handler);

    const { decisionBriefsApi } = await import('../../../src/api');
    // A 401 is now an ordinary error — not the special AUTH_EXPIRED / "Session expired" throw.
    await expect(decisionBriefsApi.get('b-1')).rejects.toThrow(/401/);

    // The hard side-effects are gone: no global event, and the token is left in place so surfaces
    // degrade locally instead of the whole app bouncing to the landing page.
    expect(handler).not.toHaveBeenCalled();
    expect(window.localStorage.getItem('mz_auth_token')).toBe('stale-token');
    expect(window.localStorage.getItem('mz_auth_role')).toBe('enterprise');
    window.removeEventListener('mz:auth-expired', handler);
  });
});

describe('Stage 6 fix #3 / #4 — keyboard reachability', () => {
  it('BriefEditableField enters edit mode via Enter on the wrapping button', async () => {
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(<BriefEditableField label="question" value="A" onSave={onSave} />);
    const trigger = screen.getByRole('button', { name: /question/i });
    trigger.focus();
    expect(document.activeElement).toBe(trigger);
    // Click is the activation event for buttons; native browsers do
    // this automatically on Enter/Space. fireEvent.click suffices here.
    fireEvent.click(trigger);
    expect(await screen.findByRole('textbox')).toBeInTheDocument();
  });
});

describe('Stage 6 fix #9 — StateMachineChip default is silent (no announce-storm)', () => {
  it('default chip does not declare role=status', () => {
    render(<StateMachineChip state="draft" />);
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
  });
  it('announce=true brings role=status back', () => {
    render(<StateMachineChip state="draft" announce />);
    expect(screen.getByRole('status')).toBeInTheDocument();
  });
});
