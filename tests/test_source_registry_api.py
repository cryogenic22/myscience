"""SPEC_027 — Source Registry tests.

Covers: dimension scorers in isolation, register idempotency, license-health
linear degradation, recompute writes history + updates latest pointer,
health-summary aggregation, auth gates, red-team edge cases.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


# ────────────────────────────────────────────────────────────────────
# Pure scorer tests
# ────────────────────────────────────────────────────────────────────

class TestLicenseHealth:
    def test_expired_returns_zero(self):
        from services.source_registry import score_license_health
        assert score_license_health("expired", None) == 0.0

    def test_rate_limited_returns_half(self):
        from services.source_registry import score_license_health
        assert score_license_health("rate_limited", None) == 0.5

    def test_not_applicable_returns_one(self):
        from services.source_registry import score_license_health
        assert score_license_health("not_applicable", None) == 1.0

    def test_active_no_renewal_date_returns_one(self):
        from services.source_registry import score_license_health
        assert score_license_health("active", None) == 1.0

    def test_active_renewal_in_future_30d_full_score(self):
        from services.source_registry import score_license_health
        now = datetime(2026, 5, 9, tzinfo=timezone.utc)
        renewal = now + timedelta(days=60)  # well outside 30d window
        assert score_license_health("active", renewal, now=now) == 1.0

    def test_active_renewal_already_passed_returns_zero(self):
        from services.source_registry import score_license_health
        now = datetime(2026, 5, 9, tzinfo=timezone.utc)
        renewal = now - timedelta(days=1)  # already expired (but status still active)
        assert score_license_health("active", renewal, now=now) == 0.0

    def test_active_renewal_in_window_degrades_linearly(self):
        from services.source_registry import score_license_health
        now = datetime(2026, 5, 9, tzinfo=timezone.utc)
        # Halfway through the 30-day window: 15 days left → 0.5
        renewal = now + timedelta(days=15)
        score = score_license_health("active", renewal, now=now, window_days=30)
        assert 0.45 < score < 0.55


class TestLatencyScore:
    def test_none_returns_neutral(self):
        from services.source_registry import score_latency
        ms, score = score_latency(None)
        assert ms is None and score == 0.5

    def test_zero_lag_full_score(self):
        from services.source_registry import score_latency
        _, score = score_latency(0)
        assert score == 1.0

    def test_floor_or_above_zero_score(self):
        from services.source_registry import score_latency, LATENCY_FLOOR_MS
        _, score = score_latency(LATENCY_FLOOR_MS)
        assert score == 0.0
        _, score = score_latency(LATENCY_FLOOR_MS * 10)
        assert score == 0.0

    def test_halfway_returns_half(self):
        from services.source_registry import score_latency, LATENCY_FLOOR_MS
        _, score = score_latency(LATENCY_FLOOR_MS // 2)
        assert 0.45 < score < 0.55


class TestComputeOverall:
    def test_all_full_returns_one(self):
        from services.source_registry import compute_overall
        assert compute_overall(1.0, 1.0, 1.0, 1.0, 1.0) == 1.0

    def test_all_zero_returns_zero(self):
        from services.source_registry import compute_overall
        assert compute_overall(0.0, 0.0, 0.0, 0.0, 0.0) == 0.0

    def test_none_dims_default_to_neutral(self):
        from services.source_registry import compute_overall
        # All None → all 0.5 → score 0.5
        assert compute_overall(None, None, None, None, None) == 0.5

    def test_weighted_correctly(self):
        from services.source_registry import compute_overall, QUALITY_WEIGHTS
        # Only coverage has full score, others 0 → score = weight['coverage']
        s = compute_overall(1.0, 0.0, 0.0, 0.0, 0.0)
        assert abs(s - QUALITY_WEIGHTS["coverage"]) < 1e-6


# ────────────────────────────────────────────────────────────────────
# Fake DB
# ────────────────────────────────────────────────────────────────────

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
    sources: dict[str, dict] = {}
    history: dict[str, dict] = {}
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

        # SELECT source by id
        if (
            "from sources" in s
            and "where source_id = %s" in s
            and "insert" not in s
            and params
        ):
            return sources.get(params[0])

        # INSERT source RETURNING
        if "insert into sources" in s and "returning" in s and params:
            sid = params[0]
            row = {
                "source_id": sid,
                "display_name": params[1],
                "tier": params[2],
                "kind": params[3],
                "base_url": params[4],
                "description": params[5],
                "active": True,
                "license_status": params[6],
                "license_renewal_at": params[7],
                "rate_limit_per_min": params[8],
                "usage_profile": json.loads(params[9]) if isinstance(params[9], str) else (params[9] or {}),
                "latest_quality_id": None,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
            sources[sid] = row
            return row

        # SELECT history by quality_id
        if (
            "from source_quality_history" in s
            and "quality_id::text = %s" in s
            and params
        ):
            return history.get(str(params[0]))

        # latency p95 (always returns null in fake — tests fall back to default)
        if "percentile_cont" in s:
            return {"p95_ms": None}

        # INSERT history RETURNING
        if "insert into source_quality_history" in s and "returning" in s and params:
            qid = _gen("qty")
            row = {
                "quality_id": qid,
                "source_id": params[0],
                "computed_at": datetime.now(timezone.utc),
                "coverage": params[1],
                "latency_p95_ms": params[2],
                "latency_score": params[3],
                "predictive_accuracy": params[4],
                "stability_score": params[5],
                "license_health_score": params[6],
                "overall_score": params[7],
                "inputs_jsonb": json.loads(params[8]) if isinstance(params[8], str) else params[8],
            }
            history[qid] = row
            return row

        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()

        # LIST sources w/ JOIN to latest quality
        if "from sources s" in s and "left join source_quality_history" in s and "limit" in s:
            out = list(sources.values())
            if params:
                idx = 0
                if "tier = %s" in s:
                    out = [r for r in out if r["tier"] == params[idx]]; idx += 1
                if "kind = %s" in s:
                    out = [r for r in out if r["kind"] == params[idx]]; idx += 1
                if "active = %s" in s:
                    out = [r for r in out if r["active"] == params[idx]]; idx += 1
                limit = params[-2]; offset = params[-1]
            else:
                limit = 200; offset = 0
            # Add quality fields
            joined = []
            for r in out:
                d = dict(r)
                qid = r.get("latest_quality_id")
                if qid:
                    q = history.get(str(qid))
                    if q:
                        for k in ("coverage", "latency_p95_ms", "latency_score",
                                  "predictive_accuracy", "stability_score",
                                  "license_health_score", "overall_score", "inputs_jsonb"):
                            d[k] = q.get(k)
                joined.append(d)
            joined.sort(key=lambda r: (r["tier"], r["source_id"]))
            return joined[offset:offset + limit]

        # SELECT history list
        if "from source_quality_history" in s and "limit" in s and "where source_id = %s" in s and params:
            sid = params[0]; limit = params[1]
            out = [h for h in history.values() if h["source_id"] == sid]
            out.sort(key=lambda h: h["computed_at"], reverse=True)
            return out[:limit]

        # health-summary
        if "from sources s" in s and "left join" in s and "limit" not in s:
            joined = []
            for r in sources.values():
                d = dict(r)
                qid = r.get("latest_quality_id")
                if qid and qid in history:
                    d["overall_score"] = history[str(qid)].get("overall_score")
                else:
                    d["overall_score"] = None
                joined.append(d)
            return joined

        return []

    def fake_execute(sql, params=None):
        s = (sql or "").lower()
        # PATCH source
        if "update sources set" in s and "where source_id = %s" in s and params:
            sid = str(params[-1])
            if sid not in sources: return None
            pi = 0
            if "display_name = %s" in s:
                sources[sid]["display_name"] = params[pi]; pi += 1
            if "active = %s" in s:
                sources[sid]["active"] = params[pi]; pi += 1
            if "license_status = %s" in s:
                sources[sid]["license_status"] = params[pi]; pi += 1
            if "license_renewal_at = %s" in s:
                sources[sid]["license_renewal_at"] = params[pi]; pi += 1
            if "rate_limit_per_min = %s" in s:
                sources[sid]["rate_limit_per_min"] = params[pi]; pi += 1
            if "usage_profile = %s::jsonb" in s:
                v = params[pi]
                sources[sid]["usage_profile"] = json.loads(v) if isinstance(v, str) else (v or {})
                pi += 1
            if "description = %s" in s:
                sources[sid]["description"] = params[pi]; pi += 1
            if "latest_quality_id = %s" in s:
                sources[sid]["latest_quality_id"] = str(params[pi]); pi += 1
            sources[sid]["updated_at"] = datetime.now(timezone.utc)
            return None
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = fake_execute
    return db, sources, history


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


# ────────────────────────────────────────────────────────────────────
# Module + routes
# ────────────────────────────────────────────────────────────────────

def test_module_imports():
    from api.routes import sources as r
    from services.source_registry import SourceRegistryService
    assert r.router.prefix == "/sources"


def test_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/sources" in paths
    assert "/sources/{source_id}" in paths
    assert "/sources/{source_id}/recompute" in paths
    assert "/sources/{source_id}/history" in paths
    assert "/sources/health-summary" in paths


# ────────────────────────────────────────────────────────────────────
# Register
# ────────────────────────────────────────────────────────────────────

def test_register_minimal():
    db, sources, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/sources", json={
        "source_id": "fda_orange_book", "display_name": "FDA Orange Book", "tier": 1,
    }, headers=_hdr(tok))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source_id"] == "fda_orange_book"
    assert body["tier"] == 1
    assert body["kind"] == "free"
    assert body["active"] is True
    assert body["license_status"] == "not_applicable"


def test_register_idempotent():
    db, sources, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    payload = {"source_id": "ct_gov", "display_name": "ClinicalTrials.gov", "tier": 1}
    r1 = client.post("/sources", json=payload, headers=_hdr(tok)).json()
    r2 = client.post("/sources", json=payload, headers=_hdr(tok)).json()
    assert r1["source_id"] == r2["source_id"]
    assert len(sources) == 1


def test_register_full_payload():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/sources", json={
        "source_id": "alphasense", "display_name": "AlphaSense", "tier": 4,
        "kind": "paid", "base_url": "https://alphasense.com",
        "license_status": "active",
        "license_renewal_at": "2027-01-01T00:00:00+00:00",
        "rate_limit_per_min": 60,
        "usage_profile": {"bulk_extraction": False},
    }, headers=_hdr(tok))
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "paid"
    assert body["rate_limit_per_min"] == 60


def test_register_rejects_invalid_tier():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/sources", json={
        "source_id": "x", "display_name": "X", "tier": 99,
    }, headers=_hdr(tok))
    assert r.status_code == 422


def test_register_rejects_invalid_kind():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/sources", json={
        "source_id": "x", "display_name": "X", "tier": 1, "kind": "magic",
    }, headers=_hdr(tok))
    assert r.status_code == 422


# ────────────────────────────────────────────────────────────────────
# List + Get + Patch
# ────────────────────────────────────────────────────────────────────

def test_list_filters_by_tier():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    client.post("/sources", json={"source_id": "a", "display_name": "A", "tier": 1}, headers=_hdr(tok))
    client.post("/sources", json={"source_id": "b", "display_name": "B", "tier": 2}, headers=_hdr(tok))

    vtok = _login(client, "viewer@test.io")
    r = client.get("/sources?tier=1", headers=_hdr(vtok))
    body = r.json()
    assert body["count"] == 1
    assert body["sources"][0]["source_id"] == "a"


def test_get_404_for_unknown():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/sources/does-not-exist", headers=_hdr(tok))
    assert r.status_code == 404


def test_patch_license_status():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    client.post("/sources", json={
        "source_id": "alphasense", "display_name": "AlphaSense", "tier": 4, "kind": "paid",
    }, headers=_hdr(tok))
    r = client.patch("/sources/alphasense", json={"license_status": "rate_limited"}, headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["license_status"] == "rate_limited"


def test_patch_404_for_unknown():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.patch("/sources/nope", json={"active": False}, headers=_hdr(tok))
    assert r.status_code == 404


# ────────────────────────────────────────────────────────────────────
# Recompute
# ────────────────────────────────────────────────────────────────────

def test_recompute_writes_history_and_updates_pointer():
    db, sources, history = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    client.post("/sources", json={
        "source_id": "src1", "display_name": "Source 1", "tier": 1,
    }, headers=_hdr(tok))
    r = client.post("/sources/src1/recompute", headers=_hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["source_id"] == "src1"
    q = body["quality"]
    assert 0 <= q["overall_score"] <= 1
    assert q["license_health_score"] == 1.0  # not_applicable default
    assert q["coverage"] == 0.7              # tier-1 default
    assert q["stability_score"] == 1.0       # active

    # Latest pointer set
    assert sources["src1"]["latest_quality_id"] is not None
    # History row written
    assert len(history) == 1


def test_recompute_404_for_unknown():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/sources/nope/recompute", headers=_hdr(tok))
    assert r.status_code == 404


def test_history_endpoint_returns_chronological_list():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    client.post("/sources", json={"source_id": "src1", "display_name": "Source 1", "tier": 1},
                headers=_hdr(tok))
    client.post("/sources/src1/recompute", headers=_hdr(tok))
    client.post("/sources/src1/recompute", headers=_hdr(tok))

    vtok = _login(client, "viewer@test.io")
    r = client.get("/sources/src1/history", headers=_hdr(vtok))
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 2


# ────────────────────────────────────────────────────────────────────
# Health summary
# ────────────────────────────────────────────────────────────────────

def test_health_summary_empty():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/sources/health-summary", headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["total_sources"] == 0
    assert body["active_count"] == 0
    assert body["mean_overall_score"] is None
    assert body["bottom_5"] == []


def test_health_summary_with_recomputed_sources():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    for sid in ("a", "b", "c"):
        client.post("/sources", json={"source_id": sid, "display_name": sid.upper(), "tier": 1},
                    headers=_hdr(tok))
        client.post(f"/sources/{sid}/recompute", headers=_hdr(tok))

    vtok = _login(client, "viewer@test.io")
    r = client.get("/sources/health-summary", headers=_hdr(vtok))
    assert r.status_code == 200
    body = r.json()
    assert body["total_sources"] == 3
    assert body["active_count"] == 3
    assert body["scored_count"] == 3
    assert 0 <= body["mean_overall_score"] <= 1


# ────────────────────────────────────────────────────────────────────
# Auth
# ────────────────────────────────────────────────────────────────────

def test_unauth_register_returns_401():
    db, _, _ = _make_db()
    client = _client(db)
    r = client.post("/sources", json={"source_id": "x", "display_name": "X", "tier": 1})
    assert r.status_code in (401, 403)


def test_register_requires_uploader():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/sources", json={"source_id": "x", "display_name": "X", "tier": 1},
                    headers=_hdr(tok))
    assert r.status_code in (401, 403)


def test_unauth_health_summary_returns_401():
    db, _, _ = _make_db()
    client = _client(db)
    r = client.get("/sources/health-summary")
    assert r.status_code in (401, 403)


# ────────────────────────────────────────────────────────────────────
# Red-team
# ────────────────────────────────────────────────────────────────────

def test_R5_no_sql_injection_via_source_id():
    """R5: source_id is parameterized; weird values just don't match."""
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/sources/'%20OR%201=1--", headers=_hdr(tok))
    assert r.status_code == 404


def test_R3_license_renewal_validates_as_datetime():
    """R3: invalid datetime → 422."""
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/sources", json={
        "source_id": "x", "display_name": "X", "tier": 1,
        "license_renewal_at": "yesterday",  # not a datetime
    }, headers=_hdr(tok))
    assert r.status_code == 422


# ────────────────────────────────────────────────────────────────────
# QUAL-001 — quality-score provenance (honest measured / estimated / unknown)
# ────────────────────────────────────────────────────────────────────

class TestSummarizeProvenance:
    """The composite score alone is falsely precise (a neutral 0.5 for an
    *unknown* dim looks like a real 0.5). summarize_provenance surfaces how much
    of the score is actually measured, keyed to QUALITY_WEIGHTS."""

    def test_weight_split_matches_quality_weights(self):
        from services.source_registry import (
            summarize_provenance,
            QUALITY_BASIS_MEASURED as M, QUALITY_BASIS_ESTIMATED as E,
            QUALITY_BASIS_UNKNOWN as U,
        )
        prov = summarize_provenance({
            "coverage": E, "latency": M, "predictive_accuracy": U,
            "stability": M, "license_health": M,
        })
        assert prov["measured"] == ["latency", "license_health", "stability"]
        assert prov["estimated"] == ["coverage"]
        assert prov["unknown"] == ["predictive_accuracy"]
        # latency 0.20 + stability 0.15 + license_health 0.10 = 0.45
        assert prov["measured_weight"] == pytest.approx(0.45)
        assert prov["estimated_weight"] == pytest.approx(0.25)   # coverage
        assert prov["unknown_weight"] == pytest.approx(0.30)     # predictive_accuracy is 30% of the score
        assert (prov["measured_weight"] + prov["estimated_weight"]
                + prov["unknown_weight"]) == pytest.approx(1.0)

    def test_latency_without_rows_is_unknown_not_measured(self):
        from services.source_registry import (
            summarize_provenance,
            QUALITY_BASIS_MEASURED as M, QUALITY_BASIS_ESTIMATED as E,
            QUALITY_BASIS_UNKNOWN as U,
        )
        prov = summarize_provenance({
            "coverage": E, "latency": U, "predictive_accuracy": U,
            "stability": M, "license_health": M,
        })
        assert prov["unknown_weight"] == pytest.approx(0.50)   # latency 0.20 + predictive 0.30
        assert prov["measured_weight"] == pytest.approx(0.25)  # stability 0.15 + license 0.10

    def test_unrecognized_basis_fails_closed_to_unknown(self):
        """A garbage/absent basis must never be silently promoted to measured."""
        from services.source_registry import summarize_provenance
        prov = summarize_provenance({"coverage": "totally-made-up", "stability": "measured"})
        assert prov["unknown"] == ["coverage"]
        assert prov["measured"] == ["stability"]

    def test_all_measured_reads_fully_real(self):
        from services.source_registry import summarize_provenance, QUALITY_BASIS_MEASURED as M
        prov = summarize_provenance({d: M for d in
                                     ("coverage", "latency", "predictive_accuracy",
                                      "stability", "license_health")})
        assert prov["measured_weight"] == pytest.approx(1.0)
        assert prov["unknown_weight"] == pytest.approx(0.0)
        assert prov["n_measured"] == 5 and prov["n_dims"] == 5

    def test_empty_is_safe(self):
        from services.source_registry import summarize_provenance
        prov = summarize_provenance({})
        assert prov["measured_weight"] == 0.0 and prov["n_dims"] == 0


def test_recompute_records_honest_provenance_via_api():
    """End-to-end: recompute persists per-dim basis + a provenance summary into
    inputs_jsonb, and it surfaces through the API (to_dict). The fake source has
    no evidence rows, so half its composite is a placeholder — exactly the
    honesty the single overall_score hides."""
    db, sources, history = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    client.post("/sources", json={"source_id": "src1", "display_name": "Source 1", "tier": 1},
                headers=_hdr(tok))
    r = client.post("/sources/src1/recompute", headers=_hdr(tok))
    assert r.status_code == 200, r.text
    inputs = r.json()["quality"]["inputs"]
    prov = inputs["provenance"]

    assert prov["estimated"] == ["coverage"]                       # tier default, not a measurement
    assert set(prov["unknown"]) == {"latency", "predictive_accuracy"}  # no rows + flat placeholder
    assert set(prov["measured"]) == {"license_health", "stability"}
    assert prov["unknown_weight"] == pytest.approx(0.50)           # half the score is a placeholder
    assert prov["measured_weight"] == pytest.approx(0.25)
    # per-dimension basis is stamped inline too
    assert inputs["predictive_accuracy"]["basis"] == "unknown"
    assert inputs["coverage"]["basis"] == "estimated"
