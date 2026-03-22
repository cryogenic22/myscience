"""Tests for services/query_telemetry.py — query gap detection and telemetry.

TDD: Verify gap detection logic and fire-and-forget persistence.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock


# ── Gap Detection (pure function tests) ──


class TestDetectQueryGap:
    """Verify gap detection from response signals."""

    def test_no_gap_when_all_found(self):
        from services.query_telemetry import detect_query_gap
        gap_type, details = detect_query_gap(
            entities_requested=["semaglutide"],
            entities_found=["semaglutide"],
            evidence_count=5,
            confidence=0.8,
        )
        assert gap_type is None
        assert details is None

    def test_missing_entity_gap(self):
        from services.query_telemetry import detect_query_gap
        gap_type, details = detect_query_gap(
            entities_requested=["semaglutide", "tirzepatide"],
            entities_found=["semaglutide"],
            evidence_count=5,
            confidence=0.8,
        )
        assert gap_type == "missing_entity"
        assert "tirzepatide" in details["missing"]

    def test_low_evidence_gap(self):
        from services.query_telemetry import detect_query_gap
        gap_type, details = detect_query_gap(
            entities_requested=["semaglutide"],
            entities_found=["semaglutide"],
            evidence_count=1,
            confidence=0.8,
        )
        assert gap_type == "low_evidence"
        assert details["evidence_count"] == 1

    def test_low_confidence_gap(self):
        from services.query_telemetry import detect_query_gap
        gap_type, details = detect_query_gap(
            entities_requested=["semaglutide"],
            entities_found=["semaglutide"],
            evidence_count=5,
            confidence=0.3,
        )
        assert gap_type == "low_confidence"
        assert details["confidence"] == 0.3

    def test_no_gap_when_confidence_none(self):
        """Legacy handler doesn't provide confidence — should not flag low_confidence."""
        from services.query_telemetry import detect_query_gap
        gap_type, details = detect_query_gap(
            entities_requested=["semaglutide"],
            entities_found=["semaglutide"],
            evidence_count=5,
            confidence=None,
        )
        assert gap_type is None

    def test_missing_entity_takes_priority_over_low_confidence(self):
        from services.query_telemetry import detect_query_gap
        gap_type, _ = detect_query_gap(
            entities_requested=["semaglutide", "tirzepatide"],
            entities_found=["semaglutide"],
            evidence_count=5,
            confidence=0.2,
        )
        assert gap_type == "missing_entity"

    def test_empty_entities_no_gap(self):
        from services.query_telemetry import detect_query_gap
        gap_type, _ = detect_query_gap(
            entities_requested=[],
            entities_found=[],
            evidence_count=5,
            confidence=0.8,
        )
        assert gap_type is None

    def test_case_insensitive_matching(self):
        from services.query_telemetry import detect_query_gap
        gap_type, _ = detect_query_gap(
            entities_requested=["Semaglutide"],
            entities_found=["semaglutide"],
            evidence_count=5,
            confidence=0.8,
        )
        assert gap_type is None


# ── Telemetry Persistence (MockDB tests) ──


class TestLogQueryEvent:
    """Verify fire-and-forget telemetry persistence."""

    def test_inserts_row(self):
        db = MagicMock()
        from services.query_telemetry import log_query_event
        log_query_event(
            db=db,
            session_id="sess-1",
            question="What is the GLP-1 landscape?",
            intent="landscape",
            entities_requested=["GLP-1"],
            evidence_count=5,
        )
        assert db.execute.call_count == 1
        sql = db.execute.call_args[0][0]
        assert "INSERT INTO query_telemetry" in sql

    def test_hashes_question(self):
        import hashlib
        db = MagicMock()
        from services.query_telemetry import log_query_event
        question = "What is the GLP-1 landscape?"
        log_query_event(db=db, question=question, intent="landscape")
        params = db.execute.call_args[0][1]
        expected_hash = hashlib.sha256(question.encode()).hexdigest()[:16]
        assert params[1] == expected_hash

    def test_never_raises_on_db_error(self):
        db = MagicMock()
        db.execute.side_effect = RuntimeError("connection pool exhausted")
        from services.query_telemetry import log_query_event
        # Should not raise
        log_query_event(db=db, question="test", intent="general")

    def test_null_optional_fields(self):
        db = MagicMock()
        from services.query_telemetry import log_query_event
        log_query_event(db=db, question="test", intent="general")
        params = db.execute.call_args[0][1]
        # session_id, entities, confidence, sources, latency, gap_type, gap_details can all be None
        assert params[0] is None  # session_id
        assert params[4] is None  # entities_requested
        assert params[5] is None  # entities_found
        assert params[6] is None  # confidence

    def test_gap_details_serialized_as_json(self):
        db = MagicMock()
        from services.query_telemetry import log_query_event
        log_query_event(
            db=db,
            question="test",
            intent="general",
            gap_type="missing_entity",
            gap_details={"missing": ["tirzepatide"]},
        )
        params = db.execute.call_args[0][1]
        # gap_details should be JSON string
        assert '"missing"' in params[11]
