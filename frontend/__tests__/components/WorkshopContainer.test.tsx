/**
 * UX-Workshop — WorkshopContainer tests.
 *
 * Covers ready (scenario launch list + resume list), launching a war room from
 * a scenario (→ inline WarRoomView), blocked-scenario gating, and the error
 * path. WarRoomView is stubbed (heavy, self-contained — tested elsewhere).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../src/components/ci/war/WarRoomView', () => ({
  default: ({ roomId }: { roomId: string }) => <div data-testid="warroom-stub">room:{roomId}</div>,
}));

vi.mock('../../src/api', () => ({
  scenariosApi: { get: vi.fn() },
  warRoomApi: { list: vi.fn(), create: vi.fn() },
}));

import { scenariosApi, warRoomApi } from '../../src/api';
import WorkshopContainer from '../../src/components/ci/WorkshopContainer';

const ENGAGEMENT = { id: 'e1', name: 'Wegovy defense', asset: 'drug:semaglutide' } as any;

function scenario(over: Partial<any> = {}) {
  return {
    id: 'sc1', name: 'Competitive pressure: tirzepatide',
    trigger: { event: 'Tirzepatide expands in obesity', evidence: [] },
    probability: 0.4, teamMoves: [], decisionOptions: [], blockedByGaps: [],
    ...over,
  };
}

describe('WorkshopContainer', () => {
  beforeEach(() => vi.clearAllMocks());

  it('lists scenarios to launch + existing rooms to resume', async () => {
    (scenariosApi.get as any).mockResolvedValue({ scenarios: [scenario()], count: 1 });
    (warRoomApi.list as any).mockResolvedValue({ war_rooms: [
      { id: 'r1', title: 'Prior room', status: 'active', game_phase: 'setup' },
    ] });
    render(<WorkshopContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('workshop-ready')).toBeInTheDocument());
    expect(screen.getByText('Competitive pressure: tirzepatide')).toBeInTheDocument();
    expect(screen.getByTestId('workshop-resume-r1')).toBeInTheDocument();
  });

  it('launches a war room seeded from a scenario and plays it inline', async () => {
    (scenariosApi.get as any).mockResolvedValue({ scenarios: [scenario()], count: 1 });
    (warRoomApi.list as any).mockResolvedValue({ war_rooms: [] });
    (warRoomApi.create as any).mockResolvedValue({ id: 'new-room', title: 'x', status: 'draft', game_phase: 'setup' });
    render(<WorkshopContainer engagement={ENGAGEMENT} />);

    await waitFor(() => expect(screen.getByTestId('workshop-launch-sc1')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('workshop-launch-sc1'));

    await waitFor(() => expect(screen.getByTestId('workshop-room')).toBeInTheDocument());
    expect(screen.getByTestId('warroom-stub')).toHaveTextContent('room:new-room');
    // seeded from the scenario.
    expect(warRoomApi.create).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Competitive pressure: tirzepatide',
      scenario_question: 'Tirzepatide expands in obesity',
      primary_entity_type: 'drug',
      primary_entity_name: 'semaglutide',
    }));
  });

  it('disables launch for a blocked scenario', async () => {
    (scenariosApi.get as any).mockResolvedValue({ scenarios: [scenario({ blockedByGaps: ['pricing gap'] })], count: 1 });
    (warRoomApi.list as any).mockResolvedValue({ war_rooms: [] });
    render(<WorkshopContainer engagement={ENGAGEMENT} />);
    await waitFor(() => expect(screen.getByTestId('workshop-ready')).toBeInTheDocument());
    expect(screen.getByTestId('workshop-launch-sc1')).toBeDisabled();
  });

  it('still renders ready when scenario load fails (degrades to empty list)', async () => {
    (scenariosApi.get as any).mockRejectedValue(new Error('boom'));
    (warRoomApi.list as any).mockResolvedValue({ war_rooms: [] });
    render(<WorkshopContainer engagement={ENGAGEMENT} />);
    // per-call .catch → empty scenarios, still a usable (empty) workshop.
    await waitFor(() => expect(screen.getByTestId('workshop-ready')).toBeInTheDocument());
    expect(screen.getByText(/No scenarios yet/)).toBeInTheDocument();
  });
});
