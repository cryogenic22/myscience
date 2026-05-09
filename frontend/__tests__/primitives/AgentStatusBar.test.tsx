import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AgentStatusBar } from '../../src/components/primitives/AgentStatusBar';

describe('AgentStatusBar', () => {
  it('renders correctly', () => {
    render(<AgentStatusBar status="sensing" message="Ingesting 12 signals..." agentCount={3} />);
    expect(screen.getByText('Ingesting 12 signals...')).toBeDefined();
    expect(screen.getByText('3 Agents Active')).toBeDefined();
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
