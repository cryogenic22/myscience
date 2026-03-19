"""Integration tests for Team Eval agent.

These tests require a live database and LLM connection.
Mark with pytest.mark.integration to skip in unit-test-only runs.

Run with: pytest tests/agent/test_team_eval_integration.py -v -m integration
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def live_team_eval_graph():
    """Build team eval graph with live dependencies."""
    try:
        from api.deps import get_team_eval_graph
        graph = get_team_eval_graph()
        if graph is None:
            pytest.skip("Team eval graph not available (agent disabled or deps missing)")
        return graph
    except Exception as exc:
        pytest.skip(f"Cannot build live graph: {exc}")


def _invoke_team_eval(graph, question: str) -> dict:
    """Invoke team eval with standard initial state."""
    return graph.invoke({
        "messages": [],
        "question": question,
        "extracted_entities": {},
        "active_personas": [],
        "persona_analyses": [],
        "tool_results": {},
        "combined_narrative": "",
        "confidence_assessment": {},
        "presentation": {},
        "table_data": None,
        "visualizations": [],
    })


class TestTirzepatideFasting:
    """The DB has 110 tirzepatide trials and 62 fasting trials.
    The response MUST reference actual trial data, not training knowledge."""

    def test_response_references_trial_data(self, live_team_eval_graph):
        result = _invoke_team_eval(
            live_team_eval_graph,
            "What about Mounjaro and events of low glucose during fasting?",
        )

        narrative = result["combined_narrative"].lower()

        # Must mention actual data indicators
        data_indicators = ["trial", "nct", "clinical_trial", "phase", "study", "evidence"]
        has_data_ref = any(word in narrative for word in data_indicators)
        assert has_data_ref, (
            f"Narrative must reference trial data. Got: {result['combined_narrative'][:300]}"
        )

        # Must NOT contain known hallucination markers
        hallucination_markers = ["no studies exist", "no targeted studies", "no relevant studies found"]
        for marker in hallucination_markers:
            assert marker not in narrative, (
                f"Narrative contains hallucination marker '{marker}'"
            )

    def test_entity_extraction_resolves_mounjaro(self, live_team_eval_graph):
        result = _invoke_team_eval(
            live_team_eval_graph,
            "What about Mounjaro and fasting?",
        )

        entities = result.get("extracted_entities", {})
        drugs = [d.lower() for d in entities.get("drugs", [])]

        # Should have resolved Mounjaro to tirzepatide
        assert "tirzepatide" in drugs or "mounjaro" in drugs, (
            f"Entity extraction should find tirzepatide/mounjaro, got: {drugs}"
        )


class TestPersonaDifferentiation:
    """Personas must provide distinct evidence from different tool types."""

    def test_personas_have_different_evidence_sources(self, live_team_eval_graph):
        result = _invoke_team_eval(
            live_team_eval_graph,
            "Should we invest in GLP-1 agonists for diabetes?",
        )

        analyses = result["persona_analyses"]
        assert len(analyses) >= 2, f"Expected >=2 personas, got {len(analyses)}"

        # Check that at least 2 personas have evidence_items
        personas_with_evidence = [
            a for a in analyses
            if a.get("evidence_items") and len(a["evidence_items"]) > 0
        ]
        assert len(personas_with_evidence) >= 2, (
            f"At least 2 personas should have gathered evidence, "
            f"got {len(personas_with_evidence)}"
        )

        # Check source diversity
        sources_by_persona = {}
        for a in analyses:
            sources = set(
                item.get("source", "") for item in a.get("evidence_items", [])
            )
            sources_by_persona[a["persona"]] = sources

        # At least 2 personas should have different primary sources
        source_sets = list(sources_by_persona.values())
        if len(source_sets) >= 2:
            # Not all personas should have identical sources
            all_same = all(s == source_sets[0] for s in source_sets[1:])
            assert not all_same, (
                f"Personas must query different data sources. "
                f"All had: {source_sets[0]}"
            )


class TestResponseShape:
    """Verify backward compatibility of the response shape."""

    def test_response_has_required_keys(self, live_team_eval_graph):
        result = _invoke_team_eval(
            live_team_eval_graph,
            "Tell me about semaglutide clinical trials",
        )

        assert "persona_analyses" in result
        assert "combined_narrative" in result
        assert "confidence_assessment" in result
        assert "tool_results" in result
        assert isinstance(result["persona_analyses"], list)
        assert isinstance(result["combined_narrative"], str)
        assert result["combined_narrative"] != ""
