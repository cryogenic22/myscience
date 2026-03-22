"""Tests for services/data_steward.py — autonomous curation loop.

TDD: Verify action selection, execution, feedback resolution, loop control.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from unittest.mock import MagicMock, patch

from services.steward_signals import StewardSignal


def _make_signal(
    source="query_telemetry",
    source_id="qt-1",
    gap_type="missing_entity",
    entity_type=None,
    entity_id=None,
    entity_name=None,
    priority_score=0.8,
    details=None,
) -> StewardSignal:
    return StewardSignal(
        source=source,
        source_id=source_id,
        entity_type=entity_type,
        entity_id=entity_id,
        entity_name=entity_name,
        gap_type=gap_type,
        priority_score=priority_score,
        details=details or {},
        created_at=datetime.now(timezone.utc),
    )


# ── Action Selection ──


class TestActionSelection:
    """Verify signal → action mapping."""

    def test_low_completeness_mechanism_maps_to_backfill(self):
        from services.data_steward import DataSteward, StewardConfig
        db = MagicMock()
        collector = MagicMock()
        steward = DataSteward(db, collector)

        signal = _make_signal(gap_type="low_completeness", entity_type="mechanism")
        action_type, mod, func = steward._select_action(signal)
        assert action_type == "backfill_mechanisms"
        assert "backfill_mechanisms" in mod

    def test_data_quality_maps_to_clean(self):
        from services.data_steward import DataSteward
        db = MagicMock()
        steward = DataSteward(db, MagicMock())

        signal = _make_signal(gap_type="data_quality")
        action_type, mod, func = steward._select_action(signal)
        assert action_type == "clean_drugs"

    def test_missing_entity_maps_to_enrich(self):
        from services.data_steward import DataSteward
        db = MagicMock()
        steward = DataSteward(db, MagicMock())

        signal = _make_signal(gap_type="missing_entity")
        action_type, mod, func = steward._select_action(signal)
        assert action_type == "enrich_drugs"

    def test_unknown_gap_falls_back_to_enrich(self):
        from services.data_steward import DataSteward, StewardConfig
        db = MagicMock()
        steward = DataSteward(db, MagicMock(), StewardConfig(skip_ai=True))

        signal = _make_signal(gap_type="completely_unknown")
        action_type, _, _ = steward._select_action(signal)
        assert action_type == "enrich_drugs"

    def test_unknown_gap_falls_to_ai_when_allowed(self):
        from services.data_steward import DataSteward, StewardConfig
        db = MagicMock()
        steward = DataSteward(db, MagicMock(), StewardConfig(skip_ai=False))

        signal = _make_signal(gap_type="completely_unknown")
        action_type, _, _ = steward._select_action(signal)
        assert action_type == "ai_enrich"

    def test_stale_data_maps_to_refetch(self):
        from services.data_steward import DataSteward
        db = MagicMock()
        steward = DataSteward(db, MagicMock())

        signal = _make_signal(gap_type="stale_data")
        action_type, mod, func = steward._select_action(signal)
        assert action_type == "refetch"


# ── Execution ──


class TestStewardExecution:
    """Verify action execution and recording."""

    def test_dry_run_no_writes(self):
        from services.data_steward import DataSteward, StewardConfig
        db = MagicMock()
        collector = MagicMock()
        collector.collect_signals.return_value = [_make_signal()]

        steward = DataSteward(db, collector, StewardConfig(dry_run=True))
        summary = steward.run_loop()
        assert summary.iterations == 1
        assert summary.skipped == 1
        assert summary.completed == 0

    def test_records_action_to_db(self):
        from services.data_steward import DataSteward
        db = MagicMock()
        db.fetch_one.return_value = {"id": "action-1", "acquired": True}

        steward = DataSteward(db, MagicMock())
        signal = _make_signal()
        action_id = steward._record_action(signal, "enrich_drugs", "running")
        assert action_id == "action-1"
        # Verify INSERT was called
        insert_calls = [c for c in db.fetch_one.call_args_list
                        if "INSERT INTO steward_actions" in str(c)]
        assert len(insert_calls) >= 1

    @patch("services.data_steward.DataSteward._execute_action")
    def test_processes_signal_and_records(self, mock_exec):
        from services.data_steward import DataSteward, StewardConfig
        mock_exec.return_value = {"status": "ok"}

        db = MagicMock()
        db.fetch_one.return_value = {"id": "action-1", "acquired": True}
        collector = MagicMock()
        collector.collect_signals.return_value = [
            _make_signal(gap_type="data_quality"),
        ]

        steward = DataSteward(db, collector, StewardConfig(max_iterations=1))
        summary = steward.run_loop()
        assert summary.iterations == 1
        assert summary.completed == 1

    def test_handles_execution_failure(self):
        from services.data_steward import DataSteward, StewardConfig
        db = MagicMock()
        db.fetch_one.return_value = {"id": "action-1", "acquired": True}
        collector = MagicMock()
        collector.collect_signals.return_value = [
            _make_signal(gap_type="missing_entity"),
        ]

        # Patch _execute_action to raise
        steward = DataSteward(db, collector, StewardConfig(max_iterations=1))
        steward._execute_action = MagicMock(side_effect=RuntimeError("script failed"))

        summary = steward.run_loop()
        assert summary.iterations == 1
        assert summary.failed == 1
        assert summary.completed == 0


# ── Feedback Resolution ──


class TestFeedbackResolution:
    """Verify auto-resolution of feedback entries."""

    def test_auto_resolves_data_quality_feedback(self):
        from services.data_steward import DataSteward
        db = MagicMock()
        steward = DataSteward(db, MagicMock())

        signal = _make_signal(source="feedback", source_id="fb-123")
        resolved = steward._auto_resolve_feedback(signal, "action-1")
        assert "fb-123" in resolved

        # Verify UPDATE was called
        update_calls = [c for c in db.execute.call_args_list
                        if "UPDATE feedback_entries" in str(c)]
        assert len(update_calls) >= 1

    def test_links_steward_action_to_feedback(self):
        from services.data_steward import DataSteward
        db = MagicMock()
        steward = DataSteward(db, MagicMock())

        signal = _make_signal(source="feedback", source_id="fb-123")
        steward._auto_resolve_feedback(signal, "action-456")

        # Check that steward_action_id is passed
        call_args = db.execute.call_args
        params = call_args[0][1]
        assert "action-456" in params

    def test_does_not_resolve_non_feedback_signal(self):
        from services.data_steward import DataSteward
        db = MagicMock()
        steward = DataSteward(db, MagicMock())

        signal = _make_signal(source="query_telemetry", source_id="qt-1")
        resolved = steward._auto_resolve_feedback(signal, "action-1")
        assert resolved == []
        db.execute.assert_not_called()


# ── Loop Control ──


class TestStewardLoop:
    """Verify loop iteration and limits."""

    def test_respects_max_iterations(self):
        from services.data_steward import DataSteward, StewardConfig
        db = MagicMock()
        db.fetch_one.return_value = {"id": "a-1", "acquired": True}
        collector = MagicMock()
        collector.collect_signals.return_value = [
            _make_signal(source_id=f"qt-{i}") for i in range(10)
        ]

        steward = DataSteward(db, collector, StewardConfig(max_iterations=3, dry_run=True))
        summary = steward.run_loop()
        assert summary.iterations == 3

    def test_loop_with_no_signals(self):
        from services.data_steward import DataSteward, StewardConfig
        db = MagicMock()
        db.fetch_one.return_value = {"acquired": True}
        collector = MagicMock()
        collector.collect_signals.return_value = []

        steward = DataSteward(db, collector, StewardConfig(dry_run=True))
        summary = steward.run_loop()
        assert summary.iterations == 0
        assert summary.completed == 0

    def test_returns_summary_with_timing(self):
        from services.data_steward import DataSteward, StewardConfig
        db = MagicMock()
        db.fetch_one.return_value = {"acquired": True}
        collector = MagicMock()
        collector.collect_signals.return_value = [_make_signal()]

        steward = DataSteward(db, collector, StewardConfig(dry_run=True))
        summary = steward.run_loop()
        assert summary.total_elapsed_s >= 0
        assert len(summary.results) == 1
