"""LangGraph query agent — classifies, plans, executes, and presents.

Graph flow:
  classify → plan_* → exec_* → present → synthesize
"""

from __future__ import annotations

import logging
import operator
import re
from typing import Annotated, Any, Optional, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langgraph.graph import END, StateGraph

from services.agent.tools.base import ToolResult

logger = logging.getLogger(__name__)

# ── Regex patterns for structured query detection ──

_STRUCTURED_PATTERNS = [
    re.compile(r"\b(how many|count|total number|number of)\b", re.I),
    re.compile(r"\b(average|avg|mean|median)\b", re.I),
    re.compile(r"\b(top\s+\d+|bottom\s+\d+|rank|ranked)\b", re.I),
    re.compile(r"\b(by company|by drug|by phase|per company|per drug|group by|by number)\b", re.I),
    re.compile(r"\b(trend|over time|year over year|monthly|quarterly)\b", re.I),
    re.compile(r"\b(percentage|proportion|ratio|rate)\b", re.I),
    re.compile(r"\b(sum|max|min|oldest|newest|latest|earliest)\b", re.I),
    re.compile(r"\b(list all|show all|which .+ have|which companies|which drugs)\b", re.I),
    re.compile(r"\b(in phase\s*\d|phase\s*\d\b)", re.I),
    re.compile(r"\b(most|fewest|highest|lowest|biggest|smallest)\b", re.I),
]


# ── State ──

class QueryAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    question: str
    conversation_context: str            # compact summary of prior exchanges for follow-ups
    intent: str                          # structured_query | knowledge_search | hybrid
    plan: dict                           # {sql, params, explanation} or {search_params}
    tool_results: dict                   # {step_name: ToolResult}
    presentation: dict                   # PresentationConfig
    table_data: Optional[dict]           # {columns, rows, title}
    visualizations: list[dict]           # VisualizationSpec list
    narrative: str
    error: Optional[str]


def _default_state(question: str, conversation_context: str = "") -> QueryAgentState:
    return QueryAgentState(
        messages=[HumanMessage(content=question)],
        question=question,
        conversation_context=conversation_context,
        intent="",
        plan={},
        tool_results={},
        presentation={},
        table_data=None,
        visualizations=[],
        narrative="",
        error=None,
    )


# ── Node implementations ──

def _classify(state: QueryAgentState, *, llm=None) -> dict:
    """Classify intent via regex fast-path, LLM fallback."""
    q = state["question"]

    # Fast-path: count structural signal matches
    hits = sum(1 for p in _STRUCTURED_PATTERNS if p.search(q))

    if hits >= 2:
        return {"intent": "structured_query"}
    if hits == 0:
        return {"intent": "knowledge_search"}

    # 1 hit — use LLM to decide if truly structured or knowledge
    if llm is not None:
        try:
            resp = llm.invoke([
                SystemMessage(content=(
                    "Classify this question as exactly one of: structured_query, knowledge_search, hybrid.\n"
                    "structured_query: needs SQL aggregation, counting, ranking, or filtering.\n"
                    "knowledge_search: needs text evidence, entity profiles, or qualitative analysis.\n"
                    "hybrid: needs both.\n"
                    "Respond with ONLY the classification label."
                )),
                HumanMessage(content=q),
            ])
            label = resp.content.strip().lower().replace('"', "").replace("'", "")
            if label in ("structured_query", "knowledge_search", "hybrid"):
                return {"intent": label}
        except Exception as exc:
            logger.warning("LLM classification failed: %s", exc)

    # Default ambiguous to hybrid
    return {"intent": "hybrid"}


def _plan_sql(state: QueryAgentState, *, llm, schema_text: str) -> dict:
    """Generate SQL plan using LLM + schema context."""
    question = state["question"]
    conversation_context = state.get("conversation_context", "")

    # Build optional context block for follow-up resolution
    context_block = ""
    if conversation_context:
        context_block = (
            "\nCONVERSATION CONTEXT (prior exchanges):\n"
            f"{conversation_context}\n"
            "Use this to resolve pronouns like 'those', 'them', 'it', 'the above'. "
            "If the user references prior results, use the prior SQL's WHERE clause as a guide.\n\n"
        )

    try:
        resp = llm.invoke([
            SystemMessage(content=(
                "You are a SQL query planner for a pharmaceutical intelligence database.\n\n"
                f"DATABASE SCHEMA:\n{schema_text}\n\n"
                f"{context_block}"
                "RULES:\n"
                "- Generate a single SELECT query that answers the user's question.\n"
                "- Use parameterized queries where possible (use %s placeholders).\n"
                "- Always include reasonable LIMIT (max 100).\n"
                "- Use JOINs when the question spans multiple tables.\n"
                "- For entity_links joins, match link_type and entity types.\n"
                "- Use LOWER() for case-insensitive text comparisons on free-text columns.\n"
                "- Cast UUIDs explicitly: column::text when comparing with text values.\n"
                "- CRITICAL: clinical_trials.status values are ALWAYS UPPERCASE with underscores:\n"
                "  'RECRUITING', 'ACTIVE_NOT_RECRUITING', 'COMPLETED', 'TERMINATED', 'WITHDRAWN',\n"
                "  'NOT_YET_RECRUITING', 'SUSPENDED'. NEVER use mixed case like 'Recruiting'.\n"
                "- CRITICAL: clinical_trials.phase values use 'Phase 1', 'Phase 2', 'Phase 3', 'Phase 4'.\n"
                "- When the user asks 'how many drugs are in Phase X trials', they usually mean\n"
                "  'how many clinical trials in Phase X mention that drug' — COUNT on clinical_trials, not drugs.\n"
                "- For questions about a SPECIFIC drug (e.g. 'for semaglutide'), filter by\n"
                "  LOWER(drugs.generic_name) or use ILIKE on clinical_trials joined to drugs.\n\n"
                "Respond with ONLY a JSON object:\n"
                '{"sql": "SELECT ...", "params": [], "explanation": "brief description",'
                ' "presentation_hint": "scalar|bar|donut|line|table"}'
            )),
            HumanMessage(content=question),
        ])

        import json
        raw = resp.content.strip()
        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        plan = json.loads(raw)
        logger.info("SQL plan: %s", plan.get("sql", "")[:200])
        return {"plan": plan}
    except Exception as exc:
        logger.warning("SQL planning failed: %s", exc)
        return {"plan": {}, "error": f"SQL planning failed: {exc}"}


def _plan_rag(state: QueryAgentState) -> dict:
    """Deterministic RAG plan — no LLM needed."""
    return {
        "plan": {
            "type": "rag",
            "query": state["question"],
            "limit": 10,
            "include_graph": True,
            "include_metrics": True,
        }
    }


def _plan_hybrid(state: QueryAgentState, *, llm, schema_text: str) -> dict:
    """Plan both SQL and RAG components."""
    sql_result = _plan_sql(state, llm=llm, schema_text=schema_text)
    rag_result = _plan_rag(state)

    plan = {
        "type": "hybrid",
        "sql_plan": sql_result.get("plan", {}),
        "rag_plan": rag_result.get("plan", {}),
    }
    return {"plan": plan, "error": sql_result.get("error")}


def _exec_sql(state: QueryAgentState, *, sql_tool) -> dict:
    """Execute the SQL plan."""
    plan = state["plan"]
    sql = plan.get("sql", "")
    params = plan.get("params", [])

    if not sql:
        return {"tool_results": {**state["tool_results"], "sql": ToolResult(
            tool="sql", success=False, error="No SQL in plan",
        )}}

    result = sql_tool.execute("query", {"sql": sql, "query_params": params})
    return {"tool_results": {**state["tool_results"], "sql": result}}


def _exec_rag(state: QueryAgentState, *, rag_tool, graph_tool, metrics_tool) -> dict:
    """Execute RAG search + graph + metrics."""
    plan = state["plan"] if state["plan"].get("type") != "hybrid" else state["plan"].get("rag_plan", {})
    question = state["question"]
    results = dict(state["tool_results"])

    # RAG search
    rag_result = rag_tool.execute("search", {"query": question, "limit": plan.get("limit", 10)})
    results["rag"] = rag_result

    # Graph expansion on top entity
    if plan.get("include_graph", True) and rag_result.success and rag_result.data:
        top = rag_result.data[0]
        graph_result = graph_tool.execute("neighborhood", {
            "entity_id": top.get("entity_id", ""),
            "entity_type": top.get("entity_type", "drug"),
        })
        results["graph"] = graph_result

    # Metrics
    if plan.get("include_metrics", True):
        metrics_result = metrics_tool.execute("pipeline", {"limit": 10})
        results["metrics"] = metrics_result

    return {"tool_results": results}


def _exec_hybrid(state: QueryAgentState, *, sql_tool, rag_tool, graph_tool, metrics_tool) -> dict:
    """Execute both SQL and RAG paths."""
    # SQL part
    sql_plan = state["plan"].get("sql_plan", {})
    sql_result = sql_tool.execute("query", {
        "sql": sql_plan.get("sql", ""),
        "query_params": sql_plan.get("params", []),
    }) if sql_plan.get("sql") else ToolResult(tool="sql", success=False, error="No SQL")

    results = {**state["tool_results"], "sql": sql_result}

    # RAG part
    rag_result = rag_tool.execute("search", {"query": state["question"], "limit": 8})
    results["rag"] = rag_result

    return {"tool_results": results}


def _validate_and_enrich(state: QueryAgentState, *, llm, schema_text: str, sql_tool) -> dict:
    """Validate SQL results and proactively enrich scalar counts with detail rows."""
    tool_results = dict(state["tool_results"])
    sql_result = tool_results.get("sql")
    warnings: list[str] = []

    # ── Validation (heuristic, no LLM) ──
    if sql_result and sql_result.success:
        if sql_result.row_count == 0:
            warnings.append("Query returned 0 rows — the entity may not exist in the database or filters may be too narrow.")
        elif sql_result.is_scalar:
            val = sql_result.scalar_value
            try:
                num_val = int(val) if val is not None else None
            except (TypeError, ValueError):
                num_val = None
            if num_val == 0:
                warnings.append("Count is 0 — the entity may not exist in the database.")
            elif num_val is not None and num_val > 1000:
                warnings.append("Count exceeds 1,000 — the query may be missing a filter.")
    elif sql_result and not sql_result.success:
        warnings.append(f"SQL execution failed: {sql_result.error or 'unknown error'}")

    if warnings:
        tool_results["validation_warnings"] = warnings

    # ── Enrichment (conditional: scalar positive int ≤ 50) ──
    if (
        sql_result
        and sql_result.success
        and sql_result.is_scalar
    ):
        val = sql_result.scalar_value
        try:
            num_val = int(val) if val is not None else None
        except (TypeError, ValueError):
            num_val = None

        if num_val is not None and 1 <= num_val <= 50:
            try:
                original_sql = state["plan"].get("sql", "")
                resp = llm.invoke([
                    SystemMessage(content=(
                        "You are a SQL query planner. The user asked a COUNT question and got a scalar result.\n"
                        "Now generate a detail SELECT that returns the actual rows behind the count.\n\n"
                        f"DATABASE SCHEMA:\n{schema_text}\n\n"
                        "RULES:\n"
                        "- Reuse the same WHERE clause and JOINs from the original COUNT query.\n"
                        "- Replace COUNT(*) with useful columns: title, name, status, phase, NCT ID, etc.\n"
                        "- Keep the same LIMIT or use the count value as LIMIT.\n"
                        "- Respond with ONLY a JSON object: {\"sql\": \"SELECT ...\", \"params\": [], \"title\": \"brief title\"}\n"
                    )),
                    HumanMessage(content=f"Original COUNT SQL:\n{original_sql}\n\nCount result: {num_val}"),
                ])
                import json
                raw = resp.content.strip()
                if raw.startswith("```"):
                    raw = re.sub(r"^```(?:json)?\s*", "", raw)
                    raw = re.sub(r"\s*```$", "", raw)
                detail_plan = json.loads(raw)
                detail_sql = detail_plan.get("sql", "")
                detail_params = detail_plan.get("params", [])
                detail_title = detail_plan.get("title", "Detail")

                if detail_sql:
                    detail_result = sql_tool.execute("query", {"sql": detail_sql, "query_params": detail_params})
                    if detail_result.success and detail_result.data:
                        tool_results["sql_detail"] = detail_result
                        tool_results["sql_detail_title"] = detail_title
                        logger.info("Enrichment: fetched %d detail rows", detail_result.row_count)
            except Exception as exc:
                logger.warning("Enrichment LLM/SQL failed (non-fatal): %s", exc)

    return {"tool_results": tool_results}


def _present(state: QueryAgentState) -> dict:
    """Deterministic presentation planning based on data shape."""
    from services.agent.presenter import plan_presentation
    pres = plan_presentation(state["tool_results"], question=state.get("question", ""))
    return {
        "presentation": pres,
        "table_data": pres.get("table_data"),
        "visualizations": pres.get("visualizations", []),
    }


def _build_domain_context(tool_results: dict) -> str:
    """Detect pharma-specific patterns in data and return analyst instructions."""
    hints: list[str] = []

    sql_result = tool_results.get("sql") or tool_results.get("exec_sql")
    columns: list[str] = []
    if sql_result and getattr(sql_result, "success", False):
        columns = [c.lower() for c in (sql_result.columns or [])]

    col_set = set(columns)

    # Phase data → pipeline maturity commentary
    phase_cols = {"p1_count", "p2_count", "p3_count", "p4_count", "phase", "pipeline_score"}
    if col_set & phase_cols:
        hints.append(
            "Data contains pipeline phase information. Comment on pipeline maturity "
            "and late-stage strength. Late-stage (Phase 3+) trials are the strongest "
            "signal of commercial viability."
        )

    # Success rate → pharma benchmarks
    if col_set & {"success_rate", "completed", "terminated"}:
        hints.append(
            "Data contains success rate metrics. Compare to typical pharma benchmarks: "
            "Phase 2→3 advancement ~30%, Phase 3→approval ~60%. Call out entities "
            "that significantly beat or trail these benchmarks."
        )

    # Multiple entities → comparative language
    rows = sql_result.data if (sql_result and getattr(sql_result, "success", False)) else []
    if len(rows) >= 2:
        hints.append(
            "Multiple entities present. Use comparative language with computed differentials "
            "('3x stronger', 'leads by 12 trials', '+15% higher success rate'). "
            "Don't just list values side-by-side."
        )

    if not hints:
        return ""

    return "\n\nDOMAIN CONTEXT:\n" + "\n".join(f"- {h}" for h in hints)


def _synthesize(state: QueryAgentState, *, llm) -> dict:
    """LLM synthesis of narrative from tool results."""
    question = state["question"]
    tool_results = state["tool_results"]

    # Build context from tool results
    context_parts = []

    sql_result = tool_results.get("sql")
    if sql_result and sql_result.success and sql_result.data:
        rows_preview = sql_result.data[:20]
        context_parts.append(f"SQL RESULTS ({sql_result.row_count} rows):\n{_format_rows(rows_preview)}")

    rag_result = tool_results.get("rag")
    if rag_result and rag_result.success and rag_result.data:
        snippets = [item.get("content", "")[:200] for item in rag_result.data[:5]]
        context_parts.append(f"EVIDENCE ({rag_result.row_count} items):\n" + "\n".join(f"- {s}" for s in snippets))

    graph_result = tool_results.get("graph")
    if graph_result and graph_result.success and graph_result.data:
        gd = graph_result.data
        context_parts.append(
            f"GRAPH CONTEXT: {graph_result.metadata.get('node_count', 0)} nodes, "
            f"{graph_result.metadata.get('edge_count', 0)} edges"
        )

    presentation = state.get("presentation", {})
    display = presentation.get("display", "narrative_only")

    # Include detail rows if enrichment produced them
    sql_detail = tool_results.get("sql_detail")
    if sql_detail and sql_detail.success and sql_detail.data:
        detail_preview = sql_detail.data[:20]
        detail_title = tool_results.get("sql_detail_title", "Details")
        context_parts.append(f"DETAIL ROWS ({detail_title}, {sql_detail.row_count} rows):\n{_format_rows(detail_preview)}")

    # Include validation warnings
    validation_warnings = tool_results.get("validation_warnings", [])
    if validation_warnings:
        context_parts.append("VALIDATION NOTES:\n" + "\n".join(f"- {w}" for w in validation_warnings))

    if not context_parts:
        return {"narrative": "I couldn't find sufficient data to answer this question. Try rephrasing or being more specific."}

    try:
        # Adapt verbosity based on intent and data shape
        intent = state.get("intent", "")
        sql_result = tool_results.get("sql")
        is_scalar = (sql_result and sql_result.success and sql_result.row_count == 1
                     and len(sql_result.columns) <= 2)
        is_small_table = (sql_result and sql_result.success and sql_result.row_count <= 10)

        if intent == "structured_query" and is_scalar:
            synth_instructions = (
                "You are a pharmaceutical intelligence analyst.\n"
                "The user asked a quantitative question and the SQL result is shown below.\n\n"
                "RULES:\n"
                "- Answer in 1-2 sentences MAX. Lead with the exact number.\n"
                "- Bold the **key metric**.\n"
                "- If DETAIL ROWS are present, mention key details briefly (do NOT say 'see the table below').\n"
                "- If VALIDATION NOTES are present, mention caveats briefly.\n"
                "- Do NOT add commentary about market implications, patient value, or investment outlook.\n"
                "- Do NOT invent data not present in the context.\n"
            )
        elif intent == "structured_query" and is_small_table:
            synth_instructions = (
                "You are a pharmaceutical intelligence analyst.\n"
                "The user asked a data question and the SQL results are shown below.\n\n"
                "RULES:\n"
                "- Write 1-3 sentences summarizing the key findings from the table.\n"
                "- Mention the top entries by name and their values.\n"
                "- Bold **key entities** and **metrics**.\n"
                "- Do NOT add filler about market implications or investment outlook.\n"
                "- Do NOT invent data not present in the context.\n"
                "- A table is being shown alongside this narrative, so don't repeat every row.\n"
            )
        else:
            domain_ctx = _build_domain_context(tool_results)
            synth_instructions = (
                "You are a pharmaceutical intelligence analyst. Synthesize the data below "
                "into a concise, analyst-grade narrative (2-4 paragraphs max).\n\n"
                "RULES:\n"
                "- Lead with the single most important insight or direct answer.\n"
                "- Use specific numbers from the data. Bold **key entities** and **metrics**.\n"
                "- When comparing entities, compute differentials (e.g. 'X leads Y by 12 trials', "
                "'2.3x stronger pipeline') instead of listing values side-by-side.\n"
                "- Note outliers explicitly (e.g. 'significantly above/below average').\n"
                "- Reference evidence with [N] citation markers.\n"
                "- Do NOT reference 'table below' or 'chart below' — the user sees data in a separate canvas panel, not inline.\n"
                "- Do NOT mention node/edge counts from graph context — the user cannot see raw graph metadata.\n"
                "- Do NOT invent data not present in the context.\n"
                f"- Display format: {display}\n"
                f"{domain_ctx}"
            )

        resp = llm.invoke([
            SystemMessage(content=synth_instructions),
            HumanMessage(content=f"QUESTION: {question}\n\n" + "\n\n".join(context_parts)),
        ])
        return {"narrative": resp.content.strip()}
    except Exception as exc:
        logger.warning("Synthesis failed: %s", exc)
        # Fallback narrative from data
        return {"narrative": _build_fallback_narrative(question, tool_results)}


def _format_rows(rows: list[dict], max_rows: int = 20) -> str:
    """Format rows into a compact text table for LLM context."""
    if not rows:
        return "(empty)"
    cols = list(rows[0].keys())
    lines = [" | ".join(cols)]
    for r in rows[:max_rows]:
        lines.append(" | ".join(str(r.get(c, ""))[:40] for c in cols))
    return "\n".join(lines)


def _build_fallback_narrative(question: str, tool_results: dict) -> str:
    """Build a template narrative when LLM synthesis fails."""
    parts = []
    sql = tool_results.get("sql")
    if sql and sql.success:
        parts.append(f"Found **{sql.row_count}** results from database query.")
    rag = tool_results.get("rag")
    if rag and rag.success:
        parts.append(f"Found **{rag.row_count}** evidence items from knowledge search.")
    if not parts:
        parts.append("Limited data available for this query.")
    return " ".join(parts)


# ── Routing ──

def _route_after_classify(state: QueryAgentState) -> str:
    intent = state["intent"]
    if intent == "structured_query":
        return "plan_sql"
    if intent == "knowledge_search":
        return "plan_rag"
    return "plan_hybrid"


def _route_after_plan(state: QueryAgentState) -> str:
    plan = state.get("plan", {})
    plan_type = plan.get("type", "")
    if plan_type == "hybrid":
        return "exec_hybrid"
    if plan_type == "rag":
        return "exec_rag"
    # Default: SQL if there's a sql key
    if plan.get("sql"):
        return "exec_sql"
    return "exec_rag"


# ── Graph builder ──

def build_query_graph(
    *,
    llm,
    sql_tool,
    rag_tool,
    graph_tool,
    metrics_tool,
    schema_text: str,
):
    """Build and compile the query agent StateGraph."""

    graph = StateGraph(QueryAgentState)

    # Add nodes with bound dependencies
    graph.add_node("classify", lambda s: _classify(s, llm=llm))
    graph.add_node("plan_sql", lambda s: _plan_sql(s, llm=llm, schema_text=schema_text))
    graph.add_node("plan_rag", _plan_rag)
    graph.add_node("plan_hybrid", lambda s: _plan_hybrid(s, llm=llm, schema_text=schema_text))
    graph.add_node("exec_sql", lambda s: _exec_sql(s, sql_tool=sql_tool))
    graph.add_node("exec_rag", lambda s: _exec_rag(
        s, rag_tool=rag_tool, graph_tool=graph_tool, metrics_tool=metrics_tool,
    ))
    graph.add_node("exec_hybrid", lambda s: _exec_hybrid(
        s, sql_tool=sql_tool, rag_tool=rag_tool, graph_tool=graph_tool, metrics_tool=metrics_tool,
    ))
    graph.add_node("validate_and_enrich", lambda s: _validate_and_enrich(
        s, llm=llm, schema_text=schema_text, sql_tool=sql_tool,
    ))
    graph.add_node("present", _present)
    graph.add_node("synthesize", lambda s: _synthesize(s, llm=llm))

    # Entry point
    graph.set_entry_point("classify")

    # Routing
    graph.add_conditional_edges("classify", _route_after_classify, {
        "plan_sql": "plan_sql",
        "plan_rag": "plan_rag",
        "plan_hybrid": "plan_hybrid",
    })

    graph.add_conditional_edges("plan_sql", _route_after_plan, {
        "exec_sql": "exec_sql",
        "exec_rag": "exec_rag",
    })
    graph.add_edge("plan_rag", "exec_rag")
    graph.add_conditional_edges("plan_hybrid", _route_after_plan, {
        "exec_hybrid": "exec_hybrid",
        "exec_rag": "exec_rag",
    })

    # All execution paths → validate_and_enrich → present → synthesize
    graph.add_edge("exec_sql", "validate_and_enrich")
    graph.add_edge("exec_rag", "validate_and_enrich")
    graph.add_edge("exec_hybrid", "validate_and_enrich")
    graph.add_edge("validate_and_enrich", "present")
    graph.add_edge("present", "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile()


def has_structured_signals(question: str) -> bool:
    """Check if a question has signals that suggest it needs SQL-based answers.

    Used by chat.py detect_intent to route to the agent graph.
    Returns True if at least 1 pattern matches (lowered from 2).
    """
    q = question.lower().strip()
    hits = sum(1 for p in _STRUCTURED_PATTERNS if p.search(q))
    return hits >= 1
