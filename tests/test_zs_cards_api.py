"""Lane-1, DB-free tests for the editable capability-card CRUD on the /zs router.

Asserts every new endpoint requires Basic auth (401 without creds), a full
CRUD round-trip with creds, import/export, and 422 on invalid pool/model. Uses a
pytest ``tmp_path`` as the data dir so nothing touches the repo's static dir.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routes import zs as zs_route

AUTH = ("zs", "zs-future")


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("ZS_PAGE_USER", raising=False)
    monkeypatch.delenv("ZS_PAGE_PASSWORD", raising=False)
    # isolate persistence to a tmp dir (no Railway var bleed-through)
    monkeypatch.setenv("ZS_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("RAILWAY_VOLUME_MOUNT_PATH", raising=False)
    app = FastAPI()
    app.include_router(zs_route.router)
    return TestClient(app)


# --- auth gate on every new endpoint ---------------------------------------
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/zs/api/cards"),
        ("get", "/zs/api/cards/export"),
        ("post", "/zs/api/cards"),
        ("post", "/zs/api/cards/import"),
        ("put", "/zs/api/cards/decisionops"),
        ("delete", "/zs/api/cards/decisionops"),
    ],
)
def test_endpoints_require_auth(client, method, path):
    r = getattr(client, method)(path)
    assert r.status_code == 401
    assert "basic" in r.headers.get("www-authenticate", "").lower()


# --- list seeds from defaults ----------------------------------------------
def test_list_cards_seeds_defaults(client):
    r = client.get("/zs/api/cards", auth=AUTH)
    assert r.status_code == 200
    cards = r.json()["cards"]
    assert len(cards) == 6
    assert {c["id"] for c in cards} == {
        "decisionops", "devreg", "cognitive", "platform", "trust", "cliff"
    }


# --- create / update / delete round-trip -----------------------------------
def test_create_update_delete_round_trip(client):
    # create
    body = {
        "name": "New capability", "pool": "ai", "model": "hybrid",
        "size": 0.4, "start": 2, "attain": 55, "color": "var(--s3)",
        "moats": {"ground": 2, "compliance": 1, "switching": 2, "trust": 1, "convenience": 3},
    }
    r = client.post("/zs/api/cards", json=body, auth=AUTH)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["id"] == "new-capability"

    # it shows up in the list
    assert any(c["id"] == "new-capability" for c in client.get("/zs/api/cards", auth=AUTH).json()["cards"])

    # update
    body["name"] = "Renamed"
    body["size"] = 0.9
    r = client.put("/zs/api/cards/new-capability", json=body, auth=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Renamed"
    assert r.json()["size"] == 0.9
    assert r.json()["id"] == "new-capability"  # path id wins

    # delete
    r = client.delete("/zs/api/cards/new-capability", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["deleted"] == "new-capability"
    assert not any(c["id"] == "new-capability" for c in client.get("/zs/api/cards", auth=AUTH).json()["cards"])


def test_create_duplicate_id_conflicts(client):
    client.get("/zs/api/cards", auth=AUTH)  # seed
    body = {"id": "decisionops", "name": "dup", "pool": "ai", "model": "hybrid", "size": 0.1, "start": 1, "attain": 10}
    r = client.post("/zs/api/cards", json=body, auth=AUTH)
    assert r.status_code == 409


def test_create_invalid_pool_is_422(client):
    body = {"name": "bad", "pool": "NOPE", "model": "hybrid", "size": 0.1, "start": 1, "attain": 10}
    r = client.post("/zs/api/cards", json=body, auth=AUTH)
    assert r.status_code == 422


def test_create_invalid_model_is_422(client):
    body = {"name": "bad", "pool": "ai", "model": "NOPE", "size": 0.1, "start": 1, "attain": 10}
    r = client.post("/zs/api/cards", json=body, auth=AUTH)
    assert r.status_code == 422


def test_update_missing_is_404(client):
    body = {"name": "x", "pool": "ai", "model": "hybrid", "size": 0.1, "start": 1, "attain": 10}
    r = client.put("/zs/api/cards/does-not-exist", json=body, auth=AUTH)
    assert r.status_code == 404


def test_delete_missing_is_404(client):
    r = client.delete("/zs/api/cards/does-not-exist", auth=AUTH)
    assert r.status_code == 404


# --- export / import -------------------------------------------------------
def test_export_is_attachment_with_full_set(client):
    r = client.get("/zs/api/cards/export", auth=AUTH)
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    assert len(r.json()["cards"]) == 6


def test_import_replaces_set(client):
    payload = {
        "cards": [
            {"name": "Sole", "pool": "governance", "model": "assurance", "size": 0.2, "start": 3, "attain": 55},
        ]
    }
    r = client.post("/zs/api/cards/import", json=payload, auth=AUTH)
    assert r.status_code == 200, r.text
    assert len(r.json()["cards"]) == 1
    # the live set is now just the imported card
    assert {c["id"] for c in client.get("/zs/api/cards", auth=AUTH).json()["cards"]} == {"sole"}


def test_import_invalid_card_is_422_and_does_not_replace(client):
    # seed + capture the current set
    before = client.get("/zs/api/cards", auth=AUTH).json()
    bad = {"cards": [{"name": "x", "pool": "BAD", "model": "hybrid", "size": 0.1, "start": 1, "attain": 10}]}
    r = client.post("/zs/api/cards/import", json=bad, auth=AUTH)
    assert r.status_code == 422
    # set unchanged
    assert client.get("/zs/api/cards", auth=AUTH).json() == before


def test_import_malformed_payload_is_422(client):
    r = client.post("/zs/api/cards/import", json={"nope": []}, auth=AUTH)
    assert r.status_code == 422
