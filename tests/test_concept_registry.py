"""Tests for ConceptRegistry — formal registry of pharma domain concepts.

TDD: These tests are written BEFORE the implementation.
Run with: pytest tests/test_concept_registry.py -v

The Concept Registry is the Phase 2 semantic layer foundation.
Each concept describes a named analytical primitive (e.g., pipeline_strength)
with metadata for activation, staleness, and ranking.
"""

from __future__ import annotations

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock

from services.concept_registry import Concept, ConceptRegistry


# ── TestConceptDefinition ──


class TestConceptDefinition:
    """Verify Concept dataclass field requirements and helpers."""

    def test_concept_has_required_fields(self):
        """A Concept must carry all required metadata."""
        c = Concept(
            name="pipeline_strength",
            description="Weighted count of active trials by phase",
            computation="services.metrics.PharmaMetrics.drug_pipeline_strength",
            intents=["landscape", "pipeline"],
            entity_types=["drug", "therapeutic_area"],
            staleness_days=7,
            weight=0.9,
        )
        assert c.name == "pipeline_strength"
        assert c.description
        assert c.computation
        assert len(c.intents) == 2
        assert len(c.entity_types) == 2
        assert c.staleness_days == 7
        assert 0.0 <= c.weight <= 1.0

    def test_concept_relevance_for_intent(self):
        """A concept should report whether it is relevant for a given intent."""
        c = Concept(
            name="evidence_density",
            description="Publication count per entity",
            computation="services.metrics.PharmaMetrics.evidence_density",
            intents=["dossier", "general"],
            entity_types=["drug"],
            staleness_days=14,
            weight=0.7,
        )
        assert c.is_relevant_for_intent("dossier") is True
        assert c.is_relevant_for_intent("landscape") is False

    def test_concept_staleness_check(self):
        """A concept should detect when its value is stale."""
        c = Concept(
            name="trial_success_rate",
            description="Historical success rate by phase",
            computation="services.metrics.PharmaMetrics.trial_success_rate",
            intents=["pipeline"],
            entity_types=["drug", "trial"],
            staleness_days=30,
            weight=0.8,
        )
        fresh = datetime.now() - timedelta(days=5)
        stale = datetime.now() - timedelta(days=45)

        assert c.is_stale(fresh) is False
        assert c.is_stale(stale) is True


# ── TestConceptRegistry ──


class TestConceptRegistry:
    """Verify registry CRUD: register, get, list by intent/entity type."""

    def _make_registry(self) -> ConceptRegistry:
        """Create an empty registry (no auto-registered pharma concepts)."""
        reg = ConceptRegistry(auto_register=False)
        return reg

    def test_register_concept(self):
        reg = self._make_registry()
        c = Concept(
            name="test_concept",
            description="A test concept",
            computation="some.method",
            intents=["general"],
            entity_types=["drug"],
            staleness_days=7,
            weight=0.5,
        )
        reg.register(c)
        assert reg.get("test_concept") is c

    def test_get_concept_by_name(self):
        reg = self._make_registry()
        c = Concept(
            name="market_concentration",
            description="HHI for therapeutic area",
            computation="services.metrics.PharmaMetrics.competitive_landscape",
            intents=["landscape"],
            entity_types=["therapeutic_area"],
            staleness_days=14,
            weight=0.6,
        )
        reg.register(c)
        assert reg.get("market_concentration") is c
        assert reg.get("market_concentration").weight == 0.6

    def test_list_concepts_for_intent(self):
        reg = self._make_registry()
        c1 = Concept(
            name="a", description="a", computation="x",
            intents=["landscape", "dossier"], entity_types=["drug"],
            staleness_days=7, weight=0.8,
        )
        c2 = Concept(
            name="b", description="b", computation="y",
            intents=["pipeline"], entity_types=["drug"],
            staleness_days=7, weight=0.5,
        )
        c3 = Concept(
            name="c", description="c", computation="z",
            intents=["landscape"], entity_types=["company"],
            staleness_days=7, weight=0.6,
        )
        reg.register(c1)
        reg.register(c2)
        reg.register(c3)

        landscape_concepts = reg.list_for_intent("landscape")
        names = [c.name for c in landscape_concepts]
        assert "a" in names
        assert "c" in names
        assert "b" not in names

    def test_list_concepts_for_entity_type(self):
        reg = self._make_registry()
        c1 = Concept(
            name="d", description="d", computation="x",
            intents=["dossier"], entity_types=["drug", "company"],
            staleness_days=7, weight=0.9,
        )
        c2 = Concept(
            name="e", description="e", computation="y",
            intents=["landscape"], entity_types=["trial"],
            staleness_days=7, weight=0.4,
        )
        reg.register(c1)
        reg.register(c2)

        drug_concepts = reg.list_for_entity_type("drug")
        assert len(drug_concepts) == 1
        assert drug_concepts[0].name == "d"

        trial_concepts = reg.list_for_entity_type("trial")
        assert len(trial_concepts) == 1
        assert trial_concepts[0].name == "e"

    def test_unknown_concept_returns_none(self):
        reg = self._make_registry()
        assert reg.get("nonexistent") is None


# ── TestConceptActivation ──


class TestConceptActivation:
    """Verify activate() which combines intent + entity type filtering and ranks by weight."""

    def _make_full_registry(self) -> ConceptRegistry:
        """Create a registry with the default pharma concepts loaded."""
        return ConceptRegistry(auto_register=True)

    def test_activate_concepts_for_landscape_query(self):
        reg = self._make_full_registry()
        activated = reg.activate(intent="landscape", entity_types=["drug", "company"])
        assert len(activated) >= 2
        # Should include competitive_landscape and competitive_position
        names = [c.name for c in activated]
        assert "competitive_landscape" in names

    def test_activate_concepts_for_dossier_query(self):
        reg = self._make_full_registry()
        activated = reg.activate(intent="dossier", entity_types=["drug"])
        assert len(activated) >= 2
        names = [c.name for c in activated]
        assert "evidence_density" in names

    def test_no_concepts_for_empty_query(self):
        reg = self._make_full_registry()
        activated = reg.activate(intent="", entity_types=[])
        assert activated == []

    def test_multiple_concepts_ranked_by_relevance(self):
        reg = self._make_full_registry()
        activated = reg.activate(intent="landscape", entity_types=["drug"])
        # Verify descending weight order
        weights = [c.weight for c in activated]
        assert weights == sorted(weights, reverse=True)
        # At least 2 concepts should match a landscape + drug query
        assert len(activated) >= 2


# ── TestConceptRegistryDBBacked ──


class _MockDB:
    """Minimal mock database for ConceptRegistry DB tests."""

    def __init__(self):
        self._rows: list[dict] = []
        self._executed: list[tuple] = []

    def seed(self, rows: list[dict]) -> None:
        """Seed the mock with rows that fetch_all will return."""
        self._rows = list(rows)

    def fetch_all(self, query: str, params=None) -> list[dict]:
        return self._rows

    def execute(self, query: str, params=None) -> None:
        self._executed.append((query, params))

    @property
    def executed_queries(self) -> list[tuple]:
        return self._executed


def _make_db_row(
    name: str = "test_concept",
    description: str = "A test concept",
    computation_path: str = "services.test.method",
    intents: list[str] | None = None,
    entity_types: list[str] | None = None,
    staleness_days: int = 7,
    weight: float = 0.5,
) -> dict:
    return {
        "name": name,
        "description": description,
        "computation_path": computation_path,
        "intents": intents or ["general"],
        "entity_types": entity_types or ["drug"],
        "staleness_days": staleness_days,
        "weight": weight,
    }


class TestConceptRegistryDBBacked:
    """Verify DB-backed loading, cache invalidation, sync, and weight updates."""

    def test_db_backed_load_concepts(self):
        """Concepts loaded from DB should populate the registry cache."""
        db = _MockDB()
        db.seed([
            _make_db_row(name="pipeline_strength", weight=0.95),
            _make_db_row(name="evidence_density", weight=0.80),
        ])
        reg = ConceptRegistry(auto_register=True, db=db)
        assert reg.get("pipeline_strength") is not None
        assert reg.get("evidence_density") is not None
        assert reg.get("pipeline_strength").weight == 0.95

    def test_db_backed_empty_falls_back_to_hardcoded(self):
        """If DB returns no rows, fall back to the 15 hardcoded concepts."""
        db = _MockDB()
        db.seed([])  # empty table
        reg = ConceptRegistry(auto_register=True, db=db)
        # Should still have the 15 hardcoded concepts
        assert reg.get("pipeline_strength") is not None
        assert reg.get("competitive_landscape") is not None
        assert len(reg.list_for_intent("landscape")) >= 2

    def test_db_exception_falls_back_to_hardcoded(self):
        """If DB raises an exception, fall back to hardcoded concepts."""
        db = MagicMock()
        db.fetch_all.side_effect = Exception("connection refused")
        reg = ConceptRegistry(auto_register=True, db=db)
        assert reg.get("pipeline_strength") is not None
        assert reg.get("competitive_landscape") is not None

    def test_cache_invalidation_via_reload(self):
        """After reload_from_db(), new concepts from DB should appear."""
        db = _MockDB()
        # Start with one concept
        db.seed([_make_db_row(name="alpha", weight=0.9)])
        reg = ConceptRegistry(auto_register=True, db=db)
        assert reg.get("alpha") is not None
        assert reg.get("beta") is None

        # Simulate a new concept added to DB
        db.seed([
            _make_db_row(name="alpha", weight=0.9),
            _make_db_row(name="beta", weight=0.7),
        ])
        count = reg.reload_from_db()
        assert count == 2
        assert reg.get("alpha") is not None
        assert reg.get("beta") is not None

    def test_reload_empty_db_falls_back(self):
        """reload_from_db with empty DB falls back to hardcoded."""
        db = _MockDB()
        db.seed([_make_db_row(name="alpha")])
        reg = ConceptRegistry(auto_register=True, db=db)
        assert reg.get("alpha") is not None

        db.seed([])  # DB now empty
        count = reg.reload_from_db()
        assert count == 15  # fell back to hardcoded
        assert reg.get("pipeline_strength") is not None
        assert reg.get("alpha") is None

    def test_reload_without_db_returns_zero(self):
        """reload_from_db with no DB returns 0."""
        reg = ConceptRegistry(auto_register=True)
        assert reg.reload_from_db() == 0

    def test_update_weight_in_cache_and_db(self):
        """update_weight should change the in-memory weight and write to DB."""
        db = _MockDB()
        db.seed([_make_db_row(name="pipeline_strength", weight=0.95)])
        reg = ConceptRegistry(auto_register=True, db=db)

        result = reg.update_weight("pipeline_strength", 0.99)
        assert result is True
        assert reg.get("pipeline_strength").weight == 0.99
        # Should have issued an UPDATE query
        assert any("UPDATE concepts" in q[0] for q in db.executed_queries)

    def test_update_weight_unknown_concept(self):
        """update_weight on a nonexistent concept returns False."""
        db = _MockDB()
        db.seed([_make_db_row(name="alpha")])
        reg = ConceptRegistry(auto_register=True, db=db)
        assert reg.update_weight("nonexistent", 0.5) is False

    def test_update_weight_without_db(self):
        """update_weight without DB still updates cache."""
        reg = ConceptRegistry(auto_register=True)
        old_weight = reg.get("pipeline_strength").weight
        reg.update_weight("pipeline_strength", 0.99)
        assert reg.get("pipeline_strength").weight == 0.99

    def test_sync_to_db_writes_all_concepts(self):
        """sync_to_db should upsert all in-memory concepts to DB."""
        db = _MockDB()
        db.seed([])
        reg = ConceptRegistry(auto_register=True, db=db)
        # Registry has 15 hardcoded concepts (DB was empty, so fell back)
        count = reg.sync_to_db()
        assert count == 15
        # Each concept triggers one INSERT ... ON CONFLICT
        insert_queries = [q for q in db.executed_queries if "INSERT INTO concepts" in q[0]]
        assert len(insert_queries) == 15

    def test_sync_to_db_without_db_returns_zero(self):
        """sync_to_db with no DB returns 0."""
        reg = ConceptRegistry(auto_register=True)
        assert reg.sync_to_db() == 0

    def test_backward_compat_no_db(self):
        """ConceptRegistry() with no db still works exactly as before."""
        reg = ConceptRegistry(auto_register=True)
        assert reg.get("pipeline_strength") is not None
        assert reg.get("competitive_landscape") is not None
        assert len(reg.list_for_intent("landscape")) >= 2
        activated = reg.activate("dossier", ["drug"])
        assert len(activated) >= 3

    def test_backward_compat_no_auto_register(self):
        """ConceptRegistry(auto_register=False) still gives empty registry."""
        reg = ConceptRegistry(auto_register=False)
        assert reg.get("pipeline_strength") is None
        assert len(reg.list_for_intent("landscape")) == 0
