import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AgentStatusBar } from '../../src/components/primitives/AgentStatusBar';

describe('AgentStatusBar', () => {
  it('renders correctly', () => {
    render(<AgentStatusBar status="sensing" message="Ingesting 12 signals..." agentCount={3} />);
    expect(screen.getByText('Ingesting 12 signals...')).toBeDefined();
    expect(screen.getByText('3 Agents Active')).toBeDefined();
  });

  it('has no pill outline — separation is tone-shift only (regression)', () => {
    // The header status bar previously wrapped its text in a `rounded-lg
    // border` capsule (the "cylindrical outline around text" the design
    // review kept flagging). Separation must come from the surface-2
    // tone-shift, never a border utility or inline borderColor.
    const { container } = render(
      <AgentStatusBar status="sensing" message="x" agentCount={1} />,
    );
    const root = container.firstChild as HTMLElement;
    // No standalone `border` utility class (border-* radius helpers are fine).
    expect(/(^|\s)border(\s|$)/.test(root.className)).toBe(false);
    // No inline border styling.
    expect(root.style.border).toBe('');
    expect(root.style.borderColor).toBe('');
  });

  it('renders correct semantic color based on status', () => {
    const { container, rerender } = render(<AgentStatusBar status="idle" message="Idle" />);
    // Idle is neutral
    expect(container.querySelector('[data-status="idle"]')).toBeDefined();

    rerender(<AgentStatusBar status="simulating" message="Running Monte Carlo" />);
    // Simulating uses accent color
    expect(container.querySelector('[data-status="simulating"]')).toBeDefined();
  });
});
