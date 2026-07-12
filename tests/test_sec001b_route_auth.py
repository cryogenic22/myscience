"""SEC-001b — mutation/job routes on catalog/steward/enrichment require a role.

Red-team 2026-07-10 (COORDINATION §9.4 item 3): these POST/PUT/PATCH/DELETE
routes carried only ``Depends(get_db)`` — anonymously reachable, so any caller
could trigger enrichment/curation pipelines, bulk-mutate entities, or resolve
HITL reviews. Reads stay public; mutations now require at least the listed role.

Pattern mirrors the existing precedent (connectors.py / decision_briefs.py):
``require_role`` resolves the caller via ``get_current_user`` (Bearer JWT). Here
we override ``get_current_user`` to inject a role directly — DB-free.

RED (routes ungated): anonymous POST reaches the handler (200/500), not 401.
"""
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from api.deps import get_current_user, get_db

# (method, path, min_role) — the mutation surface being gated.
ENTERPRISE_MUTATIONS = [
    ("post", "/enrichment/run"),
    ("post", "/enrichment/research"),
    ("post", "/enrichment/derive-competition"),
    ("post", "/enrichment/refresh-source/fda_orange_book"),
    ("post", "/enrichment/curate"),
]


@pytest.fixture
def app():
    a = create_app()
    # DB-free: get_current_user -> get_db, which raises on a missing local DB and
    # would surface as 500 (masking the 401). A stub keeps the auth gate the only
    # thing under test. Anonymous short-circuits before any db use.
    a.dependency_overrides[get_db] = lambda: MagicMock()
    return a


@pytest.fixture
def client(app):
    # don't raise handler 500s — for the enterprise case we only assert the gate
    # was passed (status not 401/403), the handler may then fail on no-DB.
    return TestClient(app, raise_server_exceptions=False)


def _act_as(app, role):
    if role is None:
        app.dependency_overrides.pop(get_current_user, None)
    else:
        app.dependency_overrides[get_current_user] = lambda: {
            "id": "u1", "email": "e@x.io", "role": role, "is_active": True,
        }


@pytest.mark.parametrize("method,path", ENTERPRISE_MUTATIONS)
def test_mutation_anonymous_is_401(app, client, method, path):
    _act_as(app, None)
    r = getattr(client, method)(path)
    assert r.status_code == 401, f"{path} reachable anonymously ({r.status_code})"


@pytest.mark.parametrize("method,path", ENTERPRISE_MUTATIONS)
def test_mutation_viewer_is_403(app, client, method, path):
    _act_as(app, "viewer")
    r = getattr(client, method)(path)
    assert r.status_code == 403, f"{path} allowed a viewer ({r.status_code})"


def test_require_role_gate_logic_accepts_enterprise():
    """Unit-test the gate directly (no handler, no DB): the positive path.

    Proves the gate is not a blanket always-deny — an enterprise caller is
    admitted, a viewer is 403, and anonymous is 401. (Invoking the real routes
    for the accept case would execute the enrichment pipeline, so assert the
    dependency logic instead.)
    """
    from fastapi import HTTPException

    from api.deps import require_role

    dep = require_role("enterprise")
    assert dep(user={"id": "u", "role": "enterprise", "is_active": True})["role"] == "enterprise"
    with pytest.raises(HTTPException) as viewer:
        dep(user={"id": "u", "role": "viewer", "is_active": True})
    assert viewer.value.status_code == 403
    with pytest.raises(HTTPException) as anon:
        dep(user=None)
    assert anon.value.status_code == 401
