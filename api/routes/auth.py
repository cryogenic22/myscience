"""SPEC_018 — Auth endpoints: POST /auth/login, GET /auth/me.

Login exchanges email+password for a JWT. /auth/me echoes back the current
user (requires viewer+). Both endpoints are unprefixed-path under /auth.

NEVER log raw passwords here — the static check in tests/test_role_gates.py
enforces this.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from api.deps import get_current_user, get_db, require_role
from db import Database
from services.auth import (
    AuthError,
    issue_token,
    role_satisfies,
    verify_password,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    email: str


class UserMeResponse(BaseModel):
    id: str
    email: str
    role: str


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, db: Database = Depends(get_db)) -> LoginResponse:
    """Exchange email + password for a 24h JWT."""
    email = (body.email or "").strip().lower()
    if not email or not body.password:
        raise HTTPException(status_code=401, detail="invalid credentials")

    row = db.fetch_one(
        "SELECT id::text AS id, email, password_hash, role, is_active "
        "FROM users WHERE LOWER(email) = %s LIMIT 1",
        [email],
    )
    if not row or not row.get("is_active"):
        # Generic error — don't reveal whether email exists
        raise HTTPException(status_code=401, detail="invalid credentials")

    if not verify_password(body.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="invalid credentials")

    # Update last_login_at (fire-and-forget — failure shouldn't block login)
    try:
        db.execute(
            "UPDATE users SET last_login_at = NOW() WHERE id::text = %s",
            [row["id"]],
        )
    except Exception:
        logger.exception("failed to update last_login_at for user")

    token = issue_token(
        user_id=row["id"],
        email=row["email"],
        role=row["role"],
    )
    return LoginResponse(
        access_token=token,
        token_type="bearer",
        role=row["role"],
        email=row["email"],
    )


@router.get("/me", response_model=UserMeResponse)
def me(user: dict = Depends(require_role("viewer"))) -> UserMeResponse:
    """Return the current authenticated user's basic info."""
    return UserMeResponse(
        id=user["id"],
        email=user["email"],
        role=user["role"],
    )
