# SPEC-018: Authentication + Role-Based Access

*Date: 19 April 2026*
*Status: implementation in progress*

---

## Goal

Add a 4-tier role-based access layer to Market Zero so we can demo different user
experiences in consulting pitches and gate sensitive features (uploads, admin
operations) appropriately. Demo credentials, no SSO, JWT-based.

## Role Model

| Role | Can do | Demo email |
|------|--------|------------|
| **anonymous** (no auth) | Browse public catalog, view entity details, search literature | — |
| **viewer** | Anonymous + chat, save sessions, give feedback, see CTX telemetry | `viewer@demo.market-zero.io` |
| **uploader** | Viewer + upload documents (POST /upload, SPEC_014) | `uploader@demo.market-zero.io` |
| **enterprise** | Uploader + admin endpoints (steward triggers, dataset config, view internal data) | `enterprise@demo.market-zero.io` |

Roles are **strictly hierarchical**: enterprise > uploader > viewer > anonymous. A check for "uploader" passes for both `uploader` and `enterprise` users.

All demo accounts use password `demo` (overridable via `MZ_DEMO_PASSWORD` env var if production needs different defaults).

## Non-Goals (deferred)

- OAuth / SSO / SAML — single demo password is enough for the consulting accelerator pitch
- Password reset flow — demo credentials are seeded; users don't change them
- Multi-tenant isolation — single tenant for v1
- Refresh tokens — 24-hour access tokens with re-login on expiry is fine for demo
- Email verification — accounts are pre-seeded
- Rate limiting per user — handled at infrastructure layer (Railway/Cloudflare)
- Audit logging — basic last_login_at only; richer audit is a follow-up

## Architecture

### Storage

New `users` table (migration 034):

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_login_at TIMESTAMPTZ,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSONB DEFAULT '{}'::jsonb,
    CONSTRAINT users_role_valid CHECK (role IN ('viewer', 'uploader', 'enterprise'))
);

CREATE INDEX idx_users_email ON users(LOWER(email));
```

Note: `anonymous` is not stored as a row — it's the absence of auth.

### Token

JWT (HS256) with payload:

```json
{
  "sub": "<user_id>",
  "email": "<email>",
  "role": "viewer | uploader | enterprise",
  "iat": <unix_ts>,
  "exp": <unix_ts + 24h>
}
```

Signed with `MZ_JWT_SECRET` env var (must be set in production; dev uses random per-process value).

### Endpoints

| Method | Path | Purpose | Auth |
|--------|------|---------|------|
| POST | `/auth/login` | Exchange email+password for JWT | none |
| GET | `/auth/me` | Return current user info | viewer+ |

### Dependencies (FastAPI)

```python
# api/deps.py

def get_current_user(authorization: str = Header(None), db = Depends(get_db)) -> Optional[User]:
    """Returns User if valid JWT in Authorization header, None otherwise (anonymous)."""

def require_role(min_role: str):
    """Returns a FastAPI dependency that 401s anonymous and 403s insufficient role."""
```

Usage:
```python
@router.post("/upload", dependencies=[Depends(require_role("uploader"))])
def upload_document(...): ...
```

## Route Gating (initial pass)

| Route | Min role | Reason |
|-------|----------|--------|
| `GET /search`, `/catalog/*` (browse), `/entities/*` (read), `/graph/*` | anonymous | Public catalog browsing — must work without login for demos |
| `POST /chat`, `/chat/stream`, `/chat/sessions/*` | anonymous (for now) | Chatbot demo accessible to anonymous; we can promote to `viewer` later if abuse is observed |
| `POST /feedback/*` | viewer | Need session attribution |
| `POST /upload` | uploader | The whole reason this spec exists |
| `POST /steward/*`, `/intelligence/*` (admin actions) | enterprise | Internal curation, mutates state |
| `POST /catalog/refresh-views`, `/catalog/bulk-update`, `/enrichment/*` (write) | enterprise | DB mutations |
| `GET /catalog/admin/*`, `/metrics/ctx-telemetry` | viewer | Internal but read-only |

**Rationale**: keep the "demo wedge" (chat, browse) open so anyone can experience the system. Gate the upload — that's where consulting clients see "this is yours, log in to use." Gate enterprise endpoints to prevent demo users from triggering production-affecting operations.

## Tests First

Two test files (TDD):

### `tests/test_auth.py`
- `password_hash_and_verify_roundtrip` — bcrypt hash + verify
- `password_verify_rejects_wrong_password`
- `jwt_issue_and_decode_roundtrip` — payload preserved
- `jwt_expired_token_raises`
- `jwt_invalid_signature_raises`
- `role_hierarchy_satisfies` — enterprise satisfies uploader, uploader satisfies viewer
- `role_hierarchy_does_not_satisfy_higher` — viewer does NOT satisfy uploader

### `tests/test_role_gates.py`
- `login_endpoint_returns_token_for_valid_credentials`
- `login_endpoint_returns_401_for_invalid_password`
- `login_endpoint_returns_401_for_unknown_email`
- `me_endpoint_returns_user_info_with_valid_token`
- `me_endpoint_returns_401_without_token`
- `protected_route_returns_401_without_token` (e.g. `/upload`)
- `protected_route_returns_403_with_insufficient_role` (viewer hits /upload)
- `protected_route_returns_200_with_sufficient_role` (uploader hits /upload)
- `enterprise_role_can_access_uploader_endpoint` (hierarchy)
- `static_check_upload_route_has_role_gate` (regression-proof — code must contain `require_role("uploader")`)

All tests must FAIL before implementation.

## Implementation Plan

1. Add deps to requirements.txt: `bcrypt>=4.0`, `pyjwt>=2.8`
2. Migration 034: `users` table + indices + constraint
3. `services/auth.py`: hash, verify, issue, decode, hierarchy
4. `api/deps.py`: `get_current_user`, `require_role`
5. `api/routes/auth.py`: `POST /auth/login`, `GET /auth/me`; register in `api/app.py`
6. Gate `/upload` route with `require_role("uploader")`
7. Seed script `scripts/seed_demo_users.py`
8. Run all tests; commit

## Acceptance

- All tests in `tests/test_auth.py` and `tests/test_role_gates.py` pass
- Existing test suite: zero regressions (1214+ baseline)
- After deploy + migration 034 + seed:
  - `POST /auth/login {email: "viewer@demo.market-zero.io", password: "demo"}` → 200 with token
  - `GET /auth/me` with bearer token → 200 with user info
  - `POST /upload` without token → 401
  - `POST /upload` with viewer token → 403
  - `POST /upload` with uploader/enterprise token → 200
  - `POST /chat` still works without token (anonymous chat preserved)

## Rollout

1. Local tests pass
2. Deploy to Railway (RAILWAY env auto-deploys from main)
3. Apply migration: `railway run python migrate.py`
4. Seed demo users: `railway run python scripts/seed_demo_users.py`
5. Set `MZ_JWT_SECRET` in Railway env (random 32+ chars)
6. Verify login works from frontend or curl
7. Frontend follow-up: add login page + token storage + role-aware UI rendering (separate spec)

## Rollback

- Remove `Depends(require_role(...))` from any over-restrictive route
- Set `MZ_JWT_SECRET` to empty to disable token validation entirely (dev only)
- Migration 034 is additive (no breaking schema change); safe to leave applied

## Frontend Follow-up (separate spec)

- Login modal/page
- Token stored in `localStorage` under `mz_auth_token`
- API client (`frontend/src/api.ts`) adds `Authorization: Bearer <token>` to fetch calls
- Role-aware UI: hide upload button for viewer, hide steward controls for uploader, etc.
- Logout button
- "Try the demo" landing-page links to pre-fill login with each demo user
