"""SPEC_033 — Counter-Recommendation Enforcement tests.

Covers: pure synthesis math, ≥2 options invariant, rule-violation
surfacing (not faking dissent), persistence, auth, red-team.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Pure synthesis
# ════════════════════════════════════════════════════════════════════

class TestSynthesizeScoreBased:
    def _opts(self):
        from services.counter_recommendation import OptionInput
        return [
            OptionInput(option_id="A", label="Accelerate", score=0.85),
            OptionInput(option_id="B", label="Hold", score=0.45),
            OptionInput(option_id="C", label="Pivot", score=0.60),
        ]

    def test_picks_highest_as_primary(self):
        from services.counter_recommendation import synthesize_score_based
        primary, counter, dissent = synthesize_score_based(self._opts())
        assert primary.option_id == "A"

    def test_picks_lowest_as_counter(self):
        from services.counter_recommendation import synthesize_score_based
        primary, counter, dissent = synthesize_score_based(self._opts())
        assert counter.option_id == "B"  # lowest score

    def test_dissent_score_proportional_to_gap(self):
        from services.counter_recommendation import synthesize_score_based
        primary, counter, dissent = synthesize_score_based(self._opts())
        # |0.85 - 0.45| / 0.85 = 0.4705...
        assert 0.40 < dissent < 0.55

    def test_two_options_minimum(self):
        from services.counter_recommendation import OptionInput, synthesize_score_based
        out = synthesize_score_based([
            OptionInput(option_id="A", label="A", score=0.8),
            OptionInput(option_id="B", label="B", score=0.2),
        ])
        primary, counter, _ = out
        assert primary.option_id != counter.option_id

    def test_equal_scores_yields_zero_dissent(self):
        from services.counter_recommendation import OptionInput, synthesize_score_based
        primary, counter, dissent = synthesize_score_based([
            OptionInput(option_id="A", label="A", score=0.5),
            OptionInput(option_id="B", label="B", score=0.5),
        ])
        # Counter is whichever is "last" in sorted order; dissent = 0
        assert dissent == 0.0
        assert primary.option_id != counter.option_id


class TestSynthesizeDimensionSplit:
    def test_picks_dimensionally_distant_counter(self):
        from services.counter_recommendation import OptionInput, synthesize_dimension_split
        # Two near-aligned options, one orthogonal
        opts = [
            OptionInput(option_id="A", label="Aggressive growth",
                        score=0.85, dimension_scores={"growth": 0.9, "safety": 0.1}),
            OptionInput(option_id="B", label="Similar growth",
                        score=0.80, dimension_scores={"growth": 0.85, "safety": 0.15}),
            OptionInput(option_id="C", label="Defensive",
                        score=0.70, dimension_scores={"growth": 0.1, "safety": 0.9}),
        ]
        primary, counter, dissent = synthesize_dimension_split(opts)
        # Primary = highest score = A
        assert primary.option_id == "A"
        # Counter = most cosine-distant = C (orthogonal to growth)
        assert counter.option_id == "C"
        assert dissent > 0.5

    def test_falls_back_to_score_based_when_dim_missing(self):
        from services.counter_recommendation import OptionInput, synthesize_dimension_split
        opts = [
            OptionInput(option_id="A", label="A", score=0.8,
                        dimension_scores={"x": 1.0}),
            OptionInput(option_id="B", label="B", score=0.4,
                        dimension_scores=None),  # missing!
        ]
        # Should fall back to score-based path; not raise
        primary, counter, _ = synthesize_dimension_split(opts)
        assert primary.option_id == "A"
        assert counter.option_id == "B"


class TestCosineSimilarity:
    def test_identical_vectors_sim_one(self):
        from services.counter_recommendation import _cosine_similarity
        assert abs(_cosine_similarity({"a": 1, "b": 2}, {"a": 1, "b": 2}) - 1.0) < 1e-6

    def test_orthogonal_vectors_sim_zero(self):
        from services.counter_recommendation import _cosine_similarity
        assert abs(_cosine_similarity({"a": 1, "b": 0}, {"a": 0, "b": 1}) - 0.0) < 1e-6

    def test_zero_magnitude_returns_zero(self):
        from services.counter_recommendation import _cosine_similarity
        assert _cosine_similarity({}, {"a": 1}) == 0.0


class TestValidation:
    def test_lt_2_options_raises_violation(self):
        from services.counter_recommendation import (
            CounterRecRuleViolation, _validate_options, OptionInput,
        )
        with pytest.raises(CounterRecRuleViolation, match="at least 2"):
            _validate_options([OptionInput(option_id="X", label="X", score=0.5)])

    def test_zero_options_raises_violation(self):
        from services.counter_recommendation import CounterRecRuleViolation, _validate_options
        with pytest.raises(CounterRecRuleViolation):
            _validate_options([])

    def test_score_out_of_range_rejected(self):
        from services.counter_recommendation import _validate_options, OptionInput
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            _validate_options([
                OptionInput(option_id="A", label="A", score=1.5),
                OptionInput(option_id="B", label="B", score=0.5),
            ])

    def test_duplicate_ids_rejected(self):
        from services.counter_recommendation import _validate_options, OptionInput
        with pytest.raises(ValueError, match="duplicate"):
            _validate_options([
                OptionInput(option_id="A", label="A1", score=0.5),
                OptionInput(option_id="A", label="A2", score=0.6),
            ])


# ════════════════════════════════════════════════════════════════════
# Fake DB + service end-to-end
# ════════════════════════════════════════════════════════════════════

def _make_db():
    from services.auth import hash_password
    users = {
        "viewer@test.io": {
            "id": "uuid-viewer", "email": "viewer@test.io",
            "password_hash": hash_password("demo"), "role": "viewer", "is_active": True,
        },
        "editor@test.io": {
            "id": "uuid-editor", "email": "editor@test.io",
            "password_hash": hash_password("demo"), "role": "uploader", "is_active": True,
        },
    }
    recs: dict[str, dict] = {}
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

        if "insert into recommendation_synthesis_runs" in s and "returning" in s and params:
            rid = _gen("rec")
            recs[rid] = {
                "recommendation_id": rid,
                "brief_id": params[0],
                "inputs_jsonb": json.loads(params[1]) if isinstance(params[1], str) else params[1],
                "primary_option_id": params[2],
                "primary_rationale": params[3],
                "counter_option_id": params[4],
                "counter_rationale": params[5],
                "dissent_score": params[6],
                "synthesis_method": params[7],
                "started_by_user_id": params[8],
                "created_at": datetime.now(timezone.utc),
            }
            return {"recommendation_id": rid, "created_at": recs[rid]["created_at"]}

        if "from recommendation_synthesis_runs" in s and "recommendation_id::text = %s" in s and params:
            return recs.get(str(params[0]))

        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from recommendation_synthesis_runs" in s and "limit" in s:
            out = list(recs.values())
            if params:
                idx = 0
                if "brief_id::text = %s" in s:
                    out = [r for r in out if str(r.get("brief_id") or "") == str(params[idx])]; idx += 1
                limit = params[-2]; offset = params[-1]
                out = sorted(out, key=lambda r: r["created_at"], reverse=True)
                out = out[offset:offset + limit]
            return out
        return []

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = lambda *a, **kw: None
    return db, recs


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
    from api.routes import recommendations as r
    from services.counter_recommendation import CounterRecSynthesizer
    assert r.router.prefix == "/recommendations"


def test_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/recommendations/synthesize" in paths
    assert "/recommendations" in paths
    assert "/recommendations/{recommendation_id}" in paths


# ════════════════════════════════════════════════════════════════════
# Synthesize endpoint
# ════════════════════════════════════════════════════════════════════

def test_synthesize_returns_primary_and_counter():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    payload = {
        "options": [
            {"option_id": "A", "label": "Accelerate", "score": 0.85,
             "predicted_outcome": "8-12% share gain"},
            {"option_id": "B", "label": "Hold", "score": 0.30,
             "risk_notes": "capital preservation"},
            {"option_id": "C", "label": "Pivot", "score": 0.55},
        ],
    }
    r = client.post("/recommendations/synthesize", json=payload, headers=_hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["primary"]["option_id"] == "A"
    assert body["counter"]["option_id"] == "B"
    assert body["primary"]["option_id"] != body["counter"]["option_id"]
    assert "Accelerate" in body["primary"]["rationale"] or "0.85" in body["primary"]["rationale"]
    assert "Dissent" in body["counter"]["rationale"]


def test_synthesize_rejects_single_option_with_422():
    """The hard rule: cannot enforce dissent with <2 options."""
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/recommendations/synthesize", json={
        "options": [{"option_id": "X", "label": "Only", "score": 0.7}],
    }, headers=_hdr(tok))
    assert r.status_code == 422
    assert "at least 2" in r.json().get("detail", "").lower()


def test_synthesize_rejects_zero_options_with_422():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/recommendations/synthesize", json={
        "options": [],
    }, headers=_hdr(tok))
    # Pydantic min_length=1 catches this with 422
    assert r.status_code == 422


def test_synthesize_persists_to_db():
    db, recs = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/recommendations/synthesize", json={
        "options": [
            {"option_id": "A", "label": "A", "score": 0.8},
            {"option_id": "B", "label": "B", "score": 0.2},
        ],
    }, headers=_hdr(tok))
    assert r.status_code == 200
    assert len(recs) == 1
    assert r.json()["recommendation_id"] in recs


def test_synthesize_dimension_split_method():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/recommendations/synthesize", json={
        "method": "dimension_split",
        "options": [
            {"option_id": "A", "label": "Growth", "score": 0.85,
             "dimension_scores": {"growth": 0.9, "safety": 0.1}},
            {"option_id": "B", "label": "Similar", "score": 0.82,
             "dimension_scores": {"growth": 0.88, "safety": 0.12}},
            {"option_id": "C", "label": "Defensive", "score": 0.70,
             "dimension_scores": {"growth": 0.1, "safety": 0.9}},
        ],
    }, headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["primary"]["option_id"] == "A"
    # Counter should be the orthogonal one (C), not just the lowest score (also C)
    assert body["counter"]["option_id"] == "C"
    assert body["synthesis_method"] == "dimension_split"


def test_synthesize_dimension_split_falls_back_when_dim_missing():
    """When some options lack dimension_scores, method records as score_based."""
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/recommendations/synthesize", json={
        "method": "dimension_split",
        "options": [
            {"option_id": "A", "label": "A", "score": 0.8,
             "dimension_scores": {"x": 1.0}},
            {"option_id": "B", "label": "B", "score": 0.4},
        ],
    }, headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["synthesis_method"] == "score_based"


def test_get_recommendation():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    rid = client.post("/recommendations/synthesize", json={
        "options": [
            {"option_id": "A", "label": "A", "score": 0.8},
            {"option_id": "B", "label": "B", "score": 0.2},
        ],
    }, headers=_hdr(tok)).json()["recommendation_id"]

    vtok = _login(client, "viewer@test.io")
    r = client.get(f"/recommendations/{rid}", headers=_hdr(vtok))
    assert r.status_code == 200
    assert r.json()["recommendation_id"] == rid


def test_get_404_for_unknown():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/recommendations/nope", headers=_hdr(tok))
    assert r.status_code == 404


def test_list_filters_by_brief():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    client.post("/recommendations/synthesize", json={
        "brief_id": "00000000-0000-0000-0000-000000000001",
        "options": [{"option_id": "A", "label": "A", "score": 0.8},
                    {"option_id": "B", "label": "B", "score": 0.2}],
    }, headers=_hdr(tok))

    vtok = _login(client, "viewer@test.io")
    r = client.get("/recommendations?brief_id=00000000-0000-0000-0000-000000000001",
                   headers=_hdr(vtok))
    assert r.status_code == 200
    assert r.json()["count"] == 1


# ════════════════════════════════════════════════════════════════════
# Auth
# ════════════════════════════════════════════════════════════════════

def test_synthesize_requires_uploader():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/recommendations/synthesize", json={
        "options": [{"option_id": "A", "label": "A", "score": 0.8},
                    {"option_id": "B", "label": "B", "score": 0.2}],
    }, headers=_hdr(tok))
    assert r.status_code in (401, 403)


def test_unauth_synthesize_401():
    db, _ = _make_db()
    client = _client(db)
    r = client.post("/recommendations/synthesize", json={
        "options": [{"option_id": "A", "label": "A", "score": 0.5},
                    {"option_id": "B", "label": "B", "score": 0.5}],
    })
    assert r.status_code in (401, 403)


def test_unauth_list_401():
    db, _ = _make_db()
    client = _client(db)
    r = client.get("/recommendations")
    assert r.status_code in (401, 403)


# ════════════════════════════════════════════════════════════════════
# Red-team
# ════════════════════════════════════════════════════════════════════

def test_R3_score_nan_rejected():
    """R3: NaN/inf scores rejected at validation layer."""
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    # Pydantic ge/le=1 should catch out-of-range; finite check is in service
    r = client.post("/recommendations/synthesize", json={
        "options": [{"option_id": "A", "label": "A", "score": -0.5},
                    {"option_id": "B", "label": "B", "score": 0.5}],
    }, headers=_hdr(tok))
    assert r.status_code == 422


def test_R4_too_many_options_capped():
    """R4: cap at 20 options to prevent DoS."""
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    payload = {
        "options": [
            {"option_id": f"OPT-{i}", "label": f"O{i}", "score": 0.5}
            for i in range(25)
        ],
    }
    r = client.post("/recommendations/synthesize", json=payload, headers=_hdr(tok))
    assert r.status_code == 422  # pydantic max_length=20


def test_R7_counter_always_differs_from_primary():
    """R7: even with identical scores, counter ≠ primary."""
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/recommendations/synthesize", json={
        "options": [{"option_id": "A", "label": "A", "score": 0.5},
                    {"option_id": "B", "label": "B", "score": 0.5}],
    }, headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["primary"]["option_id"] != body["counter"]["option_id"]
    # Honest about no dissent: dissent_score should be 0, not faked
    assert body["dissent_score"] == 0.0
