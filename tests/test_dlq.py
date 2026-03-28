"""Tests for dead-letter queue integration."""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch
from integration.pipeline import IntegrationPipeline


class TestDLQInsert:
    """Verify _dlq_insert handles various failure modes gracefully."""

    def _make_pipeline(self):
        db = MagicMock()
        config = MagicMock()
        config.db.dsn = "postgresql://test:test@localhost/test"
        config.embedding.api_key = ""
        config.embedding.model = "test"
        config.embedding.dimensions = 1536
        config.embedding.batch_size = 100
        return IntegrationPipeline(db, config)

    def test_dlq_insert_with_valid_record(self):
        pipeline = self._make_pipeline()
        record = MagicMock()
        record.external_id = "NCT001"
        record.record_type = MagicMock()
        record.record_type.value = "trial"
        record.data = {"title": "Test trial"}
        record.provenance = MagicMock()
        record.provenance.source_type = MagicMock()
        record.provenance.source_type.value = "clinical_trials_gov"
        record.provenance.api_endpoint = "https://api.example.com"
        record.provenance.retrieved_at = MagicMock()
        record.provenance.retrieved_at.isoformat.return_value = "2026-03-28T00:00:00"

        pipeline._dlq_insert("run-123", record, ValueError("test error"))

        pipeline.db.execute.assert_called_once()
        call_args = pipeline.db.execute.call_args
        assert "INSERT INTO failed_records" in call_args[0][0]
        assert call_args[0][1][0] == "run-123"  # etl_run_id
        assert call_args[0][1][2] == "NCT001"  # external_id

    def test_dlq_insert_survives_db_error(self):
        """DLQ insert failure should not crash the pipeline."""
        pipeline = self._make_pipeline()
        pipeline.db.execute.side_effect = Exception("table does not exist")

        record = MagicMock()
        record.external_id = "NCT002"
        record.record_type = MagicMock(value="trial")
        record.data = {}
        record.provenance = MagicMock()
        record.provenance.source_type = MagicMock(value="test")
        record.provenance.api_endpoint = ""
        record.provenance.retrieved_at = MagicMock()
        record.provenance.retrieved_at.isoformat.return_value = ""

        # Should not raise
        pipeline._dlq_insert("run-456", record, RuntimeError("boom"))

    def test_dlq_insert_with_missing_provenance(self):
        """Records without provenance should still insert."""
        pipeline = self._make_pipeline()
        record = MagicMock()
        record.external_id = "TEST-001"
        record.record_type = MagicMock(value="drug")
        record.data = {"name": "test"}
        record.provenance = None

        pipeline._dlq_insert("run-789", record, ValueError("no prov"))
        pipeline.db.execute.assert_called_once()
