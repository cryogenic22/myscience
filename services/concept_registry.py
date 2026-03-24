"""Concept Registry — formal catalogue of pharma domain analytical concepts.

The semantic layer foundation for Phase 2. Each Concept describes a named
analytical primitive (e.g., pipeline_strength, competitive_landscape) with
metadata that tells the intelligence pipeline:
  - WHEN the concept is relevant (intent + entity type matching)
  - HOW to compute it (service method path)
  - WHETHER the value is stale (staleness threshold)
  - HOW to rank it against peer concepts (weight)

Usage:
    registry = ConceptRegistry()                        # auto-loads 15 pharma concepts
    concepts = registry.activate("landscape", ["drug"]) # ranked list for this query
    concept = registry.get("pipeline_strength")         # look up by name
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


@dataclass
class Concept:
    """A named analytical primitive in the pharma domain.

    Attributes:
        name:           Machine-readable identifier (e.g. "pipeline_strength").
        description:    Human-readable explanation of what this concept measures.
        computation:    Dotted path to the service method that computes this concept.
        intents:        Chat intents that activate this concept (e.g. ["landscape", "pipeline"]).
        entity_types:   Entity types this concept applies to (e.g. ["drug", "company"]).
        staleness_days: After how many days a cached value should be recomputed.
        weight:         Relevance weight 0-1 used for ranking when multiple concepts match.
    """

    name: str
    description: str
    computation: str
    intents: list[str] = field(default_factory=list)
    entity_types: list[str] = field(default_factory=list)
    staleness_days: int = 7
    weight: float = 0.5

    def is_relevant_for_intent(self, intent: str) -> bool:
        """Check whether this concept is relevant for the given intent."""
        return intent in self.intents

    def is_stale(self, last_computed: datetime) -> bool:
        """Check whether the value is stale given its last computation timestamp."""
        threshold = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=self.staleness_days)
        return last_computed < threshold


class ConceptRegistry:
    """Registry of domain concepts with activation logic.

    Args:
        auto_register: When True (default), pre-loads the pharma domain concepts.
                       Set False for unit tests that need an empty registry.
    """

    def __init__(self, auto_register: bool = True) -> None:
        self._concepts: dict[str, Concept] = {}
        if auto_register:
            self._register_pharma_concepts()

    def register(self, concept: Concept) -> None:
        """Register a concept. Overwrites if name already exists."""
        self._concepts[concept.name] = concept

    def get(self, name: str) -> Concept | None:
        """Look up a concept by name. Returns None if not found."""
        return self._concepts.get(name)

    def list_for_intent(self, intent: str) -> list[Concept]:
        """Return all concepts relevant to the given intent, sorted by weight descending."""
        return sorted(
            [c for c in self._concepts.values() if intent in c.intents],
            key=lambda c: c.weight,
            reverse=True,
        )

    def list_for_entity_type(self, entity_type: str) -> list[Concept]:
        """Return all concepts applicable to the given entity type, sorted by weight descending."""
        return sorted(
            [c for c in self._concepts.values() if entity_type in c.entity_types],
            key=lambda c: c.weight,
            reverse=True,
        )

    def activate(self, intent: str, entity_types: list[str]) -> list[Concept]:
        """Activate concepts matching both intent AND at least one entity type.

        Returns concepts sorted by weight descending. This is the primary
        entry point used by the query pipeline to decide which analytical
        concepts to compute for a given user question.
        """
        if not intent or not entity_types:
            return []

        entity_set = set(entity_types)
        matched = [
            c for c in self._concepts.values()
            if intent in c.intents
            and entity_set.intersection(c.entity_types)
        ]
        return sorted(matched, key=lambda c: c.weight, reverse=True)

    # ── Pharma Domain Concepts ──────────────────────────────────

    def _register_pharma_concepts(self) -> None:
        """Register the 15 core pharma analytical concepts."""

        concepts = [
            Concept(
                name="pipeline_strength",
                description="Weighted count of active clinical trials by phase, "
                            "with later phases scored higher (P3=4, P2=2, P1=1).",
                computation="services.metrics.PharmaMetrics.drug_pipeline_strength",
                intents=["landscape", "pipeline", "dossier"],
                entity_types=["drug", "therapeutic_area"],
                staleness_days=7,
                weight=0.95,
            ),
            Concept(
                name="competitive_landscape",
                description="Market structure analysis: competitor count, concentration, "
                            "and positioning within a therapeutic area.",
                computation="services.metrics.PharmaMetrics.competitive_landscape",
                intents=["landscape", "compare"],
                entity_types=["drug", "company", "therapeutic_area"],
                staleness_days=14,
                weight=0.90,
            ),
            Concept(
                name="trial_success_rate",
                description="Historical phase transition success rate for a drug "
                            "or therapeutic area, based on trial status progression.",
                computation="services.metrics.PharmaMetrics.trial_success_rate",
                intents=["pipeline", "dossier"],
                entity_types=["drug", "trial", "therapeutic_area"],
                staleness_days=30,
                weight=0.85,
            ),
            Concept(
                name="evidence_density",
                description="Publication volume and recency across PubMed, PMC, "
                            "and clinical trial results for an entity.",
                computation="services.metrics.PharmaMetrics.evidence_density",
                intents=["dossier", "general", "compare"],
                entity_types=["drug", "mechanism", "therapeutic_area"],
                staleness_days=14,
                weight=0.80,
            ),
            Concept(
                name="safety_signals",
                description="Adverse event reports from FAERS, FDA shortages, "
                            "and label warnings aggregated per drug.",
                computation="services.metrics.PharmaMetrics.evidence_density",
                intents=["dossier", "pipeline", "compare"],
                entity_types=["drug"],
                staleness_days=7,
                weight=0.88,
            ),
            Concept(
                name="company_portfolio",
                description="Breadth and depth of a company's drug portfolio "
                            "across therapeutic areas and development phases.",
                computation="services.metrics.PharmaMetrics.company_portfolio",
                intents=["portfolio", "landscape", "dossier"],
                entity_types=["company"],
                staleness_days=14,
                weight=0.85,
            ),
            Concept(
                name="mechanism_coverage",
                description="How many drugs target a given mechanism of action, "
                            "and their distribution across development phases.",
                computation="services.graph.GraphTraversal.drugs_by_mechanism_class",
                intents=["landscape", "dossier", "general"],
                entity_types=["mechanism", "drug"],
                staleness_days=14,
                weight=0.75,
            ),
            Concept(
                name="patent_landscape",
                description="Patent expiry timeline, exclusivity windows, "
                            "and generic entry risk for a drug or company.",
                computation="services.graph.GraphTraversal.neighborhood",
                intents=["dossier", "landscape"],
                entity_types=["drug", "patent", "company"],
                staleness_days=30,
                weight=0.70,
            ),
            Concept(
                name="regulatory_status",
                description="Current regulatory milestones: NDA filing, "
                            "approval dates, supplemental indications, REMS.",
                computation="services.graph.GraphTraversal.entity_summary",
                intents=["dossier", "pipeline"],
                entity_types=["drug"],
                staleness_days=7,
                weight=0.82,
            ),
            Concept(
                name="therapeutic_area_depth",
                description="Knowledge density for a therapeutic area: entity count, "
                            "link density, trial count, publication volume.",
                computation="services.graph.GraphTraversal.entity_summary",
                intents=["landscape", "general"],
                entity_types=["therapeutic_area"],
                staleness_days=14,
                weight=0.70,
            ),
            Concept(
                name="clinical_endpoint_data",
                description="Primary and secondary endpoint results from completed "
                            "trials, including effect sizes and confidence intervals.",
                computation="services.search.HybridSearch.search",
                intents=["dossier", "compare", "pipeline"],
                entity_types=["drug", "trial"],
                staleness_days=30,
                weight=0.78,
            ),
            Concept(
                name="market_concentration",
                description="Herfindahl-Hirschman Index (HHI) approximation for "
                            "therapeutic area competitive intensity.",
                computation="services.metrics.PharmaMetrics.competitive_landscape",
                intents=["landscape"],
                entity_types=["therapeutic_area", "company"],
                staleness_days=14,
                weight=0.65,
            ),
            Concept(
                name="evidence_recency",
                description="Median age of publications and trial updates, "
                            "indicating how actively an entity is being studied.",
                computation="services.metrics.PharmaMetrics.evidence_density",
                intents=["dossier", "general"],
                entity_types=["drug", "mechanism", "therapeutic_area"],
                staleness_days=14,
                weight=0.60,
            ),
            Concept(
                name="entity_completeness",
                description="Data quality score: percentage of recommended fields "
                            "populated, link density, and source diversity.",
                computation="services.metrics.PharmaMetrics.evidence_density",
                intents=["general", "dossier"],
                entity_types=["drug", "company", "trial", "mechanism", "therapeutic_area"],
                staleness_days=7,
                weight=0.55,
            ),
            Concept(
                name="competitive_position",
                description="A drug's relative standing among competitors in the same "
                            "therapeutic area, based on trial phase, evidence, and portfolio.",
                computation="services.metrics.PharmaMetrics.competitive_landscape",
                intents=["landscape", "compare", "dossier"],
                entity_types=["drug", "company"],
                staleness_days=14,
                weight=0.85,
            ),
        ]

        for concept in concepts:
            self.register(concept)

        logger.debug("Registered %d pharma concepts", len(concepts))


def format_concept_context(concepts: list[Concept], max_concepts: int = 5) -> str:
    """Format activated concepts as an LLM context hint.

    Returns a string like:
        RELEVANT CONCEPTS for this query:
        - pipeline_strength: Drug pipeline depth and phase distribution (from PharmaMetrics.drug_pipeline_strength)
        - competitive_landscape: Market segments by mechanism and TA (from PharmaMetrics.competitive_landscape)

    Returns empty string if concepts list is empty.
    """
    if not concepts:
        return ""

    top = concepts[:max_concepts]
    lines = ["RELEVANT CONCEPTS for this query:"]
    for c in top:
        # Extract the short computation reference (last two dotted parts)
        parts = c.computation.rsplit(".", 2)
        short_ref = ".".join(parts[-2:]) if len(parts) >= 2 else c.computation
        lines.append(f"- {c.name}: {c.description} (from {short_ref})")

    return "\n".join(lines)
