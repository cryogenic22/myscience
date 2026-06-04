"""UX08 / L15 — update_bcb (in-app brief authoring) tests."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from services.business_context_brief import BCBContractError, update_bcb

NOW = datetime(2026, 6, 4, tzinfo=timezone.utc)


def _existing_row(signed=False):
    return {
        "id": "b1", "engagement_id": "e1", "focal_asset": "drug:semaglutide",
        "situation": "launch",
        "strategic_decisions": [{"statement": "old", "rationale": "old"}],
        "competitive_set": [], "success_criteria": [], "constraints": [],
        "created_by": "u", "created_at": NOW,
        "signed_off": signed,
        "signed_off_by": "reviewer" if signed else None,
        "signed_off_at": NOW if signed else None,
    }


def _db(existing):
    db = MagicMock()

    def fetch_one(sql, params=None):
        s = sql.lower()
        if "update business_context_briefs" in s:
            if not existing or existing.get("signed_off"):
                return None                       # WHERE signed_off=FALSE → 0 rows
            return {**_existing_row(),
                    "focal_asset": params["focal_asset"],
                    "situation": params["situation"],
                    "strategic_decisions": params["strategic_decisions"],
                    "competitive_set": params["competitive_set"],
                    "success_criteria": params["success_criteria"],
                    "constraints": params["constraints"]}
        if "from business_context_briefs" in s:
            return existing
        return None

    db.fetch_one.side_effect = fetch_one
    db.execute = MagicMock()
    return db


_DECISIONS = [{"statement": "Defend on CV outcomes", "rationale": "SELECT trial differentiates"}]


class TestUpdateBcb:
    def test_updates_content(self):
        db = _db(_existing_row())
        bcb = update_bcb(
            db, engagement_id="e1", focal_asset="drug:semaglutide",
            situation="defense", strategic_decisions=_DECISIONS, competitive_set=[],
        )
        assert bcb.situation == "defense"
        assert bcb.strategic_decisions[0].statement == "Defend on CV outcomes"

    def test_refuses_missing_brief(self):
        db = _db(None)
        with pytest.raises(BCBContractError, match="no brief to update"):
            update_bcb(db, engagement_id="e1", focal_asset="x", situation="launch",
                       strategic_decisions=_DECISIONS, competitive_set=[])

    def test_refuses_signed_brief(self):
        db = _db(_existing_row(signed=True))
        with pytest.raises(BCBContractError, match="signed-off"):
            update_bcb(db, engagement_id="e1", focal_asset="x", situation="launch",
                       strategic_decisions=_DECISIONS, competitive_set=[])

    def test_enforces_at_least_one_decision(self):
        db = _db(_existing_row())
        with pytest.raises(BCBContractError):
            update_bcb(db, engagement_id="e1", focal_asset="x", situation="launch",
                       strategic_decisions=[], competitive_set=[])


class TestRouteRegistered:
    def test_put_brief_on_the_wire(self):
        from api.app import create_app
        app = create_app()
        routes = [(getattr(r, "path", ""), getattr(r, "methods", set()) or set())
                  for r in app.routes]
        assert any(p == "/engagements/{eid}/brief" and "PUT" in m for p, m in routes)
