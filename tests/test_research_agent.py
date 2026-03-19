"""Tests for AutonomousResearchAgent — autonomous knowledge gap filling.

TDD: These tests are written BEFORE the implementation.
Run with: pytest tests/test_research_agent.py -v

Inspired by karpathy/autoresearch: identify target -> plan -> execute -> evaluate -> keep/revert -> log.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ── Re-use MockDB from test_ctx_corpus ──
from tests.test_ctx_corpus import MockDB, MOCK_DRUGS, MOCK_COMPANIES, MOCK_TRIALS, MOCK_MECHANISMS


# ── Extended mock data for quality scoring ──

MOCK_ENTITY_QUALITY = [
    {
        "entity_id": "d001",
        "entity_type": "drug",
        "entity_name": "semaglutide",
        "quality_score": 7.5,
        "connection_count": 5,
        "enrichment_count": 0,
        "mechanism_name": "GLP-1 Receptor Agonists",
        "company_name": "Novo Nordisk",
        "trial_count": 3,
    },
    {
        "entity_id": "d002",
        "entity_type": "drug",
        "entity_name": "tirzepatide",
        "quality_score": 4.2,
        "connection_count": 3,
        "enrichment_count": 0,
        "mechanism_name": None,  # gap: missing mechanism
        "company_name": "Eli Lilly",
        "trial_count": 1,
    },
    {
        "entity_id": "d003",
        "entity_type": "drug",
        "entity_name": "dulaglutide",
        "quality_score": 3.0,
        "connection_count": 8,
        "enrichment_count": 0,
        "mechanism_name": None,
        "company_name": None,  # gap: missing company
        "trial_count": 0,  # gap: no trials
    },
    {
        "entity_id": "c001",
        "entity_type": "company",
        "entity_name": "Novo Nordisk",
        "quality_score": 8.5,
        "connection_count": 12,
        "enrichment_count": 1,
        "mechanism_name": None,
        "company_name": None,
        "trial_count": None,
    },
    {
        "entity_id": "d004",
        "entity_type": "drug",
        "entity_name": "already_enriched_drug",
        "quality_score": 5.0,
        "connection_count": 2,
        "enrichment_count": 3,  # already enriched 3 times
        "mechanism_name": "Some mechanism",
        "company_name": "Some company",
        "trial_count": 1,
    },
]


class MockQualityScorer:
    """Simple quality scorer that returns scores based on entity data completeness."""

    def score_entity(self, entity_data: dict) -> float:
        """Score based on how many key fields are filled."""
        score = 0.0
        if entity_data.get("mechanism_name"):
            score += 2.5
        if entity_data.get("company_name"):
            score += 2.5
        if entity_data.get("trial_count") and entity_data["trial_count"] > 0:
            score += 2.5
        if entity_data.get("entity_name"):
            score += 2.5
        return score

    def compute_fair_score(self, entity_data: dict) -> float:
        """Compute FAIR-like score (0-10) for entity."""
        return self.score_entity(entity_data)


@pytest.fixture
def mock_db():
    db = MockDB()
    db.set_results("drugs", MOCK_DRUGS)
    db.set_results("companies", MOCK_COMPANIES)
    db.set_results("clinical_trials", MOCK_TRIALS)
    db.set_results("mechanisms", MOCK_MECHANISMS)
    db.set_results("entity_quality", MOCK_ENTITY_QUALITY)
    return db


@pytest.fixture
def quality_scorer():
    return MockQualityScorer()


@pytest.fixture
def agent(mock_db, quality_scorer):
    from services.research_agent import AutonomousResearchAgent
    return AutonomousResearchAgent(
        db=mock_db,
        quality_scorer=quality_scorer,
        entity_data=MOCK_ENTITY_QUALITY,
        max_api_calls_per_iteration=5,
        max_enrichments_per_entity=3,
        quality_threshold=6.0,
    )


@pytest.fixture
def all_high_agent(mock_db, quality_scorer):
    """Agent where all entities are above the quality threshold."""
    from services.research_agent import AutonomousResearchAgent
    high_quality_data = [
        {
            "entity_id": "d001",
            "entity_type": "drug",
            "entity_name": "semaglutide",
            "quality_score": 9.0,
            "connection_count": 5,
            "enrichment_count": 0,
            "mechanism_name": "GLP-1 Receptor Agonists",
            "company_name": "Novo Nordisk",
            "trial_count": 3,
        },
    ]
    return AutonomousResearchAgent(
        db=mock_db,
        quality_scorer=quality_scorer,
        entity_data=high_quality_data,
        quality_threshold=6.0,
    )


# ── 1. TestTargetIdentification (5 tests) ──

class TestTargetIdentification:
    """Verify the agent can identify the best entity to enrich next."""

    def test_identifies_lowest_fair_entity(self, agent):
        """Returns entity with lowest quality score (weighted by connections)."""
        from services.research_agent import ResearchTarget
        target = agent.identify_target()
        assert target is not None
        assert isinstance(target, ResearchTarget)
        # d003 has lowest score (3.0) AND highest connections (8) => highest priority
        assert target.entity_id == "d003"
        assert target.quality_score == 3.0

    def test_skips_recently_enriched(self, agent):
        """Doesn't re-target entities enriched in the current cycle."""
        # Enrich d003 once via the agent's tracking
        agent._enrichment_history.add("d003")
        target = agent.identify_target()
        assert target is not None
        # Should skip d003 and pick d002 (next lowest score at 4.2)
        assert target.entity_id == "d002"

    def test_returns_none_when_all_above_threshold(self, all_high_agent):
        """No target if all entities score > threshold."""
        target = all_high_agent.identify_target()
        assert target is None

    def test_prioritizes_high_impact(self, agent):
        """Entities with more connections get priority when scores are close."""
        from services.research_agent import AutonomousResearchAgent
        # Create two entities with same low score but different connection counts
        data = [
            {
                "entity_id": "x1",
                "entity_type": "drug",
                "entity_name": "drug_a",
                "quality_score": 4.0,
                "connection_count": 2,
                "enrichment_count": 0,
                "mechanism_name": None,
                "company_name": None,
                "trial_count": 0,
            },
            {
                "entity_id": "x2",
                "entity_type": "drug",
                "entity_name": "drug_b",
                "quality_score": 4.0,
                "connection_count": 10,
                "enrichment_count": 0,
                "mechanism_name": None,
                "company_name": None,
                "trial_count": 0,
            },
        ]
        a = AutonomousResearchAgent(
            db=MagicMock(),
            quality_scorer=MockQualityScorer(),
            entity_data=data,
            quality_threshold=6.0,
        )
        target = a.identify_target()
        assert target is not None
        # x2 should be picked because more connections = higher impact
        assert target.entity_id == "x2"

    def test_respects_max_enrichments(self, agent):
        """Skip entities enriched 3+ times (max_enrichments_per_entity=3)."""
        target = agent.identify_target()
        # d004 has enrichment_count=3 and quality_score=5.0 (below threshold)
        # but should be skipped due to max enrichments
        assert target is not None
        assert target.entity_id != "d004"


# ── 2. TestEnrichmentPlanning (5 tests) ──

class TestEnrichmentPlanning:
    """Verify the agent generates correct enrichment plans based on gaps."""

    def test_plans_mechanism_gap(self, agent):
        """Missing mechanism => PubMed search plan."""
        from services.research_agent import ResearchTarget, EnrichmentPlan
        target = ResearchTarget(
            entity_id="d002",
            entity_type="drug",
            entity_name="tirzepatide",
            quality_score=4.2,
            connection_count=3,
            enrichment_count=0,
            gaps=["mechanism"],
        )
        plan = agent.plan_enrichment(target)
        assert isinstance(plan, EnrichmentPlan)
        action_types = [a["type"] for a in plan.actions]
        assert "pubmed_search" in action_types
        assert "tirzepatide" in plan.actions[0].get("query", "").lower() or \
               "tirzepatide" in str(plan.actions).lower()

    def test_plans_company_gap(self, agent):
        """Missing company => company enrichment plan."""
        from services.research_agent import ResearchTarget, EnrichmentPlan
        target = ResearchTarget(
            entity_id="d003",
            entity_type="drug",
            entity_name="dulaglutide",
            quality_score=3.0,
            connection_count=8,
            enrichment_count=0,
            gaps=["company"],
        )
        plan = agent.plan_enrichment(target)
        action_types = [a["type"] for a in plan.actions]
        assert "company_lookup" in action_types

    def test_plans_trial_gap(self, agent):
        """Few trials => ClinicalTrials.gov search plan."""
        from services.research_agent import ResearchTarget, EnrichmentPlan
        target = ResearchTarget(
            entity_id="d003",
            entity_type="drug",
            entity_name="dulaglutide",
            quality_score=3.0,
            connection_count=8,
            enrichment_count=0,
            gaps=["trials"],
        )
        plan = agent.plan_enrichment(target)
        action_types = [a["type"] for a in plan.actions]
        assert "clinical_trials_search" in action_types

    def test_plans_stale_data(self, agent):
        """Old data => re-fetch plan."""
        from services.research_agent import ResearchTarget, EnrichmentPlan
        target = ResearchTarget(
            entity_id="d001",
            entity_type="drug",
            entity_name="semaglutide",
            quality_score=5.5,
            connection_count=5,
            enrichment_count=0,
            gaps=["stale_data"],
        )
        plan = agent.plan_enrichment(target)
        action_types = [a["type"] for a in plan.actions]
        assert "refetch" in action_types

    def test_plan_has_api_budget(self, agent):
        """Plan respects max 5 API calls per iteration."""
        from services.research_agent import ResearchTarget
        target = ResearchTarget(
            entity_id="d003",
            entity_type="drug",
            entity_name="dulaglutide",
            quality_score=3.0,
            connection_count=8,
            enrichment_count=0,
            gaps=["mechanism", "company", "trials", "stale_data"],
        )
        plan = agent.plan_enrichment(target)
        assert plan.estimated_api_calls <= 5


# ── 3. TestEvaluation (5 tests) ──

class TestEvaluation:
    """Verify the agent correctly evaluates enrichment results."""

    def test_improvement_detected(self, agent):
        """FAIR +0.5 => improved=True."""
        from services.research_agent import ResearchTarget, EvalResult
        target = ResearchTarget(
            entity_id="d002",
            entity_type="drug",
            entity_name="tirzepatide",
            quality_score=4.2,
            connection_count=3,
            enrichment_count=0,
            gaps=["mechanism"],
        )
        enrichment_data = {"mechanism_name": "GLP-1 Receptor Agonists"}
        result = agent.evaluate(target, enrichment_data)
        assert isinstance(result, EvalResult)
        assert result.improved is True
        assert result.delta >= 0.5

    def test_regression_detected(self, agent):
        """FAIR goes down => improved=False."""
        from services.research_agent import ResearchTarget, EvalResult
        target = ResearchTarget(
            entity_id="d001",
            entity_type="drug",
            entity_name="semaglutide",
            quality_score=7.5,
            connection_count=5,
            enrichment_count=0,
            gaps=[],
        )
        # Enrichment that removes data (simulated by providing worse data)
        enrichment_data = {"_regression": True}
        result = agent.evaluate(target, enrichment_data)
        assert result.improved is False
        assert result.delta <= 0.0

    def test_no_change_detected(self, agent):
        """FAIR unchanged => improved=False (conservative)."""
        from services.research_agent import ResearchTarget, EvalResult
        target = ResearchTarget(
            entity_id="d001",
            entity_type="drug",
            entity_name="semaglutide",
            quality_score=7.5,
            connection_count=5,
            enrichment_count=0,
            gaps=[],
        )
        # Empty enrichment = no change
        enrichment_data = {}
        result = agent.evaluate(target, enrichment_data)
        assert result.improved is False
        assert result.delta == 0.0

    def test_false_link_detection(self, agent):
        """New link to wrong entity => detected and rejected."""
        from services.research_agent import ResearchTarget, EvalResult
        target = ResearchTarget(
            entity_id="d002",
            entity_type="drug",
            entity_name="tirzepatide",
            quality_score=4.2,
            connection_count=3,
            enrichment_count=0,
            gaps=["mechanism"],
        )
        # Enrichment with a false link
        enrichment_data = {"_false_links": [{"target": "wrong_entity", "type": "TREATS"}]}
        result = agent.evaluate(target, enrichment_data)
        assert result.false_links > 0

    def test_evaluation_returns_delta(self, agent):
        """Returns exact FAIR score change."""
        from services.research_agent import ResearchTarget, EvalResult
        target = ResearchTarget(
            entity_id="d002",
            entity_type="drug",
            entity_name="tirzepatide",
            quality_score=4.2,
            connection_count=3,
            enrichment_count=0,
            gaps=["mechanism"],
        )
        enrichment_data = {"mechanism_name": "GLP-1 Receptor Agonists"}
        result = agent.evaluate(target, enrichment_data)
        assert isinstance(result.delta, float)
        assert result.fair_before < result.fair_after
        assert abs(result.delta - (result.fair_after - result.fair_before)) < 0.001


# ── 4. TestResultsLogging (4 tests) ──

class TestResultsLogging:
    """Verify the agent correctly logs all iterations."""

    def test_logs_iteration(self, agent):
        """Every iteration logged with timestamp."""
        from services.research_agent import ResearchTarget, EvalResult
        target = ResearchTarget(
            entity_id="d002",
            entity_type="drug",
            entity_name="tirzepatide",
            quality_score=4.2,
            connection_count=3,
            enrichment_count=0,
            gaps=["mechanism"],
        )
        eval_result = EvalResult(
            improved=True,
            fair_before=4.2,
            fair_after=6.7,
            delta=2.5,
            false_links=0,
            details="Added mechanism link",
        )
        agent.log_iteration(target, "pubmed_search", eval_result)
        assert len(agent.iteration_log) == 1
        entry = agent.iteration_log[0]
        assert "timestamp" in entry

    def test_log_format(self, agent):
        """Log has target, action, delta, status columns."""
        from services.research_agent import ResearchTarget, EvalResult
        target = ResearchTarget(
            entity_id="d002",
            entity_type="drug",
            entity_name="tirzepatide",
            quality_score=4.2,
            connection_count=3,
            enrichment_count=0,
            gaps=["mechanism"],
        )
        eval_result = EvalResult(
            improved=True,
            fair_before=4.2,
            fair_after=6.7,
            delta=2.5,
            false_links=0,
            details="Added mechanism link",
        )
        agent.log_iteration(target, "pubmed_search", eval_result)
        entry = agent.iteration_log[0]
        assert "target" in entry
        assert "action" in entry
        assert "delta" in entry
        assert "status" in entry

    def test_log_persists(self, agent):
        """Results written to TSV file."""
        from services.research_agent import ResearchTarget, EvalResult
        target = ResearchTarget(
            entity_id="d002",
            entity_type="drug",
            entity_name="tirzepatide",
            quality_score=4.2,
            connection_count=3,
            enrichment_count=0,
            gaps=["mechanism"],
        )
        eval_result = EvalResult(
            improved=True,
            fair_before=4.2,
            fair_after=6.7,
            delta=2.5,
            false_links=0,
            details="Added mechanism link",
        )
        agent.log_iteration(target, "pubmed_search", eval_result)

        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = Path(tmpdir) / "research_log.tsv"
            agent.persist_log(str(log_path))
            assert log_path.exists()
            content = log_path.read_text()
            assert "tirzepatide" in content
            assert "pubmed_search" in content
            # TSV should have tab-separated columns
            lines = content.strip().split("\n")
            assert len(lines) >= 2  # header + at least 1 data row
            assert "\t" in lines[0]  # tab-separated

    def test_log_tracks_cumulative_stats(self, agent):
        """Running count of improvements/rejections."""
        from services.research_agent import ResearchTarget, EvalResult

        # Log an improvement
        target1 = ResearchTarget("d002", "drug", "tirzepatide", 4.2, 3, 0, ["mechanism"])
        agent.log_iteration(target1, "pubmed_search",
                            EvalResult(True, 4.2, 6.7, 2.5, 0, "Added mechanism"))
        # Log a rejection
        target2 = ResearchTarget("d003", "drug", "dulaglutide", 3.0, 8, 0, ["company"])
        agent.log_iteration(target2, "company_lookup",
                            EvalResult(False, 3.0, 2.8, -0.2, 0, "Bad enrichment"))

        stats = agent.get_cumulative_stats()
        assert stats["improvements"] == 1
        assert stats["rejections"] == 1
        assert stats["total_iterations"] == 2


# ── 5. TestLoopControl (5 tests) ──

class TestLoopControl:
    """Verify the autonomous loop respects its control parameters."""

    def test_loop_runs_n_iterations(self, agent):
        """Runs exactly max_iterations times (or fewer if no targets)."""
        from services.research_agent import LoopSummary
        summary = agent.run_loop(max_iterations=3)
        assert isinstance(summary, LoopSummary)
        assert summary.iterations <= 3

    def test_loop_stops_on_no_targets(self, all_high_agent):
        """Stops when identify_target returns None."""
        summary = all_high_agent.run_loop(max_iterations=10)
        assert summary.iterations == 0  # no targets found, stops immediately

    def test_loop_respects_api_budget(self, agent):
        """Total API calls across iterations bounded."""
        from services.research_agent import AutonomousResearchAgent
        # Create agent with very tight total budget
        a = AutonomousResearchAgent(
            db=agent.db,
            quality_scorer=agent.quality_scorer,
            entity_data=MOCK_ENTITY_QUALITY,
            max_api_calls_per_iteration=5,
            max_total_api_calls=8,
            quality_threshold=6.0,
        )
        summary = a.run_loop(max_iterations=10)
        assert summary.total_api_calls <= 8

    def test_loop_flags_for_hitl(self, agent):
        """Uncertain enrichments flagged for human review."""
        from services.research_agent import LoopSummary
        summary = agent.run_loop(max_iterations=3)
        assert isinstance(summary, LoopSummary)
        assert isinstance(summary.hitl_flagged, int)
        assert summary.hitl_flagged >= 0

    def test_loop_summary(self, agent):
        """Returns summary with total iterations, improvements, rejections."""
        summary = agent.run_loop(max_iterations=3)
        assert hasattr(summary, "iterations")
        assert hasattr(summary, "improvements")
        assert hasattr(summary, "rejections")
        assert hasattr(summary, "hitl_flagged")
        assert hasattr(summary, "total_api_calls")
        assert hasattr(summary, "mean_fair_delta")
        assert summary.iterations == summary.improvements + summary.rejections + summary.hitl_flagged


# ── 6. TestResearchProtocol (3 tests) ──

class TestResearchProtocol:
    """Verify the agent respects research protocol constraints."""

    def test_protocol_loaded(self, agent):
        """Agent loads research_protocol.md if present."""
        with tempfile.TemporaryDirectory() as tmpdir:
            protocol_path = Path(tmpdir) / "research_protocol.md"
            protocol_path.write_text("# Research Protocol\n- Max 1 entity per iteration\n- Never delete data\n")

            from services.research_agent import AutonomousResearchAgent
            a = AutonomousResearchAgent(
                db=agent.db,
                quality_scorer=agent.quality_scorer,
                entity_data=MOCK_ENTITY_QUALITY,
                protocol_path=str(protocol_path),
            )
            assert a.protocol is not None
            assert "Research Protocol" in a.protocol

    def test_protocol_constrains_behavior(self, agent):
        """Max 1 entity per iteration — loop processes one target per iteration."""
        summary = agent.run_loop(max_iterations=3)
        # Each iteration should process exactly 1 entity (or 0 if no targets)
        # The agent log should have at most max_iterations entries
        assert len(agent.iteration_log) <= 3

    def test_protocol_never_deletes(self, agent):
        """Agent only adds/updates, never removes data."""
        from services.research_agent import ResearchTarget, EnrichmentPlan
        target = ResearchTarget(
            entity_id="d002",
            entity_type="drug",
            entity_name="tirzepatide",
            quality_score=4.2,
            connection_count=3,
            enrichment_count=0,
            gaps=["mechanism"],
        )
        plan = agent.plan_enrichment(target)
        # No action should have type "delete" or "remove"
        for action in plan.actions:
            assert action["type"] not in ("delete", "remove", "drop", "truncate")
        # commit_or_revert should never delete data
        enrichment_data = agent.execute_enrichment(plan)
        eval_result = agent.evaluate(target, enrichment_data)
        committed = agent.commit_or_revert(eval_result)
        # Even on revert, the agent should not delete existing data
        assert agent._deleted_count == 0
