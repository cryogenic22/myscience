import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import AgentIdentityStrip from '../../src/components/primitives/AgentIdentityStrip';

describe('AgentIdentityStrip (PB-201)', () => {
  it('renders all three agents in fixed order — Sentinel, Strategist, Curator', () => {
    const { container } = render(<AgentIdentityStrip />);
    const glyphs = Array.from(container.querySelectorAll('[data-agent]')).map((el) =>
      el.getAttribute('data-agent'),
    );
    expect(glyphs).toEqual(['sentinel', 'strategist', 'curator']);
  });

  it('shows the agent names beside each glyph', () => {
    render(<AgentIdentityStrip />);
    expect(screen.getByText('Sentinel')).toBeDefined();
    expect(screen.getByText('Strategist')).toBeDefined();
    expect(screen.getByText('Curator')).toBeDefined();
  });

  it('shows the role line for each agent (noun form, Phase 8)', () => {
    render(<AgentIdentityStrip />);
    expect(screen.getByText(/sense/i)).toBeDefined();
    expect(screen.getByText(/frame.*simulate/i)).toBeDefined();
    expect(screen.getByText(/learn.*recalibrate/i)).toBeDefined();
  });

  it('exposes role="group" with an aria-label so AT announce the group as one thing', () => {
    const { container } = render(<AgentIdentityStrip />);
    const group = container.querySelector('[role="group"]');
    expect(group).not.toBeNull();
    expect(group?.getAttribute('aria-label')).toMatch(/agents/i);
  });
});
