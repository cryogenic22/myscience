"""Tests for ConceptWeightAdjuster — telemetry-driven concept weight feedback loop.

TDD: Tests written BEFORE implementation.
Run with: pytest tests/test_concept_weight_adjuster.py -v

The ConceptWeightAdjuster analyzes query_telemetry to correlate concept
activations with response quality, then adjusts concept weights up/down
to improve future query handling.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from services.concept_registry import Concept, ConceptRegistry


# ── Mock DB for tests ─────────────────────────────────────────────────


class _MockDB:
    """Minimal mock database for ConceptWeightAdjuster tests."""

    def __init__(self):
        self._queries: dict[str, list[dict]] = {}
        self._executed: list[tuple] = []

    def seed_query(self, pattern: str, rows: list[dict]) -> None:
        """Register rows to return when a query contains ``pattern``."""
        self._queries[pattern] = rows

    def fetch_all(self, query: str, params=None) -> list[dict]:
        for pattern, rows in self._queries.items():
            if pattern in query:
                return rows
        return []

    def fetch_one(self, query: str, params=None) -> dict | None:
        rows = self.fetch_all(query, params)
        return rows[0] if rows else None

    def execute(self, query: str, params=None) -> None:
        self._executed.append((query, params))

    @property
    def executed_queries(self) -> list[tuple]:
        return self._executed


class _ErrorDB:
    """A mock DB that always raises — simulates missing table."""

    def fetch_all(self, query: str, params=None) -> list[dict]:
        raise Exception("relation 'query_telemetry' does not exist")

    def fetch_one(self, query: str, params=None) -> dict | None:
        raise Exception("relation 'query_telemetry' does not exist")

    def execute(self, query: str, params=None) -> None:
        self._executed = getattr(self, "_executed", [])
        self._executed.append((query, params))


# ── Helper to create registry with known concepts ─────────────────────


def _make_registry_with_concepts(concepts: list[Concept]) -> ConceptRegistry:
    """Create a ConceptRegistry with specific concepts (no auto-register)."""
    reg = ConceptRegistry(auto_register=False)
    for c in concepts:
        reg.register(c)
    return reg


def _make_concept(
    name: str = "test_concept",
    weight: float = 0.5,
    intents: list[str] | None = None,
    entity_types: list[str] | None = None,
) -> Concept:
    return Concept(
        name=name,
        description=f"Test concept: {name}",
        computation=f"services.test.{name}",
        intents=intents or ["general"],
        entity_types=entity_types or ["drug"],
        staleness_days=7,
        weight=weight,
    )


# ═══════════════════════════════════════════════════════════════════════
# Tests
# ═══════════════════════════════════════════════════════════════════════


class TestConceptWeightAdjusterEmptyTelemetry:
    """When no telemetry data exists, adjuster returns empty report."""

    def test_no_adjustments_when_telemetry_empty(self):
        from services.concept_weight_adjuster import ConceptWeightAdjuster

        db = _MockDB()
        registry = _make_registry_with_concepts([
            _make_concept("pipeline_strength", weight=0.9),
        ])

        adjuster = ConceptWeightAdjuster(db, registry)
        report = adjuster.analyze_and_adjust(lookback_days=7)

        assert report.analyzed_queries == 0
        assert report.concepts_adjusted == 0
        assert report.adjustments == []
        assert report.timestamp  # should have a timestamp

    def test_graceful_when_table_missing(self):
        """If query_telemetry table does not exist, return empty report."""
        from services.concept_weight_adjuster import ConceptWeightAdjuster

        db = _ErrorDB()
        registry = _make_registry_with_concepts([
            _make_concept("pipeline_strength", weight=0.9),
        ])

        adjuster = ConceptWeightAdjuster(db, registry)
        report = adjuster.analyze_and_adjust(lookback_days=7)

        assert report.analyzed_queries == 0
        assert report.concepts_adjusted == 0
        assert report.adjustments == []


class TestConceptWeightBoosting:
    """When a concept is activated frequently with high quality, boost its weight."""

    def test_concept_boosted_high_activation_high_quality(self):
        from services.concept_weight_adjuster import ConceptWeightAdjuster

        db = _MockDB()
        # Seed: 15 activations of "landscape" intent, avg confidence=0.85
        db.seed_query(
            "query_telemetry",
            [
                {
                    "intent": "landscape",
                    "activation_count": 15,
                    "avg_confidence": 0.85,
                    "avg_evidence_count": 8.0,
                }
            ],
        )

        registry = _make_registry_with_concepts([
            _make_concept("competitive_landscape", weight=0.90, intents=["landscape"]),
            _make_concept("pipeline_strength", weight=0.80, intents=["pipeline"]),
        ])

        adjuster = ConceptWeightAdjuster(db, registry)
        report = adjuster.analyze_and_adjust(lookback_days=7)

        assert report.concepts_adjusted >= 1
        # competitive_landscape should have been boosted
        boosted = [a for a in report.adjustments if a["name"] == "competitive_landscape"]
        assert len(boosted) == 1
        assert boosted[0]["new_weight"] > boosted[0]["old_weight"]
        assert "boost" in boosted[0]["reason"].lower()

        # Verify registry was updated
        assert registry.get("competitive_landscape").weight > 0.90


class TestConceptWeightDampening:
    """When a concept is activated frequently with low quality, dampen its weight."""

    def test_concept_dampened_high_activation_low_quality(self):
        from services.concept_weight_adjuster import ConceptWeightAdjuster

        db = _MockDB()
        # Seed: 20 activations of "dossier" intent, avg confidence=0.25
        db.seed_query(
            "query_telemetry",
            [
                {
                    "intent": "dossier",
                    "activation_count": 20,
                    "avg_confidence": 0.25,
                    "avg_evidence_count": 1.0,
                }
            ],
        )

        registry = _make_registry_with_concepts([
            _make_concept("evidence_density", weight=0.80, intents=["dossier"]),
        ])

        adjuster = ConceptWeightAdjuster(db, registry)
        report = adjuster.analyze_and_adjust(lookback_days=7)

        assert report.concepts_adjusted >= 1
        dampened = [a for a in report.adjustments if a["name"] == "evidence_density"]
        assert len(dampened) == 1
        assert dampened[0]["new_weight"] < dampened[0]["old_weight"]
        assert "dampen" in dampened[0]["reason"].lower()

        # Verify registry was updated
        assert registry.get("evidence_density").weight < 0.80


class TestMinimumActivationThreshold:
    """Concepts below the minimum activation count should not be adjusted."""

    def test_no_adjustment_below_threshold(self):
        from services.concept_weight_adjuster import ConceptWeightAdjuster

        db = _MockDB()
        # Only 5 activations — below the minimum 10 threshold
        db.seed_query(
            "query_telemetry",
            [
                {
                    "intent": "landscape",
                    "activation_count": 5,
                    "avg_confidence": 0.90,
                    "avg_evidence_count": 10.0,
                }
            ],
        )

        registry = _make_registry_with_concepts([
            _make_concept("competitive_landscape", weight=0.90, intents=["landscape"]),
        ])

        adjuster = ConceptWeightAdjuster(db, registry)
        report = adjuster.analyze_and_adjust(lookback_days=7)

        assert report.concepts_adjusted == 0
        assert registry.get("competitive_landscape").weight == 0.90


class TestWeightClamping:
    """Weights must be clamped to [0.1, 5.0] range."""

    def test_weight_clamped_at_upper_bound(self):
        from services.concept_weight_adjuster import ConceptWeightAdjuster

        db = _MockDB()
        db.seed_query(
            "query_telemetry",
            [
                {
                    "intent": "landscape",
                    "activation_count": 50,
                    "avg_confidence": 0.95,
                    "avg_evidence_count": 15.0,
                }
            ],
        )

        # Start at 4.95 — a 10% boost would push it to 5.445
        registry = _make_registry_with_concepts([
            _make_concept("competitive_landscape", weight=4.95, intents=["landscape"]),
        ])

        adjuster = ConceptWeightAdjuster(db, registry)
        report = adjuster.analyze_and_adjust(lookback_days=7)

        # Should be clamped to 5.0
        final_weight = registry.get("competitive_landscape").weight
        assert final_weight <= 5.0
        if report.concepts_adjusted > 0:
            assert report.adjustments[0]["new_weight"] <= 5.0

    def test_weight_clamped_at_lower_bound(self):
        from services.concept_weight_adjuster import ConceptWeightAdjuster

        db = _MockDB()
        db.seed_query(
            "query_telemetry",
            [
                {
                    "intent": "dossier",
                    "activation_count": 50,
                    "avg_confidence": 0.10,
                    "avg_evidence_count": 0.5,
                }
            ],
        )

        # Start at 0.11 — a 10% dampen would push it to 0.099
        registry = _make_registry_with_concepts([
            _make_concept("evidence_density", weight=0.11, intents=["dossier"]),
        ])

        adjuster = ConceptWeightAdjuster(db, registry)
        report = adjuster.analyze_and_adjust(lookback_days=7)

        # Should be clamped to 0.1
        final_weight = registry.get("evidence_density").weight
        assert final_weight >= 0.1
        if report.concepts_adjusted > 0:
            assert report.adjustments[0]["new_weight"] >= 0.1


class TestAdjustmentReport:
    """Verify the AdjustmentReport contains all expected fields."""

    def test_report_structure(self):
        from services.concept_weight_adjuster import ConceptWeightAdjuster, AdjustmentReport

        db = _MockDB()
        db.seed_query(
            "query_telemetry",
            [
                {
                    "intent": "landscape",
                    "activation_count": 25,
                    "avg_confidence": 0.80,
                    "avg_evidence_count": 6.0,
                }
            ],
        )

        registry = _make_registry_with_concepts([
            _make_concept("competitive_landscape", weight=0.90, intents=["landscape"]),
        ])

        adjuster = ConceptWeightAdjuster(db, registry)
        report = adjuster.analyze_and_adjust(lookback_days=7)

        # Verify it's an AdjustmentReport
        assert isinstance(report, AdjustmentReport)
        assert isinstance(report.analyzed_queries, int)
        assert isinstance(report.concepts_adjusted, int)
        assert isinstance(report.adjustments, list)
        assert isinstance(report.timestamp, str)

        if report.adjustments:
            adj = report.adjustments[0]
            assert "name" in adj
            assert "old_weight" in adj
            assert "new_weight" in adj
            assert "reason" in adj

    def test_analyzed_queries_count_reflects_total(self):
        from services.concept_weight_adjuster import ConceptWeightAdjuster

        db = _MockDB()
        db.seed_query(
            "query_telemetry",
            [
                {
                    "intent": "landscape",
                    "activation_count": 30,
                    "avg_confidence": 0.85,
                    "avg_evidence_count": 5.0,
                },
                {
                    "intent": "dossier",
                    "activation_count": 20,
                    "avg_confidence": 0.60,
                    "avg_evidence_count": 3.0,
                },
            ],
        )

        registry = _make_registry_with_concepts([
            _make_concept("competitive_landscape", weight=0.90, intents=["landscape"]),
            _make_concept("evidence_density", weight=0.80, intents=["dossier"]),
        ])

        adjuster = ConceptWeightAdjuster(db, registry)
        report = adjuster.analyze_and_adjust(lookback_days=7)

        # analyzed_queries should be the sum of activations
        assert report.analyzed_queries == 50


class TestMultipleIntentsMultipleConcepts:
    """When multiple intents map to multiple concepts, all should be processed."""

    def test_multiple_concepts_adjusted(self):
        from services.concept_weight_adjuster import ConceptWeightAdjuster

        db = _MockDB()
        db.seed_query(
            "query_telemetry",
            [
                {
                    "intent": "landscape",
                    "activation_count": 15,
                    "avg_confidence": 0.90,
                    "avg_evidence_count": 8.0,
                },
                {
                    "intent": "dossier",
                    "activation_count": 12,
                    "avg_confidence": 0.20,
                    "avg_evidence_count": 1.0,
                },
            ],
        )

        registry = _make_registry_with_concepts([
            _make_concept("competitive_landscape", weight=0.90, intents=["landscape"]),
            _make_concept("market_concentration", weight=0.65, intents=["landscape"]),
            _make_concept("evidence_density", weight=0.80, intents=["dossier"]),
        ])

        adjuster = ConceptWeightAdjuster(db, registry)
        report = adjuster.analyze_and_adjust(lookback_days=7)

        # All three concepts should have been evaluated
        adjusted_names = {a["name"] for a in report.adjustments}

        # landscape concepts should be boosted (high quality)
        for name in ["competitive_landscape", "market_concentration"]:
            if name in adjusted_names:
                adj = [a for a in report.adjustments if a["name"] == name][0]
                assert adj["new_weight"] > adj["old_weight"]

        # dossier concept should be dampened (low quality)
        if "evidence_density" in adjusted_names:
            adj = [a for a in report.adjustments if a["name"] == "evidence_density"][0]
            assert adj["new_weight"] < adj["old_weight"]
