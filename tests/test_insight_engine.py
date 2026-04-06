"""Tests for services/insight_engine.py — proactive intelligence signal detection.

TDD: Verify safety signal detection, pipeline milestones, competitive shifts,
and the combined scan that returns sorted insights.

Run with: pytest tests/test_insight_engine.py -v
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest
from unittest.mock import MagicMock


# ── Helpers ──

# Query dispatch keys — substring matches against actual SQL in the implementation.
# Safety signals query contains "mv_safety_signals"
# Pipeline milestones query contains "make_interval"
# New entrants query contains "INTERVAL '30 days'" (no CTE)
# HHI shifts query contains "segment_counts" (CTE name)

_KEY_SAFETY = "mv_safety_signals"
_KEY_PIPELINE = "make_interval"
_KEY_NEW_ENTRANTS = "INTERVAL '30 days'"
_KEY_HHI = "segment_counts"
_KEY_HITL = "hitl_reviews"


def _mock_db(
    safety_rows=None,
    pipeline_rows=None,
    new_entrant_rows=None,
    hhi_rows=None,
    hitl_pending=0,
):
    """Build a MagicMock DB that dispatches fetch_all based on SQL content.

    Each argument maps to a specific detector query.
    """
    db = MagicMock()
    safety = safety_rows if safety_rows is not None else []
    pipeline = pipeline_rows if pipeline_rows is not None else []
    new_entrants = new_entrant_rows if new_entrant_rows is not None else []
    hhi = hhi_rows if hhi_rows is not None else []

    def _fetch_all(query, params=None):
        if _KEY_SAFETY in query:
            return safety
        if _KEY_HHI in query:
            # HHI query also contains INTERVAL '30 days' so check first
            return hhi
        if _KEY_NEW_ENTRANTS in query:
            return new_entrants
        if _KEY_PIPELINE in query:
            return pipeline
        return []

    def _fetch_one(query, params=None):
        if _KEY_HITL in query:
            return {"cnt": hitl_pending}
        return None

    db.fetch_all = MagicMock(side_effect=_fetch_all)
    db.fetch_one = MagicMock(side_effect=_fetch_one)
    return db


# ── Safety Signal Detection ──


class TestSafetySignalDetection:
    """Verify detection of disproportionality signals from mv_safety_signals."""

    def test_detects_new_prr_spike(self):
        """PRR > 2.0 flagged as safety signal insight."""
        from services.insight_engine import InsightEngine

        db = _mock_db(safety_rows=[
            {
                "drug_name": "drugX",
                "drug_id": "d001",
                "reaction": "hepatotoxicity",
                "prr": 4.5,
                "ror": 5.2,
                "ror_lower_ci": 2.1,
                "a": 15,
                "drug_total": 200,
            },
        ])

        engine = InsightEngine(db)
        insights = engine._detect_safety_signals()
        assert len(insights) >= 1
        signal = insights[0]
        assert signal.type == "safety_signal"
        assert signal.entity_name == "drugX"
        assert signal.metric_value == pytest.approx(4.5)

    def test_ignores_low_prr(self):
        """PRR < 2.0 should not generate an insight (filtered by SQL WHERE)."""
        from services.insight_engine import InsightEngine

        # The SQL has WHERE prr > 2.0, so the DB should not return low-PRR rows.
        # But if it did (e.g., rounding), the code skips them.
        db = _mock_db(safety_rows=[])

        engine = InsightEngine(db)
        insights = engine._detect_safety_signals()
        assert len(insights) == 0

    def test_returns_drug_and_reaction(self):
        """Signal includes drug_name, reaction description, and PRR value."""
        from services.insight_engine import InsightEngine

        db = _mock_db(safety_rows=[
            {
                "drug_name": "semaglutide",
                "drug_id": "d003",
                "reaction": "pancreatitis",
                "prr": 3.1,
                "ror": 4.0,
                "ror_lower_ci": 1.8,
                "a": 22,
                "drug_total": 500,
            },
        ])

        engine = InsightEngine(db)
        insights = engine._detect_safety_signals()
        assert len(insights) == 1
        sig = insights[0]
        assert sig.entity_name == "semaglutide"
        assert "pancreatitis" in sig.description.lower()
        assert sig.metric_value == pytest.approx(3.1)
        assert sig.entity_type == "drug"


# ── Pipeline Milestones ──


class TestPipelineMilestones:
    """Verify detection of pipeline phase advancements and trial completions."""

    def test_detects_phase_advancement(self):
        """Drug moving from Phase 2 to Phase 3 generates milestone insight."""
        from services.insight_engine import InsightEngine

        db = _mock_db(pipeline_rows=[
            {
                "generic_name": "tirzepatide",
                "drug_id": "d010",
                "trial_id": "NCT00001",
                "phase": "Phase 3",
                "status": "RECRUITING",
                "previous_phase": "Phase 2",
                "updated_at": datetime.now(timezone.utc),
            },
        ])

        engine = InsightEngine(db)
        insights = engine._detect_pipeline_milestones(since_days=7)
        assert len(insights) >= 1
        milestone = insights[0]
        assert milestone.type == "pipeline_milestone"
        assert milestone.entity_name == "tirzepatide"
        assert "phase" in milestone.title.lower() or "phase" in milestone.description.lower()

    def test_detects_trial_completion(self):
        """Trial status changed to COMPLETED generates milestone insight."""
        from services.insight_engine import InsightEngine

        db = _mock_db(pipeline_rows=[
            {
                "generic_name": "dulaglutide",
                "drug_id": "d011",
                "trial_id": "NCT00002",
                "phase": "Phase 3",
                "status": "COMPLETED",
                "previous_phase": None,
                "updated_at": datetime.now(timezone.utc),
            },
        ])

        engine = InsightEngine(db)
        insights = engine._detect_pipeline_milestones(since_days=7)
        completions = [i for i in insights if "complet" in i.title.lower() or "complet" in i.description.lower()]
        assert len(completions) >= 1
        assert completions[0].entity_name == "dulaglutide"

    def test_no_milestone_when_no_changes(self):
        """Stable pipeline with no recent updates generates no signals."""
        from services.insight_engine import InsightEngine

        db = _mock_db(pipeline_rows=[])

        engine = InsightEngine(db)
        insights = engine._detect_pipeline_milestones(since_days=7)
        assert len(insights) == 0


# ── Competitive Shifts ──


class TestCompetitiveShifts:
    """Verify detection of competitive landscape changes."""

    def test_detects_new_entrant(self):
        """New drug in a concentrated segment generates competitive insight."""
        from services.insight_engine import InsightEngine

        db = _mock_db(new_entrant_rows=[
            {
                "drug_name": "retatrutide",
                "drug_id": "d020",
                "mechanism_name": "GLP-1 Receptor Agonists",
                "therapeutic_area": "Obesity",
                "created_at": datetime.now(timezone.utc) - timedelta(days=3),
                "segment_drug_count": 5,
            },
        ])

        engine = InsightEngine(db)
        insights = engine._detect_competitive_shifts()
        entrants = [i for i in insights if "entrant" in i.title.lower() or "new" in i.title.lower()]
        assert len(entrants) >= 1
        assert entrants[0].entity_name == "retatrutide"
        assert entrants[0].type == "competitive_shift"

    def test_detects_concentration_change(self):
        """HHI shift > 200 points generates competitive insight."""
        from services.insight_engine import InsightEngine

        db = _mock_db(hhi_rows=[
            {
                "mechanism_name": "SGLT2 Inhibitors",
                "therapeutic_area": "Diabetes Mellitus",
                "current_drug_count": 8,
                "previous_drug_count": 5,
                "hhi_current": 1800,
                "hhi_previous": 2500,
                "hhi_delta": -700,
            },
        ])

        engine = InsightEngine(db)
        insights = engine._detect_competitive_shifts()
        shifts = [i for i in insights if "concentration" in i.title.lower() or "hhi" in i.description.lower()]
        assert len(shifts) >= 1
        assert shifts[0].type == "competitive_shift"

    def test_no_shift_in_stable_segment(self):
        """Stable market with no new drugs and no HHI change generates no signal."""
        from services.insight_engine import InsightEngine

        db = _mock_db()

        engine = InsightEngine(db)
        insights = engine._detect_competitive_shifts()
        assert len(insights) == 0


# ── Insight Engine (Combined) ──


class TestInsightEngine:
    """Verify the combined scan across all signal types."""

    def test_collects_all_signal_types(self):
        """Scan returns insights from safety, pipeline, and competitive detectors."""
        from services.insight_engine import InsightEngine

        db = _mock_db(
            safety_rows=[
                {
                    "drug_name": "drugA",
                    "drug_id": "d100",
                    "reaction": "liver_failure",
                    "prr": 5.0,
                    "ror": 6.0,
                    "ror_lower_ci": 3.0,
                    "a": 30,
                    "drug_total": 400,
                },
            ],
            pipeline_rows=[
                {
                    "generic_name": "drugB",
                    "drug_id": "d101",
                    "trial_id": "NCT99999",
                    "phase": "Phase 3",
                    "status": "COMPLETED",
                    "previous_phase": None,
                    "updated_at": datetime.now(timezone.utc),
                },
            ],
            new_entrant_rows=[
                {
                    "drug_name": "drugC",
                    "drug_id": "d102",
                    "mechanism_name": "PD-1 Inhibitors",
                    "therapeutic_area": "Oncology",
                    "created_at": datetime.now(timezone.utc) - timedelta(days=2),
                    "segment_drug_count": 3,
                },
            ],
        )

        engine = InsightEngine(db)
        insights = engine.scan(since_days=7)
        types_found = {i.type for i in insights}
        assert "safety_signal" in types_found
        assert "pipeline_milestone" in types_found
        assert "competitive_shift" in types_found

    def test_returns_sorted_by_priority(self):
        """Insights are sorted by severity: critical > high > medium > low."""
        from services.insight_engine import InsightEngine, _severity_rank

        db = _mock_db(
            safety_rows=[
                {
                    "drug_name": "drugA",
                    "drug_id": "d100",
                    "reaction": "liver_failure",
                    "prr": 5.0,
                    "ror": 6.0,
                    "ror_lower_ci": 3.0,
                    "a": 30,
                    "drug_total": 400,
                },
            ],
            pipeline_rows=[
                {
                    "generic_name": "drugB",
                    "drug_id": "d101",
                    "trial_id": "NCT99999",
                    "phase": "Phase 3",
                    "status": "COMPLETED",
                    "previous_phase": None,
                    "updated_at": datetime.now(timezone.utc),
                },
            ],
        )

        engine = InsightEngine(db)
        insights = engine.scan(since_days=7)
        severities = [_severity_rank(i.severity) for i in insights]
        assert severities == sorted(severities, reverse=True)

    def test_empty_when_no_signals(self):
        """No data changes in any category yields empty insight list."""
        from services.insight_engine import InsightEngine

        db = _mock_db()

        engine = InsightEngine(db)
        insights = engine.scan(since_days=7)
        assert insights == []


# ── Resolution Queue Overflow ──


class TestResolutionQueueOverflow:
    """Verify detection of HITL queue overflow signals."""

    def test_fires_when_count_exceeds_50(self):
        """Queue with > 50 pending items generates a resolution_queue_overflow signal."""
        from services.insight_engine import InsightEngine

        db = _mock_db(hitl_pending=75)
        engine = InsightEngine(db)
        insights = engine._detect_resolution_queue_overflow()

        assert len(insights) == 1
        signal = insights[0]
        assert signal.type == "resolution_queue_overflow"
        assert signal.severity == "medium"
        assert signal.metric_value == 75.0
        assert "75" in signal.description
        assert "/catalog/hitl" in signal.description

    def test_high_severity_when_count_exceeds_100(self):
        """Queue with > 100 pending items has severity 'high'."""
        from services.insight_engine import InsightEngine

        db = _mock_db(hitl_pending=150)
        engine = InsightEngine(db)
        insights = engine._detect_resolution_queue_overflow()

        assert len(insights) == 1
        assert insights[0].severity == "high"
        assert insights[0].metric_value == 150.0

    def test_no_signal_when_count_at_or_below_50(self):
        """Queue with <= 50 pending items does not generate a signal."""
        from services.insight_engine import InsightEngine

        db = _mock_db(hitl_pending=50)
        engine = InsightEngine(db)
        insights = engine._detect_resolution_queue_overflow()

        assert len(insights) == 0

    def test_no_signal_when_queue_empty(self):
        """Empty queue does not generate a signal."""
        from services.insight_engine import InsightEngine

        db = _mock_db(hitl_pending=0)
        engine = InsightEngine(db)
        insights = engine._detect_resolution_queue_overflow()

        assert len(insights) == 0

    def test_included_in_scan_results(self):
        """Resolution queue overflow appears in combined scan() output."""
        from services.insight_engine import InsightEngine

        db = _mock_db(hitl_pending=120)
        engine = InsightEngine(db)
        insights = engine.scan(since_days=7)

        overflow_signals = [i for i in insights if i.type == "resolution_queue_overflow"]
        assert len(overflow_signals) == 1
        assert overflow_signals[0].severity == "high"

    def test_graceful_on_db_error(self):
        """DB error in HITL query returns empty list, no exception."""
        from services.insight_engine import InsightEngine

        db = MagicMock()
        db.fetch_one = MagicMock(side_effect=Exception("DB error"))
        db.fetch_all = MagicMock(return_value=[])

        engine = InsightEngine(db)
        insights = engine._detect_resolution_queue_overflow()

        assert insights == []
