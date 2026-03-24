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
