"""C2 (learning loops) — chat answer feedback (thumbs up/down).

Covers the service helpers and the new /chat/feedback endpoints. Endpoints
are exercised through create_app() + TestClient (a service-only test would
miss a dead/shadowed route).
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services import chat_feedback as cf


# ── Service-level ──

def test_question_hash_matches_telemetry_scheme():
    import hashlib
    q = "What is semaglutide?"
    assert cf.question_hash(q) == hashlib.sha256(q.encode()).hexdigest()[:16]


def test_record_feedback_inserts_and_links_telemetry():
    db = MagicMock()
    # query_telemetry lookup returns a row → soft link
    db.fetch_one.side_effect = [
        {"id": "11111111-1111-1111-1111-111111111111"},  # telemetry lookup
        {  # INSERT ... RETURNING
            "id": "22222222-2222-2222-2222-222222222222",
            "session_id": "s1", "question_hash": cf.question_hash("q?"),
            "rating": 1, "intent": "general",
            "query_telemetry_id": "11111111-1111-1111-1111-111111111111",
            "created_at": None,
        },
    ]
    rec = cf.record_feedback(db, question="q?", rating=1, session_id="s1", intent="general")
    assert rec["rating"] == 1
    assert rec["query_telemetry_id"] == "11111111-1111-1111-1111-111111111111"
    # the INSERT is the second fetch_one call
    insert_sql = db.fetch_one.call_args_list[1][0][0].lower()
    assert "insert into chat_answer_feedback" in insert_sql


def test_record_feedback_rejects_bad_rating():
    db = MagicMock()
    with pytest.raises(ValueError):
        cf.record_feedback(db, question="q", rating=0)


def test_record_feedback_rejects_empty_question():
    db = MagicMock()
    with pytest.raises(ValueError):
        cf.record_feedback(db, question="   ", rating=1)


def test_feedback_summary_computes_satisfaction():
    db = MagicMock()
    db.fetch_one.return_value = {"up": 7, "down": 3, "total": 10}
    s = cf.feedback_summary(db, days=30)
    assert s["up"] == 7 and s["down"] == 3
    assert s["satisfaction_pct"] == 70.0


# ── Endpoint-level (TestClient) ──

def _client(db):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_post_feedback_endpoint_persists():
    db = MagicMock()
    db.fetch_one.side_effect = [
        None,  # no telemetry row
        {
            "id": "33333333-3333-3333-3333-333333333333",
            "session_id": None, "question_hash": cf.question_hash("hello?"),
            "rating": -1, "intent": None, "query_telemetry_id": None,
            "created_at": None,
        },
    ]
    client = _client(db)
    r = client.post("/chat/feedback", json={"question": "hello?", "rating": "down"})
    assert r.status_code == 200, r.text
    body = r.json()["feedback"]
    assert body["rating"] == -1


def test_post_feedback_rejects_invalid_rating():
    db = MagicMock()
    client = _client(db)
    r = client.post("/chat/feedback", json={"question": "q", "rating": 0})
    assert r.status_code == 400


def test_get_feedback_endpoint_returns_rows():
    db = MagicMock()
    db.fetch_all.return_value = [
        {
            "id": "44444444-4444-4444-4444-444444444444",
            "session_id": "s", "question_hash": cf.question_hash("q?"),
            "rating": 1, "comment": None, "intent": "general",
            "query_telemetry_id": None, "created_at": None,
        }
    ]
    client = _client(db)
    r = client.get("/chat/feedback", params={"question": "q?"})
    assert r.status_code == 200, r.text
    assert r.json()["count"] == 1
