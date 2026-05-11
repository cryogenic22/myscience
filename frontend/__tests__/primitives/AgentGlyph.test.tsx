import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import AgentGlyph from '../../src/components/primitives/AgentGlyph';

describe('AgentGlyph (PB-201)', () => {
  it('renders the Sentinel glyph with letters SE and teal tint', () => {
    const { container } = render(<AgentGlyph agent="sentinel" />);
    expect(screen.getByText('SE')).toBeDefined();
    const badge = container.querySelector('[data-agent="sentinel"]');
    expect(badge).not.toBeNull();
    expect(badge?.getAttribute('aria-label')).toMatch(/sentinel/i);
  });

  it('renders the Strategist glyph with letters ST and violet tint', () => {
    const { container } = render(<AgentGlyph agent="strategist" />);
    expect(screen.getByText('ST')).toBeDefined();
    const badge = container.querySelector('[data-agent="strategist"]');
    expect(badge).not.toBeNull();
    expect(badge?.getAttribute('aria-label')).toMatch(/strategist/i);
  });

  it('renders the Curator glyph with letters CU and green tint', () => {
    const { container } = render(<AgentGlyph agent="curator" />);
    expect(screen.getByText('CU')).toBeDefined();
    const badge = container.querySelector('[data-agent="curator"]');
    expect(badge).not.toBeNull();
    expect(badge?.getAttribute('aria-label')).toMatch(/curator/i);
  });

  it('uses noun forms (not verb forms) in aria-labels — Phase 8 verification', () => {
    const { container: c1 } = render(<AgentGlyph agent="sentinel" />);
    const { container: c2 } = render(<AgentGlyph agent="strategist" />);
    const { container: c3 } = render(<AgentGlyph agent="curator" />);
    // Noun ≠ verb: "sentinel" not "sensing", "strategist" not "framing", "curator" not "learning".
    expect(c1.querySelector('[data-agent]')?.getAttribute('aria-label')).not.toMatch(/sensing|framing|simulating/i);
    expect(c2.querySelector('[data-agent]')?.getAttribute('aria-label')).not.toMatch(/sensing|framing|simulating/i);
    expect(c3.querySelector('[data-agent]')?.getAttribute('aria-label')).not.toMatch(/sensing|framing|simulating/i);
  });

  it('shows the agent name when showLabel is true', () => {
    render(<AgentGlyph agent="sentinel" showLabel />);
    expect(screen.getByText('Sentinel')).toBeDefined();
  });

  it('omits the agent name when showLabel is omitted (default off)', () => {
    render(<AgentGlyph agent="sentinel" />);
    expect(screen.queryByText('Sentinel')).toBeNull();
  });

  it('supports a status decoration via the status prop (e.g. dot indicator)', () => {
    const { container } = render(<AgentGlyph agent="strategist" status="idle" />);
    const dot = container.querySelector('[data-status]');
    expect(dot).not.toBeNull();
    expect(dot?.getAttribute('data-status')).toBe('idle');
  });
});
