"""Tests for api/routes/feedback.py — user feedback CRUD.

TDD: Verify create, list, filter, update, and stats endpoints.
"""

from __future__ import annotations

import uuid

import pytest
from unittest.mock import MagicMock, patch


# ── Validation tests (pure logic) ──


class TestFeedbackValidation:
    """Verify category and priority validation."""

    def test_valid_categories(self):
        from api.routes.feedback import VALID_CATEGORIES
        assert "bug" in VALID_CATEGORIES
        assert "data_quality" in VALID_CATEGORIES
        assert "data_request" in VALID_CATEGORIES
        assert len(VALID_CATEGORIES) == 6

    def test_valid_priorities(self):
        from api.routes.feedback import VALID_PRIORITIES
        assert "low" in VALID_PRIORITIES
        assert "critical" in VALID_PRIORITIES
        assert len(VALID_PRIORITIES) == 4

    def test_valid_statuses(self):
        from api.routes.feedback import VALID_STATUSES
        assert "new" in VALID_STATUSES
        assert "resolved" in VALID_STATUSES
        assert "rejected" in VALID_STATUSES
        assert len(VALID_STATUSES) == 5


# ── Create endpoint tests ──


class TestCreateFeedback:
    """Verify POST /feedback logic."""

    def test_creates_bug_report(self):
        from api.routes.feedback import create_feedback, FeedbackCreateRequest
        db = MagicMock()
        fid = str(uuid.uuid4())
        db.fetch_one.return_value = {
            "id": fid, "category": "bug", "title": "Graph crashes",
            "status": "new", "priority": "high", "created_at": "2026-03-22T00:00:00Z",
        }

        body = FeedbackCreateRequest(category="bug", title="Graph crashes", priority="high")
        result = create_feedback(body, db)
        assert result["feedback"]["id"] == fid
        assert result["feedback"]["category"] == "bug"
        assert db.fetch_one.call_count == 1

    def test_creates_data_quality_feedback(self):
        from api.routes.feedback import create_feedback, FeedbackCreateRequest
        db = MagicMock()
        db.fetch_one.return_value = {
            "id": "fb-1", "category": "data_quality", "title": "Missing approval date",
            "status": "new", "priority": "medium", "created_at": "2026-03-22",
        }

        body = FeedbackCreateRequest(
            category="data_quality",
            title="Missing approval date",
            entity_context={"entity_type": "drug", "entity_id": "d001", "entity_name": "semaglutide"},
        )
        result = create_feedback(body, db)
        assert result["feedback"]["category"] == "data_quality"

    def test_rejects_invalid_category(self):
        from api.routes.feedback import create_feedback, FeedbackCreateRequest
        from fastapi import HTTPException
        db = MagicMock()

        body = FeedbackCreateRequest(category="invalid", title="Test")
        with pytest.raises(HTTPException) as exc_info:
            create_feedback(body, db)
        assert exc_info.value.status_code == 400

    def test_rejects_invalid_priority(self):
        from api.routes.feedback import create_feedback, FeedbackCreateRequest
        from fastapi import HTTPException
        db = MagicMock()

        body = FeedbackCreateRequest(category="bug", title="Test", priority="urgent")
        with pytest.raises(HTTPException) as exc_info:
            create_feedback(body, db)
        assert exc_info.value.status_code == 400


# ── List endpoint tests ──


class TestListFeedback:
    """Verify GET /feedback logic."""

    def test_lists_all(self):
        from api.routes.feedback import list_feedback
        db = MagicMock()
        db.fetch_one.return_value = {"cnt": 2}
        db.fetch_all.return_value = [
            {"id": "fb-1", "category": "bug", "title": "Bug 1", "status": "new",
             "priority": "high", "user_id": None, "page_url": None,
             "resolved_by": None, "created_at": "2026-03-22", "updated_at": "2026-03-22"},
            {"id": "fb-2", "category": "feature", "title": "Feature 1", "status": "new",
             "priority": "low", "user_id": None, "page_url": None,
             "resolved_by": None, "created_at": "2026-03-22", "updated_at": "2026-03-22"},
        ]

        result = list_feedback(db=db)
        assert result["total"] == 2
        assert len(result["items"]) == 2

    def test_filters_by_status(self):
        from api.routes.feedback import list_feedback
        db = MagicMock()
        db.fetch_one.return_value = {"cnt": 1}
        db.fetch_all.return_value = [
            {"id": "fb-1", "category": "bug", "title": "Bug 1", "status": "resolved",
             "priority": "high", "user_id": None, "page_url": None,
             "resolved_by": "steward", "created_at": "2026-03-22", "updated_at": "2026-03-22"},
        ]

        result = list_feedback(status="resolved", db=db)
        assert result["total"] == 1
        sql = db.fetch_all.call_args[0][0]
        assert "status = %s" in sql


# ── Update endpoint tests ──


class TestUpdateFeedback:
    """Verify PATCH /feedback/{id} logic."""

    def test_updates_status(self):
        from api.routes.feedback import update_feedback, FeedbackUpdateRequest
        db = MagicMock()
        db.fetch_one.return_value = {
            "id": "fb-1", "status": "resolved", "priority": "high",
            "resolution": "Fixed by steward", "resolved_by": "steward",
            "updated_at": "2026-03-22",
        }

        body = FeedbackUpdateRequest(status="resolved", resolution="Fixed by steward", resolved_by="steward")
        result = update_feedback("fb-1", body, db)
        assert result["feedback"]["status"] == "resolved"
        assert result["feedback"]["resolved_by"] == "steward"

    def test_rejects_empty_update(self):
        from api.routes.feedback import update_feedback, FeedbackUpdateRequest
        from fastapi import HTTPException
        db = MagicMock()

        body = FeedbackUpdateRequest()
        with pytest.raises(HTTPException) as exc_info:
            update_feedback("fb-1", body, db)
        assert exc_info.value.status_code == 400


# ── Delete endpoint tests (SPEC_041 Stage 6 fix M4) ──


class TestDeleteFeedback:
    """Verify DELETE /feedback/{id} logic — privacy retraction path."""

    def test_deletes_existing_entry(self):
        from api.routes.feedback import delete_feedback
        db = MagicMock()
        db.fetch_one.return_value = {"id": "fb-to-delete"}

        result = delete_feedback("fb-to-delete", db)
        assert result is None  # 204 No Content
        sql = db.fetch_one.call_args[0][0]
        assert "DELETE FROM feedback_entries" in sql

    def test_404_when_entry_missing(self):
        from api.routes.feedback import delete_feedback
        from fastapi import HTTPException
        db = MagicMock()
        db.fetch_one.return_value = None  # nothing matched

        with pytest.raises(HTTPException) as exc_info:
            delete_feedback("does-not-exist", db)
        assert exc_info.value.status_code == 404


# ── Stats endpoint tests ──


class TestFeedbackStats:
    """Verify GET /feedback/stats logic."""

    def test_returns_aggregates(self):
        from api.routes.feedback import feedback_stats
        db = MagicMock()
        db.fetch_all.side_effect = [
            [{"category": "bug", "cnt": 5}, {"category": "data_quality", "cnt": 3}],
            [{"status": "new", "cnt": 6}, {"status": "resolved", "cnt": 2}],
        ]
        db.fetch_one.side_effect = [
            {"cnt": 2},  # auto_resolved
            {"cnt": 8},  # total
        ]

        result = feedback_stats(db)
        assert result["total"] == 8
        assert result["by_category"]["bug"] == 5
        assert result["by_status"]["new"] == 6
        assert result["auto_resolved_by_steward"] == 2
