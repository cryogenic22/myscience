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
    # SEC-001a: the /zs gate fails closed unless creds are configured — set them
    # (matching AUTH) as an operator would, rather than relying on a default.
    monkeypatch.setenv("ZS_PAGE_USER", AUTH[0])
    monkeypatch.setenv("ZS_PAGE_PASSWORD", AUTH[1])
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


# ===========================================================================
# Two new card families on the /zs router — commercial constructs + bets.
# The endpoints are registered by the same factory as /api/cards, so these
# assert the auth gate, seed contents, CRUD round-trip, enum→422 and import
# validation for each new family without regressing the cards routes above.
# ===========================================================================

# --- auth gate on every new endpoint ---------------------------------------
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/zs/api/constructs"),
        ("get", "/zs/api/constructs/export"),
        ("post", "/zs/api/constructs"),
        ("post", "/zs/api/constructs/import"),
        ("put", "/zs/api/constructs/floor-per-hit"),
        ("delete", "/zs/api/constructs/floor-per-hit"),
        ("get", "/zs/api/bets"),
        ("get", "/zs/api/bets/export"),
        ("post", "/zs/api/bets"),
        ("post", "/zs/api/bets/import"),
        ("put", "/zs/api/bets/quantum"),
        ("delete", "/zs/api/bets/quantum"),
    ],
)
def test_new_family_endpoints_require_auth(client, method, path):
    r = getattr(client, method)(path)
    assert r.status_code == 401
    assert "basic" in r.headers.get("www-authenticate", "").lower()


# --- constructs: list seeds + CRUD -----------------------------------------
def test_constructs_list_seeds_defaults(client):
    r = client.get("/zs/api/constructs", auth=AUTH)
    assert r.status_code == 200
    cards = r.json()["cards"]
    assert len(cards) == 6
    assert {c["id"] for c in cards} == {
        "floor-per-hit", "decision-latency-sla", "gain-share",
        "cost-to-serve-takeout", "assurance-per-cert", "outcome-underwriting",
    }
    fph = next(c for c in cards if c["id"] == "floor-per-hit")
    assert fph["quality"] == "outcome"
    assert fph["name"] == "Floor + per-hit"


def test_constructs_create_update_delete_round_trip(client):
    body = {"name": "Retainer Plus", "quality": "recurring", "meter": "monthly", "buyer": "CFO"}
    r = client.post("/zs/api/constructs", json=body, auth=AUTH)
    assert r.status_code == 201, r.text
    assert r.json()["id"] == "retainer-plus"

    body["name"] = "Retainer Pro"
    body["quality"] = "outcome"
    r = client.put("/zs/api/constructs/retainer-plus", json=body, auth=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Retainer Pro"
    assert r.json()["id"] == "retainer-plus"  # path id wins

    r = client.delete("/zs/api/constructs/retainer-plus", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["deleted"] == "retainer-plus"


def test_constructs_invalid_quality_is_422(client):
    body = {"name": "bad", "quality": "NOPE"}
    r = client.post("/zs/api/constructs", json=body, auth=AUTH)
    assert r.status_code == 422


def test_constructs_update_missing_is_404(client):
    r = client.put("/zs/api/constructs/does-not-exist", json={"name": "x"}, auth=AUTH)
    assert r.status_code == 404


def test_constructs_delete_missing_is_404(client):
    r = client.delete("/zs/api/constructs/does-not-exist", auth=AUTH)
    assert r.status_code == 404


def test_constructs_export_is_attachment(client):
    r = client.get("/zs/api/constructs/export", auth=AUTH)
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "commercial_constructs" in r.headers.get("content-disposition", "")
    assert len(r.json()["cards"]) == 6


def test_constructs_import_replaces_and_bad_enum_422(client):
    ok = {"cards": [{"name": "Sole", "quality": "project"}]}
    r = client.post("/zs/api/constructs/import", json=ok, auth=AUTH)
    assert r.status_code == 200, r.text
    assert {c["id"] for c in client.get("/zs/api/constructs", auth=AUTH).json()["cards"]} == {"sole"}

    bad = {"cards": [{"name": "x", "quality": "BAD"}]}
    before = client.get("/zs/api/constructs", auth=AUTH).json()
    r = client.post("/zs/api/constructs/import", json=bad, auth=AUTH)
    assert r.status_code == 422
    assert client.get("/zs/api/constructs", auth=AUTH).json() == before  # unchanged


# --- bets: list seeds + CRUD -----------------------------------------------
def test_bets_list_seeds_defaults(client):
    r = client.get("/zs/api/bets", auth=AUTH)
    assert r.status_code == 200
    cards = r.json()["cards"]
    assert len(cards) == 6
    assert {c["id"] for c in cards} == {
        "simulation-aas", "digital-twin", "pharma-slms",
        "the-harness", "quantum", "hardware-edge",
    }
    quantum = next(c for c in cards if c["id"] == "quantum")
    assert quantum["native"] is False
    assert quantum["posture"] == "partner"


def test_bets_create_update_delete_round_trip(client):
    body = {"name": "Edge Inference", "horizon": "near", "posture": "build", "native": False}
    r = client.post("/zs/api/bets", json=body, auth=AUTH)
    assert r.status_code == 201, r.text
    assert r.json()["id"] == "edge-inference"
    assert r.json()["native"] is False

    body["posture"] = "partner"
    r = client.put("/zs/api/bets/edge-inference", json=body, auth=AUTH)
    assert r.status_code == 200, r.text
    assert r.json()["posture"] == "partner"

    r = client.delete("/zs/api/bets/edge-inference", auth=AUTH)
    assert r.status_code == 200
    assert r.json()["deleted"] == "edge-inference"


def test_bets_invalid_horizon_is_422(client):
    r = client.post("/zs/api/bets", json={"name": "bad", "horizon": "someday"}, auth=AUTH)
    assert r.status_code == 422


def test_bets_invalid_posture_is_422(client):
    r = client.post("/zs/api/bets", json={"name": "bad", "posture": "acquire"}, auth=AUTH)
    assert r.status_code == 422


def test_bets_update_missing_is_404(client):
    r = client.put("/zs/api/bets/does-not-exist", json={"name": "x"}, auth=AUTH)
    assert r.status_code == 404


def test_bets_delete_missing_is_404(client):
    r = client.delete("/zs/api/bets/does-not-exist", auth=AUTH)
    assert r.status_code == 404


def test_bets_export_is_attachment(client):
    r = client.get("/zs/api/bets/export", auth=AUTH)
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    assert "capability_bets" in r.headers.get("content-disposition", "")
    assert len(r.json()["cards"]) == 6


def test_bets_import_replaces_and_bad_enum_422(client):
    ok = {"cards": [{"name": "Sole Bet", "posture": "consume"}]}
    r = client.post("/zs/api/bets/import", json=ok, auth=AUTH)
    assert r.status_code == 200, r.text
    assert {c["id"] for c in client.get("/zs/api/bets", auth=AUTH).json()["cards"]} == {"sole-bet"}

    bad = {"cards": [{"name": "x", "posture": "BAD"}]}
    before = client.get("/zs/api/bets", auth=AUTH).json()
    r = client.post("/zs/api/bets/import", json=bad, auth=AUTH)
    assert r.status_code == 422
    assert client.get("/zs/api/bets", auth=AUTH).json() == before  # unchanged


def test_families_persist_to_separate_files_via_api(client):
    # mutating one family's set must not change another's
    client.post("/zs/api/constructs/import", json={"cards": [{"name": "Only"}]}, auth=AUTH)
    assert len(client.get("/zs/api/constructs", auth=AUTH).json()["cards"]) == 1
    assert len(client.get("/zs/api/cards", auth=AUTH).json()["cards"]) == 6
    assert len(client.get("/zs/api/bets", auth=AUTH).json()["cards"]) == 6


# --- regression: `family` is NOT a client-controllable query param ---------
def test_family_is_not_a_client_query_param(client):
    """Regression for the review finding: the handlers used to take
    ``_family: str = family``, which FastAPI promoted to a ``?_family=`` query
    param — a caller could cross-read/write another family's file (and a bogus
    value 500'd). The family is now bound from the route closure only."""
    cards_ids = {c["id"] for c in client.get("/zs/api/cards", auth=AUTH).json()["cards"]}
    bets_ids = {c["id"] for c in client.get("/zs/api/bets", auth=AUTH).json()["cards"]}
    assert cards_ids != bets_ids  # sanity: the two families seed differently

    # a query param must NOT switch which family /api/cards reads (try both names)
    for qp in ("_family", "family"):
        r = client.get("/zs/api/cards", params={qp: "bets"}, auth=AUTH)
        assert r.status_code == 200
        assert {c["id"] for c in r.json()["cards"]} == cards_ids  # still cards

    # a bogus family value must not 500 — it's simply ignored
    r = client.get("/zs/api/cards", params={"_family": "nonsense"}, auth=AUTH)
    assert r.status_code == 200
    assert {c["id"] for c in r.json()["cards"]} == cards_ids

    # a write to /api/cards must land in cards, never cross into bets
    r = client.post(
        "/zs/api/cards", params={"_family": "bets"},
        json={"name": "Sneaky", "pool": "ai", "model": "hybrid", "size": 0.1, "start": 1, "attain": 10},
        auth=AUTH,
    )
    assert r.status_code == 201
    assert "sneaky" in {c["id"] for c in client.get("/zs/api/cards", auth=AUTH).json()["cards"]}
    bets_after = client.get("/zs/api/bets", auth=AUTH).json()["cards"]
    assert "sneaky" not in {c["id"] for c in bets_after}
    assert len(bets_after) == 6  # bets untouched
