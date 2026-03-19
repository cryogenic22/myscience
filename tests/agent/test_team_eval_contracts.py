"""Contract tests for Team Eval agent.

Each test validates a specific architectural requirement from the spec.
Tests use ToolCallRecorder wrappers around stub tools to verify call patterns.
"""

from __future__ import annotations

import json
import re
import pytest

from tests.conftest import (
    MockLLM,
    StubTool,
    ToolCallRecorder,
    make_rag_result,
    make_sql_result,
    make_empty_result,
)
from services.agent.graphs.team_eval_graph import (
    _extract_entities,
    _persona_node,
    _persona_rag_queries,
    _persona_sql_queries,
    _persona_metrics_queries,
    _synthesize_team,
    _parse_entity_json,
    _build_evidence_context,
    build_team_eval_graph,
    PersonaInput,
    TeamEvalState,
)


# ── Contract 1: Each persona executes its assigned tools ──

class TestContract1_PersonaToolExecution:
    """SPEC: Each persona must execute only its assigned tools."""

    def test_clinical_researcher_uses_rag_and_graph(
        self, populated_rag_tool, populated_graph_tool, stub_sql_tool, stub_metrics_tool, persona_llm, personas,
    ):
        rag_rec = ToolCallRecorder(populated_rag_tool)
        graph_rec = ToolCallRecorder(populated_graph_tool)
        sql_rec = ToolCallRecorder(stub_sql_tool)
        metrics_rec = ToolCallRecorder(stub_metrics_tool)

        state = PersonaInput(
            question="What about tirzepatide and fasting?",
            persona_name="clinical_researcher",
            extracted_entities={"drugs": ["tirzepatide"], "conditions": ["fasting"], "companies": [], "mechanisms": []},
            schema_text="",
        )

        result = _persona_node(
            state, llm=persona_llm, personas=personas,
            sql_tool=sql_rec, rag_tool=rag_rec,
            graph_tool=graph_rec, metrics_tool=metrics_rec,
        )

        assert rag_rec.call_count >= 1, "clinical_researcher must use RAG tool"
        assert graph_rec.call_count >= 1, "clinical_researcher must use graph tool"
        assert sql_rec.call_count == 0, "clinical_researcher must NOT use SQL tool"
        assert metrics_rec.call_count == 0, "clinical_researcher must NOT use metrics tool"

    def test_market_analyst_uses_sql_and_metrics(
        self, stub_rag_tool, stub_graph_tool, populated_sql_tool, populated_metrics_tool, persona_llm, personas,
    ):
        rag_rec = ToolCallRecorder(stub_rag_tool)
        graph_rec = ToolCallRecorder(stub_graph_tool)
        sql_rec = ToolCallRecorder(populated_sql_tool)
        metrics_rec = ToolCallRecorder(populated_metrics_tool)

        # Need an LLM that can plan SQL
        def sql_plan_response(messages):
            system = messages[0].content if messages else ""
            if "sql" in system.lower() and ("generate" in system.lower() or "planner" in system.lower()):
                return json.dumps([{"sql": "SELECT COUNT(*) FROM drugs", "label": "Drug count"}])
            return json.dumps({
                "analysis": "Market analysis based on database evidence [1].",
                "confidence": "medium",
                "key_findings": ["Pipeline score data available [1]"],
                "data_gaps": [],
            })

        llm = MockLLM(response_fn=sql_plan_response)

        state = PersonaInput(
            question="Should we invest in GLP-1 agonists?",
            persona_name="market_analyst",
            extracted_entities={"drugs": ["semaglutide", "tirzepatide"], "conditions": ["diabetes"], "companies": [], "mechanisms": ["GLP-1 agonist"]},
            schema_text="Tables:\n  - drugs (id, generic_name)\n  - clinical_trials (id, drug_id, status, phase)",
        )

        result = _persona_node(
            state, llm=llm, personas=personas,
            sql_tool=sql_rec, rag_tool=rag_rec,
            graph_tool=graph_rec, metrics_tool=metrics_rec,
        )

        assert rag_rec.call_count == 0, "market_analyst must NOT use RAG tool"
        assert graph_rec.call_count == 0, "market_analyst must NOT use graph tool"
        assert sql_rec.call_count >= 1, "market_analyst must use SQL tool"
        assert metrics_rec.call_count >= 1, "market_analyst must use metrics tool"


# ── Contract 2: SQL personas generate targeted queries ──

class TestContract2_TargetedSQL:
    """SPEC: Personas with SQL access generate targeted queries containing entity names."""

    def test_sql_contains_entity_names(self, stub_sql_tool, persona_llm, personas):
        sql_rec = ToolCallRecorder(stub_sql_tool)

        def sql_plan_response(messages):
            system = messages[0].content if messages else ""
            if "sql" in system.lower() and "planner" in system.lower():
                return json.dumps([{
                    "sql": "SELECT phase, COUNT(*) FROM clinical_trials WHERE drug_id IN (SELECT id FROM drugs WHERE LOWER(generic_name) = LOWER('tirzepatide')) GROUP BY phase",
                    "label": "Phase breakdown for tirzepatide",
                }])
            return json.dumps({
                "analysis": "Analysis [1].",
                "confidence": "medium",
                "key_findings": ["Finding [1]"],
                "data_gaps": [],
            })

        llm = MockLLM(response_fn=sql_plan_response)

        evidence = _persona_sql_queries(
            sql_rec, llm,
            question="What about tirzepatide and fasting?",
            entities={"drugs": ["tirzepatide"], "conditions": ["fasting"], "companies": [], "mechanisms": []},
            schema_text="Tables: drugs, clinical_trials",
            persona_name="regulatory_expert",
        )

        assert sql_rec.call_count >= 1, "Must execute at least one SQL query"
        # Check that the SQL contains entity-specific terms
        sql_params = sql_rec.get_params("query")
        any_targeted = any("tirzepatide" in p.get("sql", "").lower() for p in sql_params)
        assert any_targeted, "SQL queries must reference entity names from the question"


# ── Contract 3: Entity extraction populates extracted_entities ──

class TestContract3_EntityExtraction:
    """SPEC: extract_entities → route_team → personas."""

    def test_tirzepatide_fasting_extraction(self):
        def response_fn(messages):
            return json.dumps({
                "drugs": ["tirzepatide", "mounjaro"],
                "conditions": ["fasting", "low glucose"],
                "companies": ["Eli Lilly"],
                "mechanisms": [],
            })

        llm = MockLLM(response_fn=response_fn)

        state = TeamEvalState(
            messages=[], question="What about Mounjaro and events of low glucose during fasting?",
            extracted_entities={}, active_personas=[], persona_analyses=[],
            tool_results={}, combined_narrative="", confidence_assessment={},
            presentation={}, table_data=None, visualizations=[],
        )

        result = _extract_entities(state, llm=llm)
        entities = result["extracted_entities"]

        assert "tirzepatide" in entities["drugs"], "Must extract generic name tirzepatide"
        assert any("fasting" in c.lower() for c in entities["conditions"]), "Must extract condition 'fasting'"

    def test_brand_to_generic_resolution(self):
        def response_fn(messages):
            return json.dumps({
                "drugs": ["tirzepatide", "mounjaro"],
                "conditions": [],
                "companies": [],
                "mechanisms": [],
            })

        llm = MockLLM(response_fn=response_fn)

        state = TeamEvalState(
            messages=[], question="Tell me about Mounjaro trials",
            extracted_entities={}, active_personas=[], persona_analyses=[],
            tool_results={}, combined_narrative="", confidence_assessment={},
            presentation={}, table_data=None, visualizations=[],
        )

        result = _extract_entities(state, llm=llm)
        entities = result["extracted_entities"]

        # Both brand and generic should be present
        drug_lower = [d.lower() for d in entities["drugs"]]
        assert "tirzepatide" in drug_lower or "mounjaro" in drug_lower, \
            "Must resolve brand name to include in drug list"


# ── Contract 4: Persona analysis cites database evidence ──

class TestContract4_CitationGrounding:
    """SPEC: Only cite data from DATABASE EVIDENCE."""

    def test_findings_have_citation_markers(
        self, populated_rag_tool, populated_graph_tool, stub_sql_tool, stub_metrics_tool, personas,
    ):
        def grounded_response(messages):
            return json.dumps({
                "analysis": "Tirzepatide shows active trials [1]. Ramadan study data available [2].",
                "confidence": "high",
                "key_findings": [
                    "110 tirzepatide trials in database [1]",
                    "Phase 4 Ramadan study NCT06635057 [2]",
                    "PubMed evidence supports efficacy [3]",
                ],
                "data_gaps": ["Limited long-term data"],
            })

        llm = MockLLM(response_fn=grounded_response)

        state = PersonaInput(
            question="What about tirzepatide and fasting?",
            persona_name="clinical_researcher",
            extracted_entities={"drugs": ["tirzepatide"], "conditions": ["fasting"], "companies": [], "mechanisms": []},
            schema_text="",
        )

        result = _persona_node(
            state, llm=llm, personas=personas,
            sql_tool=stub_sql_tool, rag_tool=populated_rag_tool,
            graph_tool=populated_graph_tool, metrics_tool=stub_metrics_tool,
        )

        analysis = result["persona_analyses"][0]
        findings = analysis["key_findings"]
        citation_pattern = re.compile(r'\[\d+\]')

        for finding in findings:
            assert citation_pattern.search(finding), \
                f"Key finding must contain [N] citation: '{finding}'"


# ── Contract 5: Personas receive different data (not shared blob) ──

class TestContract5_DifferentiatedData:
    """TEST: Personas must query different data, not share a blob."""

    def test_persona_tool_calls_are_distinct(
        self, populated_rag_tool, populated_graph_tool, populated_sql_tool, populated_metrics_tool, personas,
    ):
        # Clinical researcher tools
        cr_rag = ToolCallRecorder(populated_rag_tool)
        cr_graph = ToolCallRecorder(populated_graph_tool)
        cr_sql = ToolCallRecorder(StubTool("sql"))
        cr_metrics = ToolCallRecorder(StubTool("metrics"))

        # Market analyst tools
        ma_rag = ToolCallRecorder(StubTool("rag"))
        ma_graph = ToolCallRecorder(StubTool("graph"))
        ma_sql = ToolCallRecorder(populated_sql_tool)
        ma_metrics = ToolCallRecorder(populated_metrics_tool)

        entities = {"drugs": ["tirzepatide"], "conditions": ["fasting"], "companies": [], "mechanisms": []}

        def persona_resp(messages):
            return json.dumps({
                "analysis": "Analysis based on evidence [1].",
                "confidence": "medium",
                "key_findings": ["Finding [1]"],
                "data_gaps": [],
            })

        def sql_plan_resp(messages):
            system = messages[0].content if messages else ""
            if "sql" in system.lower() and "planner" in system.lower():
                return json.dumps([{"sql": "SELECT COUNT(*) FROM drugs", "label": "count"}])
            return persona_resp(messages)

        cr_llm = MockLLM(response_fn=persona_resp)
        ma_llm = MockLLM(response_fn=sql_plan_resp)

        cr_state = PersonaInput(
            question="tirzepatide fasting", persona_name="clinical_researcher",
            extracted_entities=entities, schema_text="",
        )
        ma_state = PersonaInput(
            question="tirzepatide fasting", persona_name="market_analyst",
            extracted_entities=entities, schema_text="Tables: drugs, clinical_trials",
        )

        _persona_node(cr_state, llm=cr_llm, personas=personas,
                       sql_tool=cr_sql, rag_tool=cr_rag, graph_tool=cr_graph, metrics_tool=cr_metrics)
        _persona_node(ma_state, llm=ma_llm, personas=personas,
                       sql_tool=ma_sql, rag_tool=ma_rag, graph_tool=ma_graph, metrics_tool=ma_metrics)

        # Clinical researcher should use RAG, market analyst should NOT
        assert cr_rag.call_count > 0, "Clinical researcher must make RAG calls"
        assert ma_rag.call_count == 0, "Market analyst must NOT make RAG calls"

        # Market analyst should use metrics, clinical researcher should NOT
        assert ma_metrics.call_count > 0, "Market analyst must make metrics calls"
        assert cr_metrics.call_count == 0, "Clinical researcher must NOT make metrics calls"


# ── Contract 6: Synthesis drops ungrounded claims ──

class TestContract6_SynthesisGrounding:
    """TEST: Synthesis prompt instructs to only propagate cited claims."""

    def test_synthesis_prompt_contains_grounding_rules(self):
        analyses = [
            {
                "persona": "clinical_researcher",
                "display_name": "Clinical Researcher",
                "analysis": "Grounded claim [1]. Ungrounded claim without citation.",
                "confidence": 0.85,
                "key_findings": ["Grounded finding [1]", "Ungrounded finding"],
                "data_gaps": [],
                "evidence_items": [],
            }
        ]

        # Capture the messages sent to synthesis LLM
        captured_messages = []

        def capture_fn(messages):
            captured_messages.extend(messages)
            return "Synthesis: Tirzepatide shows strong evidence [1]."

        llm = MockLLM(response_fn=capture_fn)

        state = TeamEvalState(
            messages=[], question="tirzepatide fasting",
            extracted_entities={}, active_personas=[], persona_analyses=analyses,
            tool_results={}, combined_narrative="", confidence_assessment={},
            presentation={}, table_data=None, visualizations=[],
        )

        _synthesize_team(state, llm=llm)

        # Verify the synthesis prompt includes grounding instructions
        system_msg = captured_messages[0].content if captured_messages else ""
        assert "[N] citation" in system_msg.lower() or "[n]" in system_msg.lower(), \
            "Synthesis prompt must instruct to only propagate cited claims"
        assert "do not introduce" in system_msg.lower() or "not present in specialist" in system_msg.lower(), \
            "Synthesis prompt must warn against introducing new claims"


# ── Contract 7: Empty evidence → explicit "no data" statement ──

class TestContract7_EmptyEvidence:
    """TEST: When no evidence exists, persona must state so with low confidence."""

    def test_no_evidence_returns_low_confidence(
        self, stub_rag_tool, stub_graph_tool, stub_sql_tool, stub_metrics_tool, personas,
    ):
        def no_data_response(messages):
            system = messages[0].content if messages else ""
            if "no database evidence" in system.lower() or "(0 items)" in system.lower():
                return json.dumps({
                    "analysis": "No data found in database for this query.",
                    "confidence": "low",
                    "key_findings": [],
                    "data_gaps": ["No database evidence available"],
                })
            return json.dumps({
                "analysis": "No data found.",
                "confidence": "high",  # Deliberately wrong — should be downgraded
                "key_findings": [],
                "data_gaps": [],
            })

        llm = MockLLM(response_fn=no_data_response)

        state = PersonaInput(
            question="What about imaginarydrug-xyz-999?",
            persona_name="clinical_researcher",
            extracted_entities={"drugs": ["imaginarydrug-xyz-999"], "conditions": [], "companies": [], "mechanisms": []},
            schema_text="",
        )

        result = _persona_node(
            state, llm=llm, personas=personas,
            sql_tool=stub_sql_tool, rag_tool=stub_rag_tool,
            graph_tool=stub_graph_tool, metrics_tool=stub_metrics_tool,
        )

        analysis = result["persona_analyses"][0]
        assert analysis["confidence"] <= 0.35, \
            f"Empty evidence must result in low confidence (<=0.35), got {analysis['confidence']}"


# ── Contract 8: Backward compatibility with chat.py response format ──

class TestContract8_BackwardCompatibility:
    """TEST: Full graph output matches expected response shape."""

    def test_full_graph_response_shape(self, smart_llm, personas, schema_text):
        sql_tool = StubTool("sql", {"query": make_sql_result([{"count": 5}])})
        rag_tool = StubTool("rag", {"search": make_rag_result([
            {"source": "test", "entity_type": "clinical_trial", "entity_id": "NCT001",
             "content": "Test trial", "relevance": 0.9, "provenance": {"source_api": "test"}},
        ])})
        graph_tool = StubTool("graph")
        metrics_tool = StubTool("metrics", {"pipeline": make_empty_result("metrics"), "landscape": make_empty_result("metrics")})

        graph = build_team_eval_graph(
            llm=smart_llm,
            sql_tool=sql_tool,
            rag_tool=rag_tool,
            graph_tool=graph_tool,
            metrics_tool=metrics_tool,
            personas=personas,
            schema_text=schema_text,
        )

        result = graph.invoke({
            "messages": [],
            "question": "What about tirzepatide and fasting?",
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

        # Verify required top-level keys
        assert "persona_analyses" in result, "Must have persona_analyses"
        assert "combined_narrative" in result, "Must have combined_narrative"
        assert "confidence_assessment" in result, "Must have confidence_assessment"
        assert "tool_results" in result, "Must have tool_results"

        # Verify persona_analyses structure
        analyses = result["persona_analyses"]
        assert isinstance(analyses, list), "persona_analyses must be a list"
        assert len(analyses) >= 2, f"Expected >=2 persona analyses, got {len(analyses)}"

        for a in analyses:
            assert "persona" in a, "Each analysis must have 'persona'"
            assert "display_name" in a, "Each analysis must have 'display_name'"
            assert "analysis" in a, "Each analysis must have 'analysis'"
            assert "confidence" in a, "Each analysis must have 'confidence'"
            assert "key_findings" in a, "Each analysis must have 'key_findings'"
            assert "data_gaps" in a, "Each analysis must have 'data_gaps'"

        # Verify confidence_assessment structure
        conf = result["confidence_assessment"]
        assert "overall" in conf, "confidence_assessment must have 'overall'"
        assert "by_dimension" in conf, "confidence_assessment must have 'by_dimension'"

        # Verify combined_narrative is non-empty
        assert result["combined_narrative"], "combined_narrative must not be empty"
