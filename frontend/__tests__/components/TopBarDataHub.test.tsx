/**
 * DataHub · F1 — TopBar DataHub entry.
 *
 * The workspace top bar surfaces a "DataHub" action so the Catalog
 * (`/hub/catalog`) is reachable from the main workspace. Mirrors the CI
 * Cockpit entry: an optional `onDataHub` callback that, when provided, renders
 * a discoverable button.
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('../../src/hooks/useTheme', () => ({
  useTheme: () => ({ theme: 'light', toggleTheme: vi.fn() }),
}));
vi.mock('../../src/components/intelligence/FeedBadge', () => ({
  FeedBadge: () => <span data-testid="feed-badge" />,
}));

import TopBar from '../../src/components/layout/TopBar';

describe('TopBar — DataHub entry', () => {
  it('renders a DataHub button and fires onDataHub', () => {
    const onDataHub = vi.fn();
    render(
      <TopBar onBack={() => {}} onDataHub={onDataHub} activeTab="chat" onTabChange={() => {}} />,
    );
    const btn = screen.getByTestId('topbar-datahub');
    expect(btn).toBeInTheDocument();
    expect(btn).toHaveTextContent(/datahub/i);
    fireEvent.click(btn);
    expect(onDataHub).toHaveBeenCalledTimes(1);
  });

  it('omits the DataHub button when onDataHub is not provided', () => {
    render(<TopBar onBack={() => {}} activeTab="chat" onTabChange={() => {}} />);
    expect(screen.queryByTestId('topbar-datahub')).not.toBeInTheDocument();
  });
});
