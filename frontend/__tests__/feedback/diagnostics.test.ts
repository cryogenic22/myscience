/**
 * SPEC_041 Stage 3 — diagnostics module
 *
 * Wraps console.error and window.fetch so that errors / failed requests
 * are captured in a ring buffer (max 50 each) for later submission with
 * a feedback report. installDiagnostics() runs once per session;
 * collectDiagnostics() snapshots the buffers + page metadata; clear()
 * empties them after a successful submit.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import {
  installDiagnostics,
  collectDiagnostics,
  clearDiagnostics,
  __resetDiagnosticsForTests,
} from '../../src/lib/diagnostics';

describe('diagnostics — installDiagnostics()', () => {
  beforeEach(() => {
    __resetDiagnosticsForTests();
  });
  afterEach(() => {
    __resetDiagnosticsForTests();
  });

  it('wraps console.error and pushes to the error buffer', () => {
    installDiagnostics();
    console.error('boom: thing failed');
    const snap = collectDiagnostics();
    expect(snap.errors.length).toBe(1);
    expect(snap.errors[0].message).toContain('boom: thing failed');
    expect(snap.errors[0].ts).toBeTruthy();
  });

  it('does not double-install — calling twice is a no-op', () => {
    installDiagnostics();
    installDiagnostics();
    console.error('once');
    const snap = collectDiagnostics();
    expect(snap.errors.length).toBe(1);
  });

  it('caps the error ring buffer at 50 (FIFO eviction)', () => {
    installDiagnostics();
    for (let i = 0; i < 60; i++) console.error(`err-${i}`);
    const snap = collectDiagnostics();
    expect(snap.errors.length).toBe(50);
    expect(snap.errors[0].message).toContain('err-10');
    expect(snap.errors[49].message).toContain('err-59');
  });

  it('wraps fetch and records non-OK responses to failed_requests', async () => {
    installDiagnostics();
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response('not found', { status: 404, statusText: 'Not Found' }),
    );
    vi.stubGlobal('fetch', fetchMock);

    // The wrapper is installed once; subsequent fetch calls go through it.
    // installDiagnostics replaces window.fetch with a wrapper; reinstall after
    // the mock so the wrapper points at the mock.
    __resetDiagnosticsForTests();
    installDiagnostics();

    await fetch('/api/widgets');
    const snap = collectDiagnostics();
    expect(snap.failed_requests.length).toBe(1);
    expect(snap.failed_requests[0].status).toBe(404);
    expect(snap.failed_requests[0].url).toContain('/api/widgets');
  });

  it('does NOT record OK fetches to failed_requests', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response('{}', { status: 200 }),
    );
    vi.stubGlobal('fetch', fetchMock);
    installDiagnostics();
    await fetch('/api/health');
    const snap = collectDiagnostics();
    expect(snap.failed_requests.length).toBe(0);
  });

  it('caps the failed_requests buffer at 50', async () => {
    const responses = Array.from({ length: 60 }, (_, i) =>
      new Response('boom', { status: 500 }),
    );
    let i = 0;
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(responses[i++]));
    vi.stubGlobal('fetch', fetchMock);
    installDiagnostics();
    for (let n = 0; n < 60; n++) {
      await fetch(`/api/n/${n}`);
    }
    const snap = collectDiagnostics();
    expect(snap.failed_requests.length).toBe(50);
  });

  it('collectDiagnostics() returns viewport, theme, route metadata', () => {
    installDiagnostics();
    const snap = collectDiagnostics();
    expect(snap.viewport).toBeDefined();
    expect(typeof snap.viewport.w).toBe('number');
    expect(typeof snap.viewport.h).toBe('number');
    expect(snap.theme === 'light' || snap.theme === 'dark').toBe(true);
    expect(typeof snap.route).toBe('string');
    expect(typeof snap.user_agent).toBe('string');
  });

  it('clearDiagnostics() empties both buffers', () => {
    installDiagnostics();
    console.error('still here?');
    clearDiagnostics();
    const snap = collectDiagnostics();
    expect(snap.errors.length).toBe(0);
    expect(snap.failed_requests.length).toBe(0);
  });

  it('captures fetch network errors (rejected promise) as failed_requests', async () => {
    const fetchMock = vi.fn().mockRejectedValueOnce(new TypeError('NetworkError'));
    vi.stubGlobal('fetch', fetchMock);
    installDiagnostics();
    await expect(fetch('/api/down')).rejects.toThrow();
    const snap = collectDiagnostics();
    expect(snap.failed_requests.length).toBe(1);
    expect(snap.failed_requests[0].url).toContain('/api/down');
    expect(snap.failed_requests[0].status).toBeUndefined();
  });

  it.todo('errors fired before installDiagnostics() are not captured (documented behavior)');
});
