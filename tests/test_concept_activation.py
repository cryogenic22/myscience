"""Tests for concept activation wiring into chat handlers.

TDD: These tests verify that activated concepts from ConceptRegistry
are formatted and injected into the LLM context during chat handling.

Run with: pytest tests/test_concept_activation.py -v
"""

from __future__ import annotations

import pytest

from services.concept_registry import Concept, ConceptRegistry, format_concept_context


# ── TestConceptActivationInHandlers ──


class TestConceptActivationInHandlers:
    """Verify that handlers activate relevant concepts for each intent."""

    def _registry(self) -> ConceptRegistry:
        return ConceptRegistry(auto_register=True)

    def test_dossier_activates_relevant_concepts(self):
        """dossier + drug should activate pipeline_strength, evidence_density, etc."""
        reg = self._registry()
        activated = reg.activate("dossier", ["drug"])
        names = [c.name for c in activated]
        assert "pipeline_strength" in names
        assert "evidence_density" in names
        assert "safety_signals" in names
        assert len(activated) >= 3

    def test_landscape_activates_competitive_concepts(self):
        """landscape intent should activate competitive_landscape, market_concentration."""
        reg = self._registry()
        activated = reg.activate("landscape", ["therapeutic_area", "company"])
        names = [c.name for c in activated]
        assert "competitive_landscape" in names
        assert "market_concentration" in names

    def test_compare_activates_both_entity_concepts(self):
        """compare intent should activate concepts for both drug and company types."""
        reg = self._registry()
        activated = reg.activate("compare", ["drug", "company"])
        names = [c.name for c in activated]
        # competitive_landscape applies to drug + company + compare
        assert "competitive_landscape" in names
        # competitive_position applies to drug + company + compare
        assert "competitive_position" in names
        assert len(activated) >= 2

    def test_general_activates_broad_concepts(self):
        """general intent should activate multiple concepts across entity types."""
        reg = self._registry()
        activated = reg.activate("general", ["drug", "mechanism", "therapeutic_area"])
        names = [c.name for c in activated]
        assert "evidence_density" in names
        assert "mechanism_coverage" in names
        assert len(activated) >= 2

    def test_concepts_added_to_llm_extra_context(self):
        """Activated concept names should appear in formatted extra_context string."""
        reg = self._registry()
        activated = reg.activate("dossier", ["drug"])
        context_str = format_concept_context(activated)
        assert "RELEVANT CONCEPTS" in context_str
        assert "pipeline_strength" in context_str
        assert "evidence_density" in context_str

    def test_empty_concepts_no_extra_context(self):
        """No concepts activated should produce no extra context."""
        reg = self._registry()
        activated = reg.activate("", [])
        context_str = format_concept_context(activated)
        assert context_str == ""


# ── TestConceptContextFormatter ──


class TestConceptContextFormatter:
    """Verify format_concept_context output shape and limits."""

    def test_formats_concept_hints(self):
        """Concepts should be formatted as 'RELEVANT CONCEPTS: name (description), ...'."""
        concepts = [
            Concept(
                name="pipeline_strength",
                description="Drug pipeline depth and phase distribution",
                computation="services.metrics.PharmaMetrics.drug_pipeline_strength",
                intents=["dossier"],
                entity_types=["drug"],
                weight=0.95,
            ),
            Concept(
                name="evidence_density",
                description="Publication volume and recency",
                computation="services.metrics.PharmaMetrics.evidence_density",
                intents=["dossier"],
                entity_types=["drug"],
                weight=0.80,
            ),
        ]
        result = format_concept_context(concepts)
        assert "RELEVANT CONCEPTS" in result
        assert "pipeline_strength" in result
        assert "Drug pipeline depth" in result
        assert "evidence_density" in result

    def test_limits_to_top_5_concepts(self):
        """Should include at most 5 concepts even if more are passed."""
        concepts = [
            Concept(
                name=f"concept_{i}",
                description=f"Description {i}",
                computation=f"services.test.method_{i}",
                intents=["general"],
                entity_types=["drug"],
                weight=1.0 - i * 0.1,
            )
            for i in range(8)
        ]
        result = format_concept_context(concepts, max_concepts=5)
        # Count the number of "- " bullet lines (concept entries)
        bullet_lines = [line for line in result.splitlines() if line.startswith("- ")]
        assert len(bullet_lines) == 5

    def test_includes_computation_hint(self):
        """Each concept line should hint at the data source."""
        concepts = [
            Concept(
                name="competitive_landscape",
                description="Market segments by mechanism and TA",
                computation="services.metrics.PharmaMetrics.competitive_landscape",
                intents=["landscape"],
                entity_types=["drug"],
                weight=0.90,
            ),
        ]
        result = format_concept_context(concepts)
        assert "competitive_landscape" in result
        # Should reference the computation source
        assert "PharmaMetrics.competitive_landscape" in result

    def test_empty_list_returns_empty_string(self):
        """Empty concept list should return empty string."""
        result = format_concept_context([])
        assert result == ""
