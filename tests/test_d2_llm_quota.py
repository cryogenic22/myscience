"""SPEC-021 D2 — LLM daily quota tests."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from services import llm_quota as q


def test_check_under_cap_returns_allowed(monkeypatch):
    monkeypatch.setenv("MZ_LLM_DAILY_CAP", "100")
    db = MagicMock()
    db.fetch_one.return_value = {"call_count": 50}
    allowed, used, cap, reset = q.quota_check(db, "user-1")
    assert allowed is True
    assert used == 50
    assert cap == 100
    assert reset > 0


def test_check_at_cap_denies(monkeypatch):
    monkeypatch.setenv("MZ_LLM_DAILY_CAP", "100")
    db = MagicMock()
    db.fetch_one.return_value = {"call_count": 100}
    allowed, used, cap, _ = q.quota_check(db, "user-1")
    assert allowed is False


def test_check_no_row_treats_as_zero(monkeypatch):
    monkeypatch.setenv("MZ_LLM_DAILY_CAP", "100")
    db = MagicMock()
    db.fetch_one.return_value = None
    allowed, used, _, _ = q.quota_check(db, "user-1")
    assert allowed is True
    assert used == 0


def test_check_db_failure_fails_open(monkeypatch):
    """Infra error must not block legitimate traffic."""
    monkeypatch.setenv("MZ_LLM_DAILY_CAP", "100")
    db = MagicMock()
    db.fetch_one.side_effect = RuntimeError("connection lost")
    allowed, _, _, _ = q.quota_check(db, "user-1")
    assert allowed is True


def test_increment_calls_upsert():
    db = MagicMock()
    q.quota_increment(db, "user-1")
    assert db.execute.called
    sql = db.execute.call_args[0][0].lower()
    assert "insert into llm_quota_usage" in sql
    assert "on conflict" in sql


def test_envelope_shape():
    env = q.quota_envelope(used=200, cap=200, reset_in_seconds=3600)
    assert env["error"]["code"] == 429
    assert env["error"]["type"] == "llm_quota_exceeded"
    assert env["error"]["details"]["used"] == 200
    assert env["error"]["details"]["cap"] == 200
    assert "Resets in" in env["error"]["message"]


def test_default_cap_when_env_unset(monkeypatch):
    monkeypatch.delenv("MZ_LLM_DAILY_CAP", raising=False)
    assert q._cap() == 200


def test_invalid_env_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("MZ_LLM_DAILY_CAP", "not-a-number")
    assert q._cap() == 200
