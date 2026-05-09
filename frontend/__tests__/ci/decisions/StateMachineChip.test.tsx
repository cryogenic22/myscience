/**
 * SPEC_030 Stage 3 — StateMachineChip
 *
 * Renders a state pill with shape-glyph + color token. Click opens a
 * popover showing the full DAG with the current state pulsing.
 */

import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ALL_STATES, applyTheme } from './_fixtures';
import StateMachineChip from '../../../src/components/ci/decisions/StateMachineChip';

describe('StateMachineChip', () => {
  describe('renders every BriefState without crashing', () => {
    it.each(ALL_STATES)('state=%s', (state) => {
      render(<StateMachineChip state={state} />);
      // Each state's label is visible (lowercased compare; chip is a plain
      // span by default after Stage 6 fix #9)
      expect(
        screen
          .getByText(new RegExp(state.replace('_', ' '), 'i'))
      ).toBeInTheDocument();
    });
  });

  it('aria-live="polite" only when announce=true (Stage 6 fix #9)', () => {
    const { unmount } = render(<StateMachineChip state="draft" />);
    // Default: NOT a live region — lists of chips do not spam screen readers
    expect(screen.queryByRole('status')).not.toBeInTheDocument();
    unmount();

    render(<StateMachineChip state="draft" announce />);
    const node = screen.getByRole('status');
    expect(node.getAttribute('aria-live')).toBe('polite');
  });

  it('has a shape-glyph (color is not the only meaning carrier)', () => {
    render(<StateMachineChip state="committed" announce />);
    const node = screen.getByRole('status');
    expect(node.textContent).toMatch(/[✓◯▶⟳⊕◆]/);
  });

  it('opens transition popover on click when interactive=true', () => {
    render(<StateMachineChip state="draft" interactive />);
    const chip = screen.getByRole('button');
    fireEvent.click(chip);
    expect(screen.getByRole('dialog', { name: /transitions/i })).toBeInTheDocument();
  });

  it('does not render as a button when interactive=false', () => {
    render(<StateMachineChip state="draft" />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });

  it('renders consistently in light and dark themes', () => {
    applyTheme('light');
    const { unmount } = render(<StateMachineChip state="committed" />);
    expect(screen.getByText(/committed/i)).toBeInTheDocument();
    unmount();
    applyTheme('dark');
    render(<StateMachineChip state="committed" />);
    expect(screen.getByText(/committed/i)).toBeInTheDocument();
  });

  it.todo('clicking an allowed transition in the popover invokes onTransition(toState)');
  it.todo('disabled transitions are aria-disabled and do not invoke the callback');
});
