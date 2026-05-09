/**
 * SPEC_030 Stage 3 — ReasoningTraceDrawer
 *
 * Right-side drawer (semantic <dialog>) showing the brief's state_log
 * timeline. Future: integrate with llm_call_log via SPEC_026 telemetry
 * (deferred to v2).
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { makeBrief, makeStateLogEntry } from './_fixtures';
import ReasoningTraceDrawer from '../../../src/components/ci/decisions/ReasoningTraceDrawer';

describe('ReasoningTraceDrawer', () => {
  it('does not render when open=false', () => {
    render(<ReasoningTraceDrawer brief={makeBrief()} open={false} onClose={vi.fn()} />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders dialog with aria-labelledby pointing at title when open', () => {
    render(<ReasoningTraceDrawer brief={makeBrief()} open={true} onClose={vi.fn()} />);
    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-labelledby')).toBeTruthy();
  });

  it('lists each state_log entry chronologically', () => {
    const brief = makeBrief({
      state_log: [
        makeStateLogEntry({ to_state: 'draft', transitioned_at: '2026-05-09T10:00:00Z' }),
        makeStateLogEntry({ from_state: 'draft', to_state: 'human_review', transitioned_at: '2026-05-09T11:00:00Z' }),
        makeStateLogEntry({ from_state: 'human_review', to_state: 'simulation_pending', transitioned_at: '2026-05-09T12:00:00Z' }),
      ],
    });
    render(<ReasoningTraceDrawer brief={brief} open={true} onClose={vi.fn()} />);
    const items = screen.getAllByRole('listitem');
    expect(items.length).toBe(3);
    // Last entry visible
    expect(screen.getByText(/simulation_pending/i)).toBeInTheDocument();
  });

  it('renders actor + reason for each entry when present', () => {
    const brief = makeBrief({
      state_log: [
        makeStateLogEntry({
          to_state: 'human_review',
          actor_user_id: 'analyst-jane',
          reason: 'Clinical signal sufficient',
        }),
      ],
    });
    render(<ReasoningTraceDrawer brief={brief} open={true} onClose={vi.fn()} />);
    expect(screen.getByText(/analyst-jane/)).toBeInTheDocument();
    expect(screen.getByText(/Clinical signal sufficient/)).toBeInTheDocument();
  });

  it('escape key invokes onClose', () => {
    const onClose = vi.fn();
    render(<ReasoningTraceDrawer brief={makeBrief()} open={true} onClose={onClose} />);
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(onClose).toHaveBeenCalled();
  });

  it.todo('integrates with /llm-gateway/cost-summary in v2 to show per-call cost');
});
