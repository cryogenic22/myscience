/**
 * SPEC_030 Stage 3 — BriefsTab
 *
 * List view that replaces legacy DecisionsTab. Consumes /decision-briefs
 * with cursor pagination. Linear-style row anatomy (state-glyph + question
 * + meta) per SPEC_030 §8.5.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { makeBrief, applyTheme } from './_fixtures';

const { mockList } = vi.hoisted(() => ({ mockList: vi.fn() }));
vi.mock('../../../src/api', async () => {
  const actual = await vi.importActual<typeof import('../../../src/api')>('../../../src/api');
  return {
    ...actual,
    decisionBriefsApi: { ...(actual as any).decisionBriefsApi, list: mockList },
  };
});

import BriefsTab from '../../../src/components/ci/decisions/BriefsTab';

describe('BriefsTab', () => {
  beforeEach(() => mockList.mockReset());

  it('shows skeleton during initial load (not a spinner)', async () => {
    let resolve: any;
    mockList.mockImplementation(() => new Promise((r) => { resolve = r; }));
    render(<BriefsTab onOpen={vi.fn()} />);
    expect(await screen.findByLabelText(/loading briefs/i)).toBeInTheDocument();
    resolve({ briefs: [], next_cursor: null, count: 0 });
  });

  it('renders an empty state when 0 briefs come back', async () => {
    mockList.mockResolvedValueOnce({ briefs: [], next_cursor: null, count: 0 });
    render(<BriefsTab onOpen={vi.fn()} />);
    expect(await screen.findByText(/no briefs yet/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /new brief/i })).toBeInTheDocument();
  });

  it('renders one row per brief with state-label + question', async () => {
    mockList.mockResolvedValueOnce({
      briefs: [
        makeBrief({ brief_id: 'b-1', state: 'draft', question: 'Q1?' }),
        makeBrief({ brief_id: 'b-2', state: 'human_review', question: 'Q2?' }),
      ],
      next_cursor: null,
      count: 2,
    });
    render(<BriefsTab onOpen={vi.fn()} />);
    expect(await screen.findByText('Q1?')).toBeInTheDocument();
    expect(screen.getByText('Q2?')).toBeInTheDocument();
    expect(screen.getByText(/draft/i)).toBeInTheDocument();
    expect(screen.getByText(/human.review/i)).toBeInTheDocument();
  });

  it('row click invokes onOpen(brief_id)', async () => {
    mockList.mockResolvedValueOnce({
      briefs: [makeBrief({ brief_id: 'b-7', question: 'Click me?' })],
      next_cursor: null,
      count: 1,
    });
    const onOpen = vi.fn();
    render(<BriefsTab onOpen={onOpen} />);
    const row = await screen.findByText('Click me?');
    fireEvent.click(row);
    expect(onOpen).toHaveBeenCalledWith('b-7');
  });

  describe('keyboard navigation', () => {
    beforeEach(() => {
      mockList.mockResolvedValueOnce({
        briefs: [
          makeBrief({ brief_id: 'b-1', question: 'Q1?' }),
          makeBrief({ brief_id: 'b-2', question: 'Q2?' }),
          makeBrief({ brief_id: 'b-3', question: 'Q3?' }),
        ],
        next_cursor: null,
        count: 3,
      });
    });

    it('"j" moves selection down', async () => {
      render(<BriefsTab onOpen={vi.fn()} />);
      await screen.findByText('Q1?');
      fireEvent.keyDown(window, { key: 'j' });
      // The 2nd row gets aria-selected="true"
      const rows = screen.getAllByRole('option');
      expect(rows[1].getAttribute('aria-selected')).toBe('true');
    });

    it('"k" moves selection up', async () => {
      render(<BriefsTab onOpen={vi.fn()} />);
      await screen.findByText('Q1?');
      fireEvent.keyDown(window, { key: 'j' });
      fireEvent.keyDown(window, { key: 'j' });
      fireEvent.keyDown(window, { key: 'k' });
      const rows = screen.getAllByRole('option');
      expect(rows[1].getAttribute('aria-selected')).toBe('true');
    });

    it('"return" opens the selected brief', async () => {
      const onOpen = vi.fn();
      render(<BriefsTab onOpen={onOpen} />);
      await screen.findByText('Q1?');
      fireEvent.keyDown(window, { key: 'Enter' });
      expect(onOpen).toHaveBeenCalledWith('b-1');
    });

    it('"n" opens new-brief modal', async () => {
      render(<BriefsTab onOpen={vi.fn()} />);
      await screen.findByText('Q1?');
      fireEvent.keyDown(window, { key: 'n' });
      expect(screen.getByRole('dialog', { name: /new brief/i })).toBeInTheDocument();
    });

    it('"?" opens keyboard hint overlay', async () => {
      render(<BriefsTab onOpen={vi.fn()} />);
      await screen.findByText('Q1?');
      fireEvent.keyDown(window, { key: '?' });
      expect(screen.getByRole('dialog', { name: /keyboard/i })).toBeInTheDocument();
    });
  });

  it('shows error card on fetch failure with retry', async () => {
    mockList.mockRejectedValueOnce(new Error('network down'));
    render(<BriefsTab onOpen={vi.fn()} />);
    expect(await screen.findByText(/network down/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });

  it('renders consistently in light and dark theme', async () => {
    mockList.mockResolvedValue({
      briefs: [makeBrief()],
      next_cursor: null,
      count: 1,
    });
    applyTheme('light');
    const { unmount } = render(<BriefsTab onOpen={vi.fn()} />);
    await screen.findByText(/Should we accelerate/);
    unmount();
    applyTheme('dark');
    render(<BriefsTab onOpen={vi.fn()} />);
    await screen.findByText(/Should we accelerate/);
  });

  it.todo('cursor pagination loads next page when scrolling near bottom');
  it.todo('filter chip group filters by state without refetching all');
});
