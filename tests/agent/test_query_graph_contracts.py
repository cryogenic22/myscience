"""Contract tests for query graph improvements: context, enrichment, validation.

5 contracts:
1. Context resolution — conversation_context causes _plan_sql to reference prior entities
2. Scalar enrichment — scalar COUNT triggers detail row generation
3. No enrichment for non-scalar — multi-row results are untouched
4. Validation warnings — 0-row result produces a warning
5. Backward compatibility — graph output has all required keys
"""

from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock

from tests.conftest import MockLLM, StubTool, make_sql_result, make_empty_result
from services.agent.tools.base import ToolResult
from services.agent.graphs.query_graph import (
    _classify,
    _plan_sql,
    _validate_and_enrich,
    _default_state,
    build_query_graph,
    QueryAgentState,
)

SCHEMA_TEXT = """Tables:
  - drugs (id uuid PK, generic_name text, brand_name text, company_id uuid)
  - clinical_trials (id text PK, title text, status text, phase text, drug_id uuid)
  - companies (id uuid PK, name text)
"""


# ── Helpers ──

def _make_state(
    question: str = "test",
    conversation_context: str = "",
    plan: dict | None = None,
    tool_results: dict | None = None,
) -> QueryAgentState:
    state = _default_state(question, conversation_context)
    if plan:
        state["plan"] = plan
    if tool_results:
        state["tool_results"] = tool_results
    return state


def _sql_plan_llm(sql_text: str = "SELECT COUNT(*) FROM clinical_trials"):
    """LLM that returns a fixed SQL plan JSON."""
    return MockLLM(default_response=json.dumps({
        "sql": sql_text,
        "params": [],
        "explanation": "test",
        "presentation_hint": "scalar",
    }))


def _detail_llm():
    """LLM that responds to both plan and enrichment prompts."""
    def response_fn(messages):
        system = messages[0].content if messages else ""
        if "detail SELECT" in system or "COUNT question" in system:
            return json.dumps({
                "sql": "SELECT title, status, phase FROM clinical_trials WHERE phase = 'Phase 3' LIMIT 4",
                "params": [],
                "title": "Phase 3 Trials",
            })
        # Default: SQL plan
        return json.dumps({
            "sql": "SELECT COUNT(*) AS cnt FROM clinical_trials WHERE phase = 'Phase 3'",
            "params": [],
            "explanation": "count phase 3 trials",
            "presentation_hint": "scalar",
        })
    return MockLLM(response_fn=response_fn)


# ── Contract 1: Context resolution ──

class TestContextResolution:
    """Given conversation_context with prior SQL, _plan_sql includes context in the prompt."""

    def test_context_injected_into_plan_sql_prompt(self):
        prior_context = (
            "[user] How many phase 3 trials for semaglutide?\n"
            "[assistant] There are 4 phase 3 trials.\n"
            "  Prior SQL: SELECT COUNT(*) FROM clinical_trials ct JOIN drugs d ON ct.drug_id = d.id "
            "WHERE d.generic_name = 'semaglutide' AND ct.phase = 'Phase 3'"
        )

        # Track what LLM receives
        received_prompts: list[str] = []

        def tracking_response(messages):
            for msg in messages:
                received_prompts.append(getattr(msg, "content", ""))
            return json.dumps({
                "sql": "SELECT ct.title FROM clinical_trials ct JOIN drugs d ON ct.drug_id = d.id "
                       "WHERE d.generic_name = 'semaglutide' AND ct.phase = 'Phase 3'",
                "params": [],
                "explanation": "list those trials",
                "presentation_hint": "table",
            })

        llm = MockLLM(response_fn=tracking_response)
        state = _make_state(
            question="List those 4 trials",
            conversation_context=prior_context,
        )

        result = _plan_sql(state, llm=llm, schema_text=SCHEMA_TEXT)

        # The system prompt should contain the conversation context
        system_prompt = received_prompts[0] if received_prompts else ""
        assert "CONVERSATION CONTEXT" in system_prompt
        assert "semaglutide" in system_prompt
        assert "Phase 3" in system_prompt

        # Plan should reference semaglutide
        assert "semaglutide" in result["plan"].get("sql", "")

    def test_empty_context_does_not_inject_block(self):
        received_prompts: list[str] = []

        def tracking_response(messages):
            for msg in messages:
                received_prompts.append(getattr(msg, "content", ""))
            return json.dumps({
                "sql": "SELECT COUNT(*) FROM drugs",
                "params": [],
                "explanation": "count drugs",
                "presentation_hint": "scalar",
            })

        llm = MockLLM(response_fn=tracking_response)
        state = _make_state(question="How many drugs?", conversation_context="")

        _plan_sql(state, llm=llm, schema_text=SCHEMA_TEXT)

        system_prompt = received_prompts[0] if received_prompts else ""
        assert "CONVERSATION CONTEXT" not in system_prompt


# ── Contract 2: Scalar enrichment ──

class TestScalarEnrichment:
    """Given a scalar COUNT result with value ≤ 50, validate_and_enrich produces sql_detail."""

    def test_scalar_count_triggers_enrichment(self):
        scalar_result = make_sql_result([{"cnt": 4}], columns=["cnt"])
        detail_result = make_sql_result([
            {"title": "Trial A", "status": "RECRUITING", "phase": "Phase 3"},
            {"title": "Trial B", "status": "COMPLETED", "phase": "Phase 3"},
            {"title": "Trial C", "status": "RECRUITING", "phase": "Phase 3"},
            {"title": "Trial D", "status": "ACTIVE_NOT_RECRUITING", "phase": "Phase 3"},
        ])

        sql_tool = StubTool("sql", {"query": detail_result})

        state = _make_state(
            question="How many phase 3 trials?",
            plan={"sql": "SELECT COUNT(*) AS cnt FROM clinical_trials WHERE phase = 'Phase 3'"},
            tool_results={"sql": scalar_result},
        )

        result = _validate_and_enrich(state, llm=_detail_llm(), schema_text=SCHEMA_TEXT, sql_tool=sql_tool)

        assert "sql_detail" in result["tool_results"]
        detail = result["tool_results"]["sql_detail"]
        assert detail.success
        assert detail.row_count == 4
        assert "sql_detail_title" in result["tool_results"]


# ── Contract 3: No enrichment for non-scalar ──

class TestNoEnrichmentForNonScalar:
    """Given a multi-row result, validate_and_enrich does not add sql_detail."""

    def test_multi_row_result_skips_enrichment(self):
        multi_row = make_sql_result([
            {"drug": "semaglutide", "count": 10},
            {"drug": "tirzepatide", "count": 8},
            {"drug": "liraglutide", "count": 5},
        ])

        sql_tool = StubTool("sql")
        state = _make_state(
            question="How many trials by drug?",
            plan={"sql": "SELECT drug, COUNT(*) FROM trials GROUP BY drug"},
            tool_results={"sql": multi_row},
        )

        result = _validate_and_enrich(state, llm=_detail_llm(), schema_text=SCHEMA_TEXT, sql_tool=sql_tool)

        assert "sql_detail" not in result["tool_results"]

    def test_scalar_above_50_skips_enrichment(self):
        large_scalar = make_sql_result([{"cnt": 1500}], columns=["cnt"])
        sql_tool = StubTool("sql")
        state = _make_state(
            question="How many trials total?",
            plan={"sql": "SELECT COUNT(*) AS cnt FROM clinical_trials"},
            tool_results={"sql": large_scalar},
        )

        result = _validate_and_enrich(state, llm=_detail_llm(), schema_text=SCHEMA_TEXT, sql_tool=sql_tool)

        assert "sql_detail" not in result["tool_results"]
        # Should have a "may be missing a filter" warning (>1000)
        assert any("1,000" in w or "filter" in w for w in result["tool_results"].get("validation_warnings", []))


# ── Contract 4: Validation warnings ──

class TestValidationWarnings:
    """0-row or 0-count results produce validation warnings."""

    def test_zero_rows_produces_warning(self):
        empty_result = ToolResult(tool="sql", success=True, data=[], columns=["cnt"], row_count=0)
        sql_tool = StubTool("sql")
        state = _make_state(
            question="How many trials for nonexistentdrug123?",
            plan={"sql": "SELECT COUNT(*) FROM trials WHERE drug = 'nonexistent'"},
            tool_results={"sql": empty_result},
        )

        result = _validate_and_enrich(state, llm=_detail_llm(), schema_text=SCHEMA_TEXT, sql_tool=sql_tool)

        warnings = result["tool_results"].get("validation_warnings", [])
        assert len(warnings) >= 1
        assert any("0 rows" in w for w in warnings)

    def test_scalar_zero_produces_warning(self):
        zero_scalar = make_sql_result([{"cnt": 0}], columns=["cnt"])
        sql_tool = StubTool("sql")
        state = _make_state(
            question="How many trials for nonexistentdrug123?",
            plan={"sql": "SELECT COUNT(*) AS cnt FROM trials WHERE drug = 'nonexistent'"},
            tool_results={"sql": zero_scalar},
        )

        result = _validate_and_enrich(state, llm=_detail_llm(), schema_text=SCHEMA_TEXT, sql_tool=sql_tool)

        warnings = result["tool_results"].get("validation_warnings", [])
        assert len(warnings) >= 1
        assert any("0" in w and "not exist" in w for w in warnings)


# ── Contract 5: Backward compatibility ──

class TestBackwardCompatibility:
    """Graph output has all required keys: narrative, table_data, visualizations, tool_results."""

    def test_output_has_required_keys(self):
        def smart_response(messages):
            system = messages[0].content if messages else ""
            if "SQL query planner" in system:
                return json.dumps({
                    "sql": "SELECT COUNT(*) AS cnt FROM drugs",
                    "params": [],
                    "explanation": "count drugs",
                    "presentation_hint": "scalar",
                })
            if "detail SELECT" in system or "COUNT question" in system:
                return json.dumps({
                    "sql": "SELECT generic_name FROM drugs LIMIT 5",
                    "params": [],
                    "title": "Drugs",
                })
            if "Classify" in system:
                return "structured_query"
            # Synthesis
            return "There are **5** drugs in the database."

        llm = MockLLM(response_fn=smart_response)
        count_result = make_sql_result([{"cnt": 5}], columns=["cnt"])
        detail_result = make_sql_result([
            {"generic_name": "semaglutide"},
            {"generic_name": "tirzepatide"},
        ])
        sql_tool = StubTool("sql", {"query": count_result})

        graph = build_query_graph(
            llm=llm,
            sql_tool=sql_tool,
            rag_tool=StubTool("rag"),
            graph_tool=StubTool("graph"),
            metrics_tool=StubTool("metrics"),
            schema_text=SCHEMA_TEXT,
        )

        result = graph.invoke({
            "messages": [],
            "question": "How many drugs?",
            "conversation_context": "",
            "intent": "",
            "plan": {},
            "tool_results": {},
            "presentation": {},
            "table_data": None,
            "visualizations": [],
            "narrative": "",
            "error": None,
        })

        # Required output keys
        assert "narrative" in result
        assert "table_data" in result
        assert "visualizations" in result
        assert "tool_results" in result
        assert isinstance(result["narrative"], str)
        assert len(result["narrative"]) > 0
