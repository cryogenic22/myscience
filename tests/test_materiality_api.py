"""SPEC_031 — Materiality Scoring tests."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Pure scorer
# ════════════════════════════════════════════════════════════════════

class TestComputeMateriality:
    def test_default_weights_sum_to_one(self):
        from services.materiality import DEFAULT_WEIGHTS
        assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-6

    def test_max_score_setup(self):
        """Tier 1 + focal + clinical_readout + 0 days → score = 100."""
        from services.materiality import compute_materiality
        r = compute_materiality(
            source_tier=1,
            entity_criticality="focal",
            claim_type="clinical_readout",
            age_days=0,
        )
        assert r.score == 100.0
        # Each contribution: 0.30*1 + 0.30*1 + 0.25*1 + 0.15*1 = 1.0 → 100
        assert abs(r.factors["source_tier"].contribution - 30.0) < 0.01
        assert abs(r.factors["recency"].contribution - 15.0) < 0.01

    def test_min_realistic_score(self):
        """Tier 3 + other + earnings + 365 days → low score."""
        from services.materiality import compute_materiality
        r = compute_materiality(
            source_tier=3,
            entity_criticality="other",
            claim_type="earnings_commentary",
            age_days=365,
        )
        # source_tier: 0.30*0.4=12 ; criticality: 0.30*0.2=6 ;
        # claim_type: 0.25*0.4=10 ; recency: 0.15*tiny ≈ 0
        # Total ≈ 28
        assert 25 < r.score < 32

    def test_recency_at_half_life_is_05(self):
        from services.materiality import compute_materiality, DEFAULT_RECENCY_HALF_LIFE_DAYS
        r = compute_materiality(
            source_tier=3, entity_criticality="other",
            claim_type="other", age_days=DEFAULT_RECENCY_HALF_LIFE_DAYS,
        )
        assert abs(r.factors["recency"].factor_value - 0.5) < 0.001

    def test_recency_at_zero_is_1(self):
        from services.materiality import compute_materiality
        r = compute_materiality(
            source_tier=3, entity_criticality="other",
            claim_type="other", age_days=0,
        )
        assert abs(r.factors["recency"].factor_value - 1.0) < 0.001

    def test_negative_age_clamped_to_zero(self):
        from services.materiality import compute_materiality
        r1 = compute_materiality(
            source_tier=3, entity_criticality="other",
            claim_type="other", age_days=-10,
        )
        r2 = compute_materiality(
            source_tier=3, entity_criticality="other",
            claim_type="other", age_days=0,
        )
        # Both should produce the same recency factor (clamped to 0)
        assert abs(r1.factors["recency"].factor_value - r2.factors["recency"].factor_value) < 1e-6

    def test_unknown_claim_type_falls_back_to_other(self):
        from services.materiality import compute_materiality
        r = compute_materiality(
            source_tier=2, entity_criticality="focal",
            claim_type="alien_invasion", age_days=1,
        )
        # Should not raise; claim_type should be reported as 'other'
        assert r.factors["claim_type"].input_value == "other"
        # value should match default for 'other' (0.3)
        assert abs(r.factors["claim_type"].factor_value - 0.3) < 1e-6

    def test_unknown_criticality_falls_back_to_other(self):
        from services.materiality import compute_materiality
        r = compute_materiality(
            source_tier=2, entity_criticality="enemy_combatant",
            claim_type="other", age_days=1,
        )
        assert r.factors["entity_criticality"].input_value == "other"

    def test_missing_source_tier_uses_tier_3_default(self):
        from services.materiality import compute_materiality
        r = compute_materiality(
            source_tier=None, entity_criticality="focal",
            claim_type="other", age_days=0,
        )
        assert r.factors["source_tier"].input_value == 3
        assert abs(r.factors["source_tier"].factor_value - 0.4) < 1e-6

    def test_score_clamped_to_0_100(self):
        from services.materiality import compute_materiality
        r = compute_materiality(
            source_tier=1, entity_criticality="focal",
            claim_type="clinical_readout", age_days=0,
        )
        assert 0 <= r.score <= 100

    def test_contributions_sum_to_score(self):
        from services.materiality import compute_materiality
        r = compute_materiality(
            source_tier=2, entity_criticality="top_competitor",
            claim_type="pricing_change", age_days=14,
        )
        s = sum(f.contribution for f in r.factors.values())
        assert abs(s - r.score) < 0.01


class TestValidation:
    def test_validate_weights_must_sum_to_one(self):
        from services.materiality import validate_weights
        with pytest.raises(ValueError, match="sum to 1"):
            validate_weights({"source_tier": 0.5, "entity_criticality": 0.3,
                              "claim_type": 0.3, "recency": 0.3})

    def test_validate_weights_missing_keys(self):
        from services.materiality import validate_weights
        with pytest.raises(ValueError, match="missing required keys"):
            validate_weights({"source_tier": 1.0})

    def test_validate_weights_extra_keys(self):
        from services.materiality import validate_weights
        with pytest.raises(ValueError, match="unknown keys"):
            validate_weights({
                "source_tier": 0.25, "entity_criticality": 0.25,
                "claim_type": 0.25, "recency": 0.15, "extra": 0.10,
            })

    def test_validate_weights_negative(self):
        from services.materiality import validate_weights
        with pytest.raises(ValueError, match="≥ 0"):
            validate_weights({
                "source_tier": -0.1, "entity_criticality": 0.4,
                "claim_type": 0.3, "recency": 0.4,
            })

    def test_validate_factor_values_out_of_range(self):
        from services.materiality import validate_factor_values
        with pytest.raises(ValueError, match=r"\[0, 1\]"):
            validate_factor_values({"x": 1.5}, "test")


# ════════════════════════════════════════════════════════════════════
# API layer
# ════════════════════════════════════════════════════════════════════

def _make_db(seed_active_config: bool = True):
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
    configs: dict[str, dict] = {}
    signals_updated: list[dict] = []
    next_id = [1]

    def _gen(p):
        n = next_id[0]; next_id[0] += 1
        return f"{p}-{n:04d}"

    if seed_active_config:
        cid = _gen("cfg")
        configs[cid] = {
            "config_id": cid,
            "is_active": True,
            "weights_jsonb": {"source_tier": 0.30, "entity_criticality": 0.30,
                              "claim_type": 0.25, "recency": 0.15},
            "tier_values_jsonb": {"1": 1.0, "2": 0.7, "3": 0.4, "4": 0.6},
            "claim_type_values_jsonb": {
                "clinical_readout": 1.0, "regulatory_action": 0.95,
                "safety_signal": 0.85, "pricing_change": 0.8,
                "formulary_change": 0.75, "pipeline_update": 0.6,
                "earnings_commentary": 0.4, "other": 0.3,
            },
            "criticality_values_jsonb": {"focal": 1.0, "top_competitor": 0.7,
                                         "watched": 0.5, "other": 0.2},
            "recency_half_life_days": 30.0,
            "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        }

    def fake_fetch_one(sql, params=None):
        s = (sql or "").lower()
        if "from users" in s and params:
            if "where lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id::text" in s or "where id =" in s:
                for u in users.values():
                    if u["id"] == params[0]: return u
                return None

        # Active config select
        if "from materiality_weight_config" in s and "is_active = true" in s and "limit 1" in s:
            for c in configs.values():
                if c["is_active"]:
                    return c
            return None

        # Insert new active config
        if "insert into materiality_weight_config" in s and "returning" in s and params:
            cid = _gen("cfg")
            row = {
                "config_id": cid,
                "is_active": True,
                "weights_jsonb": json.loads(params[0]) if isinstance(params[0], str) else params[0],
                "tier_values_jsonb": json.loads(params[1]) if isinstance(params[1], str) else params[1],
                "claim_type_values_jsonb": json.loads(params[2]) if isinstance(params[2], str) else params[2],
                "criticality_values_jsonb": json.loads(params[3]) if isinstance(params[3], str) else params[3],
                "recency_half_life_days": params[4],
                "created_at": datetime.now(timezone.utc),
            }
            configs[cid] = row
            return row

        return None

    def fake_fetch_all(sql, params=None):
        return []

    def fake_execute(sql, params=None):
        s = (sql or "").lower()
        # Deactivate old configs
        if "update materiality_weight_config set is_active = false" in s:
            for c in configs.values():
                c["is_active"] = False
            return None
        # Persist score to signals
        if "update signals" in s and "materiality_factors" in s and params:
            signals_updated.append({
                "score": params[0], "factors": params[1],
                "id": str(params[2]),
            })
            return None
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fake_fetch_one
    db.fetch_all.side_effect = fake_fetch_all
    db.execute.side_effect = fake_execute
    return db, configs, signals_updated


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
    from api.routes import materiality as r
    from services import materiality as svc
    assert r.router.prefix == "/materiality"


def test_routes_registered():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/materiality/score" in paths
    assert "/materiality/weights" in paths


def test_post_score_returns_factor_breakdown():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/materiality/score", json={
        "source_tier": 1, "entity_criticality": "focal",
        "claim_type": "regulatory_action", "age_days": 5,
    }, headers=_hdr(tok))
    assert r.status_code == 200, r.text
    body = r.json()
    assert "materiality_score" in body
    assert "materiality_factors" in body
    factors = body["materiality_factors"]
    assert set(factors.keys()) == {"source_tier", "entity_criticality", "claim_type", "recency"}
    for f in factors.values():
        assert "contribution" in f
        assert "weight" in f
        assert "value" in f


def test_post_score_persists_when_signal_id_provided():
    db, _, signals_updated = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/materiality/score", json={
        "source_tier": 2, "entity_criticality": "top_competitor",
        "claim_type": "pricing_change", "age_days": 1,
        "signal_id": "sig-123",
    }, headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["persisted_to_signal_id"] == "sig-123"
    assert len(signals_updated) == 1
    assert signals_updated[0]["id"] == "sig-123"


def test_post_score_with_unknown_claim_type_falls_back():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.post("/materiality/score", json={
        "source_tier": 2, "entity_criticality": "focal",
        "claim_type": "alien_invasion", "age_days": 1,
    }, headers=_hdr(tok))
    assert r.status_code == 200
    assert r.json()["materiality_factors"]["claim_type"]["input"] == "other"


def test_get_weights_returns_active():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/materiality/weights", headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    assert "weights" in body
    assert "tier_values" in body
    assert "claim_type_values" in body
    assert "criticality_values" in body
    # Default-seeded weights sum to 1
    assert abs(sum(body["weights"].values()) - 1.0) < 1e-6


def test_get_weights_falls_back_to_defaults_when_no_active():
    """When DB is empty, GET still returns code defaults."""
    db, _, _ = _make_db(seed_active_config=False)
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.get("/materiality/weights", headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    assert abs(sum(body["weights"].values()) - 1.0) < 1e-6


def test_put_weights_validates_sum_to_1():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.put("/materiality/weights", json={
        "weights": {"source_tier": 0.5, "entity_criticality": 0.5,
                    "claim_type": 0.5, "recency": 0.5},
        "tier_values": {"1": 1.0, "2": 0.7, "3": 0.4, "4": 0.6},
        "claim_type_values": {"clinical_readout": 1.0, "other": 0.3},
        "criticality_values": {"focal": 1.0, "other": 0.2},
        "recency_half_life_days": 30.0,
    }, headers=_hdr(tok))
    assert r.status_code == 400
    assert "sum to 1" in r.json().get("detail", "")


def test_put_weights_creates_new_active_config():
    db, configs, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.put("/materiality/weights", json={
        "weights": {"source_tier": 0.4, "entity_criticality": 0.3,
                    "claim_type": 0.2, "recency": 0.1},
        "tier_values": {"1": 1.0, "2": 0.8, "3": 0.5, "4": 0.6},
        "claim_type_values": {"clinical_readout": 1.0, "other": 0.4},
        "criticality_values": {"focal": 1.0, "other": 0.3},
        "recency_half_life_days": 60.0,
    }, headers=_hdr(tok))
    assert r.status_code == 200
    body = r.json()
    assert body["weights"]["source_tier"] == 0.4
    # Old config deactivated, new one active → only one active
    assert sum(1 for c in configs.values() if c["is_active"]) == 1


def test_put_weights_invalid_factor_value_rejected():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "editor@test.io")
    r = client.put("/materiality/weights", json={
        "weights": {"source_tier": 0.4, "entity_criticality": 0.3,
                    "claim_type": 0.2, "recency": 0.1},
        "tier_values": {"1": 5.0, "2": 0.8, "3": 0.5, "4": 0.6},  # 5.0 > 1
        "claim_type_values": {"other": 0.3},
        "criticality_values": {"other": 0.2},
        "recency_half_life_days": 30.0,
    }, headers=_hdr(tok))
    assert r.status_code == 400


# ────────────────────────────────────────────────────────────────────
# Auth
# ────────────────────────────────────────────────────────────────────

def test_post_score_requires_uploader():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.post("/materiality/score", json={"source_tier": 1}, headers=_hdr(tok))
    assert r.status_code in (401, 403)


def test_unauth_get_weights_401():
    db, _, _ = _make_db()
    client = _client(db)
    r = client.get("/materiality/weights")
    assert r.status_code in (401, 403)


def test_put_weights_requires_uploader():
    db, _, _ = _make_db()
    client = _client(db); tok = _login(client, "viewer@test.io")
    r = client.put("/materiality/weights", json={
        "weights": {"source_tier": 0.4, "entity_criticality": 0.3,
                    "claim_type": 0.2, "recency": 0.1},
        "tier_values": {"1": 1.0},
        "claim_type_values": {"other": 0.3},
        "criticality_values": {"other": 0.2},
        "recency_half_life_days": 30.0,
    }, headers=_hdr(tok))
    assert r.status_code in (401, 403)
