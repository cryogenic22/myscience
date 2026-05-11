import { useEffect } from 'react';
import { BASE } from '../api';

/**
 * Loop #16 — demo auto-login.
 *
 * Replaces the broken `'demo-token'` literal that CIPage used to
 * stuff into `localStorage.mz_auth_token`. The backend cannot decode
 * that string as a JWT, so every protected endpoint was returning
 * 401 → `expectJson` cleared the token → user redirected to landing
 * → user navigated back to /ci → CIPage re-set the broken token →
 * infinite 401 cycle.
 *
 * This hook does it properly: POST `/auth/login` against the seeded
 * `enterprise@demo.market-zero.io / demo` account and store the
 * returned real JWT.
 *
 * It also wipes the legacy `'demo-token'` string if it's present,
 * so users who already had the broken value self-heal on next
 * page load.
 *
 * Anonymous failure mode: if the login request itself fails (DB
 * down, account not seeded, etc.), the hook leaves `mz_auth_token`
 * empty. A null token is **better than a bad token**: protected
 * surfaces show their own auth-prompt instead of triggering the
 * 401 cycle.
 */

const DEMO_EMAIL = 'enterprise@demo.market-zero.io';
const DEMO_PASSWORD = 'demo';
const LEGACY_TOKEN = 'demo-token';

interface Options {
  /** Reload the page after a successful login so the rest of the
   *  app picks up the new token from localStorage. Default true in
   *  production; set false in tests. */
  reloadOnSuccess?: boolean;
}

export function useDemoAutoLogin(options: Options = {}): void {
  const reloadOnSuccess = options.reloadOnSuccess ?? true;

  useEffect(() => {
    if (typeof window === 'undefined') return;

    const stored = window.localStorage.getItem('mz_auth_token');
    if (stored === LEGACY_TOKEN) {
      // One-time migration: nuke the broken literal so this hook
      // can re-acquire a real token.
      window.localStorage.removeItem('mz_auth_token');
      window.localStorage.removeItem('mz_auth_role');
    } else if (stored) {
      // A non-legacy token is already in place — leave it alone.
      return;
    }

    fetch(`${BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: DEMO_EMAIL, password: DEMO_PASSWORD }),
    })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        const accessToken = data?.access_token;
        const role = data?.role;
        if (!accessToken) {
          // Leave anonymous — better than a bad token.
          return;
        }
        window.localStorage.setItem('mz_auth_token', accessToken);
        if (role) window.localStorage.setItem('mz_auth_role', role);
        if (reloadOnSuccess) {
          window.location.reload();
        }
      })
      .catch(() => {
        // Network/DB error — anonymous is OK. Surfaces that need auth
        // will render their own error states.
      });
  }, [reloadOnSuccess]);
}
