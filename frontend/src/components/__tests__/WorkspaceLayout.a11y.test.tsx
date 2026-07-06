import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, beforeEach } from 'vitest';
import WorkspaceLayout from '../layout/WorkspaceLayout';

beforeEach(() => {
  // persistSplit writes to localStorage; isolate each test from the last.
  localStorage.clear();
});

describe('WorkspaceLayout divider a11y', () => {
  it('exposes the divider as a labelled ARIA separator with its current value', () => {
    render(<WorkspaceLayout left={<div>L</div>} right={<div>R</div>} defaultSplit={48} minLeft={30} minRight={25} />);
    const sep = screen.getByRole('separator', { name: /resize panels/i });
    expect(sep).toHaveAttribute('aria-orientation', 'vertical');
    expect(sep).toHaveAttribute('aria-valuenow', '48');
    expect(sep).toHaveAttribute('aria-valuemin', '30');
    expect(sep).toHaveAttribute('aria-valuemax', '75');
    expect(sep).toHaveAttribute('tabindex', '0');
  });

  it('resizes with the keyboard (Arrow keys nudge, clamped)', () => {
    render(<WorkspaceLayout left={<div>L</div>} right={<div>R</div>} defaultSplit={48} minLeft={30} minRight={25} />);
    const sep = screen.getByRole('separator', { name: /resize panels/i });

    fireEvent.keyDown(sep, { key: 'ArrowRight' });
    expect(sep).toHaveAttribute('aria-valuenow', '50');

    fireEvent.keyDown(sep, { key: 'ArrowLeft' });
    expect(sep).toHaveAttribute('aria-valuenow', '48');

    fireEvent.keyDown(sep, { key: 'Home' });
    expect(sep).toHaveAttribute('aria-valuenow', '30'); // clamped to minLeft

    fireEvent.keyDown(sep, { key: 'End' });
    expect(sep).toHaveAttribute('aria-valuenow', '75'); // clamped to 100 - minRight
  });
});
