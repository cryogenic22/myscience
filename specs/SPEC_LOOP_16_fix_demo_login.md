# Loop #16 — Fix the broken `demo-token` auto-login

**Status:** Shipped 2026-05-11
**Type:** bug
**Reporter:** user ("why am i still getting these issues still can we fix. 401: {…}")
**Source:** `CIPage.tsx:78` — pre-existing literal `'demo-token'` shim

## Root cause

`CIPage`'s auto-login stored the literal string `'demo-token'`
under `localStorage.mz_auth_token`. The backend can't decode that
as a JWT (`services.auth.decode_token` throws `AuthError`), so
`get_current_user` returns `None`, and any endpoint guarded by
`require_role(…)` returns:

```
HTTP 401
{ "detail": "authentication required" }
```

Wrapped by upstream middleware into the shape the user pasted.

The pre-existing `expectJson` 401-handler (`api.ts:1811`) then
cleared the token and dispatched `mz:auth-expired` → App redirected
to `/?session=expired` → user navigated back to `/ci` → CIPage
re-set the broken token → cycle repeated.

## Fix

New `useDemoAutoLogin()` hook:

```typescript
useEffect(() => {
  const stored = localStorage.getItem('mz_auth_token');
  if (stored === 'demo-token') {
    // One-time migration: wipe the broken literal.
    localStorage.removeItem('mz_auth_token');
    localStorage.removeItem('mz_auth_role');
  } else if (stored) {
    return;  // Real token in place — leave alone.
  }
  fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      email: 'enterprise@demo.market-zero.io',
      password: 'demo',
    }),
  })
    .then((r) => (r.ok ? r.json() : null))
    .then((d) => {
      if (!d?.access_token) return;
      localStorage.setItem('mz_auth_token', d.access_token);
      localStorage.setItem('mz_auth_role', d.role);
      window.location.reload();
    })
    .catch(() => { /* anonymous OK */ });
}, []);
```

`CIPage` replaces its inline shim with `useDemoAutoLogin()`.

### Anonymous is better than bad

If the demo-login endpoint itself fails (DB down, account not
seeded), the hook leaves the token absent. A null token is better
than a bad token because it does not trigger the AUTH_EXPIRED
cycle — protected surfaces show their own auth-prompt state
instead.

## Tests

`__tests__/hooks/useDemoAutoLogin.test.ts` — 6 cases:

1. No-op when a non-legacy token exists
2. Wipes the legacy `'demo-token'` string
3. POSTs the demo credentials with correct method + headers + body
4. Stores the real `access_token` + `role` on success
5. Leaves token empty on login failure (no broken token)
6. Does not reload when `reloadOnSuccess: false`

## Quality gate

- `npx tsc --noEmit` → clean
- `npx vitest run --no-file-parallelism` → **524 passing, 22 todo,
  0 failures** (57 files; +7 over Loop #15)

## Out of scope (filed as follow-ups)

- Same pattern in `BriefComposerPage` / `DossierPage` if those
  ever require auth — currently they don't, so anonymous works.
- A visible "logged in as enterprise@demo" indicator in the
  cockpit footer so the user can see what account is active.
- A "log out" affordance from the cockpit chrome.
