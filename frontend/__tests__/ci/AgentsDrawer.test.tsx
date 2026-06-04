/**
 * L13 — AgentsDrawer tests. Mocks agentsApi.activity (the polled feed source).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AgentsDrawer from '../../src/components/ci/AgentsDrawer';
import { agentsApi } from '../../src/api';

describe('AgentsDrawer (L13)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(agentsApi, 'activity').mockResolvedValue({
      activities: [
        { agent_id: 'sentinel', kind: 'completed', text: 'Scored a signal', timestamp: new Date().toISOString() },
      ],
      poll_after_seconds: 60,
    });
  });

  it('renders a trigger and is closed by default', () => {
    render(<AgentsDrawer />);
    expect(screen.getByTestId('agents-drawer-trigger')).toBeInTheDocument();
    expect(screen.queryByTestId('agents-drawer-panel')).not.toBeInTheDocument();
  });

  it('opens the drawer and shows the three agents with nudge affordances', async () => {
    render(<AgentsDrawer />);
    fireEvent.click(screen.getByTestId('agents-drawer-trigger'));
    expect(screen.getByTestId('agents-drawer-panel')).toBeInTheDocument();
    // AgentActivityFeed renders a row per agent, each carrying a NudgeMenu.
    await waitFor(() => expect(screen.getAllByTestId('nudge-trigger').length).toBe(3));
  });

  it('closes via the backdrop', () => {
    render(<AgentsDrawer />);
    fireEvent.click(screen.getByTestId('agents-drawer-trigger'));
    fireEvent.click(screen.getByTestId('agents-drawer-backdrop'));
    expect(screen.queryByTestId('agents-drawer-panel')).not.toBeInTheDocument();
  });
});
