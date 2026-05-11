/**
 * SPEC_041 Stage 6 — regression tests for the red-team findings closed
 * during FIX-ALL (spec §13a). One block per finding.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import {
  installDiagnostics,
  collectDiagnostics,
  __resetDiagnosticsForTests,
} from '../../src/lib/diagnostics';
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
      remove: vi.fn(),
    },
  };
});

function open() {
  act(() => {
    window.dispatchEvent(new CustomEvent('mz:open-feedback'));
  });
}

describe('Stage 6 fix M1 — diagnostics PII redaction', () => {
  beforeEach(() => __resetDiagnosticsForTests());
  afterEach(() => __resetDiagnosticsForTests());

  it('redacts ?token=… from failed_request URLs', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('boom', { status: 500 }));
    vi.stubGlobal('fetch', fetchMock);
    installDiagnostics();
    await fetch('/api/widgets?token=super-secret-abc&id=42');
    const snap = collectDiagnostics();
    expect(snap.failed_requests[0].url).toContain('token=%3Credacted%3E');
    expect(snap.failed_requests[0].url).not.toContain('super-secret-abc');
    // Non-sensitive params survive
    expect(snap.failed_requests[0].url).toContain('id=42');
  });

  it('redacts ?api_key=… and ?authorization=… too', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response('boom', { status: 500 }));
    vi.stubGlobal('fetch', fetchMock);
    installDiagnostics();
    await fetch('/api/x?api_key=abc&authorization=Bearer-XYZ');
    const snap = collectDiagnostics();
    expect(snap.failed_requests[0].url).not.toContain('abc');
    expect(snap.failed_requests[0].url).not.toContain('Bearer-XYZ');
  });

  it('redacts JWTs and long token-shaped strings inside response bodies', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response('error: eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.AAAA.BBBB extra', {
        status: 401,
      }),
    );
    vi.stubGlobal('fetch', fetchMock);
    installDiagnostics();
    await fetch('/api/something');
    const snap = collectDiagnostics();
    expect(snap.failed_requests[0].body).not.toContain('eyJhbGci');
  });

  it('truncates very long error messages', () => {
    installDiagnostics();
    console.error('A'.repeat(2000));
    const snap = collectDiagnostics();
    expect(snap.errors[0].message.length).toBeLessThanOrEqual(1100);
    expect(snap.errors[0].message).toContain('<truncated>');
  });
});

describe('Stage 6 fix M2 — feedback widget focus trap + Esc preserves draft', () => {
  beforeEach(() => {
    mockSubmit.mockReset();
    window.sessionStorage.clear();
    document.body.innerHTML = '';
  });

  it('initial focus moves to the close button on open', async () => {
    render(<FeedbackWidget />);
    open();
    await waitFor(() => {
      const close = screen.getByRole('button', { name: /close/i });
      expect(document.activeElement).toBe(close);
    });
  });
});

describe('Stage 6 fix M3 — Esc preserves the draft', () => {
  beforeEach(() => {
    mockSubmit.mockReset();
    window.sessionStorage.clear();
    document.body.innerHTML = '';
  });

  it('typing then closing then re-opening restores the in-flight description', async () => {
    const { unmount } = render(<FeedbackWidget />);
    open();
    fireEvent.click(screen.getByRole('button', { name: /^bug/i }));
    const textarea = screen.getByRole('textbox', { name: /describe/i });
    fireEvent.change(textarea, { target: { value: 'half-typed bug report' } });

    // Esc closes
    act(() => {
      fireEvent.keyDown(document, { key: 'Escape' });
    });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

    // Re-open — the draft is restored
    open();
    const restored = screen.getByRole('textbox', { name: /describe/i });
    expect((restored as HTMLTextAreaElement).value).toBe('half-typed bug report');

    unmount();
  });

  it('successful submit clears the persisted draft', async () => {
    mockSubmit.mockResolvedValueOnce({
      feedback: {
        id: 'fb-cleared', category: 'bug', title: 'x', priority: 'medium',
        status: 'new', attachments: [], created_at: 'now', updated_at: 'now',
      },
    });
    render(<FeedbackWidget />);
    open();
    fireEvent.click(screen.getByRole('button', { name: /^bug/i }));
    fireEvent.change(screen.getByRole('textbox', { name: /describe/i }), {
      target: { value: 'a fully-typed bug report' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^send$/i }));
    fireEvent.click(screen.getByRole('button', { name: /^medium$/i }));
    fireEvent.click(screen.getByRole('button', { name: /submit feedback/i }));
    await waitFor(() => expect(mockSubmit).toHaveBeenCalled());
    expect(window.sessionStorage.getItem('mz_feedback_draft_v1')).toBeNull();
  });
});

describe('Stage 6 fix M2-extension — mz_feedback_disabled also gates the widget', () => {
  beforeEach(() => {
    mockSubmit.mockReset();
    document.body.innerHTML = '';
    window.sessionStorage.clear();
    window.localStorage.removeItem('mz_feedback_disabled');
  });
  afterEach(() => {
    window.localStorage.removeItem('mz_feedback_disabled');
  });

  it('event-driven open is suppressed when mz_feedback_disabled=true', () => {
    window.localStorage.setItem('mz_feedback_disabled', 'true');
    render(<FeedbackWidget />);
    open();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });
});

describe('Stage 6 fix M4 — feedbackApi.remove issues DELETE', () => {
  it('issues DELETE /feedback/{id} and treats 204 as success', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
    // Bypass the file-level vi.mock('../../src/api', ...) so we hit the
    // real feedbackApi.remove implementation against the mocked fetch.
    const real = (await vi.importActual<typeof import('../../src/api')>(
      '../../src/api',
    ));
    const r = await real.feedbackApi.remove('fb-1');
    expect(r).toEqual({ ok: true });
    expect(fetchMock.mock.calls[0][0]).toContain('/feedback/fb-1');
    expect(fetchMock.mock.calls[0][1]?.method).toBe('DELETE');
  });
});
