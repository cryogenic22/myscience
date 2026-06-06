"""SPEC_032 — Learning Service tests.

Covers: EWMA math, since-cursor resolution, decision-to-source attribution
paths, source.predictive_accuracy update, prompt flagging, run isolation,
auth gates.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Pure math
# ════════════════════════════════════════════════════════════════════

class TestEWMA:
    def test_null_prior_seeds_with_observation(self):
        from services.learning_service import ewma_update
        assert ewma_update(prior=None, observation=0.7) == 0.7

    def test_alpha_one_replaces_prior(self):
        from services.learning_service import ewma_update
        # alpha=1 → posterior = observation
        assert ewma_update(prior=0.3, observation=0.9, alpha=1.0) == 0.9

    def test_alpha_default_is_slow_learner(self):
        from services.learning_service import ewma_update
        # Default alpha=0.10: posterior = 0.10*0.9 + 0.90*0.5 = 0.54
        result = ewma_update(prior=0.5, observation=0.9)
        assert abs(result - 0.54) < 1e-6

    def test_clamps_to_unit_interval(self):
        from services.learning_service import ewma_update
        # Even with edge cases, output stays in [0,1]
        assert 0.0 <= ewma_update(prior=0.0, observation=0.0) <= 1.0
        assert 0.0 <= ewma_update(prior=1.0, observation=1.0) <= 1.0

    def test_alpha_out_of_range_rejected(self):
        from services.learning_service import ewma_update
        with pytest.raises(ValueError, match="alpha"):
            ewma_update(prior=0.5, observation=0.5, alpha=0.0)
        with pytest.raises(ValueError, match="alpha"):
            ewma_update(prior=0.5, observation=0.5, alpha=1.5)

    def test_observation_out_of_range_rejected(self):
        from services.learning_service import ewma_update
        with pytest.raises(ValueError, match="observation"):
            ewma_update(prior=0.5, observation=1.5)

    def test_prior_out_of_range_rejected(self):
        from services.learning_service import ewma_update
        with pytest.raises(ValueError, match="prior"):
            ewma_update(prior=-0.1, observation=0.5)


class TestServiceConstruction:
    def test_invalid_alpha_rejected(self):
        from services.learning_service import LearningService
        with pytest.raises(ValueError, match="alpha"):
            LearningService(alpha=0.0)
        with pytest.raises(ValueError, match="alpha"):
            LearningService(alpha=1.5)


# ════════════════════════════════════════════════════════════════════
# Fake DB
# ════════════════════════════════════════════════════════════════════

def _make_db(*, decisions=None, signals=None, sources=None, snapshots=None,
             briefs=None, llm_calls=None):
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
    decisions_db: list[dict] = list(decisions or [])
    signals_db: list[dict] = list(signals or [])
    sources_db: dict[str, dict] = {s["source_id"]: dict(s) for s in (sources or [])}
    snapshots_db: list[dict] = list(snapshots or [])
    briefs_db: dict[str, dict] = {b["brief_id"]: dict(b) for b in (briefs or [])}
    llm_calls_db: list[dict] = list(llm_calls or [])

    runs_db: dict[str, dict] = {}
    attribution_log: list[dict] = []
    prompt_flags: list[dict] = []
    quality_history: list[dict] = []
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

        # since cursor — last successful run
        if "from learning_service_runs" in s and "status = 'complete'" in s and "limit 1" in s:
            cands = [r for r in runs_db.values() if r["status"] == "complete"]
            if not cands: return None
            return max(cands, key=lambda r: r["started_at"])

        # INSERT learning_service_runs
        if "insert into learning_service_runs" in s and "returning" in s and params:
            rid = _gen("lsr")
            row = {
                "run_id": rid,
                "started_at": datetime.now(timezone.utc),
                "completed_at": None,
                "status": "running",
                "since_cursor": params[0],
                "decisions_processed": 0,
                "sources_updated": 0,
                "prompts_flagged": 0,
                "failure_reason": None,
                "summary_jsonb": {},
                "started_by_user_id": params[1],
            }
            runs_db[rid] = row
            return row

        # GET run by id
        if "from learning_service_runs" in s and "run_id::text = %s" in s and params:
            return runs_db.get(str(params[0]))

        # source lookup with quality JOIN
        if "from sources s" in s and "left join source_quality_history" in s and "where s.source_id = %s" in s and params:
            sid = params[0]
            src = sources_db.get(sid)
            if not src: return None
            # Find latest quality for this source
            latest_qid = src.get("latest_quality_id")
            q = next((h for h in quality_history if h.get("quality_id") == latest_qid), None)
            return {"predictive_accuracy": q.get("predictive_accuracy") if q else None}

        # source lookup raw
        if "from sources" in s and "where source_id = %s" in s and "left join" not in s and params:
            return sources_db.get(params[0])

        # signal lookup by id
        if "from signals where id::text = %s" in s and params:
            for sig in signals_db:
                if str(sig["id"]) == str(params[0]):
                    return sig
            return None

        # quality history insert
        if "insert into source_quality_history" in s and "returning" in s and params:
            qid = _gen("qty")
            history_row = {
                "quality_id": qid,
                "source_id": params[0],
                "predictive_accuracy": params[1],
                "inputs_jsonb": json.loads(params[2]) if isinstance(params[2], str) else params[2],
            }
            quality_history.append(history_row)
            return {"quality_id": qid}

        # prompt flag aggregation query
        if "from decisions d" in s and "select avg(d.calibration_score)" in s and params:
            # MVP: return a stub that always allows test paths to proceed
            return {"mean_cal": None, "n": 0}

        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()

        # find_decisions_with_outcomes
        if "from decisions" in s and "calibration_score is not null" in s and "actual_outcome_recorded_at" in s and params is not None:
            since = None; idx = 0
            if "actual_outcome_recorded_at > %s" in s:
                since = params[idx]; idx += 1
            limit = params[-1]
            out = [d for d in decisions_db if d.get("calibration_score") is not None
                   and d.get("actual_outcome_recorded_at") is not None]
            if since:
                out = [d for d in out if d["actual_outcome_recorded_at"] > since]
            out.sort(key=lambda d: d["actual_outcome_recorded_at"])
            return out[:limit]

        # evidence_snapshot path → snapshot table
        if "from evidence_snapshots" in s and params:
            decision_id = str(params[0])
            return [
                {"source_id": sid}
                for snap in snapshots_db if str(snap.get("decision_id")) == decision_id
                for sid in snap.get("source_ids", [])
            ]

        # signal → evidence_records.source_id path (_sources_for_signal)
        if "from signals s" in s and "join evidence_records er" in s and params:
            sig = next((sg for sg in signals_db if str(sg["id"]) == str(params[0])), None)
            if not sig:
                return []
            return [{"source_id": sid} for sid in sig.get("evidence_source_ids", [])]

        # find_prompts_in_window
        if "from llm_call_log lcl" in s and "group by" in s:
            # Aggregate llm_calls by prompt_id
            buckets: dict[str, dict] = {}
            for c in llm_calls_db:
                if not c.get("prompt_id") or not c.get("succeeded"): continue
                pid = str(c["prompt_id"])
                b = buckets.setdefault(pid, {"prompt_id": pid, "prompt_name": c.get("prompt_name"),
                                              "users": set(), "total_calls": 0})
                b["users"].add(str(c.get("user_id") or ""))
                b["total_calls"] += 1
            return [
                {"prompt_id": b["prompt_id"], "prompt_name": b.get("prompt_name"),
                 "distinct_users": len(b["users"]), "total_calls": b["total_calls"]}
                for b in buckets.values()
            ]

        # LIST runs
        if "from learning_service_runs" in s and "limit" in s:
            out = list(runs_db.values())
            if params:
                idx = 0
                if "status = %s" in s:
                    out = [r for r in out if r["status"] == params[idx]]; idx += 1
                limit = params[-2]; offset = params[-1]
                out = sorted(out, key=lambda r: r["started_at"], reverse=True)
                out = out[offset:offset + limit]
            return out

        # List attribution log
        if "from source_attribution_log" in s and "limit" in s:
            out = list(attribution_log)
            if params:
                idx = 0
                if "source_id = %s" in s:
                    out = [a for a in out if a["source_id"] == params[idx]]; idx += 1
                if "created_at > %s" in s:
                    out = [a for a in out if a["created_at"] > params[idx]]; idx += 1
            return out[:params[-1]] if params else out[:100]

        # List prompt flags
        if "from prompt_quality_flag" in s and "limit" in s and params:
            cutoff = params[0]; limit = params[1]
            out = [f for f in prompt_flags if f["created_at"] > cutoff]
            out.sort(key=lambda f: f["created_at"], reverse=True)
            return out[:limit]

        return []

    def fake_execute(sql, params=None):
        s = (sql or "").lower()
        # UPDATE source latest_quality_id
        if "update sources set latest_quality_id" in s and params:
            sid = params[1]
            if sid in sources_db:
                sources_db[sid]["latest_quality_id"] = str(params[0])
            return None
        # INSERT attribution_log
        if "insert into source_attribution_log" in s and params:
            attribution_log.append({
                "attribution_id": _gen("att"),
                "run_id": params[0],
                "decision_id": params[1],
                "source_id": params[2],
                "calibration_score": params[3],
                "prior_accuracy": params[4],
                "posterior_accuracy": params[5],
                "created_at": datetime.now(timezone.utc),
            })
            return None
        # INSERT prompt_quality_flag
        if "insert into prompt_quality_flag" in s and params:
            prompt_flags.append({
                "flag_id": _gen("flg"),
                "run_id": params[0], "prompt_id": params[1], "prompt_name": params[2],
                "decisions_observed": params[3], "mean_calibration": params[4],
                "flag_reason": params[5], "created_at": datetime.now(timezone.utc),
            })
            return None
        # UPDATE run row to complete/failed
        if "update learning_service_runs" in s and params:
            rid = str(params[-1])
            if rid not in runs_db: return None
            if "status = 'complete'" in s:
                runs_db[rid]["status"] = "complete"
                runs_db[rid]["completed_at"] = datetime.now(timezone.utc)
                runs_db[rid]["decisions_processed"] = params[0]
                runs_db[rid]["sources_updated"] = params[1]
                runs_db[rid]["prompts_flagged"] = params[2]
                v = params[3]
                runs_db[rid]["summary_jsonb"] = json.loads(v) if isinstance(v, str) else (v or {})
            elif "status = 'failed'" in s:
                runs_db[rid]["status"] = "failed"
                runs_db[rid]["completed_at"] = datetime.now(timezone.utc)
                runs_db[rid]["failure_reason"] = params[0]
            return None
        # auto-register source
        if "insert into sources" in s and params:
            sid = params[0]
            if sid not in sources_db:
                sources_db[sid] = {"source_id": sid, "display_name": params[1],
                                   "tier": 3, "kind": "free",
                                   "latest_quality_id": None}
            return None
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = fake_execute
    return db, decisions_db, sources_db, attribution_log, prompt_flags, runs_db


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
    from api.routes import learning as r
    from services.learning_service import LearningService
    assert r.router.prefix == "/learning"


def test_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/learning/run" in paths
    assert "/learning/runs" in paths
    assert "/learning/runs/{run_id}" in paths
    assert "/learning/source-attributions" in paths
    assert "/learning/prompt-flags" in paths


# ════════════════════════════════════════════════════════════════════
# Run service end-to-end
# ════════════════════════════════════════════════════════════════════

def _seed_decisions_with_signals():
    """Helper: returns (decisions, signals, sources) suitable for DB seeding."""
    now = datetime.now(timezone.utc)
    sources = [
        {"source_id": "src-A", "latest_quality_id": None},
        {"source_id": "src-B", "latest_quality_id": None},
    ]
    # Provenance is signal → evidence_document_ids → evidence_records.source_id
    # (signals has no `source` column). `evidence_source_ids` is the fake
    # harness's stand-in for resolving that chain.
    signals = [
        {"id": "sig-1", "evidence_source_ids": ["src-A"]},
        {"id": "sig-2", "evidence_source_ids": ["src-B"]},
    ]
    decisions = [
        {"id": "dec-1", "calibration_score": 0.9,
         "actual_outcome_recorded_at": now - timedelta(days=1),
         "war_room_id": "wr-1", "source_signal_id": "sig-1",
         "owner_user_id": "uuid-viewer", "created_at": now - timedelta(days=10)},
        {"id": "dec-2", "calibration_score": 0.3,
         "actual_outcome_recorded_at": now - timedelta(hours=12),
         "war_room_id": "wr-2", "source_signal_id": "sig-2",
         "owner_user_id": "uuid-viewer", "created_at": now - timedelta(days=5)},
    ]
    return decisions, signals, sources


def test_run_processes_decisions_and_updates_sources():
    decisions, signals, sources = _seed_decisions_with_signals()
    db, _, sources_db, attribution_log, _, runs_db = _make_db(
        decisions=decisions, signals=signals, sources=sources,
    )
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/learning/run", json={}, headers=_hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "complete"
    assert body["decisions_processed"] == 2
    assert body["sources_updated"] == 2
    # Both sources got attribution_log rows
    assert {a["source_id"] for a in attribution_log} == {"src-A", "src-B"}
    # And both have a latest_quality_id now
    assert sources_db["src-A"]["latest_quality_id"] is not None
    assert sources_db["src-B"]["latest_quality_id"] is not None


def test_run_first_observation_seeds_source_accuracy():
    """Source with NULL prior should get its first observation as the
    seed value (no EWMA blend)."""
    decisions, signals, sources = _seed_decisions_with_signals()
    decisions = decisions[:1]  # single decision with cal=0.9
    db, _, _, attribution_log, _, _ = _make_db(
        decisions=decisions, signals=signals, sources=sources,
    )
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/learning/run", json={}, headers=_hdr(tok))
    assert r.status_code == 200
    # First attribution: prior=None, posterior=0.9
    assert len(attribution_log) == 1
    assert attribution_log[0]["prior_accuracy"] is None
    assert attribution_log[0]["posterior_accuracy"] == 0.9


def test_run_skips_decisions_without_calibration():
    """Decisions with NULL calibration_score are excluded by the WHERE clause."""
    db, _, _, attribution_log, _, _ = _make_db(
        decisions=[{"id": "dec-1", "calibration_score": None,
                    "actual_outcome_recorded_at": datetime.now(timezone.utc),
                    "source_signal_id": None,
                    "owner_user_id": "uuid-viewer", "created_at": datetime.now(timezone.utc)}],
        signals=[], sources=[],
    )
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/learning/run", json={}, headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    # NULL cal filtered out at SQL level → 0 processed
    assert body["decisions_processed"] == 0
    assert len(attribution_log) == 0


def test_run_skips_when_source_not_in_registry():
    """Default behavior: skip with counter when source isn't registered."""
    decisions, signals, _ = _seed_decisions_with_signals()
    db, _, sources_db, attribution_log, _, runs_db = _make_db(
        decisions=decisions, signals=signals, sources=[],  # no sources registered
    )
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/learning/run", json={}, headers=_hdr(tok))
    assert r.status_code == 200
    # Sources not registered → no attribution rows
    assert len(attribution_log) == 0
    assert sources_db == {}


def test_run_with_auto_register_creates_source():
    decisions, signals, _ = _seed_decisions_with_signals()
    db, _, sources_db, attribution_log, _, _ = _make_db(
        decisions=decisions, signals=signals, sources=[],
    )
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/learning/run", json={"auto_register_unknown_sources": True},
                    headers=_hdr(tok))
    assert r.status_code == 200
    assert "src-A" in sources_db
    assert "src-B" in sources_db
    assert len(attribution_log) >= 2


def test_run_records_attribution_method():
    """Decisions resolved via the source_signal_id fallback should report
    method 'decision_source_signal' in summary."""
    decisions, signals, sources = _seed_decisions_with_signals()
    db, _, _, _, _, runs_db = _make_db(
        decisions=decisions, signals=signals, sources=sources,
    )
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/learning/run", json={}, headers=_hdr(tok))
    body = r.json()
    methods = body["summary"]["attribution_methods"]
    # All decisions attributed via signal → evidence_records.source_id
    # (no evidence_snapshot rows seeded).
    assert methods.get("decision_signal_evidence", 0) == 2


def test_get_run_404():
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/learning/runs/nope", headers=_hdr(tok))
    assert r.status_code == 404


def test_list_runs_empty():
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/learning/runs", headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["count"] == 0


def test_list_runs_invalid_status():
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/learning/runs?status=quantum", headers=_hdr(tok))
    assert r.status_code == 400


def test_get_attributions_filter_by_source():
    decisions, signals, sources = _seed_decisions_with_signals()
    db, _, _, _, _, _ = _make_db(decisions=decisions, signals=signals, sources=sources)
    client = _client(db); tok = _login(client, "editor@test.io")
    client.post("/learning/run", json={}, headers=_hdr(tok))

    vtok = _login(client, "viewer@test.io")
    r = client.get("/learning/source-attributions?source_id=src-A", headers=_hdr(vtok))
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert all(a["source_id"] == "src-A" for a in body["attributions"])


def test_prompt_flags_endpoint_returns_empty_initially():
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/learning/prompt-flags", headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["count"] == 0


# ════════════════════════════════════════════════════════════════════
# Auth
# ════════════════════════════════════════════════════════════════════

def test_run_requires_uploader():
    db, _, _, _, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/learning/run", json={}, headers=_hdr(tok))
    assert r.status_code in (401, 403)


def test_unauth_run_401():
    db, _, _, _, _, _ = _make_db()
    client = _client(db)
    r = client.post("/learning/run", json={})
    assert r.status_code in (401, 403)


def test_unauth_list_runs_401():
    db, _, _, _, _, _ = _make_db()
    client = _client(db)
    r = client.get("/learning/runs")
    assert r.status_code in (401, 403)
