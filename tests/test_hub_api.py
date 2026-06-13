"""DataHub D-API-1 — REST surface over the L2 connector-taxonomy + onboarding
service (`services/connector_taxonomy.py`, #245).

Lane-1, DB-free. The route functions are exercised two ways:
  1. directly (bypassing auth) with a stateful FakeDB to assert response shape +
     status mapping (InvalidTransition→400, OnboardingNotFound→404, …);
  2. through a TestClient to assert the `/hub/*` routes are actually mounted.

The FakeDB mirrors migration-096's tables (connector_types, source_onboarding)
plus the `sources` existence probe the start endpoint uses for a clean 404.
"""
from __future__ import annotations

import pytest
from fastapi import HTTPException

from services.connector_taxonomy import CONNECTOR_TYPE_NAMES


# ── stateful fake db (mirrors migration 096 + a sources existence probe) ──────

class FakeDB:
    def __init__(self, *, sources=None, onboarding=None):
        self.types = {
            n: {"name": n, "payload_formats": ["json"], "auth_kinds": ["none"],
                "description": f"{n} desc"}
            for n in CONNECTOR_TYPE_NAMES
        }
        self.sources = set(sources if sources is not None else ["acme_api"])
        self.onboarding: dict[str, dict] = dict(onboarding or {})
        self.source_connector_type: dict[str, str] = {}

    def fetch_one(self, sql, params=None):
        if "FROM sources WHERE source_id" in sql:
            return {"ok": 1} if params[0] in self.sources else None
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


VIEWER = {"id": "u-1", "role": "viewer"}
UPLOADER = {"id": "u-2", "role": "uploader"}


# ── connector-types ──────────────────────────────────────────────────────────

class TestConnectorTypes:
    def test_list_returns_all_seeded_types(self):
        from api.routes.hub import list_connector_types_route
        out = list_connector_types_route(user=VIEWER, db=FakeDB())
        assert out["count"] == len(CONNECTOR_TYPE_NAMES)
        assert {t["name"] for t in out["connector_types"]} == set(CONNECTOR_TYPE_NAMES)
        # shape the wizard renders
        first = out["connector_types"][0]
        assert {"name", "payload_formats", "auth_kinds", "description"} <= set(first)

    def test_get_known_type(self):
        from api.routes.hub import get_connector_type_route
        out = get_connector_type_route("API_REST", user=VIEWER, db=FakeDB())
        assert out["name"] == "API_REST"

    def test_get_unknown_type_404(self):
        from api.routes.hub import get_connector_type_route
        with pytest.raises(HTTPException) as e:
            get_connector_type_route("FTP", user=VIEWER, db=FakeDB())
        assert e.value.status_code == 404


# ── onboarding reads ─────────────────────────────────────────────────────────

class TestOnboardingReads:
    def test_get_missing_onboarding_404(self):
        from api.routes.hub import get_onboarding_route
        with pytest.raises(HTTPException) as e:
            get_onboarding_route("acme_api", user=VIEWER, db=FakeDB())
        assert e.value.status_code == 404

    def test_list_onboarding_and_status_filter(self):
        from api.routes.hub import list_onboarding_route
        db = FakeDB(onboarding={
            "a": {"source_id": "a", "status": "draft", "owner": None,
                  "contact": None, "go_live_date": None, "escalation": None,
                  "created_at": None, "updated_at": None},
            "b": {"source_id": "b", "status": "prod", "owner": None,
                  "contact": None, "go_live_date": None, "escalation": None,
                  "created_at": None, "updated_at": None},
        })
        allr = list_onboarding_route(status=None, user=VIEWER, db=db)
        assert allr["count"] == 2
        prod = list_onboarding_route(status="prod", user=VIEWER, db=db)
        assert prod["count"] == 1 and prod["onboarding"][0]["source_id"] == "b"

    def test_list_onboarding_bad_status_400(self):
        from api.routes.hub import list_onboarding_route
        with pytest.raises(HTTPException) as e:
            list_onboarding_route(status="bogus", user=VIEWER, db=FakeDB())
        assert e.value.status_code == 400


# ── start onboarding ─────────────────────────────────────────────────────────

class TestStartOnboarding:
    def _body(self, **kw):
        from api.routes.hub import StartOnboardingBody
        return StartOnboardingBody(**kw)

    def test_start_creates_draft(self):
        from api.routes.hub import start_onboarding_route
        db = FakeDB(sources=["acme_api"])
        out = start_onboarding_route(
            "acme_api", self._body(owner="ops", connector_type="API_REST"),
            user=UPLOADER, db=db,
        )
        assert out["status"] == "draft"
        assert out["owner"] == "ops"
        assert db.source_connector_type["acme_api"] == "API_REST"

    def test_start_is_idempotent(self):
        from api.routes.hub import start_onboarding_route
        db = FakeDB(sources=["acme_api"])
        start_onboarding_route("acme_api", self._body(), user=UPLOADER, db=db)
        again = start_onboarding_route("acme_api", self._body(), user=UPLOADER, db=db)
        assert again["status"] == "draft"
        assert len(db.onboarding) == 1

    def test_start_unknown_connector_type_400(self):
        from api.routes.hub import start_onboarding_route
        db = FakeDB(sources=["acme_api"])
        with pytest.raises(HTTPException) as e:
            start_onboarding_route(
                "acme_api", self._body(connector_type="FTP"), user=UPLOADER, db=db,
            )
        assert e.value.status_code == 400

    def test_start_unknown_source_404(self):
        from api.routes.hub import start_onboarding_route
        db = FakeDB(sources=[])  # source does not exist
        with pytest.raises(HTTPException) as e:
            start_onboarding_route(
                "ghost", self._body(), user=UPLOADER, db=db,
            )
        assert e.value.status_code == 404


# ── advance onboarding ───────────────────────────────────────────────────────

class TestAdvanceOnboarding:
    def _adv(self, to_status):
        from api.routes.hub import AdvanceOnboardingBody
        return AdvanceOnboardingBody(to_status=to_status)

    def _started_db(self):
        db = FakeDB(sources=["acme_api"])
        from api.routes.hub import start_onboarding_route, StartOnboardingBody
        start_onboarding_route("acme_api", StartOnboardingBody(), user=UPLOADER, db=db)
        return db

    def test_legal_advance(self):
        from api.routes.hub import advance_onboarding_route
        db = self._started_db()
        out = advance_onboarding_route(
            "acme_api", self._adv("test"), user=UPLOADER, db=db,
        )
        assert out["status"] == "test"

    def test_illegal_skip_400(self):
        from api.routes.hub import advance_onboarding_route
        db = self._started_db()
        with pytest.raises(HTTPException) as e:
            advance_onboarding_route(
                "acme_api", self._adv("prod"), user=UPLOADER, db=db,  # skips test+staged
            )
        assert e.value.status_code == 400

    def test_advance_not_started_404(self):
        from api.routes.hub import advance_onboarding_route
        db = FakeDB(sources=["acme_api"])
        with pytest.raises(HTTPException) as e:
            advance_onboarding_route(
                "acme_api", self._adv("test"), user=UPLOADER, db=db,
            )
        assert e.value.status_code == 404

    def test_bad_target_status_422_or_400(self):
        # Pydantic rejects an out-of-enum to_status before the handler runs.
        from api.routes.hub import AdvanceOnboardingBody
        with pytest.raises(Exception):
            AdvanceOnboardingBody(to_status="bogus")


# ── routes are actually mounted ──────────────────────────────────────────────

class TestRoutesMounted:
    def test_hub_routes_present(self):
        from api.app import create_app
        app = create_app()
        paths = {r.path for r in app.routes}
        assert "/hub/connector-types" in paths
        assert "/hub/onboarding/{source_id}" in paths
        assert "/hub/onboarding/{source_id}/advance" in paths
        # mounted at /api/v1 too
        assert "/api/v1/hub/connector-types" in paths

    def test_connector_types_requires_auth(self):
        from fastapi.testclient import TestClient
        from api.app import create_app
        client = TestClient(create_app())
        r = client.get("/hub/connector-types")
        # viewer role required → anonymous is 401 (route exists, not 404)
        assert r.status_code in (401, 403), r.text
