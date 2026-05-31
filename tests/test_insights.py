"""Z2 — tests for the Insight type + synthesis-test gate.

Riya's catch made this load-bearing: an insight without a traceable chain
back to dossier facts is the platform-credibility-killer. The type refuses
to construct without that chain. See specs/SPEC_Z2_insight_type.md.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from services.insights import (
    Insight,
    InsightContractError,
    FactCitation,
    StrategicFrame,
    synthesis_test,
    assert_insight,
    list_insights,
)

NOW = datetime(2026, 5, 30, tzinfo=timezone.utc)


def _citation(fact_id="f1", predicate="trial_result", contribution="REDEFINE 4 missed non-inferiority margin vs Zepbound") -> FactCitation:
    return FactCitation(fact_id=fact_id, predicate=predicate, contribution=contribution)


# ── Type invariants (pure, no DB) ─────────────────────────────────

class TestInsightInvariants:
    def test_refuses_to_construct_without_derived_from(self):
        with pytest.raises(InsightContractError):
            Insight(
                id="i1",
                statement="Lilly will defend at WAC",
                strategic_frame=StrategicFrame.RISK,
                derived_from=[],  # empty — refuse
                synthesis_test_passed=True,
                synthesis_test_rationale="defends current strategy",
                domain="competitive",
            )

    def test_refuses_empty_statement(self):
        with pytest.raises(InsightContractError):
            Insight(
                id="i1",
                statement="   ",
                strategic_frame=StrategicFrame.RISK,
                derived_from=[_citation()],
                synthesis_test_passed=True,
                synthesis_test_rationale="r",
                domain="competitive",
            )

    def test_refuses_empty_rationale(self):
        with pytest.raises(InsightContractError):
            Insight(
                id="i1",
                statement="ok",
                strategic_frame=StrategicFrame.RISK,
                derived_from=[_citation()],
                synthesis_test_passed=True,
                synthesis_test_rationale="",
                domain="competitive",
            )

    def test_refuses_citation_with_empty_contribution(self):
        with pytest.raises(InsightContractError):
            Insight(
                id="i1",
                statement="ok",
                strategic_frame=StrategicFrame.RISK,
                derived_from=[FactCitation(fact_id="f1", predicate="p", contribution="")],
                synthesis_test_passed=True,
                synthesis_test_rationale="r",
                domain="competitive",
            )

    def test_constructs_with_full_chain(self):
        i = Insight(
            id="i1",
            statement="CagriSema's REDEFINE 4 miss compresses its differentiation window",
            strategic_frame=StrategicFrame.RISK,
            derived_from=[_citation(), _citation(fact_id="f2", contribution="Lilly Q1 revenue +56%")],
            synthesis_test_passed=True,
            synthesis_test_rationale="changes pricing-strategy decision in the wargame",
            domain="competitive",
        )
        assert len(i.derived_from) == 2
        assert i.strategic_frame is StrategicFrame.RISK


# ── synthesis_test ────────────────────────────────────────────────

class TestSynthesisTest:
    def test_passes_when_chain_and_frame_present(self):
        result = synthesis_test({
            "statement": "CagriSema must price below Zepbound to capture Tier 2 access",
            "strategic_frame": "risk",
            "derived_from": [_citation()],
            "domain": "pricing_access",
        })
        assert result.passed is True
        assert result.rationale

    def test_rejects_when_no_derived_from(self):
        result = synthesis_test({
            "statement": "Some insight",
            "strategic_frame": "risk",
            "derived_from": [],
            "domain": "competitive",
        })
        assert result.passed is False
        assert "fact" in result.rationale.lower() or "derived" in result.rationale.lower()

    def test_rejects_when_no_frame(self):
        result = synthesis_test({
            "statement": "Some insight",
            "strategic_frame": "",
            "derived_from": [_citation()],
            "domain": "competitive",
        })
        assert result.passed is False

    def test_rejects_empty_statement(self):
        result = synthesis_test({
            "statement": "  ",
            "strategic_frame": "risk",
            "derived_from": [_citation()],
            "domain": "competitive",
        })
        assert result.passed is False


# ── assert_insight (DB path) ──────────────────────────────────────

def _db():
    db = MagicMock()
    db.execute = MagicMock()
    db.fetch_one = MagicMock(return_value={"id": "new-id"})
    db.fetch_all = MagicMock(return_value=[])
    return db


class TestAssertInsight:
    def test_writes_to_insights_when_synthesis_passes(self):
        db = _db()
        iid = assert_insight(
            db,
            statement="CagriSema's REDEFINE 4 miss compresses differentiation window",
            strategic_frame="risk",
            derived_from=[_citation()],
            domain="competitive",
            synthesis_test_rationale="changes wargame pricing-strategy decision",
        )
        assert iid
        # Inspect insert SQL
        insert_calls = [
            c for c in (db.fetch_one.call_args_list + db.execute.call_args_list)
            if c.args and "INSERT INTO insights" in c.args[0]
        ]
        assert len(insert_calls) >= 1, "must write to insights table on pass"

    def test_writes_to_rejected_insights_when_synthesis_fails(self):
        db = _db()
        iid = assert_insight(
            db,
            statement="Some insight",
            strategic_frame="risk",
            derived_from=[],  # no facts — will fail synthesis test
            domain="competitive",
            synthesis_test_rationale="(will be overridden by synthesis test)",
        )
        assert iid
        rejected_calls = [
            c for c in (db.fetch_one.call_args_list + db.execute.call_args_list)
            if c.args and "INSERT INTO rejected_insights" in c.args[0]
        ]
        assert len(rejected_calls) >= 1, "must write to rejected_insights on fail"


# ── list_insights ─────────────────────────────────────────────────

class TestListInsights:
    def test_filters_by_domain(self):
        rows = [{
            "id": "i1", "statement": "x", "strategic_frame": "risk",
            "derived_from": [{"fact_id": "f1", "predicate": "p", "contribution": "c"}],
            "synthesis_test_passed": True, "synthesis_test_rationale": "r",
            "domain": "competitive", "created_by": "intelligence_agent",
            "created_at": NOW,
        }]
        db = MagicMock()
        db.fetch_all.return_value = rows
        out = list_insights(db, domain="competitive")
        assert len(out) == 1
        assert out[0].domain == "competitive"

    def test_filters_by_frame(self):
        rows = [{
            "id": "i1", "statement": "x", "strategic_frame": "opportunity",
            "derived_from": [{"fact_id": "f1", "predicate": "p", "contribution": "c"}],
            "synthesis_test_passed": True, "synthesis_test_rationale": "r",
            "domain": "competitive", "created_by": "intelligence_agent",
            "created_at": NOW,
        }]
        db = MagicMock()
        db.fetch_all.return_value = rows
        out = list_insights(db, strategic_frame="opportunity")
        assert len(out) == 1
        assert out[0].strategic_frame is StrategicFrame.OPPORTUNITY
