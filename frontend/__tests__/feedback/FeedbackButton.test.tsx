/**
 * SPEC_041 Stage 3 — FeedbackButton (the floating pill).
 *
 * Renders bottom-right on every authenticated route except / and /login.
 * On /workspace it auto-shifts to bottom-LEFT to clear the chat send
 * button (Q4 sign-off). Hidden when localStorage.mz_feedback_disabled
 * === 'true'.
 *
 * Pressing the pill or Enter on it dispatches a `mz:open-feedback`
 * event the FeedbackWidget listens for.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import FeedbackButton from '../../src/components/feedback/FeedbackButton';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <FeedbackButton />
    </MemoryRouter>,
  );
}

describe('FeedbackButton', () => {
  beforeEach(() => {
    window.localStorage.removeItem('mz_feedback_disabled');
  });
  afterEach(() => {
    window.localStorage.removeItem('mz_feedback_disabled');
  });

  it('renders on /ci', () => {
    renderAt('/ci');
    expect(screen.getByRole('button', { name: /feedback/i })).toBeInTheDocument();
  });

  it('renders on /ci/decisions/:id', () => {
    renderAt('/ci/decisions/b-001');
    expect(screen.getByRole('button', { name: /feedback/i })).toBeInTheDocument();
  });

  it('does NOT render on /', () => {
    renderAt('/');
    expect(screen.queryByRole('button', { name: /feedback/i })).not.toBeInTheDocument();
  });

  it('does NOT render on /login', () => {
    renderAt('/login');
    expect(screen.queryByRole('button', { name: /feedback/i })).not.toBeInTheDocument();
  });

  it('does NOT render when mz_feedback_disabled is set', () => {
    window.localStorage.setItem('mz_feedback_disabled', 'true');
    renderAt('/ci');
    expect(screen.queryByRole('button', { name: /feedback/i })).not.toBeInTheDocument();
  });

  it('positions bottom-right by default', () => {
    renderAt('/ci');
    const btn = screen.getByRole('button', { name: /feedback/i });
    const style = (btn as HTMLElement).style;
    expect(style.right).toBeTruthy();
    expect(style.left).toBeFalsy();
  });

  it('positions bottom-LEFT on /workspace (Q4 sign-off)', () => {
    renderAt('/workspace');
    const btn = screen.getByRole('button', { name: /feedback/i });
    const style = (btn as HTMLElement).style;
    expect(style.left).toBeTruthy();
    expect(style.right).toBeFalsy();
  });

  it('dispatches mz:open-feedback when clicked', () => {
    renderAt('/ci');
    const handler = vi.fn();
    window.addEventListener('mz:open-feedback', handler);
    fireEvent.click(screen.getByRole('button', { name: /feedback/i }));
    expect(handler).toHaveBeenCalled();
    window.removeEventListener('mz:open-feedback', handler);
  });

  it('has aria-haspopup="dialog"', () => {
    renderAt('/ci');
    const btn = screen.getByRole('button', { name: /feedback/i });
    expect(btn.getAttribute('aria-haspopup')).toBe('dialog');
  });
});
