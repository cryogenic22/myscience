"""Loop #19 — backend tests for POST /evidence/by-ids."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


def _row(
    *,
    evidence_id: str = "11111111-1111-1111-1111-111111111111",
    source_id: str = "clinicaltrials.gov",
    source_url: str = "https://clinicaltrials.gov/study/NCT0123",
    extracted_text: str = (
        "The trial met its primary endpoint with a statistically significant "
        "reduction in major adverse cardiovascular events."
    ),
    confidence: float = 0.95,
):
    return {
        "evidence_id": evidence_id,
        "source_id": source_id,
        "source_url": source_url,
        "retrieved_at": datetime(2026, 5, 9, 10, 0, tzinfo=timezone.utc),
        "extracted_text": extracted_text,
        "confidence": confidence,
    }


def _make_db(rows: list[dict] | None = None):
    rows = rows if rows is not None else []

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from evidence_records" in s:
            requested = (params or [[]])[0] or []
            return [r for r in rows if r["evidence_id"] in set(requested)]
        return []

    db = MagicMock()
    db.fetch_all = MagicMock(side_effect=fake_fetch_all)
    db.fetch_one = MagicMock(return_value=None)
    return db


def _client(db):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


class TestEvidenceBatch:
    def test_endpoint_exists(self):
        client = _client(_make_db([]))
        r = client.post(
            "/evidence/by-ids",
            json={"ids": ["11111111-1111-1111-1111-111111111111"]},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "documents" in body
        assert "missing_ids" in body

    def test_returns_resolved_docs(self):
        db = _make_db([_row()])
        client = _client(db)
        r = client.post(
            "/evidence/by-ids",
            json={"ids": ["11111111-1111-1111-1111-111111111111"]},
        )
        body = r.json()
        assert len(body["documents"]) == 1
        d = body["documents"][0]
        assert d["evidence_id"] == "11111111-1111-1111-1111-111111111111"
        assert d["source_id"] == "clinicaltrials.gov"
        assert d["source_tier"] == "tier_1"
        assert d["source_url"].startswith("https://")
        assert d["snippet"]
        assert "primary endpoint" in d["snippet"]
        assert d["retrieved_at"].startswith("2026-05-09")
        assert d["confidence"] == 0.95

    def test_missing_ids_returned(self):
        db = _make_db([_row(evidence_id="11111111-1111-1111-1111-111111111111")])
        client = _client(db)
        r = client.post(
            "/evidence/by-ids",
            json={
                "ids": [
                    "11111111-1111-1111-1111-111111111111",
                    "22222222-2222-2222-2222-222222222222",
                ],
            },
        )
        body = r.json()
        assert len(body["documents"]) == 1
        assert body["missing_ids"] == ["22222222-2222-2222-2222-222222222222"]

    def test_tier_inference(self):
        rows = [
            _row(evidence_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", source_id="clinicaltrials.gov"),
            _row(evidence_id="bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb", source_id="sec_edgar"),
            _row(evidence_id="cccccccc-cccc-cccc-cccc-cccccccccccc", source_id="pharma_news"),
            _row(evidence_id="dddddddd-dddd-dddd-dddd-dddddddddddd", source_id="weird_source"),
        ]
        client = _client(_make_db(rows))
        r = client.post(
            "/evidence/by-ids",
            json={"ids": [r["evidence_id"] for r in rows]},
        )
        tier_by_id = {d["evidence_id"]: d["source_tier"] for d in r.json()["documents"]}
        assert tier_by_id["aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"] == "tier_1"
        assert tier_by_id["bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"] == "tier_2"
        assert tier_by_id["cccccccc-cccc-cccc-cccc-cccccccccccc"] == "tier_3"
        assert tier_by_id["dddddddd-dddd-dddd-dddd-dddddddddddd"] == "unknown"

    def test_rejects_empty_id_list(self):
        client = _client(_make_db([]))
        r = client.post("/evidence/by-ids", json={"ids": []})
        # Pydantic min_length=1
        assert r.status_code == 422

    def test_caps_id_list_at_50(self):
        client = _client(_make_db([]))
        # 51 ids should be rejected by validation.
        r = client.post(
            "/evidence/by-ids",
            json={"ids": [f"{i:08d}-0000-0000-0000-000000000000" for i in range(51)]},
        )
        assert r.status_code == 422

    def test_snippet_truncated_at_280_chars(self):
        long_text = "x" * 500
        db = _make_db([_row(extracted_text=long_text)])
        client = _client(db)
        r = client.post(
            "/evidence/by-ids",
            json={"ids": ["11111111-1111-1111-1111-111111111111"]},
        )
        snippet = r.json()["documents"][0]["snippet"]
        assert snippet is not None
        assert len(snippet) <= 280
