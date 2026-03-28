"""ImpactRouter: Event-driven impact assessment via graph traversal + scenario simulation.

Takes detected events (approvals, safety signals, M&A deals, etc.), finds
affected entities via graph traversal, runs scenario simulations to quantify
impact, and generates LLM-synthesized impact narratives.

Usage:
    router = ImpactRouter(db=db, graph=graph, scenario_engine=engine, llm=llm)
    result = router.route_event(event_dict)
    results = router.route_batch([event1, event2])
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Optional

from services.graph import GraphNode, GraphTraversal, Subgraph
from services.scenario_engine import ScenarioEngine, ScenarioResult

logger = logging.getLogger(__name__)


# ── Data types ──

@dataclass
class ImpactAssessment:
    """Assessment of an event's impact on a single affected entity."""

    event_id: str
    affected_entity_id: str
    affected_entity_type: str
    affected_entity_name: str
    impact_magnitude: float
    impact_direction: str
    assessment_type: str
    scenario_result: dict | None = None
    graph_path: list[dict] | None = None
    narrative: str | None = None


@dataclass
class RoutingResult:
    """Result of routing a single event through impact assessment."""

    event_id: str
    event_description: str
    assessments: list[ImpactAssessment] = field(default_factory=list)
    total_entities_affected: int = 0
    max_impact_magnitude: float = 0.0


# ── Classification constants ──

IMPACT_DIRECTION_MAP = {
    "approval": "positive",
    "trial_readout": "positive",
    "safety_signal": "negative",
    "regulatory_setback": "negative",
    "supply_disruption": "negative",
    "ma_deal": "neutral",
    "general": "neutral",
}

EVENT_SCENARIO_MAP: dict[str, list[tuple[str, str]]] = {
    "approval": [("landscape_single_mechanism", "mechanism")],
    "regulatory_setback": [("pipeline_without_entity", "primary_entity")],
    "trial_readout": [("competitive_landscape", "mechanism")],
    "safety_signal": [("threshold_alert", "prr")],
    "ma_deal": [("landscape_without_company", "primary_entity")],
    "supply_disruption": [("pipeline_excluding_inactive", "therapeutic_area")],
}


# ── Module-level helpers ──

def classify_impact_direction(event_type: str) -> str:
    """Classify impact direction based on event type.

    Returns "positive", "negative", or "neutral".
    """
    return IMPACT_DIRECTION_MAP.get(event_type, "neutral")


def compute_impact_magnitude(confidence: float, path_length: int) -> float:
    """Compute impact magnitude from edge confidence and graph distance.

    Magnitude = confidence * distance_factor, where distance_factor decays
    with path length (closer entities are impacted more).

    Args:
        confidence: Edge confidence score (0.0-1.0).
        path_length: Number of hops from source entity (0 = source itself).

    Returns:
        Float between 0.0 and 1.0.
    """
    # Distance factor: 1.0 at distance 0, decaying by 0.2 per hop
    distance_factor = max(0.0, 1.0 - (path_length * 0.2))
    magnitude = confidence * distance_factor
    return max(0.0, min(1.0, magnitude))


# ── Service class ──

class ImpactRouter:
    """Routes detected events through graph traversal, scenario simulation, and LLM synthesis.

    Dependencies are injected, making the class fully testable with mocks.
    """

    def __init__(self, db, graph: GraphTraversal, scenario_engine: ScenarioEngine, llm):
        self.db = db
        self.graph = graph
        self.scenario_engine = scenario_engine
        self.llm = llm

    # ── Graph traversal ──

    def find_affected_entities(
        self,
        entity_id: str,
        entity_type: str,
        hops: int = 2,
    ) -> list[GraphNode]:
        """Find entities affected by an event via graph traversal.

        Traverses the knowledge graph from the source entity and returns
        neighboring nodes, excluding the source entity itself.
        """
        subgraph = self.graph.traverse(entity_id, entity_type, hops=hops)
        # Exclude the source entity from affected list
        return [
            node for node in subgraph.nodes
            if node.entity_id != entity_id
        ]

    # ── Scenario dispatch ──

    def run_scenario_if_applicable(self, event: dict) -> dict | None:
        """Run scenario simulation if the event type has a mapped scenario.

        Returns a dict with scenario results, or None if no scenario applies.
        """
        event_type = event.get("event_type", "")
        scenario_mappings = EVENT_SCENARIO_MAP.get(event_type)
        if not scenario_mappings:
            return None

        results = {}
        for scenario_method_name, param_source in scenario_mappings:
            try:
                result = self._dispatch_scenario(
                    scenario_method_name, param_source, event,
                )
                if result is not None:
                    results[scenario_method_name] = (
                        asdict(result) if isinstance(result, ScenarioResult) else result
                    )
            except Exception:
                logger.warning(
                    "Scenario %s failed for event %s",
                    scenario_method_name,
                    event.get("id", "?"),
                    exc_info=True,
                )

        return results if results else None

    def _dispatch_scenario(
        self,
        method_name: str,
        param_source: str,
        event: dict,
    ):
        """Dispatch to the appropriate ScenarioEngine method."""
        entity_id = event.get("entity_id", "")
        metadata = event.get("metadata", {})

        if method_name == "landscape_single_mechanism":
            mechanism_id = metadata.get("mechanism_id", entity_id)
            return self.scenario_engine.landscape_single_mechanism(
                mechanism_id=mechanism_id,
            )
        elif method_name == "pipeline_without_entity":
            return self.scenario_engine.pipeline_without_entity(
                entity_id=entity_id,
            )
        elif method_name == "competitive_landscape":
            mechanism = metadata.get("mechanism_id", "")
            return self.scenario_engine.competitive_landscape(
                topic=mechanism,
            )
        elif method_name == "threshold_alert":
            metric = param_source  # e.g., "prr"
            threshold = float(metadata.get(metric, 2.0))
            return self.scenario_engine.threshold_alert(
                metric=metric,
                threshold=threshold,
            )
        elif method_name == "landscape_without_company":
            return self.scenario_engine.landscape_without_company(
                company_id=entity_id,
            )
        elif method_name == "pipeline_excluding_inactive":
            ta = metadata.get("therapeutic_area", "")
            return self.scenario_engine.pipeline_excluding_inactive(
                therapeutic_area=ta,
            )
        else:
            logger.warning("Unknown scenario method: %s", method_name)
            return None

    # ── Narrative generation ──

    def _generate_narrative(
        self,
        event: dict,
        affected_entity: GraphNode,
        magnitude: float,
        direction: str,
        scenario_result: dict | None,
    ) -> str | None:
        """Generate impact narrative via LLM synthesis."""
        if not getattr(self.llm, "enabled", False):
            return None

        try:
            return self.llm.synthesize(
                question=f"What is the impact of this event on {affected_entity.label}?",
                intent="impact_assessment",
                entity_info={
                    "name": affected_entity.label,
                    "type": affected_entity.entity_type,
                    "id": affected_entity.entity_id,
                },
                metrics={
                    "impact_magnitude": magnitude,
                    "impact_direction": direction,
                    "scenario": scenario_result,
                },
                extra_context=event.get("description", ""),
                fallback_narrative=f"Event may affect {affected_entity.label} ({direction}, magnitude {magnitude:.2f}).",
            )
        except Exception:
            logger.warning(
                "Narrative generation failed for entity %s",
                affected_entity.entity_id,
                exc_info=True,
            )
            return None

    # ── Persistence ──

    def _persist_assessments(self, assessments: list[ImpactAssessment]) -> None:
        """Persist impact assessments to the database."""
        for assessment in assessments:
            try:
                self.db.execute(
                    """
                    INSERT INTO impact_assessments
                        (event_id, affected_entity_id, affected_entity_type,
                         affected_entity_name, impact_magnitude, impact_direction,
                         assessment_type, narrative)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    [
                        assessment.event_id,
                        assessment.affected_entity_id,
                        assessment.affected_entity_type,
                        assessment.affected_entity_name,
                        assessment.impact_magnitude,
                        assessment.impact_direction,
                        assessment.assessment_type,
                        assessment.narrative,
                    ],
                )
            except Exception:
                logger.warning(
                    "Failed to persist assessment for event %s → entity %s",
                    assessment.event_id,
                    assessment.affected_entity_id,
                    exc_info=True,
                )

    def _update_event_status(self, event_id: str, status: str = "assessed") -> None:
        """Update the event's processing status."""
        try:
            self.db.execute(
                "UPDATE market_events SET status = %s WHERE id::text = %s",
                [status, event_id],
            )
        except Exception:
            logger.warning("Failed to update event status for %s", event_id, exc_info=True)

    # ── Main routing ──

    def route_event(self, event: dict) -> RoutingResult:
        """Route a single event through the full impact assessment pipeline.

        Steps:
        1. Classify impact direction from event type
        2. Find affected entities via graph traversal
        3. Run scenario simulation if applicable
        4. Compute impact magnitude per affected entity
        5. Generate narrative per affected entity
        6. Persist assessments and update event status
        """
        event_id = event.get("id", "")
        entity_id = event.get("entity_id", "")
        entity_type = event.get("entity_type", "drug")
        event_type = event.get("event_type", "general")
        description = event.get("description", "")

        # 1. Direction
        direction = classify_impact_direction(event_type)

        # 2. Affected entities
        affected = self.find_affected_entities(entity_id, entity_type)

        # 3. Scenario
        scenario_result = self.run_scenario_if_applicable(event)

        # 4+5. Build assessments
        assessments: list[ImpactAssessment] = []
        for node in affected:
            # Find confidence of the edge connecting this node to the source
            confidence = self._edge_confidence(entity_id, node.entity_id)
            # Estimate path length (1 hop for direct neighbors)
            path_length = 1
            magnitude = compute_impact_magnitude(confidence, path_length)

            narrative = self._generate_narrative(
                event, node, magnitude, direction, scenario_result,
            )

            assessments.append(ImpactAssessment(
                event_id=event_id,
                affected_entity_id=node.entity_id,
                affected_entity_type=node.entity_type,
                affected_entity_name=node.label,
                impact_magnitude=magnitude,
                impact_direction=direction,
                assessment_type=event_type,
                scenario_result=scenario_result,
                graph_path=[{"entity_id": entity_id}, {"entity_id": node.entity_id}],
                narrative=narrative,
            ))

        # 6. Persist
        if assessments:
            self._persist_assessments(assessments)
        self._update_event_status(event_id, "assessed")

        max_mag = max((a.impact_magnitude for a in assessments), default=0.0)

        return RoutingResult(
            event_id=event_id,
            event_description=description,
            assessments=assessments,
            total_entities_affected=len(assessments),
            max_impact_magnitude=max_mag,
        )

    def _edge_confidence(self, source_id: str, target_id: str) -> float:
        """Look up edge confidence from the graph subgraph.

        Falls back to 0.5 if no direct edge found.
        """
        # Search through the last traversal's edges
        subgraph = self.graph.traverse(source_id, "drug", hops=1)
        for edge in subgraph.edges:
            if (edge.source_id == source_id and edge.target_id == target_id) or \
               (edge.source_id == target_id and edge.target_id == source_id):
                return edge.confidence
        return 0.5

    # ── Batch routing ──

    def route_batch(self, events: list[dict]) -> list[RoutingResult]:
        """Route multiple events, skipping already-processed ones.

        Args:
            events: List of event dicts with at least 'id', 'status', 'event_type'.

        Returns:
            List of RoutingResult for events that were processed.
        """
        results: list[RoutingResult] = []
        for event in events:
            status = event.get("status", "")
            if status == "assessed":
                logger.debug("Skipping already-assessed event %s", event.get("id"))
                continue
            try:
                result = self.route_event(event)
                results.append(result)
            except Exception:
                logger.warning(
                    "Failed to route event %s",
                    event.get("id", "?"),
                    exc_info=True,
                )
        return results
