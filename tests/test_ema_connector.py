"""Tests for EMA connector."""

from __future__ import annotations

import pytest
from connectors.ema import EMAConnector
from connectors.base import SourceType


class TestEMAConnector:
    def test_source_type(self):
        connector = EMAConnector()
        assert connector.source_type == SourceType.EMA

    def test_extract_phase_roman(self):
        connector = EMAConnector()
        assert connector._extract_phase({"phase": "Phase III"}) == "Phase 3"
        assert connector._extract_phase({"phase": "Phase IV"}) == "Phase 4"
        assert connector._extract_phase({"phase": "Phase II"}) == "Phase 2"
        assert connector._extract_phase({"phase": "Phase I"}) == "Phase 1"

    def test_extract_phase_numeric(self):
        connector = EMAConnector()
        assert connector._extract_phase({"trial_phase": "3"}) == "Phase 3"
        assert connector._extract_phase({"trial_phase": "4"}) == "Phase 4"

    def test_extract_phase_unknown(self):
        connector = EMAConnector()
        assert connector._extract_phase({}) == "Unknown"

    def test_hash_payload(self):
        h1 = EMAConnector._hash_payload({"a": 1, "b": 2})
        h2 = EMAConnector._hash_payload({"b": 2, "a": 1})
        assert h1 == h2  # deterministic regardless of key order

    def test_get_target_drugs_default(self):
        connector = EMAConnector()
        drugs = connector._get_target_drugs()
        assert len(drugs) > 0
        assert "semaglutide" in drugs

    def test_target_overrides(self):
        connector = EMAConnector(target_overrides={"drugs": ["nivolumab", "pembrolizumab"]})
        assert connector._target_drugs == ["nivolumab", "pembrolizumab"]

    def test_registered_in_connector_registry(self):
        from connectors import CONNECTOR_REGISTRY
        assert SourceType.EMA in CONNECTOR_REGISTRY

    def test_registered_in_scheduler(self):
        from scheduler.config import CONNECTOR_SCHEDULES, RUN_ORDER
        assert SourceType.EMA in CONNECTOR_SCHEDULES
        assert SourceType.EMA in RUN_ORDER
