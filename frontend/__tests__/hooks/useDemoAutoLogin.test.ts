import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useDemoAutoLogin } from '../../src/hooks/useDemoAutoLogin';

/** Build a JWT-shaped token with a given `exp` (seconds). Signature is irrelevant to the hook,
 *  which only decodes the payload to check expiry. */
function makeJwt(expSeconds: number): string {
  const enc = (o: object) =>
    btoa(JSON.stringify(o)).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  return `${enc({ alg: 'HS256', typ: 'JWT' })}.${enc({ sub: 'u', role: 'enterprise', exp: expSeconds })}.sig`;
}
const nowS = () => Math.floor(Date.now() / 1000);

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
  it('does nothing when a valid, unexpired JWT is already stored', async () => {
    const good = makeJwt(nowS() + 3600); // expires in 1h
    window.localStorage.setItem('mz_auth_token', good);
    const fetchSpy = vi.spyOn(globalThis, 'fetch');

    renderHook(() => useDemoAutoLogin());
    // give the effect a tick
    await new Promise((r) => setTimeout(r, 10));
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(window.localStorage.getItem('mz_auth_token')).toBe(good);
  });

  it('re-logs-in when the stored token is EXPIRED (self-heals instead of wedging on 401)', async () => {
    window.localStorage.setItem('mz_auth_token', makeJwt(nowS() - 3600)); // expired 1h ago
    window.localStorage.setItem('mz_auth_role', 'enterprise');
    const fresh = makeJwt(nowS() + 3600);
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ access_token: fresh, role: 'enterprise', email: 'e@d' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );

    renderHook(() => useDemoAutoLogin({ reloadOnSuccess: false }));
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    expect(String(fetchSpy.mock.calls[0]?.[0] ?? '')).toMatch(/\/auth\/login$/);
    await waitFor(() => expect(window.localStorage.getItem('mz_auth_token')).toBe(fresh));
  });

  it('re-logs-in when the stored token is malformed (not a JWT)', async () => {
    window.localStorage.setItem('mz_auth_token', 'not-a-jwt');
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ access_token: makeJwt(nowS() + 3600), role: 'viewer', email: 'e@d' }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    renderHook(() => useDemoAutoLogin({ reloadOnSuccess: false }));
    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
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
    // Token must remain absent — anonymous is OK; a bogus value is worse than none because every
    // protected fetch would 401. (isTokenUsable also rejects a bad value on the next load.)
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
