"""Z4 — tests for the Business Context Brief.

BCB is the ZS framework's most upstream commitment: an engagement starts
when the lead types a brief stating the situation, the competitive set, and
the specific decisions the wargame must inform. The type refuses to
construct without at least one strategic decision — the wargame has to
INFORM something. See specs/SPEC_Z4_business_context_brief.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from services.business_context_brief import (
    BusinessContextBrief,
    StrategicDecision,
    CompetitorThreat,
    BCBContractError,
    create_bcb,
    get_bcb_for_engagement,
    sign_off_bcb,
)

NOW = datetime(2026, 5, 30, tzinfo=timezone.utc)


def _decision(**over):
    base = {
        "statement": "Should Novo pre-launch CagriSema at WAC parity with Zepbound?",
        "rationale": "Pricing decision drives 5-year NPV by >$2B; needs defensible answer",
    }
    base.update(over)
    return StrategicDecision(**base)


def _threat(**over):
    base = {
        "entity_ref": "drug:zepbound",
        "threat_level": "primary",
        "note": "incumbent with 22.5% benchmark from SURMOUNT-1",
    }
    base.update(over)
    return CompetitorThreat(**base)


# ── Type invariants (no DB) ────────────────────────────────────────


class TestBCBInvariants:
    def test_refuses_to_construct_without_strategic_decisions(self):
        with pytest.raises(BCBContractError):
            BusinessContextBrief(
                id="b1", engagement_id="e1", focal_asset="drug:cagrisema",
                situation="launch",
                strategic_decisions=[],  # empty — refuse
                competitive_set=[_threat()],
                success_criteria=[], constraints=[],
                created_by="kapil", created_at=NOW,
            )

    def test_refuses_empty_focal_asset(self):
        with pytest.raises(BCBContractError):
            BusinessContextBrief(
                id="b1", engagement_id="e1", focal_asset="",
                situation="launch",
                strategic_decisions=[_decision()],
                competitive_set=[],
                success_criteria=[], constraints=[],
                created_by="kapil", created_at=NOW,
            )

    def test_constructs_with_full_set(self):
        b = BusinessContextBrief(
            id="b1", engagement_id="e1", focal_asset="drug:cagrisema",
            situation="launch",
            strategic_decisions=[_decision(), _decision(statement="What pricing?", rationale="r")],
            competitive_set=[_threat(), _threat(entity_ref="drug:wegovy_hd", threat_level="secondary")],
            success_criteria=["defensible 5-year NPV"],
            constraints=["no MFN reference in messaging"],
            created_by="kapil", created_at=NOW,
        )
        assert len(b.strategic_decisions) == 2
        assert b.signed_off is False


class TestStrategicDecisionInvariants:
    def test_requires_statement(self):
        with pytest.raises(BCBContractError):
            StrategicDecision(statement="  ", rationale="ok")

    def test_requires_rationale(self):
        with pytest.raises(BCBContractError):
            StrategicDecision(statement="ok", rationale="")


class TestCompetitorThreatInvariants:
    def test_invalid_threat_level_rejected(self):
        with pytest.raises(BCBContractError):
            CompetitorThreat(entity_ref="drug:x", threat_level="weird", note="n")

    def test_empty_entity_ref_rejected(self):
        with pytest.raises(BCBContractError):
            CompetitorThreat(entity_ref="", threat_level="primary", note="n")


# ── create_bcb / get_bcb / sign_off ────────────────────────────────


def _db(row=None):
    db = MagicMock()
    db.fetch_one = MagicMock(return_value=row or {"id": "new-bcb-id"})
    db.fetch_all = MagicMock(return_value=[])
    db.execute = MagicMock()
    return db


class TestCreateBCB:
    def test_creates_and_returns_id(self):
        db = _db()
        bid = create_bcb(
            db, engagement_id="e1",
            focal_asset="drug:cagrisema", situation="launch",
            strategic_decisions=[_decision()],
            competitive_set=[_threat()],
            created_by="kapil",
        )
        assert bid

    def test_persists_decisions_as_jsonb(self):
        db = _db()
        create_bcb(
            db, engagement_id="e1",
            focal_asset="drug:cagrisema", situation="launch",
            strategic_decisions=[_decision()],
            competitive_set=[_threat()],
            created_by="kapil",
        )
        # INSERT params should include a strategic_decisions string with
        # the statement text inside.
        call = db.fetch_one.call_args
        params = call.args[1]
        assert "Should Novo pre-launch" in params["strategic_decisions"]

    def test_requires_at_least_one_decision(self):
        with pytest.raises(BCBContractError):
            create_bcb(
                _db(), engagement_id="e1",
                focal_asset="drug:cagrisema", situation="launch",
                strategic_decisions=[],
                competitive_set=[],
                created_by="kapil",
            )


def _bcb_row(**over):
    base = {
        "id": "b1",
        "engagement_id": "e1",
        "focal_asset": "drug:cagrisema",
        "situation": "launch",
        "strategic_decisions": [
            {"statement": "Should Novo pre-launch?", "rationale": "drives NPV"},
        ],
        "competitive_set": [
            {"entity_ref": "drug:zepbound", "threat_level": "primary", "note": "incumbent"},
        ],
        "success_criteria": [],
        "constraints": [],
        "created_by": "kapil",
        "created_at": NOW,
        "signed_off": False,
        "signed_off_by": None,
        "signed_off_at": None,
    }
    base.update(over)
    return base


class TestGetBCBForEngagement:
    def test_returns_bcb_when_present(self):
        db = _db(row=_bcb_row())
        b = get_bcb_for_engagement(db, "e1")
        assert b is not None
        assert b.engagement_id == "e1"
        assert b.signed_off is False

    def test_returns_none_when_missing(self):
        db = _db()
        db.fetch_one.return_value = None
        assert get_bcb_for_engagement(db, "e1") is None


class TestSignOffBCB:
    def test_signs_off(self):
        db = _db(row=_bcb_row())
        b = sign_off_bcb(db, "b1", by="anika")
        assert b.signed_off is True
        assert b.signed_off_by == "anika"
        assert b.signed_off_at is not None

    def test_writes_engagement_audit_entry(self):
        db = _db(row=_bcb_row())
        sign_off_bcb(db, "b1", by="anika")
        # Look for an engagement_audit_log INSERT — sign-off is an event
        # the engagement should know about.
        audit_calls = [
            c for c in (db.execute.call_args_list + db.fetch_one.call_args_list)
            if c.args and "engagement_audit_log" in c.args[0]
        ]
        assert audit_calls, "sign-off must emit engagement audit entry"
