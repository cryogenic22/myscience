"""Tests for ImpactRouter — event-driven impact assessment via graph + scenario + LLM.

TDD: Tests written BEFORE implementation.
Run with: pytest tests/test_impact_router.py -v
"""

from __future__ import annotations

from dataclasses import asdict
from unittest.mock import MagicMock

import pytest

from services.graph import GraphEdge, GraphNode, Subgraph
from services.impact_router import (
    ImpactAssessment,
    ImpactRouter,
    RoutingResult,
    classify_impact_direction,
    compute_impact_magnitude,
    EVENT_SCENARIO_MAP,
)
from services.scenario_engine import ScenarioResult


# ── Test data ──

DRUG_NODE = GraphNode(entity_id="d1", entity_type="drug", label="semaglutide")
COMPANY_NODE = GraphNode(entity_id="c1", entity_type="company", label="Novo Nordisk")
MECHANISM_NODE = GraphNode(entity_id="m1", entity_type="mechanism", label="GLP-1 RA")
TRIAL_NODE = GraphNode(entity_id="t1", entity_type="trial", label="NCT00001234")

EDGE_D1_C1 = GraphEdge(source_id="d1", target_id="c1", link_type="OWNED_BY", confidence=0.95)
EDGE_D1_M1 = GraphEdge(source_id="d1", target_id="m1", link_type="HAS_MECHANISM", confidence=0.9)
EDGE_D1_T1 = GraphEdge(source_id="d1", target_id="t1", link_type="INVESTIGATES", confidence=0.8)

SAMPLE_SUBGRAPH = Subgraph(
    nodes=[DRUG_NODE, COMPANY_NODE, MECHANISM_NODE, TRIAL_NODE],
    edges=[EDGE_D1_C1, EDGE_D1_M1, EDGE_D1_T1],
    center_entity_id="d1",
    hops=2,
)

EMPTY_SUBGRAPH = Subgraph(nodes=[], edges=[], center_entity_id="d1", hops=2)

SAMPLE_EVENT = {
    "id": "evt-001",
    "event_type": "approval",
    "description": "FDA approves semaglutide for obesity indication",
    "entity_id": "d1",
    "entity_type": "drug",
    "entity_name": "semaglutide",
    "status": "detected",
    "metadata": {"mechanism_id": "m1", "therapeutic_area": "Obesity"},
}

SAFETY_EVENT = {
    "id": "evt-002",
    "event_type": "safety_signal",
    "description": "PRR spike for semaglutide — pancreatitis reports",
    "entity_id": "d1",
    "entity_type": "drug",
    "entity_name": "semaglutide",
    "status": "detected",
    "metadata": {"prr": 3.5},
}

MA_EVENT = {
    "id": "evt-003",
    "event_type": "ma_deal",
    "description": "AstraZeneca acquires Alexion",
    "entity_id": "c2",
    "entity_type": "company",
    "entity_name": "AstraZeneca",
    "status": "detected",
    "metadata": {},
}

GENERAL_EVENT = {
    "id": "evt-004",
    "event_type": "general",
    "description": "Industry conference summary",
    "entity_id": "d1",
    "entity_type": "drug",
    "entity_name": "semaglutide",
    "status": "detected",
    "metadata": {},
}

SAMPLE_SCENARIO_RESULT = ScenarioResult(
    scenario_type="segment_isolation",
    description="Landscape isolated to mechanism 'm1'",
    baseline={"rows": [{"mechanism_id": "m1"}], "row_count": 1},
    modified={"rows": [{"mechanism_id": "m1"}], "row_count": 1},
    delta={"row_count_change": 0},
    entities_affected=0,
)


# ── Mock classes ──

class MockGraphTraversal:
    """Mock GraphTraversal returning configurable subgraphs."""

    def __init__(self, subgraph: Subgraph | None = None):
        self._subgraph = subgraph or EMPTY_SUBGRAPH
        self.traverse_calls: list[dict] = []

    def traverse(self, entity_id: str, entity_type: str, hops: int = 2, **kwargs) -> Subgraph:
        self.traverse_calls.append({
            "entity_id": entity_id,
            "entity_type": entity_type,
            "hops": hops,
        })
        return self._subgraph


class MockScenarioEngine:
    """Mock ScenarioEngine returning canned results."""

    def __init__(self, result: ScenarioResult | None = None):
        self._result = result or SAMPLE_SCENARIO_RESULT
        self.calls: list[dict] = []

    def landscape_single_mechanism(self, **kwargs) -> ScenarioResult:
        self.calls.append(("landscape_single_mechanism", kwargs))
        return self._result

    def pipeline_without_entity(self, **kwargs) -> ScenarioResult:
        self.calls.append(("pipeline_without_entity", kwargs))
        return self._result

    def competitive_landscape(self, **kwargs) -> ScenarioResult:
        self.calls.append(("competitive_landscape", kwargs))
        return self._result

    def threshold_alert(self, **kwargs) -> list[dict]:
        self.calls.append(("threshold_alert", kwargs))
        return [{"drug_name": "semaglutide", "alert_value": 3.5}]

    def landscape_without_company(self, **kwargs) -> ScenarioResult:
        self.calls.append(("landscape_without_company", kwargs))
        return self._result

    def pipeline_excluding_inactive(self, **kwargs) -> ScenarioResult:
        self.calls.append(("pipeline_excluding_inactive", kwargs))
        return self._result


class MockLLMSynthesizer:
    """Mock LLM that returns canned narrative."""

    def __init__(self, narrative: str = "Impact assessment narrative."):
        self._narrative = narrative
        self.calls: list[dict] = []

    @property
    def enabled(self) -> bool:
        return True

    def synthesize(self, **kwargs) -> str:
        self.calls.append(kwargs)
        return self._narrative


class MockDB:
    """Mock DB for persistence checks."""

    def __init__(self):
        self._queries: list[tuple[str, list | None]] = []

    def execute(self, query: str, params=None):
        self._queries.append((query, params))

    def fetch_all(self, query: str, params=None):
        self._queries.append((query, params))
        return []

    def fetch_one(self, query: str, params=None):
        self._queries.append((query, params))
        return None


# ── Fixtures ──

@pytest.fixture
def mock_db():
    return MockDB()


@pytest.fixture
def mock_graph():
    return MockGraphTraversal(subgraph=SAMPLE_SUBGRAPH)


@pytest.fixture
def mock_scenario():
    return MockScenarioEngine()


@pytest.fixture
def mock_llm():
    return MockLLMSynthesizer()


@pytest.fixture
def router(mock_db, mock_graph, mock_scenario, mock_llm):
    return ImpactRouter(
        db=mock_db,
        graph=mock_graph,
        scenario_engine=mock_scenario,
        llm=mock_llm,
    )


# ── 1. classify_impact_direction ──

class TestClassifyImpactDirection:
    """Impact direction classification based on event type."""

    def test_approval_is_positive(self):
        assert classify_impact_direction("approval") == "positive"

    def test_safety_signal_is_negative(self):
        assert classify_impact_direction("safety_signal") == "negative"

    def test_trial_readout_is_positive(self):
        assert classify_impact_direction("trial_readout") == "positive"

    def test_regulatory_setback_is_negative(self):
        assert classify_impact_direction("regulatory_setback") == "negative"

    def test_general_is_neutral(self):
        assert classify_impact_direction("general") == "neutral"

    def test_unknown_type_is_neutral(self):
        assert classify_impact_direction("totally_made_up") == "neutral"


# ── 2. compute_impact_magnitude ──

class TestComputeImpactMagnitude:
    """Magnitude calculation from trust score and graph distance."""

    def test_high_trust_nearby_yields_high_magnitude(self):
        mag = compute_impact_magnitude(confidence=0.95, path_length=1)
        assert mag >= 0.7

    def test_low_trust_distant_yields_low_magnitude(self):
        mag = compute_impact_magnitude(confidence=0.3, path_length=4)
        assert mag <= 0.3

    def test_magnitude_between_0_and_1(self):
        for conf in [0.0, 0.1, 0.5, 0.9, 1.0]:
            for dist in [0, 1, 2, 3, 4, 5]:
                mag = compute_impact_magnitude(confidence=conf, path_length=dist)
                assert 0.0 <= mag <= 1.0, f"Out of range for conf={conf}, dist={dist}: {mag}"

    def test_zero_path_length_max_distance_factor(self):
        """Path length 0 means the entity IS the source — max distance factor."""
        mag = compute_impact_magnitude(confidence=1.0, path_length=0)
        assert mag == 1.0


# ── 3. find_affected_entities ──

class TestFindAffectedEntities:
    """Graph traversal to find affected neighbors."""

    def test_returns_graph_neighbors(self, router, mock_graph):
        affected = router.find_affected_entities("d1", "drug")
        # Should return nodes from the subgraph
        assert len(affected) > 0
        # All returned items should be GraphNode instances
        for node in affected:
            assert isinstance(node, GraphNode)

    def test_excludes_source_entity(self, router):
        affected = router.find_affected_entities("d1", "drug")
        affected_ids = [n.entity_id for n in affected]
        assert "d1" not in affected_ids

    def test_empty_for_isolated_entity(self, mock_db, mock_scenario, mock_llm):
        """Isolated entity (no graph neighbors) returns empty list."""
        isolated_graph = MockGraphTraversal(subgraph=EMPTY_SUBGRAPH)
        router = ImpactRouter(
            db=mock_db,
            graph=isolated_graph,
            scenario_engine=mock_scenario,
            llm=mock_llm,
        )
        affected = router.find_affected_entities("d1", "drug")
        assert affected == []


# ── 4. run_scenario_if_applicable ──

class TestRunScenarioIfApplicable:
    """Scenario dispatch based on event type."""

    def test_approval_triggers_landscape_scenario(self, router, mock_scenario):
        result = router.run_scenario_if_applicable(SAMPLE_EVENT)
        assert result is not None
        # Should have called landscape_single_mechanism
        called_methods = [c[0] for c in mock_scenario.calls]
        assert "landscape_single_mechanism" in called_methods

    def test_safety_signal_triggers_threshold_alert(self, router, mock_scenario):
        result = router.run_scenario_if_applicable(SAFETY_EVENT)
        assert result is not None
        called_methods = [c[0] for c in mock_scenario.calls]
        assert "threshold_alert" in called_methods

    def test_general_event_returns_none(self, router, mock_scenario):
        result = router.run_scenario_if_applicable(GENERAL_EVENT)
        assert result is None

    def test_ma_deal_triggers_company_landscape(self, router, mock_scenario):
        result = router.run_scenario_if_applicable(MA_EVENT)
        assert result is not None
        called_methods = [c[0] for c in mock_scenario.calls]
        assert "landscape_without_company" in called_methods


# ── 5. route_event ──

class TestRouteEvent:
    """Full event routing pipeline."""

    def test_full_routing_produces_result(self, router):
        result = router.route_event(SAMPLE_EVENT)
        assert isinstance(result, RoutingResult)
        assert result.event_id == "evt-001"

    def test_result_has_assessments(self, router):
        result = router.route_event(SAMPLE_EVENT)
        assert len(result.assessments) > 0
        for assessment in result.assessments:
            assert isinstance(assessment, ImpactAssessment)
            assert assessment.event_id == "evt-001"
            assert assessment.impact_magnitude >= 0.0
            assert assessment.impact_direction in ("positive", "negative", "neutral")

    def test_persists_assessments_to_db(self, router, mock_db):
        router.route_event(SAMPLE_EVENT)
        # Should have INSERT queries for persisting assessments
        insert_queries = [q for q, _ in mock_db._queries if "INSERT" in q.upper()]
        assert len(insert_queries) > 0

    def test_handles_missing_entity_gracefully(self, router):
        """Event with entity that has no graph neighbors still produces a result."""
        event = dict(SAMPLE_EVENT)
        event["entity_id"] = "nonexistent-entity"
        # Use isolated graph for this test
        router.graph = MockGraphTraversal(subgraph=EMPTY_SUBGRAPH)
        result = router.route_event(event)
        assert isinstance(result, RoutingResult)
        assert result.total_entities_affected == 0

    def test_updates_event_status_to_assessed(self, router, mock_db):
        router.route_event(SAMPLE_EVENT)
        # Should have UPDATE query setting status to 'assessed'
        update_queries = [
            (q, p) for q, p in mock_db._queries
            if "UPDATE" in q.upper() and "assessed" in str(p).lower()
        ]
        assert len(update_queries) > 0


# ── 6. route_batch ──

class TestRouteBatch:
    """Batch processing of multiple events."""

    def test_routes_multiple_events(self, router):
        events = [SAMPLE_EVENT, SAFETY_EVENT, MA_EVENT]
        results = router.route_batch(events)
        assert len(results) == 3
        for result in results:
            assert isinstance(result, RoutingResult)

    def test_skips_already_processed(self, router):
        processed_event = dict(SAMPLE_EVENT)
        processed_event["status"] = "assessed"
        events = [processed_event, SAFETY_EVENT]
        results = router.route_batch(events)
        # Only the unprocessed event should have been routed
        assert len(results) == 1
        assert results[0].event_id == "evt-002"
