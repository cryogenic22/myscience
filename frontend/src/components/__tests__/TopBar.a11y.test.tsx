import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import TopBar from '../layout/TopBar';

vi.mock('../../hooks/useTheme', () => ({ useTheme: () => ({ theme: 'light', toggleTheme: vi.fn() }) }));
vi.mock('../intelligence/FeedBadge', () => ({ FeedBadge: () => null }));

describe('TopBar a11y', () => {
  it('nav tabs expose an accessible name and mark the active tab', () => {
    render(<TopBar activeTab="feed" onBack={vi.fn()} onTabChange={vi.fn()} />);

    // Below the sm breakpoint the label span is display:none — the aria-label
    // keeps the name for screen readers regardless of viewport.
    const feed = screen.getByRole('button', { name: 'Feed' });
    expect(feed).toHaveAttribute('aria-current', 'page');

    const search = screen.getByRole('button', { name: 'Search' });
    expect(search).not.toHaveAttribute('aria-current');

    // All five tabs are individually addressable by name.
    expect(screen.getByRole('button', { name: 'Intelligence' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Graph' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Entity Library' })).toBeInTheDocument();
  });
});
