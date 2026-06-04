/**
 * PB-203 / L13 — NudgeMenu tests. Mocks agentsApi (intents + nudge).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import NudgeMenu from '../../src/components/ci/NudgeMenu';
import { agentsApi } from '../../src/api';
import type { NudgeIntent } from '../../src/types/agents';

const STRATEGIST_INTENTS: NudgeIntent[] = [
  { key: 'rerun_sim', label: 'Re-run simulation', description: 'Re-run the war-game.', requires_target: true, target_kind: 'scenario' },
  { key: 'draft_counter', label: 'Draft counter-move', description: 'Draft a counter.', requires_target: true, target_kind: 'scenario' },
];

describe('NudgeMenu (PB-203)', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('lazily loads + lists the agent intents on open', async () => {
    vi.spyOn(agentsApi, 'intents').mockResolvedValue({ agent: 'strategist', intents: STRATEGIST_INTENTS });
    render(<NudgeMenu agent="strategist" />);
    fireEvent.click(screen.getByTestId('nudge-trigger'));
    await waitFor(() => expect(screen.getByTestId('nudge-intent-rerun_sim')).toBeInTheDocument());
    expect(screen.getByTestId('nudge-intent-draft_counter')).toBeInTheDocument();
    expect(agentsApi.intents).toHaveBeenCalledWith('strategist');
  });

  it('prompts for a target then queues the nudge', async () => {
    vi.spyOn(agentsApi, 'intents').mockResolvedValue({ agent: 'strategist', intents: STRATEGIST_INTENTS });
    const nudge = vi.spyOn(agentsApi, 'nudge').mockResolvedValue({
      nudge: { id: 'n1', agent: 'strategist', intent: 'rerun_sim', target: null, note: null, status: 'queued', created_by: 'u1', created_at: null },
    });
    render(<NudgeMenu agent="strategist" />);
    fireEvent.click(screen.getByTestId('nudge-trigger'));
    await waitFor(() => screen.getByTestId('nudge-intent-rerun_sim'));
    fireEvent.click(screen.getByTestId('nudge-intent-rerun_sim'));
    // target form appears since the intent requires a target
    const input = await screen.findByTestId('nudge-target-input');
    fireEvent.change(input, { target: { value: 'scen-7' } });
    fireEvent.click(screen.getByTestId('nudge-send'));
    await waitFor(() =>
      expect(nudge).toHaveBeenCalledWith('strategist', { intent: 'rerun_sim', target: { scenario_id: 'scen-7' } }),
    );
    await waitFor(() => expect(screen.getByText('Queued ✓')).toBeInTheDocument());
  });

  it('uses a parent-supplied target without prompting', async () => {
    vi.spyOn(agentsApi, 'intents').mockResolvedValue({ agent: 'strategist', intents: STRATEGIST_INTENTS });
    const nudge = vi.spyOn(agentsApi, 'nudge').mockResolvedValue({
      nudge: { id: 'n1', agent: 'strategist', intent: 'rerun_sim', target: null, note: null, status: 'queued', created_by: 'u1', created_at: null },
    });
    render(<NudgeMenu agent="strategist" resolveTarget={() => ({ scenario_id: 'ctx-1' })} />);
    fireEvent.click(screen.getByTestId('nudge-trigger'));
    await waitFor(() => screen.getByTestId('nudge-intent-rerun_sim'));
    fireEvent.click(screen.getByTestId('nudge-intent-rerun_sim'));
    await waitFor(() =>
      expect(nudge).toHaveBeenCalledWith('strategist', { intent: 'rerun_sim', target: { scenario_id: 'ctx-1' } }),
    );
    // no target prompt
    expect(screen.queryByTestId('nudge-target-input')).not.toBeInTheDocument();
  });

  it('surfaces an error when the nudge fails', async () => {
    vi.spyOn(agentsApi, 'intents').mockResolvedValue({ agent: 'sentinel', intents: [
      { key: 'watch', label: 'Watch', description: 'Watch entity.', requires_target: true, target_kind: 'entity' },
    ] });
    vi.spyOn(agentsApi, 'nudge').mockRejectedValue(new Error('401'));
    render(<NudgeMenu agent="sentinel" />);
    fireEvent.click(screen.getByTestId('nudge-trigger'));
    await waitFor(() => screen.getByTestId('nudge-intent-watch'));
    fireEvent.click(screen.getByTestId('nudge-intent-watch'));
    fireEvent.change(await screen.findByTestId('nudge-target-input'), { target: { value: 'e1' } });
    fireEvent.click(screen.getByTestId('nudge-send'));
    await waitFor(() => expect(screen.getByTestId('nudge-error')).toHaveTextContent('401'));
  });
});
