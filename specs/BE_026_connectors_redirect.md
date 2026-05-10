# BE-26 — /connectors → /api/v1/connectors + 301 to /catalog

> Filed in `docs/AGENT_BACKLOG.md#be-26`. Branch:
> `claude/be-026-connectors-redirect`.

## 1 · What backend does (this PR)

The JSON API is already mounted at **both** `/connectors` and
`/api/v1/connectors` via the versioned-router pattern in
`api/app.py` (lines 301-303). So step 1 of BE-26 — "Move JSON
response to /api/connectors" — is already structurally true.

What this PR adds is the **deprecation hint** so clients hitting
the legacy path migrate. RFC 8594-compatible response headers on
GET /connectors and GET /connectors/{key}:

```
Deprecation: true
Sunset: Wed, 31 Dec 2026 23:59:59 GMT
Link: </api/v1/connectors>; rel="successor-version"
```

The headers fire only when the request URL starts with `/connectors`
(not `/api/v1/connectors`). Same handler runs for both prefixes;
the live `Request` object disambiguates.

## 2 · What stays on the frontend (PB-809)

> /connectors HTTP route returns 301 to /catalog.

That redirect is HTML / SPA routing — Vite + React decides which
component to render at `/connectors`. Lives on the FE track:

- The `/connectors` SPA route should redirect to `/catalog` once the
  catalog UI is ready (PB-801..808 ship).
- Server-rendered or static-file 301 (if used) lives in the deploy
  config (Railway / Nginx) — not in this Python codebase.

Documented here so the cutover stays auditable.

## 3 · Acceptance

- [x] `/api/v1/connectors` is the canonical JSON path (already
      mounted; documented).
- [x] Bare `/connectors` GET endpoints emit Deprecation + Sunset +
      Link headers.
- [x] `/api/v1/connectors` does NOT emit deprecation headers.
- [ ] Frontend ships a `/connectors` → `/catalog` SPA redirect
      (PB-809).
