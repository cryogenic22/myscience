"""SPEC_018 — Auth service unit tests (no DB, no HTTP).

Tests for services/auth.py: bcrypt hashing, JWT issue/decode, role hierarchy.
All tests must FAIL before implementation (TDD discipline).
"""

from __future__ import annotations

import time

import pytest


# ────────────────────────────────────────────────────────────────────
# Module / class existence
# ────────────────────────────────────────────────────────────────────

def test_auth_module_exists():
    from pathlib import Path
    assert Path("services/auth.py").exists()


def test_auth_helpers_exist():
    from services.auth import (
        hash_password,
        verify_password,
        issue_token,
        decode_token,
        role_satisfies,
    )
    assert callable(hash_password)
    assert callable(verify_password)
    assert callable(issue_token)
    assert callable(decode_token)
    assert callable(role_satisfies)


# ────────────────────────────────────────────────────────────────────
# Password hashing
# ────────────────────────────────────────────────────────────────────

def test_password_hash_and_verify_roundtrip():
    from services.auth import hash_password, verify_password
    h = hash_password("demo")
    assert isinstance(h, str)
    assert h != "demo"  # not stored plaintext
    assert verify_password("demo", h) is True


def test_password_verify_rejects_wrong_password():
    from services.auth import hash_password, verify_password
    h = hash_password("demo")
    assert verify_password("wrong", h) is False
    assert verify_password("", h) is False


def test_password_hash_is_unique_per_call():
    """bcrypt salts each hash — same password → different hash."""
    from services.auth import hash_password
    h1 = hash_password("demo")
    h2 = hash_password("demo")
    assert h1 != h2  # different salts


def test_password_verify_returns_false_for_garbage_hash():
    from services.auth import verify_password
    assert verify_password("anything", "not-a-valid-bcrypt-hash") is False


# ────────────────────────────────────────────────────────────────────
# JWT issue + decode
# ────────────────────────────────────────────────────────────────────

def test_jwt_issue_and_decode_roundtrip():
    from services.auth import issue_token, decode_token
    token = issue_token(user_id="u1", email="a@b.io", role="viewer")
    payload = decode_token(token)
    assert payload["sub"] == "u1"
    assert payload["email"] == "a@b.io"
    assert payload["role"] == "viewer"
    assert "exp" in payload
    assert "iat" in payload


def test_jwt_invalid_signature_raises():
    from services.auth import decode_token, AuthError
    # Token from another secret should fail to decode
    bogus = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ4In0.invalidsig"
    with pytest.raises(AuthError):
        decode_token(bogus)


def test_jwt_malformed_raises():
    from services.auth import decode_token, AuthError
    with pytest.raises(AuthError):
        decode_token("not-a-token")


def test_jwt_expired_token_raises(monkeypatch):
    from services.auth import issue_token, decode_token, AuthError
    # Issue a token with negative TTL → already expired
    token = issue_token(
        user_id="u1", email="a@b.io", role="viewer", expires_in_seconds=-10,
    )
    with pytest.raises(AuthError):
        decode_token(token)


def test_jwt_carries_role_in_payload():
    from services.auth import issue_token, decode_token
    for role in ("viewer", "uploader", "enterprise"):
        token = issue_token(user_id="u", email="x@y.io", role=role)
        assert decode_token(token)["role"] == role


# ────────────────────────────────────────────────────────────────────
# Role hierarchy
# ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("user_role,required,expected", [
    # Same role
    ("viewer", "viewer", True),
    ("uploader", "uploader", True),
    ("enterprise", "enterprise", True),
    # Higher role satisfies lower requirement
    ("uploader", "viewer", True),
    ("enterprise", "viewer", True),
    ("enterprise", "uploader", True),
    # Lower role does NOT satisfy higher requirement
    ("viewer", "uploader", False),
    ("viewer", "enterprise", False),
    ("uploader", "enterprise", False),
    # Anonymous (None) satisfies nothing requiring auth
    (None, "viewer", False),
    (None, "uploader", False),
    (None, "enterprise", False),
])
def test_role_satisfies(user_role, required, expected):
    from services.auth import role_satisfies
    assert role_satisfies(user_role, required) is expected


def test_role_satisfies_unknown_role_returns_false():
    """Defensive: an unknown role should not satisfy anything."""
    from services.auth import role_satisfies
    assert role_satisfies("admin_misspelled", "viewer") is False
    assert role_satisfies("ANYTHING", "viewer") is False
