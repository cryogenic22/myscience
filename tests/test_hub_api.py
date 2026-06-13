"""DataHub API (D-API-1) — connector taxonomy + onboarding lifecycle over HTTP.

DB-free: mounts only the `hub` router with `get_db` overridden to a stateful
fake that mirrors the migration-096 tables (reuses the FakeDB shape from
test_connector_taxonomy). Pins the HTTP contract the F5 Connect wizard depends
on — including that the lifecycle state machine is enforced server-side
(illegal transition → 409, not a silent write).
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.deps import get_db
from api.routes import hub
from services.connector_taxonomy import CONNECTOR_TYPE_NAMES


class FakeDB:
    """In-memory stand-in mirroring connector_types + source_onboarding +
    sources.connector_type (same dispatch as test_connector_taxonomy.FakeDB)."""

    def __init__(self):
        self.types = {
            n: {"name": n, "payload_formats": ["json"], "auth_kinds": ["none"],
                "description": f"{n} desc"}
            for n in CONNECTOR_TYPE_NAMES
        }
        self.onboarding: dict[str, dict] = {}
        self.source_connector_type: dict[str, str] = {}

    def fetch_one(self, sql, params=None):
        if "FROM connector_types WHERE name" in sql:
            return self.types.get(params[0])
        if "FROM source_onboarding WHERE source_id" in sql:
            return self.onboarding.get(params[0])
        if "INSERT INTO source_onboarding" in sql:
            source_id, status, owner, contact, go_live, esc = params
            rec = {"source_id": source_id, "status": status, "owner": owner,
                   "contact": contact, "go_live_date": go_live, "escalation": esc,
                   "created_at": None, "updated_at": None}
            self.onboarding[source_id] = rec
            return rec
        if "UPDATE source_onboarding SET status" in sql:
            status, source_id = params
            self.onboarding[source_id]["status"] = status
            return self.onboarding[source_id]
        raise AssertionError(f"unexpected fetch_one SQL: {sql!r}")

    def fetch_all(self, sql, params=None):
        if "FROM connector_types" in sql:
            return sorted(self.types.values(), key=lambda r: r["name"])
        if "FROM source_onboarding" in sql:
            rows = list(self.onboarding.values())
            if params:
                rows = [r for r in rows if r["status"] == params[0]]
            return rows
        raise AssertionError(f"unexpected fetch_all SQL: {sql!r}")

    def execute(self, sql, params=None):
        if "UPDATE sources SET connector_type" in sql:
            connector_type, source_id = params
            self.source_connector_type[source_id] = connector_type
            return
        raise AssertionError(f"unexpected execute SQL: {sql!r}")


@pytest.fixture
def client():
    db = FakeDB()
    app = FastAPI()
    app.include_router(hub.router)
    app.dependency_overrides[get_db] = lambda: db
    c = TestClient(app)
    c._db = db  # expose for assertions
    return c


# ── taxonomy ─────────────────────────────────────────────────────────

def test_list_connector_types(client):
    r = client.get("/hub/connector-types")
    assert r.status_code == 200
    names = {t["name"] for t in r.json()["connector_types"]}
    assert names == set(CONNECTOR_TYPE_NAMES)
    # each carries the shape the wizard renders
    one = r.json()["connector_types"][0]
    assert {"name", "payload_formats", "auth_kinds", "description"} <= set(one)


# ── onboarding lifecycle ─────────────────────────────────────────────

def test_get_onboarding_404_before_start(client):
    assert client.get("/hub/onboarding/ghost").status_code == 404


def test_start_then_get(client):
    r = client.post("/hub/onboarding/acme_api",
                    json={"action": "start", "owner": "data", "connector_type": "API_REST"})
    assert r.status_code == 200
    assert r.json()["status"] == "draft"
    assert client._db.source_connector_type["acme_api"] == "API_REST"
    # now readable
    g = client.get("/hub/onboarding/acme_api")
    assert g.status_code == 200 and g.json()["status"] == "draft"


def test_start_unknown_connector_type_422(client):
    r = client.post("/hub/onboarding/acme_api",
                    json={"action": "start", "connector_type": "FTP"})
    assert r.status_code == 422
    assert "acme_api" not in client._db.onboarding  # no partial write


def test_advance_legal_path(client):
    client.post("/hub/onboarding/s1", json={"action": "start"})
    for nxt in ("test", "staged", "prod"):
        r = client.post("/hub/onboarding/s1", json={"action": "advance", "to_status": nxt})
        assert r.status_code == 200 and r.json()["status"] == nxt


def test_advance_illegal_transition_409_no_write(client):
    client.post("/hub/onboarding/s1", json={"action": "start"})
    r = client.post("/hub/onboarding/s1", json={"action": "advance", "to_status": "prod"})
    assert r.status_code == 409  # can't skip test+staged from draft
    assert client._db.onboarding["s1"]["status"] == "draft"  # unchanged


def test_advance_without_start_404(client):
    r = client.post("/hub/onboarding/ghost", json={"action": "advance", "to_status": "test"})
    assert r.status_code == 404


def test_advance_unknown_status_400_not_409(client):
    # A malformed status is a bad request, not a lifecycle conflict.
    client.post("/hub/onboarding/s1", json={"action": "start"})
    r = client.post("/hub/onboarding/s1", json={"action": "advance", "to_status": "bogus"})
    assert r.status_code == 400
    assert client._db.onboarding["s1"]["status"] == "draft"  # no write


def test_start_is_idempotent(client):
    # Start twice → one row, status unchanged (matches the service contract).
    first = client.post("/hub/onboarding/s1", json={"action": "start", "owner": "a"})
    second = client.post("/hub/onboarding/s1", json={"action": "start", "owner": "b"})
    assert first.status_code == second.status_code == 200
    assert second.json()["status"] == "draft"
    assert len(client._db.onboarding) == 1            # not duplicated
    assert client._db.onboarding["s1"]["owner"] == "a"  # first-call fields win


def test_advance_requires_to_status(client):
    client.post("/hub/onboarding/s1", json={"action": "start"})
    r = client.post("/hub/onboarding/s1", json={"action": "advance"})
    assert r.status_code == 400


def test_unknown_action_400(client):
    r = client.post("/hub/onboarding/s1", json={"action": "bogus"})
    assert r.status_code == 400


def test_list_onboarding_and_status_filter(client):
    client.post("/hub/onboarding/a", json={"action": "start"})
    client.post("/hub/onboarding/b", json={"action": "start"})
    client.post("/hub/onboarding/b", json={"action": "advance", "to_status": "test"})
    allr = client.get("/hub/onboarding").json()["onboarding"]
    assert len(allr) == 2
    draft = client.get("/hub/onboarding?status=draft").json()["onboarding"]
    assert [r["source_id"] for r in draft] == ["a"]


def test_list_onboarding_bad_status_400(client):
    assert client.get("/hub/onboarding?status=nope").status_code == 400
