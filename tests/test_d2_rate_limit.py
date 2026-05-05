"""SPEC-021 D2 — rate limit middleware tests."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from api.middleware import rate_limit as rl


@pytest.fixture(autouse=True)
def _reset():
    rl.reset_rate_limit_state()
    yield
    rl.reset_rate_limit_state()


def test_under_limit_returns_allowed():
    counter = rl._SlidingCounter()
    for _ in range(5):
        allowed, retry = counter.hit("user-1", "ep-1", max_calls=10, window_s=60)
        assert allowed is True
        assert retry == 0


def test_over_limit_returns_429_with_retry_after():
    counter = rl._SlidingCounter()
    # Hit limit
    for _ in range(3):
        counter.hit("user-1", "ep-1", max_calls=3, window_s=60)
    # 4th hit should be denied
    allowed, retry = counter.hit("user-1", "ep-1", max_calls=3, window_s=60)
    assert allowed is False
    assert retry > 0


def test_different_users_have_independent_counters():
    counter = rl._SlidingCounter()
    for _ in range(3):
        counter.hit("user-1", "ep-1", max_calls=3, window_s=60)
    # user-1 hit limit
    allowed_a, _ = counter.hit("user-1", "ep-1", max_calls=3, window_s=60)
    # user-2 still fresh
    allowed_b, _ = counter.hit("user-2", "ep-1", max_calls=3, window_s=60)
    assert allowed_a is False
    assert allowed_b is True


def test_different_endpoints_have_independent_counters():
    counter = rl._SlidingCounter()
    for _ in range(3):
        counter.hit("user-1", "ep-1", max_calls=3, window_s=60)
    allowed, _ = counter.hit("user-1", "ep-2", max_calls=3, window_s=60)
    assert allowed is True


def test_match_endpoint_recognizes_parametric_paths():
    # /war-rooms/foo/rounds matches POST:/war-rooms/{room_id}/rounds
    key = rl._match_endpoint("POST", "/war-rooms/abc-123/rounds")
    assert key == "POST:/war-rooms/{room_id}/rounds"


def test_match_endpoint_returns_none_for_unconfigured():
    assert rl._match_endpoint("GET", "/health") is None
    assert rl._match_endpoint("POST", "/totally-unknown") is None


def test_disabled_via_env_skips_middleware(monkeypatch):
    monkeypatch.setenv("MZ_RATE_LIMIT_DISABLED", "true")
    assert rl._is_disabled() is True
