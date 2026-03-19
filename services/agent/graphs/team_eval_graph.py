"""LangGraph team eval agent — multi-persona fan-out with independent tool queries.

Graph flow:
  extract_entities → route_team → [persona_node × N in parallel] → synthesize → present

Each persona independently queries the database using its assigned tools
(sql, rag, graph, metrics) rather than receiving a shared blob.
"""

from __future__ import annotations

import json
import logging
import operator
import re
from typing import Annotated, Optional, TypedDict

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langgraph.types import Send
from langgraph.graph import END, StateGraph

from services.agent.tools.base import ToolResult

logger = logging.getLogger(__name__)


# ── State ──

class TeamEvalState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    question: str
    extracted_entities: dict              # {"drugs": [], "companies": [], "conditions": [], "mechanisms": []}
    active_personas: list[str]
    persona_analyses: Annotated[list[dict], operator.add]
    tool_results: dict                    # aggregated from personas for backward compat
    combined_narrative: str
    confidence_assessment: dict
    presentation: dict
    table_data: Optional[dict]
    visualizations: list[dict]


class PersonaInput(TypedDict):
    """Input passed to each persona node via Send."""
    question: str
    persona_name: str
    extracted_entities: dict
    schema_text: str


# ── Per-persona SQL instructions ──

_PERSONA_SQL_INSTRUCTIONS = {
    "market_analyst": (
        "Generate 1-2 SQL queries for competitive/market analysis. Focus on:\n"
        "- Pipeline scores and rankings for the mentioned drugs\n"
        "- Company drug counts and competitive positioning\n"
        "- Market segment comparisons\n"
        "Return a JSON array of objects with 'sql' and 'label' keys."
    ),
    "regulatory_expert": (
        "Generate 1-2 SQL queries for regulatory analysis. Focus on:\n"
        "- Trial phase distribution (count by phase) for the mentioned drugs\n"
        "- Trial status breakdown (RECRUITING, COMPLETED, etc.)\n"
        "- Approval pathway indicators\n"
        "Return a JSON array of objects with 'sql' and 'label' keys."
    ),
    "data_scientist": (
        "Generate 1-2 SQL queries for data quality assessment. Focus on:\n"
        "- Row counts per entity type related to the mentioned drugs\n"
        "- Null rates in key columns\n"
        "- Entity_links density for the drugs\n"
        "Return a JSON array of objects with 'sql' and 'label' keys."
    ),
}


# ── Node implementations ──

def _extract_entities(state: TeamEvalState, *, llm) -> dict:
    """Extract drug names, companies, conditions, mechanisms from the question."""
    question = state["question"]

    try:
        resp = llm.invoke([
            SystemMessage(content=(
                "You are an entity extractor for pharmaceutical intelligence queries.\n"
                "Extract all drug names (generic + brand), company names, medical conditions, "
                "and mechanisms of action from the user's question.\n\n"
                "IMPORTANT: If a brand name is mentioned, also include the generic name "
                "(e.g., Mounjaro → also include tirzepatide, Ozempic → also include semaglutide, "
                "Wegovy → also include semaglutide, Jardiance → also include empagliflozin).\n\n"
                "Respond with a JSON object (no markdown fences):\n"
                '{"drugs": [...], "conditions": [...], "companies": [...], "mechanisms": [...]}\n\n'
                "If no entities of a type are found, use an empty list."
            )),
            HumanMessage(content=question),
        ])

        entities = _parse_entity_json(resp.content.strip())
        logger.info("Extracted entities: %s", entities)
        return {"extracted_entities": entities}

    except Exception as exc:
        logger.warning("Entity extraction failed: %s, falling back to noun splitting", exc)
        entities = _fallback_entity_extraction(question)
        return {"extracted_entities": entities}


def _route_team(state: TeamEvalState, *, llm, personas: dict, schema_text: str) -> list[Send]:
    """LLM-based routing to select relevant personas, then fan-out via Send."""
    question = state["question"]
    available = list(personas.keys())

    selected = available  # default: all personas
    if llm is not None:
        try:
            persona_desc = "\n".join(
                f"- {name}: {p.get('focus', '')}" for name, p in personas.items()
            )
            resp = llm.invoke([
                SystemMessage(content=(
                    "You are routing a pharmaceutical intelligence question to specialist analysts.\n\n"
                    f"Available analysts:\n{persona_desc}\n\n"
                    "Select the 2-4 most relevant analysts for this question.\n"
                    "Respond with ONLY a comma-separated list of analyst names "
                    "(e.g., clinical_researcher, market_analyst)."
                )),
                HumanMessage(content=question),
            ])
            parsed = [
                name.strip().lower().replace(" ", "_")
                for name in resp.content.strip().split(",")
            ]
            valid = [name for name in parsed if name in personas]
            if len(valid) >= 2:
                selected = valid
        except Exception as exc:
            logger.warning("Team routing LLM failed: %s", exc)

    return [
        Send("persona_node", PersonaInput(
            question=state["question"],
            persona_name=name,
            extracted_entities=state.get("extracted_entities", {}),
            schema_text=schema_text,
        ))
        for name in selected
    ]


def _persona_node(
    state: PersonaInput,
    *,
    llm,
    personas: dict,
    sql_tool,
    rag_tool,
    graph_tool,
    metrics_tool,
) -> dict:
    """Single persona node: Phase A (targeted queries) then Phase B (grounded LLM analysis)."""
    question = state["question"]
    persona_name = state["persona_name"]
    extracted_entities = state.get("extracted_entities", {})
    schema_text = state.get("schema_text", "")
    persona_config = personas.get(persona_name, {})

    system_prompt = persona_config.get("system_prompt", f"You are a {persona_name}.")
    focus = persona_config.get("focus", "")
    display_name = persona_config.get("display_name", persona_name.replace("_", " ").title())
    allowed_tools = persona_config.get("tools", [])

    # ── Phase A: Targeted data gathering ──
    evidence_items = []

    if "rag" in allowed_tools:
        rag_evidence = _persona_rag_queries(rag_tool, question, extracted_entities, persona_name)
        evidence_items.extend(rag_evidence)

    if "graph" in allowed_tools:
        graph_evidence = _persona_graph_queries(graph_tool, rag_tool, extracted_entities)
        evidence_items.extend(graph_evidence)

    if "sql" in allowed_tools:
        sql_evidence = _persona_sql_queries(
            sql_tool, llm, question, extracted_entities, schema_text, persona_name,
        )
        evidence_items.extend(sql_evidence)

    if "metrics" in allowed_tools:
        metrics_evidence = _persona_metrics_queries(metrics_tool, extracted_entities, persona_name)
        evidence_items.extend(metrics_evidence)

    # ── Phase B: Grounded LLM analysis ──
    context = _build_evidence_context(evidence_items)

    try:
        resp = llm.invoke([
            SystemMessage(content=(
                f"{system_prompt}\n\n"
                f"Focus area: {focus}\n\n"
                "Evaluate this question from your specialist perspective.\n\n"
                "You MUST respond with a JSON object (no markdown fences) with these exact keys:\n"
                "{\n"
                '  "analysis": "2-3 paragraph analysis text",\n'
                '  "confidence": "high" or "medium" or "low",\n'
                '  "key_findings": ["finding 1", "finding 2", "finding 3"],\n'
                '  "data_gaps": ["gap 1", "gap 2"]\n'
                "}\n\n"
                "GROUNDING RULES (MANDATORY):\n"
                "- ONLY cite data from the DATABASE EVIDENCE above.\n"
                "- Every claim MUST include a [N] citation referencing a specific evidence item.\n"
                "- If no relevant data exists, explicitly state: \"No data found in database for X.\"\n"
                "- NEVER fill gaps with general knowledge, training data, or assumptions.\n"
                "- A short grounded answer is better than a long hallucinated one.\n"
                "- If DATABASE EVIDENCE is empty, set confidence to \"low\" and key_findings to [].\n\n"
                f"DATABASE EVIDENCE ({len(evidence_items)} items):\n{context}"
            )),
            HumanMessage(content=f"Question: {question}"),
        ])

        raw = resp.content.strip()
        parsed = _parse_persona_json(raw)

        # If no evidence was gathered but persona returned high confidence, downgrade
        if not evidence_items and parsed["confidence"] > 0.35:
            parsed["confidence"] = 0.35

        return {"persona_analyses": [{
            "persona": persona_name,
            "display_name": display_name,
            "analysis": parsed["analysis"],
            "confidence": parsed["confidence"],
            "key_findings": parsed["key_findings"],
            "data_gaps": parsed["data_gaps"],
            "evidence_items": evidence_items,
        }]}
    except Exception as exc:
        logger.warning("Persona %s failed: %s", persona_name, exc)
        return {"persona_analyses": [{
            "persona": persona_name,
            "display_name": display_name,
            "analysis": f"Analysis unavailable: {exc}",
            "confidence": 0.0,
            "key_findings": [],
            "data_gaps": ["Unable to complete analysis"],
            "evidence_items": evidence_items,
        }]}


def _synthesize_team(state: TeamEvalState, *, llm) -> dict:
    """Lead analyst synthesizes all persona analyses with grounding verification."""
    question = state["question"]
    analyses = state["persona_analyses"]

    if not analyses:
        return {
            "combined_narrative": "No specialist analyses were completed.",
            "confidence_assessment": {"overall": 0.0, "by_dimension": {}},
            "tool_results": {},
        }

    # Build synthesis prompt
    persona_summaries = []
    by_dimension = {}
    for a in analyses:
        conf_val = a["confidence"]
        if isinstance(conf_val, (int, float)):
            conf_str = f"{conf_val:.0%}"
        else:
            conf_str = str(conf_val)

        persona_summaries.append(
            f"## {a['display_name']}\n"
            f"Confidence: {conf_str}\n"
            f"Analysis: {a['analysis'][:500]}\n"
            f"Key findings: {', '.join(a.get('key_findings', [])[:3])}\n"
            f"Data gaps: {', '.join(a.get('data_gaps', [])[:2])}"
        )
        by_dimension[a["persona"]] = a["confidence"]

    overall_confidence = sum(a["confidence"] for a in analyses) / len(analyses) if analyses else 0.0

    try:
        resp = llm.invoke([
            SystemMessage(content=(
                f"You are a lead pharmaceutical intelligence analyst. You have received analyses "
                f"from {len(analyses)} specialist perspectives on this question. Synthesize them "
                "into a unified, balanced response that:\n"
                "- Leads with the strongest consensus finding\n"
                "- Highlights where perspectives diverge\n"
                "- Notes data gaps identified by specialists\n"
                "- Provides an overall confidence assessment\n"
                "- Is honest about what the data does and doesn't support\n"
                "- Uses **bold** for key entities and metrics\n"
                "- Only propagate claims that have [N] citations from specialist inputs\n"
                "- If specialists disagreed, note the discrepancy and cite both sides\n"
                "- Do NOT introduce new claims not present in specialist analyses\n"
                "- Keep to 3-5 paragraphs max\n"
            )),
            HumanMessage(content=(
                f"QUESTION: {question}\n\n"
                "SPECIALIST ANALYSES:\n\n" + "\n\n".join(persona_summaries)
            )),
        ])
        narrative = resp.content.strip()
    except Exception as exc:
        logger.warning("Team synthesis failed: %s", exc)
        narrative = _build_fallback_team_narrative(question, analyses)

    # Aggregate evidence from all personas into tool_results for backward compat
    tool_results = _aggregate_persona_evidence(analyses)

    return {
        "combined_narrative": narrative,
        "confidence_assessment": {
            "overall": overall_confidence,
            "by_dimension": by_dimension,
        },
        "tool_results": tool_results,
    }


def _present_team(state: TeamEvalState) -> dict:
    """Deterministic presentation for team eval results."""
    from services.agent.presenter import plan_team_eval_presentation

    pres = plan_team_eval_presentation(
        persona_analyses=state["persona_analyses"],
        tool_results=state["tool_results"],
        confidence_assessment=state.get("confidence_assessment", {}),
    )

    return {
        "presentation": pres,
        "table_data": pres.get("table_data"),
        "visualizations": pres.get("visualizations", []),
    }


# ── Per-persona query helpers ──

def _persona_rag_queries(
    rag_tool, question: str, entities: dict, persona_name: str,
) -> list[dict]:
    """Persona-specific RAG queries with entity_type filters."""
    evidence = []
    drugs = entities.get("drugs", [])
    conditions = entities.get("conditions", [])

    # Clinical researcher: trials + literature; Regulatory expert: trials + regulatory
    if persona_name == "clinical_researcher":
        entity_type_filters = [["clinical_trial"], ["literature"]]
    elif persona_name == "regulatory_expert":
        entity_type_filters = [["clinical_trial"]]
    else:
        entity_type_filters = [None]  # unfiltered

    for entity_types in entity_type_filters:
        # Per-drug queries
        if drugs:
            for drug in drugs[:3]:  # cap at 3 drugs
                query = f"{drug} {' '.join(conditions[:2])}" if conditions else drug
                params = {"query": query, "limit": 5}
                if entity_types:
                    params["entity_types"] = entity_types
                result = rag_tool.execute("search", params)
                if result.success and result.data:
                    type_label = entity_types[0] if entity_types else "search"
                    for item in result.data[:5]:
                        evidence.append(_to_evidence_item(item, f"rag:{type_label}:{drug}"))
        else:
            # No specific drugs, do general query
            params = {"query": question, "limit": 8}
            if entity_types:
                params["entity_types"] = entity_types
            result = rag_tool.execute("search", params)
            if result.success and result.data:
                type_label = entity_types[0] if entity_types else "search"
                for item in result.data[:8]:
                    evidence.append(_to_evidence_item(item, f"rag:{type_label}"))

    return evidence


def _persona_graph_queries(
    graph_tool, rag_tool, entities: dict,
) -> list[dict]:
    """Graph neighborhood expansion per drug entity."""
    evidence = []
    drugs = entities.get("drugs", [])

    for drug in drugs[:3]:
        # First find the entity_id via RAG
        result = rag_tool.execute("search", {"query": drug, "entity_types": ["drug"], "limit": 1})
        if result.success and result.data:
            entity_id = result.data[0].get("entity_id", "")
            if entity_id:
                graph_result = graph_tool.execute("neighborhood", {
                    "entity_id": entity_id,
                    "entity_type": "drug",
                })
                if graph_result.success and graph_result.data:
                    nodes = graph_result.data.get("nodes", [])
                    edges = graph_result.data.get("edges", [])
                    # Summarize graph neighborhood
                    node_labels = [n.get("label", "") for n in nodes[:10]]
                    edge_types = list(set(e.get("link_type", "") for e in edges[:10]))
                    evidence.append({
                        "source_label": f"graph:neighborhood:{drug}",
                        "content": (
                            f"Knowledge graph for {drug}: {len(nodes)} connected entities "
                            f"({', '.join(node_labels[:5])}), "
                            f"relationship types: {', '.join(edge_types[:5])}"
                        ),
                        "source": "graph",
                        "entity_type": "drug",
                        "entity_id": entity_id,
                    })

    return evidence


def _persona_sql_queries(
    sql_tool, llm, question: str, entities: dict, schema_text: str, persona_name: str,
) -> list[dict]:
    """LLM plans 1-2 targeted SQL queries per persona role, then executes them."""
    evidence = []
    instructions = _PERSONA_SQL_INSTRUCTIONS.get(persona_name)
    if not instructions:
        return evidence

    drugs = entities.get("drugs", [])
    conditions = entities.get("conditions", [])
    entity_summary = f"Drugs: {', '.join(drugs)}" if drugs else "No specific drugs"
    if conditions:
        entity_summary += f"; Conditions: {', '.join(conditions)}"

    try:
        resp = llm.invoke([
            SystemMessage(content=(
                f"You are a SQL query planner for a pharmaceutical database.\n\n"
                f"DATABASE SCHEMA:\n{schema_text}\n\n"
                f"ENTITIES IN QUESTION:\n{entity_summary}\n\n"
                f"ROLE-SPECIFIC INSTRUCTIONS:\n{instructions}\n\n"
                "CRITICAL RULES:\n"
                "- Only SELECT queries (no INSERT/UPDATE/DELETE)\n"
                "- Use ILIKE for text matching: WHERE LOWER(generic_name) = LOWER('drug_name')\n"
                "- Cast UUIDs: table.id::text when joining with entity_links\n"
                "- clinical_trials.status values are UPPERCASE: 'RECRUITING', 'COMPLETED', etc.\n"
                "- Respond with a JSON array only (no markdown fences)"
            )),
            HumanMessage(content=f"Question: {question}"),
        ])

        sql_plans = _parse_sql_plans(resp.content.strip())

        for plan in sql_plans[:2]:  # cap at 2 queries
            sql = plan.get("sql", "")
            label = plan.get("label", "SQL query")
            if not sql:
                continue

            result = sql_tool.execute("query", {"sql": sql})
            if result.success and result.data:
                formatted = _format_sql_result(result, label)
                evidence.append({
                    "source_label": f"sql:{label}",
                    "content": formatted,
                    "source": "sql",
                    "entity_type": "computed",
                    "entity_id": "",
                    "metadata": {"sql": sql, "row_count": result.row_count},
                })
            elif result.error:
                logger.debug("SQL query failed for %s: %s", persona_name, result.error)

    except Exception as exc:
        logger.warning("SQL planning failed for %s: %s", persona_name, exc)

    return evidence


def _persona_metrics_queries(
    metrics_tool, entities: dict, persona_name: str,
) -> list[dict]:
    """Targeted metrics queries per persona role."""
    evidence = []

    if persona_name == "market_analyst":
        # Pipeline strength
        result = metrics_tool.execute("pipeline", {"limit": 15})
        if result.success and result.data:
            drugs = entities.get("drugs", [])
            # Filter to mentioned drugs if possible
            filtered = result.data
            if drugs:
                drug_lower = {d.lower() for d in drugs}
                matched = [r for r in result.data if str(r.get("drug_name", "")).lower() in drug_lower]
                if matched:
                    filtered = matched
            for row in filtered[:5]:
                evidence.append({
                    "source_label": f"metrics:pipeline:{row.get('drug_name', 'unknown')}",
                    "content": (
                        f"Pipeline: {row.get('drug_name', 'Unknown')} — "
                        f"score {row.get('pipeline_score', 'N/A')}, "
                        f"{row.get('total_trials', 0)} trials"
                    ),
                    "source": "metrics",
                    "entity_type": "drug",
                    "entity_id": "",
                })

        # Competitive landscape
        landscape = metrics_tool.execute("landscape", {"limit": 10})
        if landscape.success and landscape.data:
            for row in landscape.data[:3]:
                evidence.append({
                    "source_label": f"metrics:landscape:{row.get('mechanism_name', 'unknown')}",
                    "content": (
                        f"Market segment: {row.get('mechanism_name', 'Unknown')} — "
                        f"{row.get('drug_count', 0)} drugs, "
                        f"total pipeline score {row.get('total_pipeline_score', 0):.0f}"
                    ),
                    "source": "metrics",
                    "entity_type": "mechanism",
                    "entity_id": "",
                })

    elif persona_name == "data_scientist":
        # Evidence density
        result = metrics_tool.execute("pipeline", {"limit": 10})
        if result.success and result.data:
            drugs = entities.get("drugs", [])
            filtered = result.data
            if drugs:
                drug_lower = {d.lower() for d in drugs}
                matched = [r for r in result.data if str(r.get("drug_name", "")).lower() in drug_lower]
                if matched:
                    filtered = matched
            for row in filtered[:5]:
                evidence.append({
                    "source_label": f"metrics:evidence_density:{row.get('drug_name', 'unknown')}",
                    "content": (
                        f"Evidence density: {row.get('drug_name', 'Unknown')} — "
                        f"{row.get('total_trials', 0)} trials, "
                        f"pipeline score {row.get('pipeline_score', 'N/A')}"
                    ),
                    "source": "metrics",
                    "entity_type": "drug",
                    "entity_id": "",
                })

    return evidence


# ── Helpers ──

_CONFIDENCE_MAP = {"high": 0.85, "medium": 0.6, "moderate": 0.6, "low": 0.35}


def _to_evidence_item(raw_item: dict, source_label: str) -> dict:
    """Normalize a raw RAG/tool result into a standard evidence item."""
    if isinstance(raw_item, dict):
        content = str(raw_item.get("content", "")).strip()
        return {
            "source_label": source_label,
            "content": content[:500] if content else "(empty)",
            "source": raw_item.get("source", ""),
            "entity_type": raw_item.get("entity_type", ""),
            "entity_id": raw_item.get("entity_id", ""),
        }
    return {
        "source_label": source_label,
        "content": str(raw_item)[:500],
        "source": "",
        "entity_type": "",
        "entity_id": "",
    }


def _format_sql_result(tool_result: ToolResult, label: str) -> str:
    """Format SQL rows into readable text for LLM context."""
    if not tool_result.data:
        return f"{label}: no rows returned"

    rows = tool_result.data
    if len(rows) == 1 and len(tool_result.columns) == 1:
        # Scalar result
        val = next(iter(rows[0].values()))
        return f"{label}: {val}"

    lines = [f"{label} ({len(rows)} rows):"]
    for row in rows[:10]:
        parts = [f"{k}: {v}" for k, v in row.items()]
        lines.append("  " + ", ".join(parts))
    if len(rows) > 10:
        lines.append(f"  ... and {len(rows) - 10} more rows")
    return "\n".join(lines)


def _build_evidence_context(evidence_items: list[dict]) -> str:
    """Build numbered evidence context for persona LLM prompt."""
    if not evidence_items:
        return "(No database evidence gathered for this query.)"

    lines = []
    for idx, item in enumerate(evidence_items, 1):
        label = item.get("source_label", "unknown")
        content = item.get("content", "")
        lines.append(f"[{idx}] ({label}) {content[:300]}")
    return "\n".join(lines)


def _parse_entity_json(raw: str) -> dict:
    """Parse entity extraction JSON from LLM response."""
    cleaned = raw
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
        return {
            "drugs": _ensure_list(data.get("drugs", [])),
            "conditions": _ensure_list(data.get("conditions", [])),
            "companies": _ensure_list(data.get("companies", [])),
            "mechanisms": _ensure_list(data.get("mechanisms", [])),
        }
    except (json.JSONDecodeError, KeyError):
        return {"drugs": [], "conditions": [], "companies": [], "mechanisms": []}


def _fallback_entity_extraction(question: str) -> dict:
    """Fallback: split question into noun phrases."""
    # Simple heuristic: split on common stop words
    words = re.findall(r'\b[A-Za-z][\w-]+\b', question)
    stop = {"what", "about", "the", "and", "for", "with", "how", "does", "should",
            "we", "in", "of", "is", "are", "can", "do", "events", "during", "invest"}
    meaningful = [w for w in words if w.lower() not in stop and len(w) > 2]
    return {
        "drugs": meaningful[:3],
        "conditions": [],
        "companies": [],
        "mechanisms": [],
    }


def _ensure_list(val) -> list[str]:
    """Ensure a value is a list of strings."""
    if isinstance(val, list):
        return [str(v).strip() for v in val if str(v).strip()]
    if isinstance(val, str):
        return [val.strip()] if val.strip() else []
    return []


def _parse_sql_plans(raw: str) -> list[dict]:
    """Parse SQL plan JSON array from LLM response."""
    cleaned = raw
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        plans = json.loads(cleaned)
        if isinstance(plans, list):
            return plans
        if isinstance(plans, dict):
            return [plans]
    except (json.JSONDecodeError, KeyError):
        pass
    return []


def _parse_persona_json(raw: str) -> dict:
    """Parse structured JSON from persona LLM response, with fallback."""
    cleaned = raw
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        data = json.loads(cleaned)
        conf_str = str(data.get("confidence", "medium")).lower().strip()
        conf_val = _CONFIDENCE_MAP.get(conf_str, 0.5)
        if conf_str not in _CONFIDENCE_MAP:
            try:
                conf_val = float(conf_str)
            except (ValueError, TypeError):
                conf_val = 0.5

        findings = data.get("key_findings", [])
        if not isinstance(findings, list):
            findings = [str(findings)]
        findings = [str(f).strip() for f in findings if str(f).strip()]

        gaps = data.get("data_gaps", [])
        if not isinstance(gaps, list):
            gaps = [str(gaps)]
        gaps = [str(g).strip() for g in gaps if str(g).strip()]

        return {
            "analysis": str(data.get("analysis", raw)),
            "confidence": conf_val,
            "key_findings": findings[:5],
            "data_gaps": gaps[:3],
        }
    except (json.JSONDecodeError, KeyError):
        return {
            "analysis": raw,
            "confidence": _extract_confidence(raw),
            "key_findings": _extract_bullet_points(raw),
            "data_gaps": _extract_data_gaps(raw),
        }


def _aggregate_persona_evidence(analyses: list[dict]) -> dict:
    """Aggregate evidence_items from all personas into a ToolResult-compatible dict.

    Produces a backward-compatible tool_results dict for _format_team_eval_response
    and the presenter.
    """
    all_evidence = []
    for a in analyses:
        for item in a.get("evidence_items", []):
            content = item.get("content", "")
            source = item.get("source", "search")
            all_evidence.append({
                "source": source,
                "entity_type": item.get("entity_type", ""),
                "entity_id": item.get("entity_id", ""),
                "content": content,
                "relevance": 0.8,
                "provenance": {"source_api": source},
            })

    # Wrap in a ToolResult-like structure
    rag_result = ToolResult(
        tool="rag",
        success=bool(all_evidence),
        data=all_evidence,
        row_count=len(all_evidence),
    )
    return {"rag": rag_result}


def _extract_confidence(text: str) -> float:
    lower = text.lower()
    if "high confidence" in lower or "confidence: high" in lower:
        return 0.85
    if "medium confidence" in lower or "confidence: medium" in lower or "moderate confidence" in lower:
        return 0.6
    if "low confidence" in lower or "confidence: low" in lower:
        return 0.35
    return 0.5


def _extract_bullet_points(text: str) -> list[str]:
    bullets = re.findall(r"[-•]\s*(.+?)(?:\n|$)", text)
    return [b.strip() for b in bullets[:5] if b.strip()]


def _extract_data_gaps(text: str) -> list[str]:
    gaps = []
    gap_section = re.search(r"(?:data gap|limitation|caveat|missing)s?:?\s*(.+?)(?:\n\n|$)", text, re.I | re.S)
    if gap_section:
        lines = gap_section.group(1).strip().split("\n")
        for line in lines[:3]:
            clean = line.strip().lstrip("-•").strip()
            if clean:
                gaps.append(clean)
    return gaps


def _build_fallback_team_narrative(question: str, analyses: list[dict]) -> str:
    parts = [f"**Team evaluation** of: {question}\n"]
    for a in analyses:
        parts.append(f"**{a['display_name']}** (confidence: {a['confidence']:.0%}): ")
        findings = a.get("key_findings", [])
        if findings:
            parts.append(", ".join(findings[:2]) + ".")
        else:
            parts.append(a["analysis"][:150] + "...")
    return "\n\n".join(parts)


# ── Graph builder ──

def build_team_eval_graph(
    *,
    llm,
    sql_tool,
    rag_tool,
    graph_tool,
    metrics_tool,
    personas: dict,
    schema_text: str = "",
):
    """Build and compile the team eval StateGraph.

    ``personas`` is a dict of persona_name -> persona config dict, each with:
        display_name, system_prompt, focus, tools

    ``schema_text`` is the database schema description for SQL generation.
    """

    graph = StateGraph(TeamEvalState)

    # Nodes
    graph.add_node("extract_entities", lambda s: _extract_entities(s, llm=llm))
    graph.add_node("persona_node", lambda s: _persona_node(
        s, llm=llm, personas=personas,
        sql_tool=sql_tool, rag_tool=rag_tool,
        graph_tool=graph_tool, metrics_tool=metrics_tool,
    ))
    graph.add_node("synthesize", lambda s: _synthesize_team(s, llm=llm))
    graph.add_node("present", _present_team)

    # Entry
    graph.set_entry_point("extract_entities")

    # extract_entities → route_team (fan-out via Send)
    graph.add_conditional_edges(
        "extract_entities",
        lambda s: _route_team(s, llm=llm, personas=personas, schema_text=schema_text),
    )

    # persona_node → synthesize
    graph.add_edge("persona_node", "synthesize")

    # synthesize → present → END
    graph.add_edge("synthesize", "present")
    graph.add_edge("present", END)

    return graph.compile()
