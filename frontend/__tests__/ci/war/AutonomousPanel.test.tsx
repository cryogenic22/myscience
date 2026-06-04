/**
 * PB-H13 — AutonomousPanel tests. Mocks warRoomApi.runAutonomous.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import AutonomousPanel from '../../../src/components/ci/war/AutonomousPanel';
import { warRoomApi, type AutoplayResult } from '../../../src/api';

const RESULT: AutoplayResult = {
  mode: 'autonomous',
  war_room_id: 'wr-1',
  rounds: [
    { round: 1, our_move: 'trial_readout', reactions: [{} as any], narration: 'Round 1: Novo plays trial readout; RivalB responds — B counters.' },
    { round: 2, our_move: 'price_cut', reactions: [{} as any, {} as any], narration: 'Round 2: Novo plays price cut; RivalA responds.' },
  ],
  narration: ['line 1', 'line 2'],
  summary: { rounds_played: 2, moves: ['trial_readout', 'price_cut'], total_reactions: 3 },
};

describe('AutonomousPanel (PB-H13)', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('shows the run button before any play', () => {
    render(<AutonomousPanel roomId="wr-1" />);
    expect(screen.getByRole('button', { name: /run autonomous play/i })).toBeInTheDocument();
  });

  it('runs the campaign and renders the transcript', async () => {
    const spy = vi.spyOn(warRoomApi, 'runAutonomous').mockResolvedValue(RESULT);
    render(<AutonomousPanel roomId="wr-1" />);
    fireEvent.click(screen.getByRole('button', { name: /run autonomous play/i }));
    await waitFor(() => expect(screen.getByText(/Round 1: Novo plays trial readout/i)).toBeInTheDocument());
    expect(spy).toHaveBeenCalledWith('wr-1', { rounds: 4 });
    // Both rounds render + the summary line.
    expect(screen.getByText(/Round 2: Novo plays price cut/i)).toBeInTheDocument();
    expect(screen.getByText(/2 rounds · 3 reactions/i)).toBeInTheDocument();
  });

  it('surfaces an error when the run fails', async () => {
    vi.spyOn(warRoomApi, 'runAutonomous').mockRejectedValue(new Error('boom'));
    render(<AutonomousPanel roomId="wr-1" />);
    fireEvent.click(screen.getByRole('button', { name: /run autonomous play/i }));
    await waitFor(() => expect(screen.getByText(/boom/i)).toBeInTheDocument());
  });
});
