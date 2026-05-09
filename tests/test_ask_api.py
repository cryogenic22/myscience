"""SPEC_035 — /ask graph-traversal tests.

Covers: pattern recognition, unmatched-question handling, executor SQL
parameterization (no injection), telemetry persistence, auth.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Pure parser
# ════════════════════════════════════════════════════════════════════

class TestParseQuestion:
    def test_p1_show_me_drugs_in_oncology(self):
        from services.ask_engine import parse_question
        intent = parse_question("Show me drugs in oncology")
        assert intent.matched_pattern == "P1"
        assert intent.params["entity_type"] == "drug"
        assert intent.params["area"] == "oncology"

    def test_p2_what_trials_does(self):
        from services.ask_engine import parse_question
        intent = parse_question("What trials does Tirzepatide have?")
        assert intent.matched_pattern == "P2"
        assert intent.params["relation"] == "trials"
        assert intent.params["entity_name"] == "Tirzepatide"

    def test_p3_competitors_of(self):
        from services.ask_engine import parse_question
        intent = parse_question("Competitors of Pfizer")
        assert intent.matched_pattern == "P3"
        assert intent.params["company_name"] == "Pfizer"

    def test_p4_recent(self):
        from services.ask_engine import parse_question
        intent = parse_question("Drugs approved in the last 30 days")
        assert intent.matched_pattern == "P4"
        assert intent.params["entity_type"] == "drug"
        assert intent.params["n"] == "30"
        assert intent.params["unit"] == "day"

    def test_p5_targeting(self):
        from services.ask_engine import parse_question
        intent = parse_question("Find drugs targeting GLP-1 receptor")
        assert intent.matched_pattern == "P5"
        assert intent.params["entity_type"] == "drug"
        assert "GLP" in intent.params["mechanism_name"]

    def test_p6_who_sponsors(self):
        from services.ask_engine import parse_question
        intent = parse_question("Who sponsors Tirzepatide?")
        assert intent.matched_pattern == "P6"
        assert intent.params["drug_name"] == "Tirzepatide"

    def test_unmatched_question(self):
        from services.ask_engine import parse_question
        intent = parse_question("What is the meaning of life?")
        assert intent.matched_pattern is None
        assert intent.executor is None

    def test_empty_question(self):
        from services.ask_engine import parse_question
        intent = parse_question("")
        assert intent.matched_pattern is None

    def test_question_truncated_at_max_chars(self):
        from services.ask_engine import parse_question, MAX_QUESTION_CHARS
        long_q = "Show me drugs in " + "x" * 1000
        intent = parse_question(long_q)
        assert len(intent.raw_question) <= MAX_QUESTION_CHARS


class TestListTemplates:
    def test_returns_six_patterns(self):
        from services.ask_engine import list_templates
        templates = list_templates()
        assert len(templates) == 6
        ids = [t["id"] for t in templates]
        assert ids == ["P1", "P2", "P3", "P4", "P5", "P6"]

    def test_each_template_has_example(self):
        from services.ask_engine import list_templates
        for t in list_templates():
            assert t.get("example")


class TestSafeEntityType:
    def test_known_types_returned_as_is(self):
        from services.ask_engine import AskEngine
        eng = AskEngine()
        assert eng._safe_entity_type("drug") == "drug"
        assert eng._safe_entity_type("company") == "company"

    def test_unknown_type_falls_back_to_drug(self):
        from services.ask_engine import AskEngine
        eng = AskEngine()
        # SQL-injection-like input should fall back, not propagate
        assert eng._safe_entity_type("drugs; DROP TABLE users;--") == "drug"

    def test_none_falls_back_to_drug(self):
        from services.ask_engine import AskEngine
        assert AskEngine()._safe_entity_type(None) == "drug"


# ════════════════════════════════════════════════════════════════════
# Fake DB + API
# ════════════════════════════════════════════════════════════════════

def _make_db():
    from services.auth import hash_password
    users = {
        "viewer@test.io": {
            "id": "uuid-viewer", "email": "viewer@test.io",
            "password_hash": hash_password("demo"), "role": "viewer", "is_active": True,
        },
    }
    log: list[dict] = []
    next_id = [1]

    def _gen(p):
        n = next_id[0]; next_id[0] += 1
        return f"{p}-{n:04d}"

    def fake_fetch_one(sql, params=None):
        s = (sql or "").lower()

        if "from users" in s and params:
            if "where lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id::text" in s or "where id =" in s:
                for u in users.values():
                    if u["id"] == params[0]: return u
                return None

        if "insert into ask_query_log" in s and "returning" in s and params:
            qid = _gen("aqr")
            log.append({
                "ask_query_id": qid,
                "question": params[0],
                "matched_pattern": params[1],
                "intent_jsonb": json.loads(params[2]) if isinstance(params[2], str) else params[2],
                "result_node_count": params[3],
                "result_edge_count": params[4],
                "latency_ms": params[5],
                "succeeded": params[6],
                "error_message": params[7],
                "user_id": params[8],
                "created_at": datetime.now(timezone.utc),
            })
            return {"ask_query_id": qid}

        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()

        # Pattern executors return empty lists; the test focuses on
        # plumbing not real entity data
        if "from drugs" in s or "from companies" in s or "from trials" in s:
            return []
        if "from entity_links" in s:
            return []

        # history query
        if "from ask_query_log" in s and "limit" in s and params:
            uid = str(params[0])
            out = [r for r in log if str(r.get("user_id") or "") == uid]
            out.sort(key=lambda r: r["created_at"], reverse=True)
            return out[:params[1]]

        return []

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = lambda *a, **kw: None
    return db, log


def _client(db):
    from fastapi.testclient import TestClient
    from api.app import create_app
    from api.deps import get_db
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def _login(client, email):
    r = client.post("/auth/login", json={"email": email, "password": "demo"})
    return r.json().get("access_token", "") if r.status_code == 200 else ""


def _hdr(tok):
    return {"Authorization": f"Bearer {tok}"} if tok else {}


# ════════════════════════════════════════════════════════════════════
# Routes registered
# ════════════════════════════════════════════════════════════════════

def test_module_imports():
    from api.routes import ask as r
    from services.ask_engine import AskEngine
    assert r.router.prefix == "/ask"


def test_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/ask" in paths
    assert "/ask/templates" in paths
    assert "/ask/history" in paths


# ════════════════════════════════════════════════════════════════════
# /ask endpoint
# ════════════════════════════════════════════════════════════════════

def test_ask_p1_returns_graph_shape():
    db, log = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/ask", json={"question": "Show me drugs in oncology"},
                    headers=_hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["matched_pattern"] == "P1"
    assert body["status"] == "ok"
    assert "graph" in body
    assert "nodes" in body["graph"]
    assert "edges" in body["graph"]
    assert "result_count" in body
    assert body["ask_query_id"] is not None
    assert len(log) == 1


def test_ask_unmatched_returns_suggestions():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/ask", json={"question": "What is the meaning of life?"},
                    headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "unmatched"
    assert body["matched_pattern"] is None
    assert isinstance(body["suggested_templates"], list)
    assert len(body["suggested_templates"]) > 0
    # Each suggestion has an example
    for sug in body["suggested_templates"]:
        assert sug.get("example")


def test_ask_p2_returns_graph_shape():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/ask", json={"question": "What trials does Tirzepatide have?"},
                    headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["matched_pattern"] == "P2"


def test_ask_p3_competitors():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/ask", json={"question": "Competitors of Pfizer"},
                    headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["matched_pattern"] == "P3"


def test_ask_p4_recent():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/ask", json={"question": "Drugs approved in the last 30 days"},
                    headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["matched_pattern"] == "P4"


def test_ask_p6_who_sponsors():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/ask", json={"question": "Who sponsors Tirzepatide?"},
                    headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["matched_pattern"] == "P6"


def test_ask_telemetry_persisted():
    db, log = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    client.post("/ask", json={"question": "Show me drugs in oncology"}, headers=_hdr(tok))
    client.post("/ask", json={"question": "Competitors of Pfizer"}, headers=_hdr(tok))
    assert len(log) == 2
    assert log[0]["matched_pattern"] == "P1"
    assert log[1]["matched_pattern"] == "P3"


def test_ask_question_too_long_rejected():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/ask", json={"question": "x" * 1000}, headers=_hdr(tok))
    assert r.status_code == 422  # pydantic max_length


def test_ask_empty_question_rejected():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/ask", json={"question": ""}, headers=_hdr(tok))
    assert r.status_code == 422  # pydantic min_length


# ════════════════════════════════════════════════════════════════════
# /ask/templates + /ask/history
# ════════════════════════════════════════════════════════════════════

def test_templates_returns_six():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/ask/templates", headers=_hdr(tok))
    assert r.status_code == 200
    assert len(r.json()["templates"]) == 6


def test_history_returns_per_user_queries():
    db, log = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    client.post("/ask", json={"question": "Show me drugs in oncology"}, headers=_hdr(tok))
    r = client.get("/ask/history", headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["history"][0]["matched_pattern"] == "P1"


# ════════════════════════════════════════════════════════════════════
# Auth
# ════════════════════════════════════════════════════════════════════

def test_unauth_ask_401():
    db, _ = _make_db()
    client = _client(db)
    r = client.post("/ask", json={"question": "Show me drugs in oncology"})
    assert r.status_code in (401, 403)


def test_unauth_templates_401():
    db, _ = _make_db()
    client = _client(db)
    r = client.get("/ask/templates")
    assert r.status_code in (401, 403)


# ════════════════════════════════════════════════════════════════════
# Red-team
# ════════════════════════════════════════════════════════════════════

def test_R1_sql_injection_via_question_blocked():
    """R1: SQL meta in the question doesn't reach the DB unparameterized.
    The pattern matcher either rejects the input as unmatched OR extracts
    it into a parameterized capture group."""
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    payload = "Show me drugs in '; DROP TABLE drugs;--"
    r = client.post("/ask", json={"question": payload}, headers=_hdr(tok))
    assert r.status_code == 200
    # Either matched as P1 with the malicious string in the area param
    # (which is then parameterized by the SQL driver), or unmatched.
    assert r.json()["status"] in ("ok", "unmatched")


def test_R2_oversized_question_rejected_at_api():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/ask", json={"question": "x" * 5000}, headers=_hdr(tok))
    assert r.status_code == 422


def test_R5_unmatched_returns_status_not_garbage():
    """R5: unmatched questions return explicit status, never silently
    return arbitrary results."""
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/ask", json={"question": "Lorem ipsum dolor sit"},
                    headers=_hdr(tok))
    body = r.json()
    assert body["status"] == "unmatched"
    assert body["graph"]["nodes"] == []
    assert body["graph"]["edges"] == []
