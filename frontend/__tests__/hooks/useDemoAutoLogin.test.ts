import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useDemoAutoLogin } from '../../src/hooks/useDemoAutoLogin';

// Reload after a successful auto-login is intentional; tests stub it.
const reloadSpy = vi.fn();
beforeEach(() => {
  window.localStorage.clear();
  reloadSpy.mockReset();
  Object.defineProperty(window, 'location', {
    value: { reload: reloadSpy, href: 'http://localhost:5180/ci' },
    writable: true,
    configurable: true,
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('useDemoAutoLogin', () => {
  it('does nothing when a non-legacy token is already stored', async () => {
    window.localStorage.setItem('mz_auth_token', 'eyJ-real-jwt');
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    renderHook(() => useDemoAutoLogin());
    // give the effect a tick
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(window.localStorage.getItem('mz_auth_token')).toBe('eyJ-real-jwt');
  });

  it('wipes the legacy `demo-token` literal so the auto-login can replace it', async () => {
    window.localStorage.setItem('mz_auth_token', 'demo-token');
    window.localStorage.setItem('mz_auth_role', 'enterprise');

    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ access_token: 'eyJ-real-jwt', role: 'enterprise', email: 'e@d' }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    renderHook(() => useDemoAutoLogin());
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    // Either the login URL was called…
    const calledUrl = String(fetchSpy.mock.calls[0]?.[0] ?? '');
    expect(calledUrl).toMatch(/\/auth\/login$/);
  });

  it('POSTs the demo enterprise credentials when token is absent', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ access_token: 'eyJ-real-jwt', role: 'enterprise', email: 'e@d' }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    renderHook(() => useDemoAutoLogin());
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());

    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(init.method).toBe('POST');
    expect(init.headers).toMatchObject({ 'Content-Type': 'application/json' });
    const body = JSON.parse(init.body as string);
    expect(body.email).toMatch(/@demo\.market-zero\.io$/);
    expect(body.password).toBe('demo');
  });

  it('stores the real access_token and role on successful login', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ access_token: 'eyJ-real-jwt', role: 'enterprise', email: 'e@d' }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    renderHook(() => useDemoAutoLogin());
    await waitFor(() => expect(window.localStorage.getItem('mz_auth_token')).toBe('eyJ-real-jwt'));
    expect(window.localStorage.getItem('mz_auth_role')).toBe('enterprise');
  });

  it('does NOT crash or leave a broken token if /auth/login fails', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('{"detail":"invalid credentials"}', { status: 401 }),
    );

    renderHook(() => useDemoAutoLogin());
    await new Promise((r) => setTimeout(r, 20));
    // Token must remain absent — anonymous user is OK, but a bogus
    // value is worse than no value because it triggers AUTH_EXPIRED
    // cycles on every protected fetch.
    expect(window.localStorage.getItem('mz_auth_token')).toBeNull();
  });

  it('does NOT reload the page in tests (reload is opt-in via the consumer)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(
        JSON.stringify({ access_token: 'eyJ-real-jwt', role: 'enterprise', email: 'e@d' }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      ),
    );

    renderHook(() => useDemoAutoLogin({ reloadOnSuccess: false }));
    await waitFor(() => expect(window.localStorage.getItem('mz_auth_token')).toBe('eyJ-real-jwt'));
    expect(reloadSpy).not.toHaveBeenCalled();
  });
});
