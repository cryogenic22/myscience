"""SPEC_018 — Authentication service: bcrypt + JWT + role hierarchy.

Pure-function helpers. No DB or HTTP — those live in api/routes/auth.py +
api/deps.py respectively. This module is the unit-testable core.

Security notes:
  - Passwords hashed with bcrypt (work factor = library default).
  - JWTs signed HS256 with MZ_JWT_SECRET. In dev (no env var) we generate
    a random per-process secret so tokens stay session-local — server
    restart invalidates all tokens.
  - Tokens carry: sub (user_id), email, role, iat, exp. 24h default TTL.
  - Role hierarchy: enterprise > uploader > viewer (anonymous = None).
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from typing import Any, Optional

import bcrypt
import jwt

logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────

ROLE_HIERARCHY: dict[str, int] = {
    "viewer": 1,
    "uploader": 2,
    "enterprise": 3,
}

DEFAULT_TOKEN_TTL_SECONDS = 24 * 3600  # 24 hours

# JWT secret: env var in prod, random per-process in dev.
# Lookup order: MZ_JWT_SECRET (preferred) → SECRET_KEY (Railway default
# secret slot) → random per-process token (dev only). Random means
# server restart → all tokens invalidated; production must set one of
# the env vars.
_JWT_SECRET = (
    os.getenv("MZ_JWT_SECRET")
    or os.getenv("SECRET_KEY")
    or secrets.token_urlsafe(32)
)
_JWT_ALGORITHM = "HS256"


class AuthError(Exception):
    """Raised on auth-layer failures (bad token, expired, signature mismatch)."""


# ── Password hashing ───────────────────────────────────────────────

def hash_password(plaintext: str) -> str:
    """Hash a password using bcrypt. Returns the hash as a UTF-8 string."""
    if not isinstance(plaintext, str):
        raise TypeError("password must be a string")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plaintext.encode("utf-8"), salt).decode("utf-8")


def verify_password(plaintext: str, hashed: str) -> bool:
    """Constant-time bcrypt verify. Returns False on any error (defensive)."""
    if not isinstance(plaintext, str) or not isinstance(hashed, str):
        return False
    if not plaintext or not hashed:
        return False
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Garbage hash format → treat as non-match
        return False


# ── JWT issue + decode ─────────────────────────────────────────────

def issue_token(
    user_id: str,
    email: str,
    role: str,
    expires_in_seconds: int = DEFAULT_TOKEN_TTL_SECONDS,
) -> str:
    """Issue a signed JWT. Negative expires_in_seconds is allowed (for testing
    expired-token rejection).
    """
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "email": email,
        "role": role,
        "iat": now,
        "exp": now + expires_in_seconds,
    }
    return jwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    """Decode and validate a JWT. Raises AuthError on any failure
    (expired, bad signature, malformed, etc.)."""
    if not token or not isinstance(token, str):
        raise AuthError("missing or invalid token")
    try:
        return jwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError(f"invalid token: {exc}") from exc


# ── Role hierarchy ─────────────────────────────────────────────────

def role_satisfies(user_role: Optional[str], required_role: str) -> bool:
    """Does the user_role meet the required_role?

    Hierarchy: enterprise > uploader > viewer. Anonymous (user_role=None)
    satisfies nothing. Unknown roles satisfy nothing.
    """
    if not user_role or not required_role:
        return False
    user_level = ROLE_HIERARCHY.get(user_role)
    required_level = ROLE_HIERARCHY.get(required_role)
    if user_level is None or required_level is None:
        return False
    return user_level >= required_level
