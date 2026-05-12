/**
 * Loop #21 — Live agent activity feed tests.
 *
 * Replaces the static AgentIdentityStrip with a three-row feed that
 * shows each agent's most recent activity line, kind dot, and relative
 * timestamp. Driven by a polling hook (5s).
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import AgentActivityFeed from '../../src/components/primitives/AgentActivityFeed';
import type { AgentActivity } from '../../src/types/agents';

const NOW = new Date('2026-05-12T20:00:00Z');

const ACTIVITIES: AgentActivity[] = [
  {
    agent_id: 'sentinel',
    kind: 'completed',
    text: 'Scored 14 new signals — 3 promoted to shipped.',
    timestamp: new Date(NOW.getTime() - 30_000).toISOString(),
  },
  {
    agent_id: 'strategist',
    kind: 'progress',
    text: 'Running Monte Carlo for "GLP-1 pricing posture" (run 6,420 / 10,000).',
    timestamp: new Date(NOW.getTime() - 60_000).toISOString(),
  },
  {
    agent_id: 'curator',
    kind: 'completed',
    text: 'Recalibrated factor weights from 12 reviewer outcomes.',
    timestamp: new Date(NOW.getTime() - 120_000).toISOString(),
  },
];

describe('AgentActivityFeed (Loop #21)', () => {
  it('renders one row per agent', () => {
    const { container } = render(
      <AgentActivityFeed activities={ACTIVITIES} loading={false} />,
    );
    const rows = container.querySelectorAll('[data-agent-row]');
    expect(rows.length).toBe(3);
  });

  it('renders each agent name', () => {
    render(<AgentActivityFeed activities={ACTIVITIES} loading={false} />);
    expect(screen.getByText(/sentinel/i)).toBeDefined();
    expect(screen.getByText(/strategist/i)).toBeDefined();
    expect(screen.getByText(/curator/i)).toBeDefined();
  });

  it('renders the most recent activity text for each agent', () => {
    render(<AgentActivityFeed activities={ACTIVITIES} loading={false} />);
    expect(screen.getByText(/scored 14 new signals/i)).toBeDefined();
    expect(screen.getByText(/running monte carlo/i)).toBeDefined();
    expect(screen.getByText(/recalibrated factor weights/i)).toBeDefined();
  });

  it('renders a kind dot per agent row with data-kind attribute', () => {
    const { container } = render(
      <AgentActivityFeed activities={ACTIVITIES} loading={false} />,
    );
    const dots = container.querySelectorAll('[data-activity-kind]');
    expect(dots.length).toBe(3);
    const kinds = Array.from(dots).map((d) => d.getAttribute('data-activity-kind'));
    expect(kinds).toContain('completed');
    expect(kinds).toContain('progress');
  });

  it('shows a relative timestamp (e.g. "30s ago") for each row', () => {
    vi.setSystemTime(NOW);
    render(<AgentActivityFeed activities={ACTIVITIES} loading={false} />);
    // 30s, 1m, 2m ago — accept either short or long forms.
    expect(screen.getByText(/30\s*s/i)).toBeDefined();
    vi.useRealTimers();
  });

  it('renders a "waiting" placeholder for agents with no activity yet', () => {
    const partial = [ACTIVITIES[0]]; // only sentinel
    const { container } = render(
      <AgentActivityFeed activities={partial} loading={false} />,
    );
    const placeholders = container.querySelectorAll('[data-agent-waiting]');
    expect(placeholders.length).toBe(2); // strategist + curator
  });

  it('renders a loading skeleton while fetching first batch', () => {
    const { container } = render(
      <AgentActivityFeed activities={[]} loading={true} />,
    );
    const skeletons = container.querySelectorAll('[data-agent-skeleton]');
    expect(skeletons.length).toBe(3);
  });
});
