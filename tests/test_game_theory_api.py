"""SPEC_025 — Game-Theoretic Simulation tests.

Pure-math correctness tests for the three subsystems + API layer + auth.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Pure math: Bayesian
# ════════════════════════════════════════════════════════════════════

class TestBayesian:
    def _cfg(self, *, sample_count=1000, seed=42):
        from services.game_theory import (
            BayesianAdversaryConfig, BayesianRunConfig,
        )
        return BayesianRunConfig(
            adversary=BayesianAdversaryConfig(
                name="Pfizer", kind="competitor",
                type_distribution={"aggressive": 0.6, "defensive": 0.3, "cash_constrained": 0.1},
                type_response_strengths={
                    "aggressive":       {"share_pp_swing": 8.0, "delay_months": -2.0},
                    "defensive":        {"share_pp_swing": 3.0, "delay_months":  0.0},
                    "cash_constrained": {"share_pp_swing": 1.0, "delay_months":  3.0},
                },
            ),
            options=[{"option_id": "opt-1", "label": "Accelerate"}],
            sample_count=sample_count,
            seed=seed,
        )

    def test_deterministic_with_seed(self):
        from services.game_theory import run_bayesian
        cfg = self._cfg()
        r1 = run_bayesian(cfg)
        r2 = run_bayesian(cfg)
        assert r1["options"][0]["posterior_per_dim"]["share_pp_swing"]["mean"] == \
               r2["options"][0]["posterior_per_dim"]["share_pp_swing"]["mean"]

    def test_mean_close_to_expected(self):
        """Expected mean = 0.6×8 + 0.3×3 + 0.1×1 = 5.8"""
        from services.game_theory import run_bayesian
        out = run_bayesian(self._cfg(sample_count=5000))
        mean = out["options"][0]["posterior_per_dim"]["share_pp_swing"]["mean"]
        assert abs(mean - 5.8) < 0.5  # sampling tolerance

    def test_dist_sums_to_1_validation(self):
        from services.game_theory import run_bayesian, BayesianAdversaryConfig, BayesianRunConfig
        cfg = self._cfg()
        cfg.adversary.type_distribution = {"a": 0.5, "b": 0.6}
        with pytest.raises(ValueError, match="sum to 1"):
            run_bayesian(cfg)

    def test_negative_prob_rejected(self):
        from services.game_theory import run_bayesian
        cfg = self._cfg()
        cfg.adversary.type_distribution = {"a": 1.5, "b": -0.5}
        with pytest.raises(ValueError, match="≥ 0|sum to 1"):
            run_bayesian(cfg)

    def test_sample_count_capped(self):
        from services.game_theory import run_bayesian
        cfg = self._cfg()
        cfg.sample_count = 999_999
        with pytest.raises(ValueError, match="sample_count"):
            run_bayesian(cfg)

    def test_missing_type_strength_rejected(self):
        from services.game_theory import run_bayesian
        cfg = self._cfg()
        cfg.adversary.type_distribution = {"a": 1.0}
        # No strengths for type "a"
        with pytest.raises(ValueError, match="type_response_strengths"):
            run_bayesian(cfg)


# ════════════════════════════════════════════════════════════════════
# Pure math: Stackelberg
# ════════════════════════════════════════════════════════════════════

class TestStackelberg:
    def _cfg(self):
        from services.game_theory import StackelbergConfig
        # Toy 2x2 — opponent best at t=0 is "fast_follow" (8 vs 2),
        # opponent best at t=1 is "hold" (10 vs 5). Our payoffs:
        # (0, fast_follow)=5; (1, hold)=12. Optimal leader timing → t=1.
        return StackelbergConfig(
            timing_grid=[0, 1],
            opponent_responses=["fast_follow", "hold"],
            our_payoff_matrix={
                (0, "fast_follow"): 5.0, (0, "hold"): 12.0,
                (1, "fast_follow"): 7.0, (1, "hold"): 12.0,
            },
            opponent_payoff_matrix={
                (0, "fast_follow"): 8.0, (0, "hold"): 2.0,
                (1, "fast_follow"): 5.0, (1, "hold"): 10.0,
            },
        )

    def test_finds_leader_optimal_timing(self):
        from services.game_theory import run_stackelberg
        out = run_stackelberg(self._cfg())
        assert out["optimal_timing"] == 1
        assert out["opponent_best_response"] == "hold"
        assert out["our_payoff"] == 12.0

    def test_tie_break_is_lex_first(self):
        """When opponent payoffs are equal, lex-first response wins."""
        from services.game_theory import StackelbergConfig, run_stackelberg
        cfg = StackelbergConfig(
            timing_grid=[0],
            opponent_responses=["b", "a"],
            our_payoff_matrix={(0, "a"): 10.0, (0, "b"): 5.0},
            opponent_payoff_matrix={(0, "a"): 7.0, (0, "b"): 7.0},
        )
        out = run_stackelberg(cfg)
        # 'a' < 'b' lex; opponent picks 'a'; our payoff = 10
        assert out["opponent_best_response"] == "a"
        assert out["our_payoff"] == 10.0

    def test_missing_payoff_cell_rejected(self):
        from services.game_theory import run_stackelberg
        cfg = self._cfg()
        del cfg.our_payoff_matrix[(0, "fast_follow")]
        with pytest.raises(ValueError, match="missing cell"):
            run_stackelberg(cfg)

    def test_grid_size_capped(self):
        from services.game_theory import StackelbergConfig, run_stackelberg
        cfg = StackelbergConfig(
            timing_grid=list(range(600)),
            opponent_responses=["a"],
            our_payoff_matrix={},
            opponent_payoff_matrix={},
        )
        with pytest.raises(ValueError, match="too large"):
            run_stackelberg(cfg)


# ════════════════════════════════════════════════════════════════════
# Pure math: POMDP
# ════════════════════════════════════════════════════════════════════

class TestPOMDP:
    def test_positive_signal_triggers_wait(self):
        from services.game_theory import POMDPConfig, POMDPSignalConfig, run_pomdp
        cfg = POMDPConfig(
            options={"opt-1": 10.0, "opt-2": 8.0},
            upcoming_signals=[
                POMDPSignalConfig(
                    name="FDA_AdComm", arrival_days=14,
                    expected_info_value=3.0,
                    posterior_shifts={"opt-1": 5.0},  # opt-1 boosted to 15
                ),
            ],
            discount_rate_per_day=0.001,
        )
        out = run_pomdp(cfg)
        assert out["recommendation"] == "wait"
        assert out["wait_for_signal"] == "FDA_AdComm"
        assert out["best_wait_option"] == "opt-1"

    def test_negative_signal_triggers_decide(self):
        from services.game_theory import POMDPConfig, POMDPSignalConfig, run_pomdp
        cfg = POMDPConfig(
            options={"opt-1": 10.0},
            upcoming_signals=[
                POMDPSignalConfig(
                    name="bad_signal", arrival_days=14,
                    expected_info_value=1.0,
                    posterior_shifts={"opt-1": -5.0},  # gets worse
                ),
            ],
            discount_rate_per_day=0.005,
        )
        out = run_pomdp(cfg)
        assert out["recommendation"] == "decide"
        assert out["wait_for_signal"] is None
        assert out["best_wait_option"] == "opt-1"

    def test_high_discount_overrides_wait(self):
        """Even a positive shift loses to a high discount over many days."""
        from services.game_theory import POMDPConfig, POMDPSignalConfig, run_pomdp
        cfg = POMDPConfig(
            options={"opt-1": 100.0},
            upcoming_signals=[
                POMDPSignalConfig(
                    name="slow_signal", arrival_days=200,
                    expected_info_value=1.0,
                    posterior_shifts={"opt-1": 5.0},
                ),
            ],
            discount_rate_per_day=0.01,  # 1% × 200 × 100 = 200 discount > 5 boost
        )
        out = run_pomdp(cfg)
        assert out["recommendation"] == "decide"

    def test_unknown_option_in_shifts_rejected(self):
        from services.game_theory import POMDPConfig, POMDPSignalConfig, run_pomdp
        cfg = POMDPConfig(
            options={"opt-1": 10.0},
            upcoming_signals=[
                POMDPSignalConfig(
                    name="x", arrival_days=1, expected_info_value=0.0,
                    posterior_shifts={"opt-99": 1.0},
                ),
            ],
        )
        with pytest.raises(ValueError, match="unknown option"):
            run_pomdp(cfg)

    def test_discount_rate_out_of_range_rejected(self):
        from services.game_theory import POMDPConfig, POMDPSignalConfig, run_pomdp
        cfg = POMDPConfig(
            options={"opt-1": 1.0},
            upcoming_signals=[
                POMDPSignalConfig(name="x", arrival_days=1,
                                  expected_info_value=0.0, posterior_shifts={"opt-1": 0.5})
            ],
            discount_rate_per_day=1.5,
        )
        with pytest.raises(ValueError, match="discount_rate_per_day"):
            run_pomdp(cfg)


# ════════════════════════════════════════════════════════════════════
# API layer
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
    runs: dict[str, dict] = {}
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

        # INSERT game_theory_runs RETURNING
        if "insert into game_theory_runs" in s and "returning" in s and params:
            rid = _gen("gtr")
            row = {
                "run_id": rid,
                "brief_id": params[0],
                "kind": params[1],
                "inputs_jsonb": json.loads(params[2]) if isinstance(params[2], str) else (params[2] or {}),
                "outputs_jsonb": json.loads(params[3]) if isinstance(params[3], str) else (params[3] or {}),
                "compute_ms": params[4],
                "started_by_user_id": params[5],
                "created_at": datetime.now(timezone.utc),
            }
            runs[rid] = row
            return row

        # GET run by id
        if "from game_theory_runs" in s and "run_id::text = %s" in s and "limit" not in s and params:
            return runs.get(str(params[0]))

        return None

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from game_theory_runs" in s and "limit" in s:
            out = list(runs.values())
            if params:
                idx = 0
                if "brief_id::text = %s" in s:
                    out = [r for r in out if str(r.get("brief_id") or "") == str(params[idx])]; idx += 1
                if "kind = %s" in s:
                    out = [r for r in out if r["kind"] == params[idx]]; idx += 1
                limit = params[-2]; offset = params[-1]
                out = sorted(out, key=lambda r: r["created_at"], reverse=True)
                out = out[offset:offset + limit]
            return out
        return []

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = lambda *a, **kw: None
    return db, runs


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
# Routes
# ────────────────────────────────────────────────────────────────────

def test_module_imports():
    from api.routes import game_theory as r
    from services import game_theory as svc
    assert r.router.prefix == "/game-theory"
    assert hasattr(svc, "run_bayesian")
    assert hasattr(svc, "run_stackelberg")
    assert hasattr(svc, "run_pomdp")


def test_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/game-theory/bayesian" in paths
    assert "/game-theory/stackelberg" in paths
    assert "/game-theory/pomdp" in paths
    assert "/game-theory/runs" in paths
    assert "/game-theory/runs/{run_id}" in paths


def test_post_bayesian_persists_run():
    db, runs = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    payload = {
        "adversary": {
            "name": "Pfizer", "kind": "competitor",
            "type_distribution": {"aggressive": 0.7, "defensive": 0.3},
            "type_response_strengths": {
                "aggressive": {"share_pp": 5.0},
                "defensive":  {"share_pp": 1.0},
            },
        },
        "options": [{"option_id": "opt-1", "label": "Test"}],
        "sample_count": 500,
        "seed": 1,
    }
    r = client.post("/game-theory/bayesian", json=payload, headers=_hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "bayesian"
    assert body["outputs"]["adversary_name"] == "Pfizer"
    assert body["compute_ms"] is not None
    assert len(runs) == 1


def test_post_bayesian_validation_error():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    payload = {
        "adversary": {
            "name": "X", "kind": "competitor",
            "type_distribution": {"a": 0.5, "b": 0.6},  # doesn't sum to 1
            "type_response_strengths": {"a": {"x": 1}, "b": {"x": 2}},
        },
        "options": [{"option_id": "o", "label": "L"}],
    }
    r = client.post("/game-theory/bayesian", json=payload, headers=_hdr(tok))
    assert r.status_code == 400


def test_post_stackelberg():
    db, runs = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    payload = {
        "timing_grid": [0, 1],
        "opponent_responses": ["a", "b"],
        "our_payoff": [
            {"timing": 0, "response": "a", "payoff": 10},
            {"timing": 0, "response": "b", "payoff": 5},
            {"timing": 1, "response": "a", "payoff": 15},
            {"timing": 1, "response": "b", "payoff": 8},
        ],
        "opponent_payoff": [
            {"timing": 0, "response": "a", "payoff": 7},
            {"timing": 0, "response": "b", "payoff": 9},
            {"timing": 1, "response": "a", "payoff": 6},
            {"timing": 1, "response": "b", "payoff": 9},
        ],
    }
    r = client.post("/game-theory/stackelberg", json=payload, headers=_hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kind"] == "stackelberg"
    # Opponent picks 'b' at both timings (higher payoff). Our payoff:
    # (0, b)=5, (1, b)=8. Optimal: t=1, our payoff=8.
    assert body["outputs"]["optimal_timing"] == 1
    assert body["outputs"]["our_payoff"] == 8.0


def test_post_pomdp():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    payload = {
        "options": {"opt-1": 10.0, "opt-2": 8.0},
        "upcoming_signals": [
            {"name": "FDA", "arrival_days": 7,
             "expected_info_value": 3.0,
             "posterior_shifts": {"opt-1": 5.0}},
        ],
        "discount_rate_per_day": 0.001,
    }
    r = client.post("/game-theory/pomdp", json=payload, headers=_hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["outputs"]["recommendation"] == "wait"


def test_get_runs_filters_by_kind():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    # Create one of each kind
    client.post("/game-theory/bayesian", json={
        "adversary": {"name": "X", "kind": "competitor",
                      "type_distribution": {"a": 1.0},
                      "type_response_strengths": {"a": {"x": 1}}},
        "options": [{"option_id": "o", "label": "L"}],
        "sample_count": 10, "seed": 1,
    }, headers=_hdr(tok))
    client.post("/game-theory/pomdp", json={
        "options": {"opt-1": 1.0},
        "upcoming_signals": [{"name": "x", "arrival_days": 0,
                              "expected_info_value": 0.0,
                              "posterior_shifts": {"opt-1": 0.5}}],
    }, headers=_hdr(tok))

    vtok = _login(client, "viewer@test.io")
    r = client.get("/game-theory/runs?kind=bayesian", headers=_hdr(vtok))
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["runs"][0]["kind"] == "bayesian"


def test_get_run_404():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/game-theory/runs/nope", headers=_hdr(tok))
    assert r.status_code == 404


# ────────────────────────────────────────────────────────────────────
# Auth
# ────────────────────────────────────────────────────────────────────

def test_post_requires_uploader():
    db, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    payload = {
        "adversary": {"name": "X", "kind": "competitor",
                      "type_distribution": {"a": 1.0},
                      "type_response_strengths": {"a": {"x": 1}}},
        "options": [{"option_id": "o", "label": "L"}],
    }
    r = client.post("/game-theory/bayesian", json=payload, headers=_hdr(tok))
    assert r.status_code in (401, 403)


def test_unauth_get_runs_401():
    db, _ = _make_db()
    client = _client(db)
    r = client.get("/game-theory/runs")
    assert r.status_code in (401, 403)
