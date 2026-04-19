"""Smoke test for the existing query_graph against drug-pipeline queries.

Goal: verify the graph CAN handle "Show pipeline for semaglutide" today
(with mocked tools) before we commit to Track 1 (route all intents through it).

If this passes, Phase 1 is wiring (extend planner with intent_hint, replace
if/elif chain). If this fails, the graph itself needs fixes first.

Per SPEC_016 Track 1 sequencing.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from services.agent.tools.base import BaseTool, ToolResult


# ────────────────────────────────────────────────────────────────────
# Mock tools
# ────────────────────────────────────────────────────────────────────

class _MockTool(BaseTool):
    """Minimal BaseTool implementation that records calls and returns canned data."""

    def __init__(self, name: str, canned_result: dict):
        self._name = name
        self._canned = canned_result
        self.calls: list[dict] = []

    @property
    def name(self) -> str:
        return self._name

    def execute(self, action, params, prior_results=None):
        self.calls.append({"action": action, "params": params})
        # Determine row_count and columns based on canned data shape
        if isinstance(self._canned, list):
            data = self._canned
            row_count = len(data)
            columns = list(data[0].keys()) if data and isinstance(data[0], dict) else []
        elif isinstance(self._canned, dict):
            data = self._canned
            rows = self._canned.get("rows")
            row_count = len(rows) if isinstance(rows, list) else 0
            columns = self._canned.get("columns", [])
        else:
            data = self._canned
            row_count = 0
            columns = []
        return ToolResult(
            tool=self._name,
            success=True,
            data=data,
            columns=columns,
            row_count=row_count,
            metadata={"mock": True},
        )


def _build_mock_llm(plan_response: str = '{"sql": "SELECT * FROM drugs WHERE generic_name = \'semaglutide\'", "params": [], "explanation": "Find semaglutide drug record"}'):
    """Mock LLM that returns deterministic planning output."""
    llm = MagicMock()

    def _invoke(messages):
        # Return different content depending on the system message
        last = messages[-1].content if hasattr(messages[-1], "content") else ""
        sys_msg = messages[0].content if len(messages) > 1 and hasattr(messages[0], "content") else ""

        # Classification step → return "structured_query" if drug name + "pipeline"
        if "Classify this question" in sys_msg:
            return MagicMock(content="structured_query")
        # Planning step → return SQL plan
        if "schema" in sys_msg.lower() or "sql" in sys_msg.lower():
            return MagicMock(content=plan_response)
        # Synthesis step → return narrative
        return MagicMock(content="Semaglutide is a GLP-1 receptor agonist with multiple Phase 3 trials.")

    llm.invoke = _invoke
    return llm


# ────────────────────────────────────────────────────────────────────
# Smoke tests
# ────────────────────────────────────────────────────────────────────

def test_query_graph_can_be_built():
    """Sanity: the graph factory builds without error given mock dependencies."""
    from services.agent.graphs.query_graph import build_query_graph

    sql_tool = _MockTool("sql", {"rows": [{"id": "uuid-sema", "generic_name": "semaglutide"}]})
    # RAG tool data must be a list (graph reads .data[0] for top entity)
    rag_tool = _MockTool("rag", [{"entity_id": "uuid-sema", "entity_type": "drug", "title": "semaglutide", "content": "stub"}])
    graph_tool = _MockTool("graph", {"nodes": [], "edges": []})
    metrics_tool = _MockTool("metrics", {"pipelines": []})

    graph = build_query_graph(
        llm=_build_mock_llm(),
        sql_tool=sql_tool,
        rag_tool=rag_tool,
        graph_tool=graph_tool,
        metrics_tool=metrics_tool,
        schema_text="drugs(id uuid, generic_name text, brand_name text)",
    )
    assert graph is not None


def test_query_graph_misclassifies_drug_pipeline_query_today():
    """SMOKE-TEST FINDING: drug-pipeline queries route to RAG, not SQL.

    Today's classify() function uses regex patterns like "list all", "phase 1",
    "how many", "most/fewest". "Show pipeline for semaglutide" hits ZERO of
    those patterns, so the regex pre-classifier returns 'knowledge_search'
    and the LLM fallback never runs.

    The query then goes to plan_rag → exec_rag, which does text similarity
    search — wrong tool for a structured pipeline question.

    Per SPEC_016 Track 1 Phase 1: add intent_hint param so the chat route
    can pass the detected intent (PIPELINE → structured) and bypass the
    pattern-counting heuristic for known-structured intents.

    This test asserts the CURRENT (broken) behavior so it serves as the
    baseline. After Phase 1 ships, flip the assertion.
    """
    from services.agent.graphs.query_graph import build_query_graph

    sql_tool = _MockTool("sql", {
        "rows": [{
            "drug_id": "uuid-sema",
            "drug_name": "semaglutide",
            "p3_count": 3,
            "total_trials": 8,
            "pipeline_score": 18.0,
        }],
        "row_count": 1,
        "columns": ["drug_id", "drug_name", "p3_count", "total_trials", "pipeline_score"],
    })
    # RAG tool data must be a list (graph reads .data[0] for top entity)
    rag_tool = _MockTool("rag", [{"entity_id": "uuid-sema", "entity_type": "drug", "title": "semaglutide", "content": "stub"}])
    graph_tool = _MockTool("graph", {"nodes": [], "edges": []})
    metrics_tool = _MockTool("metrics", {"pipelines": []})

    graph = build_query_graph(
        llm=_build_mock_llm(),
        sql_tool=sql_tool,
        rag_tool=rag_tool,
        graph_tool=graph_tool,
        metrics_tool=metrics_tool,
        schema_text="drugs(id uuid, generic_name text, brand_name text)\nclinical_trials(...)\nmv_drug_pipeline_strength(...)",
    )

    final_state = graph.invoke({
        "messages": [],
        "question": "Show pipeline for semaglutide",
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

    # CURRENT (broken) behavior: classified as knowledge_search, routed to RAG.
    # After SPEC_016 Phase 1, this assertion should FLIP to expecting structured_query.
    assert final_state.get("intent") == "knowledge_search", (
        f"Smoke test premise: today the graph misclassifies drug-pipeline as "
        f"knowledge_search. Got: {final_state.get('intent')!r}. "
        f"If this changed, update the test."
    )
    assert len(rag_tool.calls) >= 1, (
        "Today: RAG tool gets called instead of SQL/Metrics. "
        f"sql_calls={len(sql_tool.calls)} rag_calls={len(rag_tool.calls)} "
        f"metrics_calls={len(metrics_tool.calls)}"
    )


def test_query_graph_produces_narrative_output():
    """The synthesize step should populate the narrative field."""
    from services.agent.graphs.query_graph import build_query_graph

    sql_tool = _MockTool("sql", {"rows": [{"col": "value"}], "row_count": 1, "columns": ["col"]})
    # RAG tool data must be a list (graph reads .data[0] for top entity)
    rag_tool = _MockTool("rag", [{"entity_id": "uuid-sema", "entity_type": "drug", "title": "semaglutide", "content": "stub"}])
    graph_tool = _MockTool("graph", {"nodes": [], "edges": []})
    metrics_tool = _MockTool("metrics", {"pipelines": []})

    graph = build_query_graph(
        llm=_build_mock_llm(),
        sql_tool=sql_tool,
        rag_tool=rag_tool,
        graph_tool=graph_tool,
        metrics_tool=metrics_tool,
        schema_text="drugs(...)",
    )

    final_state = graph.invoke({
        "messages": [],
        "question": "Show pipeline for semaglutide",
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

    assert final_state.get("narrative"), (
        "Expected synthesize step to produce narrative; got empty"
    )
    # Mock returns "Semaglutide is a GLP-1 receptor agonist..."
    assert "semaglutide" in final_state["narrative"].lower()


def test_query_graph_intent_hint_not_yet_supported():
    """SPEC_016 Track 1 Phase 1: add intent_hint param to bias planning.

    This test EXPECTS to fail today (no intent_hint support) — it documents
    the gap that Phase 1 must close. When Phase 1 ships, this test moves to
    asserting the intent_hint actually biases the planner.
    """
    from services.agent.graphs.query_graph import QueryAgentState
    fields = QueryAgentState.__annotations__ if hasattr(QueryAgentState, "__annotations__") else {}
    has_hint = "intent_hint" in fields
    if has_hint:
        pytest.skip("intent_hint already supported — Phase 1 partially shipped")
    pytest.xfail(
        "SPEC_016 Track 1 Phase 1: QueryAgentState must add intent_hint field "
        "so chat.py can pass detected intent (dossier/compare/landscape/...) "
        "as a planning bias to the LLM planner."
    )
