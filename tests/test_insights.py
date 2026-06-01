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


# ── Engagement-scoped synthesis derivation (UX06 / PB-UX06) ────────

from services.insights import (
    derive_synthesis_insights,
    assemble_and_persist_insights,
    list_engagement_synthesis,
)
from services.dossier_kb import DossierSnapshot, build_domains


def _snapshot_with(facts=None, signals=None, related=None, focal="drug:semaglutide"):
    domains, cov, cnt = build_domains(facts or [], signals, None, related)
    return DossierSnapshot(
        engagement_id="e1", focal_asset=focal, domains=domains,
        coverage_score=cov, fact_count=cnt, id="snap1",
    )


class TestDeriveSynthesisInsights:
    def test_competitive_insight_is_grounded_and_framed(self):
        related = [{"id": "d2", "type": "drug", "name": "tirzepatide",
                    "relation": "COMPETES_WITH", "edge_count": 4}]
        cands = derive_synthesis_insights(_snapshot_with(related=related))
        comp = next(c for c in cands if c["domain"] == "competitive")
        assert comp["strategic_frame"] == "risk"
        # grounded: cites the real competitive fact, with a contribution line.
        assert comp["derived_from"] and comp["derived_from"][0]["fact_id"] == "d2"
        assert comp["derived_from"][0]["contribution"]
        assert "semaglutide" in comp["statement"]   # focal asset woven in

    def test_every_candidate_passes_the_synthesis_gate(self):
        related = [{"id": "d2", "type": "drug", "name": "tirzepatide",
                    "relation": "COMPETES_WITH", "edge_count": 4}]
        signals = [{"signal_id": "s1", "headline": "Novo cuts WAC 5%",
                    "kbq_tag": "pricing_access", "ts": None}]
        cands = derive_synthesis_insights(_snapshot_with(signals=signals, related=related))
        assert cands, "should derive at least one candidate"
        for c in cands:
            assert synthesis_test(c).passed, f"candidate must pass the gate: {c['statement']}"

    def test_signal_fact_bumps_frame_to_trigger(self):
        signals = [{"signal_id": "s1", "headline": "Novo cuts WAC 5%",
                    "kbq_tag": "pricing_access", "ts": None}]
        cands = derive_synthesis_insights(_snapshot_with(signals=signals))
        pa = next(c for c in cands if c["domain"] == "pricing_and_access")
        assert pa["strategic_frame"] == "trigger"   # signal overrides the domain default

    def test_empty_dossier_yields_no_candidates(self):
        assert derive_synthesis_insights(_snapshot_with()) == []


class TestAssembleAndListSynthesis:
    def test_assemble_archives_persists_and_lists_camelcase(self):
        related = [{"id": "d2", "type": "drug", "name": "tirzepatide",
                    "relation": "COMPETES_WITH", "edge_count": 4}]
        snap = _snapshot_with(related=related)

        db = MagicMock()
        db.execute = MagicMock()
        db.fetch_one = MagicMock(return_value={"id": "new-id"})
        # list step returns one persisted insight row.
        insight_rows = [{
            "id": "i1", "statement": "Competitive exposure: semaglutide …",
            "strategic_frame": "risk",
            "derived_from": [{"fact_id": "d2", "predicate": "competes_with", "contribution": "rival"}],
            "synthesis_test_passed": True, "synthesis_test_rationale": "grounded",
            "domain": "competitive", "created_by": "u1", "created_at": NOW,
        }]
        db.fetch_all = MagicMock(side_effect=[insight_rows, []])

        import services.dossier_kb as dk
        orig = dk.get_latest_snapshot
        dk.get_latest_snapshot = lambda _db, _eid: snap
        try:
            out = assemble_and_persist_insights(db, "e1", created_by="u1")
        finally:
            dk.get_latest_snapshot = orig

        # archived prior batch (UPDATE … is_archived) before inserting.
        assert any("is_archived = TRUE" in c.args[0] for c in db.execute.call_args_list)
        # persisted via the insights insert (engagement-scoped).
        assert any("INSERT INTO insights" in c.args[0] for c in db.fetch_one.call_args_list)
        # serialized to the frontend shape.
        assert out["count"] == 1 and out["passRate"] == 100
        ins = out["insights"][0]
        assert ins["strategicFrame"] == "risk"
        assert ins["derivedFrom"][0]["factId"] == "d2"

    def test_list_pass_rate_blends_insights_and_rejected(self):
        db = MagicMock()
        db.fetch_all = MagicMock(side_effect=[
            [{"id": "i1", "statement": "x", "strategic_frame": "risk",
              "derived_from": [{"fact_id": "f1", "predicate": "p", "contribution": "c"}],
              "synthesis_test_passed": True, "synthesis_test_rationale": "r",
              "domain": "competitive", "created_by": "u", "created_at": NOW}],
            [{"id": "r1", "candidate_statement": "weak", "rejection_reason": "no facts",
              "derived_from": []}],
        ])
        out = list_engagement_synthesis(db, "e1")
        assert out["count"] == 1
        assert out["passRate"] == 50    # 1 insight / (1 insight + 1 rejected)
        assert out["rejectedInsights"][0]["candidateStatement"] == "weak"
