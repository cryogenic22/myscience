/**
 * SPEC_041 Stage 3 — FeedbackWidget chat-style submission flow.
 *
 * State machine: greeting → category_selected → description_provided
 *               → priority_selected → confirmed → submitted | error
 *
 * Pulls the panel open by listening for window 'mz:open-feedback' so
 * FeedbackButton stays decoupled.
 */

import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import FeedbackWidget from '../../src/components/feedback/FeedbackWidget';

const { mockSubmit } = vi.hoisted(() => ({ mockSubmit: vi.fn() }));
vi.mock('../../src/api', async () => {
  const actual = await vi.importActual<typeof import('../../src/api')>('../../src/api');
  return {
    ...actual,
    feedbackApi: {
      submit: mockSubmit,
      list: vi.fn(),
      update: vi.fn(),
      stats: vi.fn(),
    },
  };
});

function open() {
  act(() => {
    window.dispatchEvent(new CustomEvent('mz:open-feedback'));
  });
}

describe('FeedbackWidget', () => {
  beforeEach(() => {
    mockSubmit.mockReset();
    // Stage 6 fix M3 added sessionStorage draft persistence — clear it
    // between tests so a previous test's transient draft doesn't seed
    // the next one.
    window.sessionStorage.clear();
  });
  afterEach(() => {
    document.body.innerHTML = '';
    window.sessionStorage.clear();
  });

  it('is closed by default — no dialog rendered until open event fires', () => {
    render(<FeedbackWidget />);
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('opens on mz:open-feedback event', () => {
    render(<FeedbackWidget />);
    open();
    expect(screen.getByRole('dialog', { name: /feedback/i })).toBeInTheDocument();
  });

  it('shows 6 category buttons in the greeting state', () => {
    render(<FeedbackWidget />);
    open();
    for (const cat of [/bug/i, /issue/i, /enhancement/i, /feature/i, /data quality/i, /data request/i]) {
      expect(screen.getByRole('button', { name: cat })).toBeInTheDocument();
    }
  });

  it('selecting a category transitions to category_selected (textarea visible)', () => {
    render(<FeedbackWidget />);
    open();
    fireEvent.click(screen.getByRole('button', { name: /^bug/i }));
    expect(screen.getByRole('textbox', { name: /describe/i })).toBeInTheDocument();
  });

  it('typing description + clicking Send moves to description_provided', () => {
    render(<FeedbackWidget />);
    open();
    fireEvent.click(screen.getByRole('button', { name: /^bug/i }));
    const textarea = screen.getByRole('textbox', { name: /describe/i });
    fireEvent.change(textarea, { target: { value: 'Brief panel jumps to top when I add a 4th option' } });
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }));
    // Priority pills appear
    for (const p of [/^low$/i, /^medium$/i, /^high$/i, /^critical$/i]) {
      expect(screen.getByRole('button', { name: p })).toBeInTheDocument();
    }
  });

  it('selecting priority then Submit posts to feedbackApi.submit with the right shape', async () => {
    mockSubmit.mockResolvedValueOnce({
      feedback: {
        id: 'fb-abc12345', category: 'bug', title: 'Brief panel jumps',
        priority: 'high', status: 'new', attachments: [],
        created_at: '2026-05-09T14:30Z', updated_at: '2026-05-09T14:30Z',
      },
    });
    render(<FeedbackWidget />);
    open();
    fireEvent.click(screen.getByRole('button', { name: /^bug/i }));
    const textarea = screen.getByRole('textbox', { name: /describe/i });
    fireEvent.change(textarea, { target: { value: 'Brief panel jumps to top when I add a 4th option.' } });
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }));
    fireEvent.click(screen.getByRole('button', { name: /^high$/i }));
    fireEvent.click(screen.getByRole('button', { name: /submit feedback/i }));

    await waitFor(() => expect(mockSubmit).toHaveBeenCalled());
    const arg = mockSubmit.mock.calls[0][0];
    expect(arg.category).toBe('bug');
    expect(arg.priority).toBe('high');
    expect(arg.title).toContain('Brief panel jumps');
    expect(arg.description).toContain('4th option');
    // Shows the recorded ID
    expect(await screen.findByText(/fb-abc12345/)).toBeInTheDocument();
  });

  it('Esc closes the open dialog', () => {
    render(<FeedbackWidget />);
    open();
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    act(() => {
      fireEvent.keyDown(document, { key: 'Escape' });
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('shows role="alert" when submit fails', async () => {
    mockSubmit.mockRejectedValueOnce(new Error('network down'));
    render(<FeedbackWidget />);
    open();
    fireEvent.click(screen.getByRole('button', { name: /^bug/i }));
    fireEvent.change(screen.getByRole('textbox', { name: /describe/i }), {
      target: { value: 'a thing went wrong' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }));
    fireEvent.click(screen.getByRole('button', { name: /^medium$/i }));
    fireEvent.click(screen.getByRole('button', { name: /submit feedback/i }));
    expect(await screen.findByRole('alert')).toHaveTextContent(/network down/);
  });

  it('paste of an image attaches a thumbnail (PNG data URI)', async () => {
    render(<FeedbackWidget />);
    open();
    fireEvent.click(screen.getByRole('button', { name: /^bug/i }));
    const textarea = screen.getByRole('textbox', { name: /describe/i });

    const blob = new Blob(['mock-png-bytes'], { type: 'image/png' });
    const file = new File([blob], 'pasted.png', { type: 'image/png' });
    const dt = {
      items: [
        {
          type: 'image/png',
          getAsFile: () => file,
        },
      ],
    } as unknown as DataTransfer;

    fireEvent.paste(textarea, { clipboardData: dt });
    // Thumbnail / message about attached screenshot appears
    expect(await screen.findByAltText(/pasted/i)).toBeInTheDocument();
  });

  it.todo('Backspace on a focused thumbnail removes that attachment');
  it.todo('focus is trapped inside the dialog when open');
});
