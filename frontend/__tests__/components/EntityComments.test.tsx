/**
 * UX02 — EntityComments tests.
 *
 * Covers: load + count badge, posting a comment (optimistic append), empty
 * state, and @mention highlighting.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

vi.mock('../../src/api', () => ({
  commentsApi: { list: vi.fn(), add: vi.fn() },
}));

import { commentsApi } from '../../src/api';
import EntityComments from '../../src/components/ci/EntityComments';

function comment(over: Partial<any> = {}) {
  return {
    id: 'c1', target_type: 'brief', target_id: 'b1', author_user_id: 'u1',
    author_display_name: 'Riya', body: 'looks good, cc @priya', mentions: ['priya'],
    created_at: '2026-06-02T10:00:00Z', edited_at: null, ...over,
  };
}

describe('EntityComments', () => {
  beforeEach(() => vi.clearAllMocks());

  it('loads the thread and shows a count badge + @mention highlight', async () => {
    (commentsApi.list as any).mockResolvedValue({ comments: [comment()], count: 1 });
    render(<EntityComments targetType="brief" targetId="b1" />);
    await waitFor(() => expect(screen.getByTestId('entity-comments')).toBeInTheDocument());
    expect(screen.getByTestId('comments-count')).toHaveTextContent('1');
    expect(screen.getByText('Riya')).toBeInTheDocument();
    // the @mention is rendered as its own highlighted span
    expect(screen.getByText('@priya')).toBeInTheDocument();
  });

  it('shows the empty state when there are no comments', async () => {
    (commentsApi.list as any).mockResolvedValue({ comments: [], count: 0 });
    render(<EntityComments targetType="brief" targetId="b1" />);
    await waitFor(() => expect(screen.getByText(/No comments yet/)).toBeInTheDocument());
    expect(screen.getByTestId('comments-count')).toHaveTextContent('0');
  });

  it('posts a comment and appends it', async () => {
    (commentsApi.list as any).mockResolvedValue({ comments: [], count: 0 });
    (commentsApi.add as any).mockResolvedValue(comment({ id: 'c2', body: 'new note' }));
    render(<EntityComments targetType="brief" targetId="b1" />);
    await waitFor(() => expect(screen.getByTestId('comment-input')).toBeInTheDocument());

    fireEvent.change(screen.getByTestId('comment-input'), { target: { value: 'new note' } });
    fireEvent.click(screen.getByTestId('comment-submit'));

    await waitFor(() => expect(screen.getByText('new note')).toBeInTheDocument());
    expect(commentsApi.add).toHaveBeenCalledWith('brief', 'b1', 'new note');
    expect(screen.getByTestId('comments-count')).toHaveTextContent('1');
  });
});
