/**
 * IX04b — standalone war-game launch from the War Game list.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import WarRoomsList from '../../../src/components/ci/war/WarRoomsList';
import { warRoomApi, type WarRoom } from '../../../src/api';

const ROOM: WarRoom = {
  id: 'wr-new', title: 'Wegovy vs Zepbound', owner_user_id: 'u1',
  scenario_question: null, primary_entity_type: null, primary_entity_id: null,
  primary_entity_name: null, source_signal_id: null, game_phase: 'launch',
  status: 'active', archived_at: null, created_at: null, updated_at: null,
};

describe('WarRoomsList — standalone launch (IX04b)', () => {
  beforeEach(() => {
    window.localStorage.setItem('mz_auth_token', 'test-token');
    vi.spyOn(warRoomApi, 'list').mockResolvedValue({ war_rooms: [] });
  });
  afterEach(() => {
    window.localStorage.removeItem('mz_auth_token');
    vi.restoreAllMocks();
  });

  it('shows a New war game button', async () => {
    render(<WarRoomsList onOpen={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('new-war-game')).toBeInTheDocument());
  });

  it('reveals the create form and creates a standalone war game, then opens it', async () => {
    const createSpy = vi.spyOn(warRoomApi, 'create').mockResolvedValue(ROOM);
    const onOpen = vi.fn();
    render(<WarRoomsList onOpen={onOpen} />);
    await waitFor(() => expect(screen.getByTestId('new-war-game')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('new-war-game'));
    const input = screen.getByPlaceholderText(/war game title/i);
    fireEvent.change(input, { target: { value: 'Wegovy vs Zepbound' } });
    fireEvent.click(screen.getByRole('button', { name: /^create$/i }));

    await waitFor(() => expect(createSpy).toHaveBeenCalledWith({ title: 'Wegovy vs Zepbound' }));
    await waitFor(() => expect(onOpen).toHaveBeenCalledWith('wr-new'));
  });

  it('disables Create until a title is entered', async () => {
    render(<WarRoomsList onOpen={() => {}} />);
    await waitFor(() => expect(screen.getByTestId('new-war-game')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('new-war-game'));
    const createBtn = screen.getByRole('button', { name: /^create$/i }) as HTMLButtonElement;
    expect(createBtn.disabled).toBe(true);
  });
});
