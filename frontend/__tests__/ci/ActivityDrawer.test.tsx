/**
 * UX11 / L12 — ActivityDrawer tests. Mocks engagementActivityApi.list.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ActivityDrawer from '../../src/components/ci/ActivityDrawer';
import { engagementActivityApi, type ActivityItem } from '../../src/api';

const ITEMS: ActivityItem[] = [
  { at: new Date().toISOString(), actor: 'u1', actor_kind: 'human', kind: 'brief', summary: 'Brief authored', ref_type: 'brief', ref_id: 'b1' },
  { at: new Date().toISOString(), actor: 'system', actor_kind: 'system', kind: 'scenario', summary: 'Derived 4 scenarios', ref_type: 'scenarios', ref_id: null },
];

describe('ActivityDrawer (UX11)', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('is closed by default and shows a trigger', () => {
    render(<ActivityDrawer engagementId="e1" />);
    expect(screen.getByTestId('activity-drawer-trigger')).toBeInTheDocument();
    expect(screen.queryByTestId('activity-drawer-panel')).not.toBeInTheDocument();
  });

  it('loads + renders the timeline newest-first on open', async () => {
    const spy = vi.spyOn(engagementActivityApi, 'list').mockResolvedValue(ITEMS);
    render(<ActivityDrawer engagementId="e1" />);
    fireEvent.click(screen.getByTestId('activity-drawer-trigger'));
    await waitFor(() => expect(screen.getByTestId('activity-list')).toBeInTheDocument());
    expect(spy).toHaveBeenCalledWith('e1');
    expect(screen.getByText('Brief authored')).toBeInTheDocument();
    expect(screen.getByText('Derived 4 scenarios')).toBeInTheDocument();
    // system action is labelled as automated
    expect(screen.getByText(/automated/)).toBeInTheDocument();
  });

  it('shows an honest empty state', async () => {
    vi.spyOn(engagementActivityApi, 'list').mockResolvedValue([]);
    render(<ActivityDrawer engagementId="e1" />);
    fireEvent.click(screen.getByTestId('activity-drawer-trigger'));
    await waitFor(() => expect(screen.getByTestId('activity-empty')).toBeInTheDocument());
  });

  it('surfaces an error', async () => {
    vi.spyOn(engagementActivityApi, 'list').mockRejectedValue(new Error('500'));
    render(<ActivityDrawer engagementId="e1" />);
    fireEvent.click(screen.getByTestId('activity-drawer-trigger'));
    await waitFor(() => expect(screen.getByTestId('activity-error')).toHaveTextContent('500'));
  });
});
