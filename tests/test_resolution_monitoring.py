"""Tests for entity resolution monitoring — /metrics/unresolved-count endpoint.

TDD: Verify the unresolved-count endpoint returns correct counts,
alert thresholds, and entity-type breakdowns.

Run with: pytest tests/test_resolution_monitoring.py -v
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ── Mock DB helper ──


def _mock_db(pending_count=0, by_type_rows=None, raise_on_query=False):
    """Build a MagicMock DB for the unresolved-count endpoint."""
    db = MagicMock()

    if raise_on_query:
        db.fetch_one = MagicMock(side_effect=Exception("DB down"))
        db.fetch_all = MagicMock(side_effect=Exception("DB down"))
        return db

    db.fetch_one = MagicMock(return_value={"cnt": pending_count})
    db.fetch_all = MagicMock(return_value=by_type_rows or [])
    return db


# ── Endpoint logic tests (unit tests without FastAPI client) ──


class TestUnresolvedCount:
    """Verify /metrics/unresolved-count response structure and logic."""

    def test_returns_correct_total_pending(self):
        """Endpoint returns the exact count from hitl_reviews."""
        from api.routes.metrics import unresolved_count

        db = _mock_db(pending_count=75, by_type_rows=[
            {"entity_type": "drug", "cnt": 50},
            {"entity_type": "company", "cnt": 25},
        ])

        result = unresolved_count(db=db)

        assert result["total_pending"] == 75
        assert result["threshold"] == 50

    def test_alert_true_when_count_exceeds_threshold(self):
        """alert=true when pending count > 50."""
        from api.routes.metrics import unresolved_count

        db = _mock_db(pending_count=51)
        result = unresolved_count(db=db)

        assert result["alert"] is True

    def test_alert_false_when_count_at_or_below_threshold(self):
        """alert=false when pending count <= 50."""
        from api.routes.metrics import unresolved_count

        db = _mock_db(pending_count=50)
        result = unresolved_count(db=db)

        assert result["alert"] is False

    def test_alert_false_when_count_zero(self):
        """alert=false when queue is empty."""
        from api.routes.metrics import unresolved_count

        db = _mock_db(pending_count=0)
        result = unresolved_count(db=db)

        assert result["alert"] is False
        assert result["total_pending"] == 0

    def test_breakdown_by_entity_type(self):
        """by_entity_type contains per-type counts."""
        from api.routes.metrics import unresolved_count

        db = _mock_db(pending_count=120, by_type_rows=[
            {"entity_type": "drug", "cnt": 80},
            {"entity_type": "company", "cnt": 30},
            {"entity_type": "trial", "cnt": 10},
        ])

        result = unresolved_count(db=db)

        assert result["by_entity_type"]["drug"] == 80
        assert result["by_entity_type"]["company"] == 30
        assert result["by_entity_type"]["trial"] == 10

    def test_empty_breakdown_when_no_pending(self):
        """by_entity_type is empty dict when no pending items."""
        from api.routes.metrics import unresolved_count

        db = _mock_db(pending_count=0, by_type_rows=[])
        result = unresolved_count(db=db)

        assert result["by_entity_type"] == {}

    def test_graceful_degradation_on_db_error(self):
        """Returns zero counts when DB queries fail."""
        from api.routes.metrics import unresolved_count

        db = _mock_db(raise_on_query=True)
        result = unresolved_count(db=db)

        assert result["total_pending"] == 0
        assert result["by_entity_type"] == {}
        assert result["alert"] is False
