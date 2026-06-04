/**
 * IX04a — War Game mode picker tests.
 * The three-mode tablist (Guided / Autonomous / Game-theoretic) wired into
 * the live war room, backed by PATCH /war-rooms/{id}/mode.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import WarRoomModePicker from '../../src/components/ci/war/WarRoomModePicker';

describe('WarRoomModePicker', () => {
  it('renders the three modes as tabs', () => {
    render(<WarRoomModePicker mode="guided" onModeChange={() => {}} />);
    expect(screen.getByRole('tab', { name: /guided/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /autonomous/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /game-theoretic/i })).toBeInTheDocument();
  });

  it('marks the active mode as selected', () => {
    render(<WarRoomModePicker mode="autonomous" onModeChange={() => {}} />);
    expect(screen.getByRole('tab', { name: /autonomous/i }).getAttribute('aria-selected')).toBe('true');
    expect(screen.getByRole('tab', { name: /guided/i }).getAttribute('aria-selected')).toBe('false');
  });

  it('calls onModeChange when a different mode is clicked', () => {
    const onModeChange = vi.fn();
    render(<WarRoomModePicker mode="guided" onModeChange={onModeChange} />);
    fireEvent.click(screen.getByRole('tab', { name: /game-theoretic/i }));
    expect(onModeChange).toHaveBeenCalledWith('game_theoretic');
  });

  it('does not fire onModeChange for the already-active mode', () => {
    const onModeChange = vi.fn();
    render(<WarRoomModePicker mode="guided" onModeChange={onModeChange} />);
    fireEvent.click(screen.getByRole('tab', { name: /guided/i }));
    expect(onModeChange).not.toHaveBeenCalled();
  });

  it('disables interaction while busy', () => {
    const onModeChange = vi.fn();
    render(<WarRoomModePicker mode="guided" onModeChange={onModeChange} busy />);
    fireEvent.click(screen.getByRole('tab', { name: /autonomous/i }));
    expect(onModeChange).not.toHaveBeenCalled();
  });
});
