/**
 * UX-Discoverability — TopBar CI cockpit entry.
 *
 * The workspace top bar surfaces a "CI Cockpit" action so the engagement
 * walkthrough is reachable from the main workspace (not just the landing page).
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

describe('TopBar — CI cockpit entry', () => {
  it('renders a CI Cockpit button and fires onCI', () => {
    const onCI = vi.fn();
    render(
      <TopBar onBack={() => {}} onCI={onCI} activeTab="chat" onTabChange={() => {}} />,
    );
    const btn = screen.getByTestId('topbar-ci');
    expect(btn).toBeInTheDocument();
    fireEvent.click(btn);
    expect(onCI).toHaveBeenCalledTimes(1);
  });

  it('omits the CI button when onCI is not provided', () => {
    render(<TopBar onBack={() => {}} activeTab="chat" onTabChange={() => {}} />);
    expect(screen.queryByTestId('topbar-ci')).not.toBeInTheDocument();
  });
});
