"""Tests for feedback loops — query patterns, resolution failures, quality tracking.

Three closed loops that connect user behaviour back to system improvement:
  1. Query Pattern Loop:       frequent intents → boost concept weights
  2. Resolution Failure Loop:  repeated misses → propose ontology aliases
  3. Quality Loop:             low-confidence patterns → flag for prompt fixes

Each loop is tested independently, then the orchestrator is tested as a unit.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock

from services.feedback_loops import (
    FeedbackAction,
    FeedbackLoopOrchestrator,
    QualityLoop,
    QueryPatternLoop,
    ResolutionFailureLoop,
)


# ── Helpers ──────────────────────────────────────────────────────────

def _mock_db(fetch_all_returns=None, fetch_one_returns=None):
    """Build a mock Database that returns canned query results."""
    db = MagicMock()
    db.fetch_all = MagicMock(return_value=fetch_all_returns or [])
    db.fetch_one = MagicMock(return_value=fetch_one_returns)
    db.execute = MagicMock()
    return db


# ═══════════════════════════════════════════════════════════════════════
# Test Query Pattern Loop
# ═══════════════════════════════════════════════════════════════════════

class TestQueryPatternLoop:

    def test_counts_queries_by_intent(self):
        """Aggregates query_telemetry rows by intent and returns counts."""
        db = _mock_db(fetch_all_returns=[
            {"intent": "landscape", "query_count": 25},
            {"intent": "dossier", "query_count": 15},
            {"intent": "compare", "query_count": 3},
        ])
        loop = QueryPatternLoop(db)
        actions = loop.analyze(since_days=7)

        # Should produce actions for intents above threshold (default 10)
        intent_actions = [a for a in actions if a.action_type == "adjust_weight"]
        assert len(intent_actions) >= 2  # landscape + dossier
        # compare has only 3, should not trigger
        compare_actions = [a for a in intent_actions if a.metadata.get("intent") == "compare"]
        assert len(compare_actions) == 0

    def test_adjusts_concept_weights(self):
        """High-frequency intents produce weight-adjustment actions."""
        db = _mock_db(fetch_all_returns=[
            {"intent": "landscape", "query_count": 50},
        ])
        loop = QueryPatternLoop(db)
        actions = loop.analyze(since_days=7)

        weight_actions = [a for a in actions if a.action_type == "adjust_weight"]
        assert len(weight_actions) >= 1
        action = weight_actions[0]
        assert action.loop == "query_pattern"
        assert action.metadata["intent"] == "landscape"
        assert action.metadata["query_count"] == 50
        # boost_factor should scale with query count
        assert action.metadata["boost_factor"] > 0

    def test_no_adjustment_below_threshold(self):
        """Intents with <10 queries produce no weight-adjustment actions."""
        db = _mock_db(fetch_all_returns=[
            {"intent": "portfolio", "query_count": 5},
            {"intent": "general", "query_count": 2},
        ])
        loop = QueryPatternLoop(db)
        actions = loop.analyze(since_days=7)

        weight_actions = [a for a in actions if a.action_type == "adjust_weight"]
        assert len(weight_actions) == 0


# ═══════════════════════════════════════════════════════════════════════
# Test Resolution Failure Loop
# ═══════════════════════════════════════════════════════════════════════

class TestResolutionFailureLoop:

    def test_clusters_failed_terms(self):
        """Groups unresolved entity names by normalised form."""
        db = _mock_db(fetch_all_returns=[
            {"failed_term": "ozempic", "failure_count": 12},
            {"failed_term": "Ozempic", "failure_count": 8},
            {"failed_term": "tirzepatide-xyz", "failure_count": 2},
        ])
        loop = ResolutionFailureLoop(db)
        actions = loop.analyze(since_days=7)

        # ozempic + Ozempic should cluster into a single alias proposal
        alias_actions = [a for a in actions if a.action_type == "propose_alias"]
        # "ozempic" cluster has 20 combined failures → should propose
        ozempic_proposals = [
            a for a in alias_actions
            if a.entity_name and "ozempic" in a.entity_name.lower()
        ]
        assert len(ozempic_proposals) >= 1

    def test_proposes_alias_for_frequent_failure(self):
        """5+ failures for the same term produce an alias proposal."""
        db = _mock_db(fetch_all_returns=[
            {"failed_term": "novo nordisk a/s", "failure_count": 7},
        ])
        loop = ResolutionFailureLoop(db)
        actions = loop.analyze(since_days=7)

        alias_actions = [a for a in actions if a.action_type == "propose_alias"]
        assert len(alias_actions) == 1
        action = alias_actions[0]
        assert action.loop == "resolution_failure"
        assert action.entity_name == "novo nordisk a/s"
        assert action.metadata["failure_count"] >= 5

    def test_no_proposal_for_rare_failures(self):
        """1-2 failures produce no alias proposal."""
        db = _mock_db(fetch_all_returns=[
            {"failed_term": "obscure-drug-xyz", "failure_count": 2},
            {"failed_term": "another-miss", "failure_count": 1},
        ])
        loop = ResolutionFailureLoop(db)
        actions = loop.analyze(since_days=7)

        alias_actions = [a for a in actions if a.action_type == "propose_alias"]
        assert len(alias_actions) == 0


# ═══════════════════════════════════════════════════════════════════════
# Test Quality Loop
# ═══════════════════════════════════════════════════════════════════════

class TestQualityLoop:

    def test_tracks_response_quality(self):
        """Stores confidence + user signal per query in analysis."""
        db = _mock_db(fetch_all_returns=[
            {
                "intent": "dossier",
                "avg_confidence": 0.35,
                "query_count": 20,
                "low_confidence_count": 15,
            },
            {
                "intent": "landscape",
                "avg_confidence": 0.72,
                "query_count": 30,
                "low_confidence_count": 3,
            },
        ])
        loop = QualityLoop(db)
        actions = loop.analyze(since_days=7)

        # Dossier with avg_confidence 0.35 should be flagged
        flagged = [a for a in actions if a.action_type == "flag_pattern"]
        assert len(flagged) >= 1
        dossier_flag = [a for a in flagged if a.metadata.get("intent") == "dossier"]
        assert len(dossier_flag) == 1

    def test_identifies_low_quality_patterns(self):
        """Queries with avg confidence < 0.5 are flagged."""
        db = _mock_db(fetch_all_returns=[
            {
                "intent": "pipeline",
                "avg_confidence": 0.3,
                "query_count": 15,
                "low_confidence_count": 12,
            },
        ])
        loop = QualityLoop(db)
        actions = loop.analyze(since_days=7)

        flagged = [a for a in actions if a.action_type == "flag_pattern"]
        assert len(flagged) == 1
        assert flagged[0].metadata["avg_confidence"] == 0.3
        assert flagged[0].metadata["query_count"] == 15

    def test_suggests_prompt_improvement(self):
        """Flagged patterns include a prompt improvement suggestion."""
        db = _mock_db(fetch_all_returns=[
            {
                "intent": "general",
                "avg_confidence": 0.25,
                "query_count": 40,
                "low_confidence_count": 35,
            },
        ])
        loop = QualityLoop(db)
        actions = loop.analyze(since_days=7)

        flagged = [a for a in actions if a.action_type == "flag_pattern"]
        assert len(flagged) == 1
        assert "suggestion" in flagged[0].metadata
        assert len(flagged[0].metadata["suggestion"]) > 10  # meaningful text


# ═══════════════════════════════════════════════════════════════════════
# Test Feedback Loop Orchestrator
# ═══════════════════════════════════════════════════════════════════════

class TestFeedbackLoopOrchestrator:

    def _make_orchestrator_db(self):
        """Build a mock DB that returns data for all three loops."""
        db = MagicMock()

        def _fetch_all(sql, params=None):
            sql_lower = sql.lower()
            if "intent" in sql_lower and "query_count" in sql_lower and "confidence" not in sql_lower:
                # QueryPatternLoop query
                return [
                    {"intent": "landscape", "query_count": 30},
                    {"intent": "dossier", "query_count": 15},
                ]
            elif "failed_term" in sql_lower:
                # ResolutionFailureLoop query
                return [
                    {"failed_term": "novo nordisk a/s", "failure_count": 8},
                ]
            elif "avg_confidence" in sql_lower or "confidence" in sql_lower:
                # QualityLoop query
                return [
                    {
                        "intent": "general",
                        "avg_confidence": 0.3,
                        "query_count": 25,
                        "low_confidence_count": 20,
                    },
                ]
            return []

        db.fetch_all = MagicMock(side_effect=_fetch_all)
        db.fetch_one = MagicMock(return_value=None)
        db.execute = MagicMock()
        return db

    def test_runs_all_loops(self):
        """Orchestrator calls all 3 loops and returns results."""
        db = self._make_orchestrator_db()
        orch = FeedbackLoopOrchestrator(db)
        result = orch.run(since_days=7)

        assert "actions" in result
        assert "summary" in result
        assert result["summary"]["loops_executed"] == 3

    def test_returns_combined_actions(self):
        """Actions from all loops are combined in the result."""
        db = self._make_orchestrator_db()
        orch = FeedbackLoopOrchestrator(db)
        result = orch.run(since_days=7)

        actions = result["actions"]
        loops_present = set(a["loop"] for a in actions)
        # All three loops should produce at least one action
        assert "query_pattern" in loops_present
        assert "resolution_failure" in loops_present
        assert "quality" in loops_present

    def test_dry_run_no_writes(self):
        """Preview mode does not call db.execute for writes."""
        db = self._make_orchestrator_db()
        orch = FeedbackLoopOrchestrator(db)
        result = orch.run(since_days=7, dry_run=True)

        assert result["dry_run"] is True
        # db.execute should NOT be called for persisting actions
        # (fetch_all is OK — it's read-only)
        for call in db.execute.call_args_list:
            sql = call[0][0].lower() if call[0] else ""
            assert "insert into feedback_loop_actions" not in sql
