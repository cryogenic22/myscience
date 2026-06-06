"""DI-5 — SME playbook authoring tests.

Covers: route/playbook validation (predicate/link/source vocab + trigger
overlap), the CRUD + versioning + rollback service over a fake DB, and the
/playbooks API end-to-end via create_app() TestClient (so a shadowed/dead
route would be caught — the /entities greedy-route gotcha).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# Pure validation
# ════════════════════════════════════════════════════════════════════

class TestRouteValidation:
    def test_known_predicate_route_ok(self):
        from services.domain_intelligence.playbook import Route
        from services.domain_intelligence.validation import validate_route
        assert validate_route(Route("predicate", "mechanism_of_action")) is None

    def test_prefix_routable_predicate_ok(self):
        from services.domain_intelligence.playbook import Route
        from services.domain_intelligence.validation import validate_route
        # "trial_xyz" is unknown exactly but the "trial" prefix routes it.
        assert validate_route(Route("predicate", "trial_phase3")) is None

    def test_unknown_predicate_rejected(self):
        from services.domain_intelligence.playbook import Route
        from services.domain_intelligence.validation import validate_route
        err = validate_route(Route("predicate", "totally_made_up_xyzzy"))
        assert err is not None and "no real ledger predicate" in err

    def test_whitelisted_link_route_ok(self):
        from services.domain_intelligence.playbook import Route
        from services.domain_intelligence.validation import validate_route
        assert validate_route(Route("link", "COMPETES_WITH")) is None

    def test_unknown_link_rejected(self):
        from services.domain_intelligence.playbook import Route
        from services.domain_intelligence.validation import validate_route
        err = validate_route(Route("link", "SECRETLY_BACKDOORS"))
        assert err is not None and "not a whitelisted link" in err

    def test_whitelisted_source_route_ok(self):
        from services.domain_intelligence.playbook import Route
        from services.domain_intelligence.validation import validate_route
        assert validate_route(Route("source", "regulatory_milestones")) is None

    def test_non_whitelisted_source_rejected(self):
        from services.domain_intelligence.playbook import Route
        from services.domain_intelligence.validation import validate_route
        err = validate_route(Route("source", "users"))  # arbitrary table → no
        assert err is not None and "not a whitelisted source" in err

    def test_empty_value_rejected(self):
        from services.domain_intelligence.playbook import Route
        from services.domain_intelligence.validation import validate_route
        assert validate_route(Route("predicate", "")) is not None


class TestPlaybookValidation:
    def _valid_payload(self) -> dict:
        return {
            "id": "compare.drug_x_drug.custom",
            "pack": "pharma",
            "trigger": {"intent": "compare", "entities": "drug x company"},
            "dimensions": [
                {"key": "mechanism", "label": "M",
                 "routes": ["predicate:mechanism_of_action"], "required": True, "weight": 0.9},
            ],
            "synthesis": {"shape": "matrix"},
        }

    def test_valid_playbook_passes(self):
        from services.domain_intelligence.playbook import Playbook
        from services.domain_intelligence.validation import validate_playbook
        validate_playbook(Playbook.from_dict(self._valid_payload()))  # no raise

    def test_no_dimensions_rejected(self):
        from services.domain_intelligence.playbook import Playbook
        from services.domain_intelligence.validation import (
            validate_playbook, PlaybookValidationError)
        p = self._valid_payload(); p["dimensions"] = []
        with pytest.raises(PlaybookValidationError, match="at least one dimension"):
            validate_playbook(Playbook.from_dict(p))

    def test_dimension_without_routes_rejected(self):
        from services.domain_intelligence.playbook import Playbook
        from services.domain_intelligence.validation import (
            validate_playbook, PlaybookValidationError)
        p = self._valid_payload()
        p["dimensions"][0]["routes"] = []
        with pytest.raises(PlaybookValidationError, match="has no routes"):
            validate_playbook(Playbook.from_dict(p))

    def test_bad_route_rejected(self):
        from services.domain_intelligence.playbook import Playbook
        from services.domain_intelligence.validation import (
            validate_playbook, PlaybookValidationError)
        p = self._valid_payload()
        p["dimensions"][0]["routes"] = ["predicate:not_a_real_predicate_zzz"]
        with pytest.raises(PlaybookValidationError, match="no real ledger predicate"):
            validate_playbook(Playbook.from_dict(p))

    def test_duplicate_dimension_keys_rejected(self):
        from services.domain_intelligence.playbook import Playbook
        from services.domain_intelligence.validation import (
            validate_playbook, PlaybookValidationError)
        p = self._valid_payload()
        p["dimensions"].append(dict(p["dimensions"][0]))
        with pytest.raises(PlaybookValidationError, match="duplicate dimension key"):
            validate_playbook(Playbook.from_dict(p))

    def test_trigger_overlap_rejected(self):
        from services.domain_intelligence.playbook import Playbook
        from services.domain_intelligence.validation import (
            validate_playbook, PlaybookValidationError)
        p = self._valid_payload()
        p["trigger"] = {"intent": "compare", "entities": "drug x drug"}
        existing = [Playbook.from_dict({
            "id": "compare.drug_x_drug",
            "trigger": {"intent": "compare", "entities": "drug × drug"},
            "dimensions": [{"key": "m", "routes": ["predicate:trial_result"]}],
        })]
        with pytest.raises(PlaybookValidationError, match="duplicates existing playbook"):
            validate_playbook(Playbook.from_dict(p), existing=existing)

    def test_editing_self_does_not_self_overlap(self):
        from services.domain_intelligence.playbook import Playbook
        from services.domain_intelligence.validation import validate_playbook
        p = self._valid_payload()
        p["id"] = "compare.drug_x_drug"
        p["trigger"] = {"intent": "compare", "entities": "drug x drug"}
        existing = [Playbook.from_dict({
            "id": "compare.drug_x_drug",
            "trigger": {"intent": "compare", "entities": "drug × drug"},
            "dimensions": [{"key": "m", "routes": ["predicate:trial_result"]}],
        })]
        validate_playbook(Playbook.from_dict(p), existing=existing)  # no raise (same id)


class TestDiff:
    def test_diff_detects_changed_field(self):
        from services.domain_intelligence.authoring import diff_playbooks
        d = diff_playbooks(
            {"pack": "pharma", "trigger": {}, "dimensions": [], "synthesis": {}},
            {"pack": "pharma", "trigger": {"intent": "compare"}, "dimensions": [], "synthesis": {}},
        )
        assert "trigger" in d and d["trigger"]["to"] == {"intent": "compare"}
        assert "pack" not in d  # unchanged

    def test_diff_create_marks_all_present(self):
        from services.domain_intelligence.authoring import diff_playbooks
        d = diff_playbooks(None, {"pack": "pharma", "dimensions": [{"key": "x"}]})
        assert "pack" in d and d["pack"]["from"] is None


# ════════════════════════════════════════════════════════════════════
# Fake DB simulating playbooks + playbook_versions
# ════════════════════════════════════════════════════════════════════

def _make_db():
    from services.auth import hash_password
    users = {
        "viewer@test.io": {"id": "uuid-viewer", "email": "viewer@test.io",
                           "password_hash": hash_password("demo"), "role": "viewer",
                           "is_active": True},
        "editor@test.io": {"id": "uuid-editor", "email": "editor@test.io",
                           "password_hash": hash_password("demo"), "role": "uploader",
                           "is_active": True},
    }
    playbooks: dict[str, dict] = {}
    versions: list[dict] = []

    def _coerce(v):
        return json.loads(v) if isinstance(v, str) else v

    def fetch_one(sql, params=None):
        s = (sql or "").lower()
        if "from users" in s and params:
            if "lower(email)" in s or "where email" in s:
                return users.get(str(params[0]).lower())
            if "where id" in s:
                for u in users.values():
                    if u["id"] == params[0]:
                        return u
                return None
        if "from playbooks where id" in s and params:
            return playbooks.get(params[0])
        if "insert into playbooks" in s and "returning" in s and params:
            row = {
                "id": params[0], "pack": params[1],
                "trigger": _coerce(params[2]), "dimensions": _coerce(params[3]),
                "synthesis": _coerce(params[4]), "active": True, "version": 1,
                "author": params[5], "tenant_scope": None,
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
            }
            playbooks[params[0]] = row
            return row
        if "update playbooks set" in s and "returning" in s and params:
            pid = params[-1]
            row = playbooks.get(pid)
            if not row:
                return None
            row["pack"] = params[0]
            row["trigger"] = _coerce(params[1])
            row["dimensions"] = _coerce(params[2])
            row["synthesis"] = _coerce(params[3])
            row["version"] = params[4]
            row["author"] = params[5]
            row["updated_at"] = datetime.now(timezone.utc)
            return row
        if "from playbook_versions where playbook_id" in s and "and version" in s and params:
            for v in versions:
                if v["playbook_id"] == params[0] and v["version"] == params[1]:
                    return {"snapshot": v["snapshot"]}
            return None
        return None

    def fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from playbooks order by id" in s:
            return sorted(playbooks.values(), key=lambda r: r["id"])
        if "from playbook_versions where playbook_id" in s and params:
            out = [v for v in versions if v["playbook_id"] == params[0]]
            out.sort(key=lambda v: v["version"], reverse=True)
            return out
        if "from playbooks where active" in s:  # registry DB-override load
            return [r for r in playbooks.values() if r.get("active", True)]
        return []

    def execute(sql, params=None):
        s = (sql or "").lower()
        if "insert into playbook_versions" in s and params:
            versions.append({
                "playbook_id": params[0], "version": params[1], "action": params[2],
                "snapshot": _coerce(params[3]), "diff": _coerce(params[4]),
                "author": params[5], "note": params[6], "rolled_back_from": params[7],
                "created_at": datetime.now(timezone.utc),
            })
            return None
        if "delete from playbooks where id" in s and params:
            playbooks.pop(params[0], None)
            return None
        return None

    db = MagicMock()
    db.fetch_one.side_effect = fetch_one
    db.fetch_all.side_effect = fetch_all
    db.execute.side_effect = execute
    return db, playbooks, versions


# ════════════════════════════════════════════════════════════════════
# Service: CRUD + versioning + rollback
# ════════════════════════════════════════════════════════════════════

_PAYLOAD = {
    "id": "compare.custom",
    "pack": "pharma",
    "trigger": {"intent": "compare", "entities": "drug x company"},
    "dimensions": [
        {"key": "mechanism", "label": "Mechanism",
         "routes": ["predicate:mechanism_of_action"], "required": True, "weight": 0.9},
    ],
    "synthesis": {"shape": "matrix"},
}


class TestServiceCRUD:
    def test_create_then_get(self):
        from services.domain_intelligence.authoring import PlaybookAuthoringService as S
        db, pbs, vers = _make_db()
        created = S.create(db, _PAYLOAD, author="alice")
        assert created["meta"]["version"] == 1
        got = S.get(db, "compare.custom")
        assert got["playbook"]["id"] == "compare.custom"
        # version 1 recorded
        assert any(v["action"] == "create" for v in vers)

    def test_create_conflict(self):
        from services.domain_intelligence.authoring import (
            PlaybookAuthoringService as S, PlaybookConflict)
        db, _, _ = _make_db()
        S.create(db, _PAYLOAD, author="alice")
        with pytest.raises(PlaybookConflict):
            S.create(db, _PAYLOAD, author="bob")

    def test_create_bad_route_rejected(self):
        from services.domain_intelligence.authoring import PlaybookAuthoringService as S
        from services.domain_intelligence.validation import PlaybookValidationError
        db, _, _ = _make_db()
        bad = dict(_PAYLOAD)
        bad["dimensions"] = [{"key": "x", "routes": ["predicate:nope_zzz"]}]
        with pytest.raises(PlaybookValidationError):
            S.create(db, bad)

    def test_update_bumps_version_and_records(self):
        from services.domain_intelligence.authoring import PlaybookAuthoringService as S
        db, _, vers = _make_db()
        S.create(db, _PAYLOAD, author="alice")
        upd = S.update(db, "compare.custom",
                       {"dimensions": [
                           {"key": "efficacy", "label": "E",
                            "routes": ["predicate:trial_result"], "weight": 1.0}]},
                       author="bob", note="add efficacy")
        assert upd["meta"]["version"] == 2
        assert upd["playbook"]["dimensions"][0]["key"] == "efficacy"
        upd_v = [v for v in vers if v["action"] == "update"]
        assert upd_v and "dimensions" in upd_v[0]["diff"]

    def test_update_partial_carries_over(self):
        from services.domain_intelligence.authoring import PlaybookAuthoringService as S
        db, _, _ = _make_db()
        S.create(db, _PAYLOAD, author="alice")
        # only change synthesis; dimensions must persist
        upd = S.update(db, "compare.custom", {"synthesis": {"shape": "list"}})
        assert upd["playbook"]["synthesis"]["shape"] == "list"
        assert upd["playbook"]["dimensions"][0]["key"] == "mechanism"

    def test_update_not_found(self):
        from services.domain_intelligence.authoring import (
            PlaybookAuthoringService as S, PlaybookNotFound)
        db, _, _ = _make_db()
        with pytest.raises(PlaybookNotFound):
            S.update(db, "nope", {"synthesis": {}})

    def test_rollback_restores_prior_version(self):
        from services.domain_intelligence.authoring import PlaybookAuthoringService as S
        db, _, vers = _make_db()
        S.create(db, _PAYLOAD, author="alice")  # v1: mechanism
        S.update(db, "compare.custom",
                 {"dimensions": [{"key": "efficacy", "routes": ["predicate:trial_result"]}]},
                 author="bob")  # v2: efficacy
        rb = S.rollback(db, "compare.custom", 1, author="carol")
        assert rb["meta"]["version"] == 3            # forward version
        assert rb["playbook"]["dimensions"][0]["key"] == "mechanism"  # v1 content restored
        rb_v = [v for v in vers if v["action"] == "rollback"]
        assert rb_v and rb_v[0]["rolled_back_from"] == 1

    def test_rollback_unknown_version(self):
        from services.domain_intelligence.authoring import (
            PlaybookAuthoringService as S, PlaybookNotFound)
        db, _, _ = _make_db()
        S.create(db, _PAYLOAD, author="alice")
        with pytest.raises(PlaybookNotFound):
            S.rollback(db, "compare.custom", 99)

    def test_list_versions_history(self):
        from services.domain_intelligence.authoring import PlaybookAuthoringService as S
        db, _, _ = _make_db()
        S.create(db, _PAYLOAD, author="alice")
        S.update(db, "compare.custom", {"synthesis": {"shape": "list"}}, author="bob")
        hist = S.list_versions(db, "compare.custom")
        assert [h["version"] for h in hist] == [2, 1]  # newest first

    def test_delete_records_audit_and_removes(self):
        from services.domain_intelligence.authoring import (
            PlaybookAuthoringService as S, PlaybookNotFound)
        db, pbs, vers = _make_db()
        S.create(db, _PAYLOAD, author="alice")
        S.delete(db, "compare.custom", author="bob")
        assert "compare.custom" not in pbs
        assert any(v["action"] == "delete" for v in vers)
        with pytest.raises(PlaybookNotFound):
            S.delete(db, "compare.custom")

    def test_list_merges_seed_and_db(self):
        from services.domain_intelligence.authoring import PlaybookAuthoringService as S
        db, _, _ = _make_db()
        S.create(db, _PAYLOAD, author="alice")
        listed = S.list(db)
        ids = {x["playbook"]["id"]: x["source"] for x in listed}
        assert ids.get("compare.custom") == "db"
        # a seeded playbook (not in DB) shows as source=seed
        assert ids.get("compare.drug_x_drug") == "seed"


class TestRegistryServesEdit:
    def test_planner_registry_picks_up_db_edit(self):
        """The PlaybookRegistry(db=...) the planner uses serves the SME edit."""
        from services.domain_intelligence.authoring import PlaybookAuthoringService as S
        from services.domain_intelligence.playbook import PlaybookRegistry
        db, _, _ = _make_db()
        S.create(db, {
            "id": "compare.drug_x_drug",  # OVERRIDE the 7-dim seed
            "trigger": {"intent": "compare", "entities": "drug × drug"},
            "dimensions": [{"key": "mechanism", "routes": ["predicate:mechanism_of_action"]}],
            "synthesis": {"shape": "matrix"},
        }, author="alice")
        reg = PlaybookRegistry(db=db)
        pb = reg.get("compare.drug_x_drug")
        assert len(pb.dimensions) == 1  # DB edit overrode the seed


# ════════════════════════════════════════════════════════════════════
# API — via create_app() TestClient (catches shadowed/dead routes)
# ════════════════════════════════════════════════════════════════════

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


def test_routes_registered_not_shadowed():
    from api.app import create_app
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/playbooks" in paths
    assert "/playbooks/{playbook_id}" in paths
    assert "/playbooks/{playbook_id}/versions" in paths
    assert "/playbooks/{playbook_id}/rollback" in paths
    assert "/playbooks/predicates" in paths


def test_router_prefix_is_own():
    from api.routes import playbooks as r
    assert r.router.prefix == "/playbooks"


class TestApiRoundTrip:
    def test_full_create_edit_version_rollback(self):
        db, _, _ = _make_db()
        c = _client(db)
        ed = _hdr(_login(c, "editor@test.io"))

        # create
        r = c.post("/playbooks", headers=ed, json=_PAYLOAD)
        assert r.status_code == 201, r.text
        assert r.json()["meta"]["version"] == 1

        # read
        r = c.get("/playbooks/compare.custom", headers=ed)
        assert r.status_code == 200

        # edit → v2
        r = c.put("/playbooks/compare.custom", headers=ed,
                  json={"synthesis": {"shape": "list"}})
        assert r.status_code == 200
        assert r.json()["meta"]["version"] == 2

        # history
        r = c.get("/playbooks/compare.custom/versions", headers=ed)
        assert r.status_code == 200
        assert [v["version"] for v in r.json()["versions"]] == [2, 1]

        # rollback to v1 → v3
        r = c.post("/playbooks/compare.custom/rollback", headers=ed,
                   json={"target_version": 1})
        assert r.status_code == 200
        assert r.json()["meta"]["version"] == 3
        assert r.json()["playbook"]["synthesis"]["shape"] == "matrix"

    def test_create_bad_route_returns_400(self):
        db, _, _ = _make_db()
        c = _client(db)
        ed = _hdr(_login(c, "editor@test.io"))
        bad = dict(_PAYLOAD)
        bad["dimensions"] = [{"key": "x", "routes": ["predicate:made_up_zzz"]}]
        r = c.post("/playbooks", headers=ed, json=bad)
        assert r.status_code == 400, r.text

    def test_viewer_cannot_create(self):
        db, _, _ = _make_db()
        c = _client(db)
        vw = _hdr(_login(c, "viewer@test.io"))
        r = c.post("/playbooks", headers=vw, json=_PAYLOAD)
        assert r.status_code == 403

    def test_viewer_can_list(self):
        db, _, _ = _make_db()
        c = _client(db)
        vw = _hdr(_login(c, "viewer@test.io"))
        r = c.get("/playbooks", headers=vw)
        assert r.status_code == 200
        assert "playbooks" in r.json()

    def test_predicates_vocabulary_endpoint(self):
        db, _, _ = _make_db()
        c = _client(db)
        vw = _hdr(_login(c, "viewer@test.io"))
        r = c.get("/playbooks/predicates", headers=vw)
        assert r.status_code == 200
        body = r.json()
        assert "mechanism_of_action" in body["predicates"]
        assert "COMPETES_WITH" in body["link_types"]
        assert "regulatory_milestones" in body["source_tables"]

    def test_get_unknown_returns_404(self):
        db, _, _ = _make_db()
        c = _client(db)
        ed = _hdr(_login(c, "editor@test.io"))
        r = c.get("/playbooks/does.not.exist", headers=ed)
        assert r.status_code == 404
