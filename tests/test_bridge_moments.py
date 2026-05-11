"""Loop #17 — backend tests for POST /bridge/moments.

The endpoint synthesises moment objects from top tier-1 signals via
`services/llm.py::LLMSynthesizer`. Tests use a mock LLM so they don't
hit a real provider.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


def _make_signal(
    *,
    sid: str = "s1",
    headline: str = "Headline",
    summary: str = "Summary",
    kbq_tags: list[str] | None = None,
    impact_tier: str = "high",
    impact_score: float = 9.0,
    company: str = "Eli Lilly",
):
    return {
        "id": sid,
        "headline": headline,
        "summary": summary,
        "kbq_tags": kbq_tags or ["clinical"],
        "impact_tier": impact_tier,
        "impact_score": impact_score,
        "primary_entity_name": company,
        "created_at": datetime(2026, 5, 9, 12, 0, tzinfo=timezone.utc),
    }


def _make_db(signals: list[dict] | None = None):
    rows = signals if signals is not None else [_make_signal()]

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from signals" in s:
            return rows
        return []

    db = MagicMock()
    db.fetch_all = MagicMock(side_effect=fake_fetch_all)
    db.fetch_one = MagicMock(return_value=None)
    return db


def _mock_llm(payload_text: str = "DETERMINISTIC"):
    """Return a fake LLMSynthesizer whose `synthesize` always returns the
    given text. The real class has many methods; we only need the
    minimum surface for the route's synthesizer call.
    """
    llm = MagicMock()
    llm.enabled = True
    llm.synthesize = MagicMock(return_value=payload_text)
    llm.synthesize_landscape = MagicMock(return_value=payload_text)
    return llm


def _client(db, llm):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db, get_llm

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm] = lambda: llm
    return TestClient(app)


class TestBridgeMomentsEndpoint:
    def test_endpoint_exists_at_post_bridge_moments(self):
        db = _make_db([])
        client = _client(db, _mock_llm())
        # Empty list of signals → still returns 200 with empty moments.
        r = client.post("/bridge/moments", json={"n": 3})
        assert r.status_code == 200, r.text
        body = r.json()
        assert "moments" in body
        assert isinstance(body["moments"], list)

    def test_synthesises_one_moment_per_top_category(self):
        """3 tier-1 signals across 3 categories → 3 moments (one per group)."""
        db = _make_db([
            _make_signal(sid="s1", headline="Lilly oral GLP-1 phase 3 readout", kbq_tags=["clinical"], impact_score=9.5),
            _make_signal(sid="s2", headline="ESI rebate floor enforcement",       kbq_tags=["access"],   impact_score=8.7),
            _make_signal(sid="s3", headline="CMS NCD draft for GLP-1 CV",         kbq_tags=["regulatory"], impact_score=9.3),
        ])
        client = _client(db, _mock_llm("synth"))
        r = client.post("/bridge/moments", json={"n": 3})
        assert r.status_code == 200, r.text
        body = r.json()
        assert len(body["moments"]) == 3
        # Each moment must have the contract fields
        for m in body["moments"]:
            assert "id" in m
            assert "title" in m and m["title"]
            assert "summary" in m and m["summary"]
            assert "ev_at_stake_musd" in m
            assert "expires_hours" in m
            assert "category" in m
            assert "signal_chain" in m and isinstance(m["signal_chain"], list)
            assert "plays" in m and len(m["plays"]) == 3
            assert "delta_belief" in m

    def test_caps_at_n(self):
        """`n` caps the number of moments even when more categories are available."""
        db = _make_db([
            _make_signal(sid=f"s{i}", kbq_tags=[cat], impact_score=8.0)
            for i, cat in enumerate(["clinical", "access", "regulatory", "strategic", "financial"], start=1)
        ])
        client = _client(db, _mock_llm())
        r = client.post("/bridge/moments", json={"n": 2})
        assert r.status_code == 200, r.text
        assert len(r.json()["moments"]) == 2

    def test_clamps_n_to_range(self):
        db = _make_db([])
        client = _client(db, _mock_llm())
        # n=0 → 400; n=99 → 400. Both reject.
        for bad in (0, 99):
            r = client.post("/bridge/moments", json={"n": bad})
            assert r.status_code in (400, 422), f"n={bad} should be rejected but got {r.status_code}"

    def test_falls_back_when_llm_disabled(self):
        """When LLM is unavailable, returns deterministic synthesis (signal
        headline echo) so the Bridge frontend never breaks on an LLM
        outage."""
        db = _make_db([
            _make_signal(sid="s1", headline="A real moment about Lilly", kbq_tags=["clinical"]),
        ])
        llm = _mock_llm()
        llm.enabled = False  # simulate outage / no api key
        client = _client(db, llm)
        r = client.post("/bridge/moments", json={"n": 1})
        assert r.status_code == 200
        body = r.json()
        assert len(body["moments"]) == 1
        # Deterministic fallback should still produce a non-empty title.
        assert body["moments"][0]["title"]
