"""Chat intent handler functions.

Each handler gathers data from services and produces a structured response dict.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Optional

from api.deps import get_query_graph, get_team_eval_graph
from api.utils import normalize_provenance
from db import Database
from services.llm import LLMSynthesizer
from services.metrics import PharmaMetrics
from services.query_engine import QueryEngine
from services.web_research import WebResearchService

from services.chat_handlers.intent import Intent
from services.chat_handlers.formatting import (
    resolve_entity,
    compute_comparison_insights,
    build_comparison_table,
    build_visualizations,
    expand_topic_synonyms,
    to_number,
)
from services.chat_handlers.context import build_conversation_context
from services.concept_registry import ConceptRegistry, format_concept_context

logger = logging.getLogger(__name__)

# Module-level registry singleton (15 pharma concepts, zero DB calls)
_concept_registry = ConceptRegistry(auto_register=True)


def _hydrate_dossier_ctx(entity_name: str, entity_type: str) -> Optional[str]:
    """Try to hydrate entity context from the CTX corpus for richer dossier context.

    Uses the unified handler's CTXQueryPipeline (if available) to retrieve
    structured corpus sections for the entity. Returns a rendered context
    string, or None if CTX hydration is unavailable or finds nothing.

    This is a best-effort enrichment — failures are silently swallowed.
    """
    try:
        from api.deps import get_unified_handler

        handler = get_unified_handler()
        if handler is None:
            return None

        pipeline = handler.pipeline

        plan = pipeline.understand(f"Tell me about {entity_name}")
        if not plan.entities_detected:
            # Try with entity type prefix for better matching
            plan = pipeline.understand(f"{entity_type} {entity_name}")
        if not plan.entities_detected:
            return None

        retrieval = pipeline.retrieve(plan)
        if not retrieval.ctx_sections:
            return None

        context_text = retrieval.render_context()
        if not context_text or len(context_text) < 50:
            return None

        logger.debug(
            "CTX hydration for %s (%s): %d tokens from %d sections",
            entity_name, entity_type,
            retrieval.token_count, len(retrieval.ctx_sections),
        )
        return f"CTX CORPUS CONTEXT:\n{context_text}"
    except Exception as e:
        logger.debug("CTX hydration unavailable for dossier: %s", e)
        return None


# ── Agent response helpers ──

def _tool_result_value(result_obj, field: str, default=None):
    if result_obj is None:
        return default
    if isinstance(result_obj, dict):
        return result_obj.get(field, default)
    return getattr(result_obj, field, default)


def _extract_rag_evidence(tool_results: dict) -> tuple[list[dict], dict]:
    rag_result = tool_results.get("rag") if isinstance(tool_results, dict) else None
    rag_success = bool(_tool_result_value(rag_result, "success", False))
    rag_data = _tool_result_value(rag_result, "data", [])
    if not rag_success or not isinstance(rag_data, list):
        return [], {"total_evidence_items": 0, "by_source": {}}

    evidence: list[dict] = []
    by_source: dict[str, int] = {}
    by_entity_type: dict[str, int] = {}
    for item in rag_data:
        if not isinstance(item, dict):
            continue

        entity_type = str(item.get("entity_type") or "unknown")
        entity_id = str(item.get("entity_id") or "")
        content = str(item.get("content") or item.get("snippet") or item.get("title") or "").strip()
        if not content:
            continue

        raw_provenance = item.get("provenance")
        provenance = dict(raw_provenance) if isinstance(raw_provenance, dict) else {}
        if not provenance.get("source_api") and item.get("source"):
            provenance["source_api"] = str(item.get("source"))
        normalized_provenance = normalize_provenance(provenance, entity_type, entity_id)
        source_api = str(normalized_provenance.get("source_api") or item.get("source") or "unknown")

        relevance_raw = item.get("relevance")
        try:
            relevance = float(relevance_raw) if relevance_raw is not None else 0.0
        except (TypeError, ValueError):
            relevance = 0.0

        evidence.append(
            {
                "source": source_api,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "content": content,
                "relevance": relevance,
                "provenance": normalized_provenance,
            }
        )
        by_source[source_api] = by_source.get(source_api, 0) + 1
        by_entity_type[entity_type] = by_entity_type.get(entity_type, 0) + 1

    return evidence, {
        "total_evidence_items": len(evidence),
        "by_source": by_source,
        "by_entity_type": by_entity_type,
    }


def _extract_graph_context(tool_results: dict) -> dict:
    graph_result = tool_results.get("graph") if isinstance(tool_results, dict) else None
    graph_success = bool(_tool_result_value(graph_result, "success", False))
    graph_data = _tool_result_value(graph_result, "data", {})
    if not graph_success or not isinstance(graph_data, dict):
        return {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0}
    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])
    return {
        "nodes": nodes if isinstance(nodes, list) else [],
        "edges": edges if isinstance(edges, list) else [],
        "node_count": len(nodes) if isinstance(nodes, list) else 0,
        "edge_count": len(edges) if isinstance(edges, list) else 0,
    }


def _format_agent_response(result: dict, intent: str) -> dict:
    """Format a query graph result into the standard chat response shape."""
    narrative = result.get("narrative", "")
    table_data = result.get("table_data")
    visualizations = result.get("visualizations", [])

    # Build a minimal data dict compatible with QueryResponse
    tool_results = result.get("tool_results", {})
    evidence, provenance_summary = _extract_rag_evidence(tool_results)
    graph_context = _extract_graph_context(tool_results)

    # Extract executed SQL for conversation context pass-through
    sql_meta = {}
    sql_result = tool_results.get("sql")
    if sql_result and hasattr(sql_result, "metadata") and isinstance(sql_result.metadata, dict):
        sql_meta["sql"] = sql_result.metadata.get("sql", "")
    elif isinstance(result.get("plan"), dict):
        sql_meta["sql"] = result["plan"].get("sql", "")

    return {
        "narrative": narrative,
        "intent": intent,
        "data": {
            "question": result.get("question", ""),
            "evidence": evidence,
            "graph_context": graph_context,
            "metrics_context": {},
            "entity_focus": [],
            "provenance_summary": provenance_summary,
        },
        "table_data": table_data,
        "visualizations": visualizations,
        "sql_meta": sql_meta,
    }


def _format_team_eval_response(result: dict) -> dict:
    """Format a team eval graph result into the standard chat response shape."""
    narrative = result.get("combined_narrative", "")
    persona_analyses = result.get("persona_analyses", [])
    confidence = result.get("confidence_assessment", {})
    table_data = result.get("table_data")
    visualizations = result.get("visualizations", [])
    tool_results = result.get("tool_results", {})
    evidence, provenance_summary = _extract_rag_evidence(tool_results)

    return {
        "narrative": narrative,
        "intent": Intent.TEAM_EVAL,
        "data": {
            "question": result.get("question", ""),
            "evidence": evidence,
            "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
            "metrics_context": {},
            "entity_focus": [],
            "provenance_summary": provenance_summary,
        },
        "table_data": table_data,
        "visualizations": visualizations,
        "persona_analyses": persona_analyses,
        "confidence_assessment": confidence,
    }


# ── Result serialization ──

def _serialize_result(result) -> dict:
    """Convert a QueryResult dataclass to a JSON-safe dict."""
    return {
        "question": result.question,
        "evidence": [
            {
                "source": e.source,
                "entity_type": e.entity_type,
                "entity_id": e.entity_id,
                "content": e.content,
                "relevance": e.relevance,
                "provenance": normalize_provenance(e.provenance, e.entity_type, e.entity_id),
            }
            for e in result.evidence
        ],
        "graph_context": result.graph_context,
        "metrics_context": result.metrics_context,
        "entity_focus": result.entity_focus,
        "provenance_summary": result.provenance_summary,
    }


def _enrich_result(result, db: Database) -> dict:
    """Serialize QueryResult and normalize graph edges for frontend compatibility."""
    raw = _serialize_result(result)

    # Normalize graph edges: backend uses source/target/type, frontend expects source_id/target_id/link_type
    gc = raw.get("graph_context", {})
    if gc.get("edges"):
        gc["edges"] = [
            {
                "source_id": e.get("source_id") or e.get("source", ""),
                "target_id": e.get("target_id") or e.get("target", ""),
                "link_type": e.get("link_type") or e.get("type", ""),
                "confidence": e.get("confidence", 0.5),
                "via": e.get("via", ""),
            }
            for e in gc["edges"]
        ]

    # Enrich entity_focus with title field (frontend expects 'title')
    for ef in raw.get("entity_focus", []):
        if "title" not in ef:
            ef["title"] = ef.get("label", ef.get("entity_id", "Unknown"))
        if "metadata" not in ef:
            ef["metadata"] = ef.get("properties", {})

    # Add connection counts to entity_focus entries
    for ef in raw.get("entity_focus", []):
        eid = ef.get("entity_id", "")
        if eid and "total_connections" not in ef:
            row = db.fetch_one(
                """SELECT COUNT(*) AS cnt FROM entity_links
                   WHERE source_entity_id::text = %s OR target_entity_id::text = %s""",
                [eid, eid],
            )
            ef["total_connections"] = row["cnt"] if row else 0

    return raw


def _format_query_result(intent: str, question: str, result, db: Database, llm: LLMSynthesizer, conv_context: str = "") -> dict:
    # Template fallback
    parts = []
    ec = len(result.evidence)
    gc = result.graph_context
    mc = result.metrics_context

    if result.entity_focus:
        parts.append(f"Found **{len(result.entity_focus)} entities** matching your query.")
    elif ec > 0:
        parts.append(f"Found **{ec} evidence items** for your query.")
    else:
        parts.append("I searched the knowledge graph but found limited results. Try being more specific.")

    # Pass connected entity names to LLM (not raw node/edge counts — user can't see those)
    connected = gc.get("connected_entities", {})
    if connected:
        for etype, labels in connected.items():
            if labels:
                parts.append(f"Connected {etype}: {', '.join(str(l) for l in labels[:5])}")

    if mc:
        for eid, metrics in mc.items():
            if isinstance(metrics, dict) and "pipeline" in metrics:
                p = metrics["pipeline"]
                if isinstance(p, dict):
                    parts.append(f"Pipeline score for {eid}: **{p.get('pipeline_score', 'N/A')}**.")
                    break

    fallback = " ".join(parts)

    # LLM synthesis
    evidence_snippets = [e.content for e in result.evidence[:10]]
    graph_summary = None
    if gc.get("node_count", 0) > 0:
        nodes_by_type: dict[str, list[str]] = {}
        for node in gc.get("nodes", [])[:30]:
            if isinstance(node, dict) and node.get("label"):
                nt = node.get("entity_type", "other")
                nodes_by_type.setdefault(nt, []).append(node["label"])
        graph_summary = {
            "node_count": gc["node_count"],
            "edge_count": gc["edge_count"],
            "connected_entities": {k: v[:10] for k, v in nodes_by_type.items()},
        }

    # Activate domain concepts for this intent + entity types
    entity_types_in_result = list({
        ef.get("entity_type", "drug")
        for ef in (result.entity_focus or [])
        if isinstance(ef, dict) and ef.get("entity_type")
    }) or ["drug"]
    activated_concepts = _concept_registry.activate(intent, entity_types_in_result)
    concept_hint = format_concept_context(activated_concepts)

    # Merge concept hint into extra_context
    extra_ctx = conv_context or ""
    if concept_hint:
        extra_ctx = f"{concept_hint}\n\n{extra_ctx}" if extra_ctx else concept_hint

    narrative = llm.synthesize(
        question=question,
        intent=intent,
        metrics=mc if mc else None,
        graph_summary=graph_summary,
        evidence_snippets=evidence_snippets,
        extra_context=extra_ctx if extra_ctx else None,
        fallback_narrative=fallback,
    )

    # Confidence scoring
    from services.chat_handlers.formatting import compute_response_confidence
    confidence = compute_response_confidence(
        entity_resolved=bool(result.entity_focus),
        evidence_count=len(result.evidence),
        graph_node_count=gc.get("node_count", 0),
        metrics_available=bool(mc),
    )

    return {
        "narrative": narrative,
        "intent": intent,
        "data": _enrich_result(result, db),
        "confidence": confidence,
    }


# ── Deep research helpers ──

def _extract_research_summary(report: str) -> str:
    if not report:
        return "Deep research completed. Open the report for full analysis."
    for raw_line in report.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        header = line.lstrip("#").strip().lower().rstrip(":")
        if header in {
            "executive summary",
            "internal evidence (knowledge graph)",
            "quantitative signals",
            "external context (web)",
            "risks and data gaps",
            "recommended next questions",
        }:
            continue
        return line if len(line) <= 340 else f"{line[:337]}..."
    compact = " ".join(report.split())
    return compact if len(compact) <= 340 else f"{compact[:337]}..."


def _build_research_fallback_report(question: str, data: dict, web_results: list[dict]) -> str:
    entities = [
        str(e.get("title") or e.get("label") or e.get("entity_id"))
        for e in data.get("entity_focus", [])[:5]
    ]
    evidence = data.get("evidence", [])
    graph_context = data.get("graph_context", {})
    provenance = data.get("provenance_summary", {})
    metrics_context = data.get("metrics_context", {})

    top_source = "unknown"
    by_source = provenance.get("by_source")
    if isinstance(by_source, dict) and by_source:
        top_source = max(by_source.items(), key=lambda item: to_number(item[1]) or 0)[0]

    pipeline_label = None
    pipeline_score = None
    for metric_group in metrics_context.values():
        if not isinstance(metric_group, dict):
            continue
        pipeline = metric_group.get("pipeline")
        if not isinstance(pipeline, dict):
            continue
        score = to_number(pipeline.get("pipeline_score"))
        if score is None:
            continue
        if pipeline_score is None or score > pipeline_score:
            pipeline_score = score
            pipeline_label = (
                pipeline.get("drug_name")
                or pipeline.get("name")
                or "top-ranked asset"
            )

    report_lines = [
        "## Executive Summary",
        (
            f'Research request: "{question}". The internal graph returned '
            f'{len(evidence)} evidence items with '
            f'{int(graph_context.get("node_count", 0))} connected nodes and '
            f'{int(graph_context.get("edge_count", 0))} links.'
        ),
        "",
        "## Internal Evidence (Knowledge Graph)",
        f"Primary entities detected: {', '.join(entities) if entities else 'None identified with high confidence.'}",
        f"Most represented source channel: {top_source}.",
        "",
        "## Quantitative Signals",
    ]
    if pipeline_label is not None and pipeline_score is not None:
        report_lines.append(f"Highest pipeline signal: {pipeline_label} (score {pipeline_score:.2f}).")
    else:
        report_lines.append("No strong quantitative metric row was available for this query.")

    if web_results:
        report_lines.extend(
            [
                "",
                "## External Context (Web)",
                f"Web search contributed {len(web_results)} additional references.",
            ]
        )
        for idx, item in enumerate(web_results[:4], 1):
            title = str(item.get("title", "Untitled source"))
            url = str(item.get("url", ""))
            report_lines.append(f"{idx}. {title} ({url})")

    report_lines.extend(
        [
            "",
            "## Risks and Data Gaps",
            "Potential entity aliasing and source freshness differences can change interpretation.",
            "",
            "## Recommended Next Questions",
            "1. Narrow to a therapeutic area and trial endpoint for precision.",
            "2. Validate top claims against linked primary sources before decisions.",
        ]
    )
    return "\n".join(report_lines)


# ── Intent handlers ──

def handle_structured_query(
    question: str,
    engine: QueryEngine,
    db: Database,
    llm: LLMSynthesizer,
    conversation_history: list[dict] | None = None,
) -> dict:
    """Route to the LangGraph query agent for SQL-computed answers."""
    graph = get_query_graph()
    if graph is None:
        logger.info("Query graph not available, falling back to general handler")
        return handle_general(question, engine, db, llm)

    conversation_context = build_conversation_context(conversation_history or [])

    try:
        result = graph.invoke({
            "messages": [],
            "question": question,
            "conversation_context": conversation_context,
            "intent": "",
            "plan": {},
            "tool_results": {},
            "presentation": {},
            "table_data": None,
            "visualizations": [],
            "narrative": "",
            "error": None,
        })
        return _format_agent_response(result, Intent.STRUCTURED_QUERY)
    except Exception as exc:
        logger.warning("Query graph failed: %s, falling back", exc)
        return handle_general(question, engine, db, llm)


def handle_team_eval(
    question: str,
    engine: QueryEngine,
    db: Database,
    llm: LLMSynthesizer,
) -> dict:
    """Route to the LangGraph team eval agent for multi-persona analysis."""
    graph = get_team_eval_graph()
    if graph is None:
        logger.info("Team eval graph not available, falling back to general handler")
        return handle_general(question, engine, db, llm)

    try:
        result = graph.invoke({
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
        return _format_team_eval_response(result)
    except Exception as exc:
        logger.warning("Team eval graph failed: %s, falling back", exc)
        return handle_general(question, engine, db, llm)


def handle_dossier(params: dict, db: Database, engine: QueryEngine, llm: LLMSynthesizer, conv_context: str = "") -> dict:
    name = params.get("entity_name", "")
    resolved = resolve_entity(name, "", db)

    if not resolved:
        # Try literature-specific search for article titles
        lit = resolve_entity(name, "literature", db)
        if lit:
            resolved = lit
        else:
            result = engine.query(name)
            return _format_query_result("general", name, result, db, llm)

    etype = resolved["entity_type"]
    eid = resolved["entity_id"]
    label = resolved["label"]
    match_score = resolved.get("match_score")

    result = engine.entity_dossier(eid, etype)

    # ── Gather structured context for LLM ──
    entity_details = {}
    template_parts = []

    if etype == "drug":
        drug_row = db.fetch_one("""
            SELECT d.generic_name, d.brand_name, d.supply_status,
                   c.name AS company_name,
                   ta.name AS therapeutic_area,
                   m.name AS mechanism
            FROM drugs d
            LEFT JOIN companies c ON d.company_id = c.id
            LEFT JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
            LEFT JOIN mechanisms_of_action m ON d.mechanism_id = m.id
            WHERE d.id = %s::uuid
        """, [eid])

        if drug_row:
            entity_details = {
                "generic_name": drug_row["generic_name"],
                "brand_name": drug_row.get("brand_name"),
                "company": drug_row.get("company_name"),
                "mechanism": drug_row.get("mechanism"),
                "therapeutic_area": drug_row.get("therapeutic_area"),
                "supply_status": drug_row.get("supply_status"),
            }
            # Template fallback
            header = f"**{drug_row['generic_name']}"
            if drug_row.get("brand_name"):
                header += f" ({drug_row['brand_name']})"
            header += "**"
            parts = []
            if drug_row.get("company_name"):
                parts.append(f"owned by **{drug_row['company_name']}**")
            if drug_row.get("mechanism"):
                parts.append(f"a **{drug_row['mechanism']}**")
            if drug_row.get("therapeutic_area"):
                parts.append(f"targeting **{drug_row['therapeutic_area']}**")
            template_parts.append(f"{header} -- {', '.join(parts)}." if parts else f"{header}.")
            if drug_row.get("supply_status") and drug_row["supply_status"] != "NORMAL":
                template_parts.append(f"Supply status: **{drug_row['supply_status']}**.")
        else:
            template_parts.append(f"**{label}**.")

        # Connection summary
        conn_row = db.fetch_one("""
            SELECT COUNT(*) FILTER (WHERE link_type = 'INVESTIGATES') AS trial_links,
                   COUNT(*) FILTER (WHERE link_type = 'EVIDENCE_FOR') AS evidence_links,
                   COUNT(*) FILTER (WHERE link_type = 'IN_THERAPEUTIC_AREA') AS ta_links,
                   COUNT(*) FILTER (WHERE link_type = 'TARGETS_MECHANISM') AS mech_links,
                   COUNT(*) FILTER (WHERE link_type = 'OWNS') AS owns_links,
                   COUNT(*) AS total
            FROM entity_links
            WHERE source_entity_id::text = %s OR target_entity_id::text = %s
        """, [eid, eid])
        if conn_row and conn_row["total"] > 0:
            entity_details["connections"] = {
                "trials": conn_row["trial_links"],
                "publications": conn_row["evidence_links"],
                "therapeutic_areas": conn_row["ta_links"],
                "mechanisms": conn_row["mech_links"],
                "total": conn_row["total"],
            }
            conn_parts = []
            if conn_row["trial_links"]:
                conn_parts.append(f"{conn_row['trial_links']} trials")
            if conn_row["evidence_links"]:
                conn_parts.append(f"{conn_row['evidence_links']} publications")
            if conn_row["ta_links"]:
                conn_parts.append(f"{conn_row['ta_links']} therapeutic areas")
            if conn_parts:
                template_parts.append(
                    f"Connected to {', '.join(conn_parts)} in the knowledge graph "
                    f"(**{conn_row['total']} total connections**)."
                )

    elif etype == "company":
        template_parts.append(f"**{label}** company profile.")

    elif etype == "literature":
        art_row = db.fetch_one("""
            SELECT pa.title, pa.abstract, pa.journal, pa.publication_date,
                   pa.authors, d.generic_name AS drug_name,
                   ta.name AS therapeutic_area
            FROM pubmed_articles pa
            LEFT JOIN drugs d ON pa.drug_id = d.id
            LEFT JOIN therapeutic_areas ta ON d.therapeutic_area_id = ta.id
            WHERE pa.id = %s::uuid
        """, [eid])
        if art_row:
            entity_details = {
                "title": art_row["title"],
                "journal": art_row.get("journal"),
                "publication_date": str(art_row.get("publication_date", "")),
                "drug": art_row.get("drug_name"),
                "therapeutic_area": art_row.get("therapeutic_area"),
            }
            template_parts.append(f"**{art_row['title']}**")
            if art_row.get("journal"):
                template_parts.append(f"Published in *{art_row['journal']}*.")
            if art_row.get("abstract"):
                template_parts.append(art_row["abstract"][:500])
        else:
            template_parts.append(f"**{label}**.")

    else:
        template_parts.append(f"**{label}**.")

    # ── Metrics for LLM context + template ──
    metrics_for_llm = {}
    if result.metrics_context:
        for m_eid, metrics in result.metrics_context.items():
            if not isinstance(metrics, dict):
                continue
            metrics_for_llm = metrics
            p = metrics.get("pipeline", {})
            sr = metrics.get("success_rate", {})
            ev = metrics.get("evidence", {})

            if isinstance(p, dict) and p.get("pipeline_score") is not None:
                score = p["pipeline_score"]
                dominant_phase = max(
                    [("Phase 1", p.get("p1_count", 0)), ("Phase 2", p.get("p2_count", 0)),
                     ("Phase 3", p.get("p3_count", 0)), ("Phase 4", p.get("p4_count", 0))],
                    key=lambda x: x[1]
                )
                template_parts.append(
                    f"Pipeline score of **{score}** across {p.get('total_trials', 0)} trials, "
                    f"strongest in **{dominant_phase[0]}** ({dominant_phase[1]} trials)."
                )
            if isinstance(sr, dict) and sr.get("total", 0) > 0:
                completed = sr.get("completed", 0)
                terminated = sr.get("terminated", 0)
                active = sr.get("active", 0)
                parts = []
                if completed:
                    parts.append(f"{completed} completed")
                if active:
                    parts.append(f"{active} active")
                if terminated:
                    parts.append(f"{terminated} terminated")
                template_parts.append(f"Trial status: {', '.join(parts)}.")
            if isinstance(ev, dict) and ev.get("total_articles", 0) > 0:
                template_parts.append(
                    f"Evidence base of **{ev['total_articles']} PubMed articles**."
                )
            break

    # ── Market events for this entity ──
    if etype == "drug":
        events = db.fetch_all("""
            SELECT event_type, event_date, description, impact_score
            FROM market_events
            WHERE drug_id = %s::uuid
            ORDER BY event_date DESC NULLS LAST
            LIMIT 5
        """, [eid])
        if events:
            entity_details["recent_events"] = [
                {
                    "type": e["event_type"],
                    "date": str(e["event_date"]) if e["event_date"] else None,
                    "description": e["description"],
                    "impact": e["impact_score"],
                }
                for e in events
            ]
            for e in events:
                desc = e.get("description", "")
                date_str = str(e["event_date"]) if e.get("event_date") else ""
                template_parts.append(
                    f"**{e.get('event_type', 'Event')}** ({date_str}): {desc[:200]}"
                )

    # ── Evidence snippets for LLM ──
    evidence_snippets = [e.content for e in result.evidence[:10]]

    # ── Graph summary for LLM (include node labels, not just counts) ──
    graph_summary = None
    gc = result.graph_context
    if gc:
        # Extract top node labels grouped by entity type for richer LLM context
        nodes_by_type: dict[str, list[str]] = {}
        for node in gc.get("nodes", [])[:30]:
            if isinstance(node, dict) and node.get("label"):
                nt = node.get("entity_type", "other")
                nodes_by_type.setdefault(nt, []).append(node["label"])
        graph_summary = {
            "node_count": gc.get("node_count", 0),
            "edge_count": gc.get("edge_count", 0),
            "connections_by_type": gc.get("connections_by_type", {}),
            "connections_by_entity_type": gc.get("connections_by_entity_type", {}),
            "connected_entities": {k: v[:10] for k, v in nodes_by_type.items()},
        }

    # ── CTX hydration — enrich context from CTX corpus if available ──
    ctx_hydration_context = _hydrate_dossier_ctx(label, etype)

    # ── LLM synthesis (with template fallback) ──
    fallback = " ".join(template_parts)

    # Build extra_context: include fuzzy match warning + conversation context + concept hints + CTX hydration
    dossier_extra_context = ""
    if ctx_hydration_context:
        dossier_extra_context += ctx_hydration_context + "\n"
    if match_score is not None and match_score < 0.8:
        dossier_extra_context += "[NOTE: Entity matched via fuzzy search — verify entity identity]\n"
    if conv_context:
        dossier_extra_context += conv_context

    # Activate domain concepts for dossier + resolved entity type
    dossier_concepts = _concept_registry.activate("dossier", [etype])
    dossier_concept_hint = format_concept_context(dossier_concepts)
    if dossier_concept_hint:
        dossier_extra_context = f"{dossier_concept_hint}\n\n{dossier_extra_context}" if dossier_extra_context else dossier_concept_hint

    dossier_extra_context = dossier_extra_context.strip() or None

    narrative = llm.synthesize_dossier(
        question=f"Tell me about {label}",
        entity_name=label,
        entity_type=etype,
        entity_details=entity_details,
        metrics=metrics_for_llm,
        graph_summary=graph_summary,
        evidence_snippets=evidence_snippets,
        fallback_narrative=fallback,
        extra_context=dossier_extra_context,
    )

    # ── Confidence scoring with match_score ──
    from services.chat_handlers.formatting import compute_response_confidence
    gc = result.graph_context
    confidence = compute_response_confidence(
        entity_resolved=True,
        entity_match_score=match_score,
        evidence_count=len(result.evidence),
        graph_node_count=gc.get("node_count", 0) if gc else 0,
        metrics_available=bool(result.metrics_context),
    )

    return {
        "narrative": narrative,
        "intent": "dossier",
        "confidence": confidence,
        "data": _enrich_result(result, db),
    }


def handle_compare(params: dict, db: Database, engine: QueryEngine, llm: LLMSynthesizer, conv_context: str = "") -> dict:
    entity_names = params.get("entities", [])
    if len(entity_names) < 2:
        return {
            "narrative": "I need at least two entities to compare. Try: 'Compare semaglutide vs tirzepatide'.",
            "intent": "compare",
            "data": None,
        }

    resolved = []
    for name in entity_names:
        # Try drug first, then any entity type
        r = resolve_entity(name, "drug", db)
        if not r:
            r = resolve_entity(name, "", db)
        if r:
            resolved.append(r)

    if len(resolved) < 2:
        # Fall back to general query instead of returning an error
        original_q = " vs ".join(entity_names)
        logger.info("Compare fallback to general query: %s", original_q)
        result = engine.query(original_q)
        return _format_query_result("general", original_q, result, db, llm)

    result = engine.compare_entities([r["entity_id"] for r in resolved], resolved[0]["entity_type"])
    names = [r["label"] for r in resolved]

    # Template fallback
    template_parts = [f"Comparison of **{' vs '.join(names)}**."]
    if result.get("shared_connections"):
        template_parts.append(f"They share **{len(result['shared_connections'])} connections**.")

    metrics_comp = result.get("metrics_comparison", {})
    for r_ent in resolved:
        m = metrics_comp.get(r_ent["entity_id"], {})
        if isinstance(m, dict):
            p = m.get("pipeline", {})
            sr = m.get("success_rate", {})
            if isinstance(p, dict) and p.get("pipeline_score") is not None:
                template_parts.append(
                    f"**{r_ent['label']}**: pipeline score {p['pipeline_score']}, "
                    f"{p.get('total_trials', 0)} trials "
                    f"(P1: {p.get('p1_count', 0)}, P2: {p.get('p2_count', 0)}, "
                    f"P3: {p.get('p3_count', 0)}, P4: {p.get('p4_count', 0)})."
                )
            if isinstance(sr, dict) and sr.get("success_rate") is not None:
                template_parts.append(
                    f"Success rate: {float(sr['success_rate']):.1f}%."
                )

    # LLM synthesis
    fallback = " ".join(template_parts)

    # Build per-entity metrics for LLM
    metrics_for_llm = {}
    for r_ent in resolved:
        m = metrics_comp.get(r_ent["entity_id"], {})
        if m:
            metrics_for_llm[r_ent["label"]] = m

    # Pre-compute differentials so the LLM can cite them directly
    comparison_insights = compute_comparison_insights(resolved, metrics_comp)
    if comparison_insights:
        fallback = fallback + "\n\n" + comparison_insights

    # Activate domain concepts for compare + resolved entity types
    compare_entity_types = list({r.get("entity_type", "drug") for r in resolved})
    compare_concepts = _concept_registry.activate("compare", compare_entity_types)
    compare_concept_hint = format_concept_context(compare_concepts)
    if compare_concept_hint:
        comparison_insights = f"{compare_concept_hint}\n\n{comparison_insights}" if comparison_insights else compare_concept_hint

    narrative = llm.synthesize_comparison(
        entity_names=names,
        metrics_by_entity=metrics_for_llm,
        shared_connections=result.get("shared_connections"),
        unique_connections=result.get("unique_connections"),
        fallback_narrative=fallback,
        computed_insights=comparison_insights,
    )

    # Normalize to standard QueryResponse format for frontend rendering
    from services.chat_handlers.formatting import build_compare_graph
    entities_list = result.get("entities", [])
    compare_gc = build_compare_graph(
        entities_list,
        result.get("shared_connections", []),
        result.get("unique_connections", {}),
    )
    normalized_data = {
        "question": f"Compare {' vs '.join(names)}",
        "evidence": [],
        "graph_context": compare_gc,
        "metrics_context": metrics_comp,
        "entity_focus": [
            {
                "entity_id": e.get("entity_id", ""),
                "entity_type": e.get("entity_type", "drug"),
                "title": e.get("label", "Unknown"),
                "label": e.get("label", "Unknown"),
                "metadata": e.get("properties", {}),
                "total_connections": e.get("total_connections"),
            }
            for e in entities_list
        ],
        "provenance_summary": {
            "total_evidence_items": len(result.get("shared_connections", [])),
            "by_source": {"graph": len(result.get("shared_connections", []))},
        },
    }

    # Build a comparison table so the frontend shows DataTable + CSV export
    comparison_table = build_comparison_table(resolved, metrics_comp)

    from services.chat_handlers.formatting import compute_response_confidence
    confidence = compute_response_confidence(
        entity_resolved=len(resolved) >= 2,
        evidence_count=sum(len(r.get("evidence", [])) for r in resolved),
        graph_node_count=compare_gc.get("node_count", 0),
        metrics_available=bool(metrics_comp),
    )

    return {
        "narrative": narrative,
        "intent": "compare",
        "confidence": confidence,
        "data": normalized_data,
        "table_data": comparison_table,
    }


def handle_landscape(question: str, params: dict, metrics_svc: PharmaMetrics, llm: LLMSynthesizer, conv_context: str = "") -> dict:
    topic = params.get("topic", "")
    expanded_topic = expand_topic_synonyms(topic) if topic else ""
    segments = metrics_svc.competitive_landscape(
        topic=expanded_topic if expanded_topic else None,
        original_topic=topic if topic and expanded_topic != topic else None,
        limit=30,
    )
    if not segments:
        return {"narrative": "No competitive landscape data available.", "intent": "landscape", "data": None}

    top = sorted(segments, key=lambda x: x.get("total_pipeline_score", 0), reverse=True)[:10]

    # Enrich with company participation data
    companies = metrics_svc.company_portfolio(limit=10)
    top_companies = sorted(companies, key=lambda c: c.get("pipeline_score_total", 0), reverse=True)[:5]

    # Compute concentration metrics
    drug_counts = [s.get("drug_count", 0) or 0 for s in segments]
    total_drugs = sum(drug_counts)

    hhi = 0
    top3_share = 0.0
    concentration_label = "fragmented"
    if total_drugs > 0:
        shares = [(dc / total_drugs) for dc in drug_counts]
        hhi = int(sum(s * s * 10000 for s in shares))
        top3_share = sum(sorted(shares, reverse=True)[:3]) * 100
        if hhi > 2500:
            concentration_label = "highly concentrated"
        elif hhi > 1500:
            concentration_label = "moderately concentrated"
        else:
            concentration_label = "fragmented"

    # Template fallback
    topic_label = f" for **{topic}**" if topic else ""
    template_parts = [f"The competitive landscape{topic_label} spans **{len(segments)} market segments**."]
    if top:
        best = top[0]
        template_parts.append(
            f"The strongest segment is **{best.get('mechanism_name', 'Unknown')}** "
            f"with {best.get('drug_count', 0)} drugs and a pipeline score of "
            f"{best.get('total_pipeline_score', 0):.0f}."
        )
    template_parts.append(
        f"Market concentration is **{concentration_label}** (HHI: {hhi}). "
        f"The top 3 segments account for **{top3_share:.0f}%** of total drugs."
    )
    if top_companies:
        company_names = [c.get("company_name", "?") for c in top_companies[:3]]
        template_parts.append(
            f"Leading companies by pipeline strength: **{', '.join(company_names)}**."
        )
    fallback = " ".join(template_parts)

    # Build extra context for LLM with company data
    extra_landscape_context = ""
    if top_companies:
        extra_landscape_context = "TOP COMPANIES:\n" + "\n".join(
            f"- {c.get('company_name', '?')}: {c.get('drug_count', 0)} drugs, "
            f"{c.get('trial_count', 0)} trials, pipeline score {c.get('pipeline_score_total', 0):.0f}"
            for c in top_companies
        )
    extra_landscape_context += (
        f"\n\nCONCENTRATION (across therapeutic areas, NOT companies): "
        f"{concentration_label} (HHI={hhi}, top-3 therapeutic area share={top3_share:.0f}%)"
    )
    if conv_context:
        extra_landscape_context += f"\n\nPRIOR CONVERSATION:\n{conv_context}"

    # Activate domain concepts for landscape intent
    landscape_concepts = _concept_registry.activate("landscape", ["drug", "company", "therapeutic_area"])
    landscape_concept_hint = format_concept_context(landscape_concepts)
    if landscape_concept_hint:
        extra_landscape_context = f"{landscape_concept_hint}\n\n{extra_landscape_context}" if extra_landscape_context else landscape_concept_hint

    # LLM synthesis
    narrative = llm.synthesize(
        question=question,
        intent="landscape",
        metrics={"segments": top},
        extra_context=extra_landscape_context,
        fallback_narrative=fallback,
    )

    # Build table for DataTable + CSV export
    landscape_table = {
        "columns": [
            {"key": "mechanism_name", "label": "Mechanism", "type": "text"},
            {"key": "therapeutic_area", "label": "Therapeutic Area", "type": "text"},
            {"key": "drug_count", "label": "Drugs", "type": "number"},
            {"key": "trial_count", "label": "Trials", "type": "number"},
            {"key": "active_trial_count", "label": "Active Trials", "type": "number"},
            {"key": "total_pipeline_score", "label": "Pipeline Score", "type": "number"},
        ],
        "rows": [
            {
                "mechanism_name": s.get("mechanism_name", "Unknown"),
                "therapeutic_area": s.get("therapeutic_area", "—"),
                "drug_count": s.get("drug_count", 0),
                "trial_count": s.get("trial_count", 0),
                "active_trial_count": s.get("active_trial_count", 0),
                "total_pipeline_score": round(s.get("total_pipeline_score", 0), 1),
            }
            for s in top
        ],
        "title": "Competitive Landscape",
    }

    from services.chat_handlers.formatting import compute_response_confidence
    confidence = compute_response_confidence(
        entity_resolved=False, evidence_count=0,
        graph_node_count=0, metrics_available=bool(segments),
    )

    return {
        "narrative": narrative,
        "intent": "landscape",
        "confidence": confidence,
        "data": {
            "question": question,
            "evidence": [],
            "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
            "metrics_context": {s.get("mechanism_name", f"seg_{i}"): {"competitive": s} for i, s in enumerate(top)},
            "entity_focus": [],
            "provenance_summary": {"total_evidence_items": len(segments), "by_source": {"metrics": len(segments)}},
        },
        "table_data": landscape_table,
    }


def handle_portfolio(params: dict, db: Database, engine: QueryEngine, metrics_svc: PharmaMetrics, llm: LLMSynthesizer, conv_context: str = "") -> dict:
    name = params.get("company_name", "")
    resolved = resolve_entity(name, "company", db)

    if not resolved:
        return {
            "narrative": f"Could not find company '{name}'. Try 'Novo Nordisk portfolio' or 'Eli Lilly portfolio'.",
            "intent": "portfolio",
            "data": None,
        }

    result = engine.entity_dossier(resolved["entity_id"], "company")
    portfolio = metrics_svc.company_portfolio(company_id=resolved["entity_id"], limit=1)

    # Template fallback
    template = f"**{resolved['label']}** portfolio overview."
    if portfolio:
        p = portfolio[0]
        template += (
            f" {p.get('drug_count', 0)} drugs, {p.get('trial_count', 0)} trials "
            f"({p.get('active_trial_count', 0)} active), pipeline score: {p.get('pipeline_score_total', 0):.0f}."
        )

    # LLM synthesis
    entity_details = {"company_name": resolved["label"]}
    if portfolio:
        entity_details.update(portfolio[0])

    evidence_snippets = [e.content for e in result.evidence[:10]]

    narrative = llm.synthesize_dossier(
        question=f"{resolved['label']} portfolio",
        entity_name=resolved["label"],
        entity_type="company",
        entity_details=entity_details,
        metrics={"portfolio": portfolio[0]} if portfolio else None,
        evidence_snippets=evidence_snippets,
        fallback_narrative=template,
    )

    # Build table for DataTable + CSV export
    portfolio_table = None
    if portfolio:
        p = portfolio[0]
        portfolio_table = {
            "columns": [
                {"key": "metric", "label": "Metric", "type": "text"},
                {"key": "value", "label": "Value", "type": "text"},
            ],
            "rows": [
                {"metric": "Drugs", "value": str(p.get("drug_count", 0))},
                {"metric": "Trials", "value": str(p.get("trial_count", 0))},
                {"metric": "Active Trials", "value": str(p.get("active_trial_count", 0))},
                {"metric": "Articles", "value": str(p.get("article_count", 0))},
                {"metric": "Therapeutic Areas", "value": str(p.get("ta_count", 0))},
                {"metric": "Pipeline Score", "value": str(round(p.get("pipeline_score_total", 0), 1))},
            ],
            "title": f"{resolved['label']} Portfolio",
        }

    return {
        "narrative": narrative,
        "intent": "portfolio",
        "data": _enrich_result(result, db),
        "table_data": portfolio_table,
    }


def handle_pipeline(params: dict, metrics_svc: PharmaMetrics, llm: LLMSynthesizer, conv_context: str = "") -> dict:
    ta = params.get("therapeutic_area", "")
    pipelines = metrics_svc.drug_pipeline_strength(therapeutic_area=ta if ta else None, limit=20)

    if not pipelines:
        return {"narrative": "No pipeline data available for this query.", "intent": "pipeline", "data": None}

    top = sorted(pipelines, key=lambda x: x.get("pipeline_score", 0), reverse=True)[:10]

    # Template fallback
    template = f"Top **{len(top)}** drugs by pipeline strength"
    if ta:
        template += f" in **{ta}**"
    template += "."
    if top:
        best = top[0]
        template += (
            f" Leading: **{best.get('drug_name', 'Unknown')}** "
            f"(score: {best.get('pipeline_score', 0)}"
        )
        pr = best.get("phase_progression_rate")
        if pr is not None:
            template += f", late/early ratio: {pr}"
        pct = best.get("percentile_rank")
        if pct is not None:
            template += f", {pct}th percentile"
        template += ")."

    # Build extra context with phase distribution insights
    early_heavy = sum(1 for p in top if (p.get("p1_count", 0) or 0) + (p.get("p2_count", 0) or 0) > (p.get("p3_count", 0) or 0) + (p.get("p4_count", 0) or 0))
    late_heavy = len(top) - early_heavy
    extra_context = f"PIPELINE MATURITY: {late_heavy} of {len(top)} drugs are late-stage heavy (Phase 3+4 > Phase 1+2)."
    if ta:
        extra_context += f"\nTherapeutic area focus: {ta}"
    if conv_context:
        extra_context += f"\n\nPRIOR CONVERSATION:\n{conv_context}"

    # Activate domain concepts for pipeline intent
    pipeline_concepts = _concept_registry.activate("pipeline", ["drug", "therapeutic_area"])
    pipeline_concept_hint = format_concept_context(pipeline_concepts)
    if pipeline_concept_hint:
        extra_context = f"{pipeline_concept_hint}\n\n{extra_context}" if extra_context else pipeline_concept_hint

    # LLM synthesis
    narrative = llm.synthesize(
        question=f"Pipeline {'for ' + ta if ta else 'overview'}",
        intent="pipeline",
        metrics={"pipelines": top},
        extra_context=extra_context,
        fallback_narrative=template,
    )

    # Build table for DataTable + CSV export
    pipeline_table = {
        "columns": [
            {"key": "drug_name", "label": "Drug", "type": "text"},
            {"key": "p1_count", "label": "Phase 1", "type": "number"},
            {"key": "p2_count", "label": "Phase 2", "type": "number"},
            {"key": "p3_count", "label": "Phase 3", "type": "number"},
            {"key": "p4_count", "label": "Phase 4", "type": "number"},
            {"key": "total_trials", "label": "Total Trials", "type": "number"},
            {"key": "pipeline_score", "label": "Pipeline Score", "type": "number"},
        ],
        "rows": [
            {
                "drug_name": p.get("drug_name", "Unknown"),
                "p1_count": p.get("p1_count", 0),
                "p2_count": p.get("p2_count", 0),
                "p3_count": p.get("p3_count", 0),
                "p4_count": p.get("p4_count", 0),
                "total_trials": p.get("total_trials", 0),
                "pipeline_score": round(p.get("pipeline_score", 0), 1),
            }
            for p in top
        ],
        "title": f"Pipeline Strength{' — ' + ta if ta else ''}",
    }

    from services.chat_handlers.formatting import compute_response_confidence
    confidence = compute_response_confidence(
        entity_resolved=False, evidence_count=0,
        graph_node_count=0, metrics_available=bool(pipelines),
    )

    return {
        "narrative": narrative,
        "intent": "pipeline",
        "confidence": confidence,
        "data": {
            "question": f"Pipeline {'for ' + ta if ta else 'overview'}",
            "evidence": [],
            "graph_context": {"nodes": [], "edges": [], "node_count": 0, "edge_count": 0},
            "metrics_context": {p.get("drug_name", f"drug_{i}"): {"pipeline": p} for i, p in enumerate(top)},
            "entity_focus": [],
            "provenance_summary": {"total_evidence_items": len(top), "by_source": {"metrics": len(top)}},
        },
        "table_data": pipeline_table,
    }


def handle_general(
    question: str,
    engine: QueryEngine,
    db: Database,
    llm: LLMSynthesizer,
    include_graph: bool = True,
    include_metrics: bool = True,
    conv_context: str = "",
) -> dict:
    result = engine.query(
        question,
        include_graph=include_graph,
        include_metrics=include_metrics,
    )
    return _format_query_result("general", question, result, db, llm, conv_context=conv_context)


def handle_deep_research(
    question: str,
    db: Database,
    engine: QueryEngine,
    llm: LLMSynthesizer,
    web_research: WebResearchService,
    include_graph: bool,
    include_metrics: bool,
    include_web: bool,
) -> dict:
    """Expanded research flow: richer evidence pass + optional web augmentation."""
    result = engine.query(
        question,
        max_evidence=24,
        include_graph=include_graph,
        include_metrics=include_metrics,
    )
    enriched = _enrich_result(result, db)
    web_results = web_research.search(question, limit=6) if include_web else []

    report_fallback = _build_research_fallback_report(question, enriched, web_results)
    report = llm.synthesize_research_report(
        question=question,
        graph_summary=enriched.get("graph_context"),
        metrics=enriched.get("metrics_context"),
        evidence_snippets=[e.get("content", "") for e in enriched.get("evidence", [])[:12]],
        web_results=web_results,
        fallback_report=report_fallback,
    )
    narrative = _extract_research_summary(report)

    return {
        "narrative": narrative,
        "intent": Intent.DEEP_RESEARCH,
        "data": enriched,
        "report": report,
        "web_results": web_results,
        "report_meta": {
            "web_enabled": include_web,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "visualizations": build_visualizations(enriched),
    }


# ── Compound intent handler ──

# Maps intent names to handler callables. Each value is a callable that
# accepts (intent, params, **handler_kwargs) and returns a response dict.
_INTENT_DISPATCH = {
    Intent.DOSSIER: lambda params, **kw: handle_dossier(params, kw["db"], kw["engine"], kw["llm"], conv_context=kw.get("conv_context", "")),
    Intent.COMPARE: lambda params, **kw: handle_compare(params, kw["db"], kw["engine"], kw["llm"], conv_context=kw.get("conv_context", "")),
    Intent.LANDSCAPE: lambda params, **kw: handle_landscape(kw.get("question", ""), params, kw["metrics_svc"], kw["llm"], conv_context=kw.get("conv_context", "")),
    Intent.PORTFOLIO: lambda params, **kw: handle_portfolio(params, kw["db"], kw["engine"], kw["metrics_svc"], kw["llm"], conv_context=kw.get("conv_context", "")),
    Intent.PIPELINE: lambda params, **kw: handle_pipeline(params, kw["metrics_svc"], kw["llm"], conv_context=kw.get("conv_context", "")),
    Intent.GENERAL: lambda params, **kw: handle_general(kw.get("question", ""), kw["engine"], kw["db"], kw["llm"], conv_context=kw.get("conv_context", "")),
}


def _merge_data_contexts(data_a: dict | None, data_b: dict | None) -> dict:
    """Merge two data context dicts (evidence, graph, entity_focus, etc.)."""
    if not data_a:
        return data_b or {}
    if not data_b:
        return data_a

    merged = dict(data_a)

    # Merge evidence lists
    ev_a = data_a.get("evidence") or []
    ev_b = data_b.get("evidence") or []
    merged["evidence"] = ev_a + ev_b

    # Merge graph_context
    gc_a = data_a.get("graph_context") or {}
    gc_b = data_b.get("graph_context") or {}
    merged["graph_context"] = {
        "nodes": (gc_a.get("nodes") or []) + (gc_b.get("nodes") or []),
        "edges": (gc_a.get("edges") or []) + (gc_b.get("edges") or []),
        "node_count": (gc_a.get("node_count") or 0) + (gc_b.get("node_count") or 0),
        "edge_count": (gc_a.get("edge_count") or 0) + (gc_b.get("edge_count") or 0),
    }

    # Merge entity_focus
    ef_a = data_a.get("entity_focus") or []
    ef_b = data_b.get("entity_focus") or []
    merged["entity_focus"] = ef_a + ef_b

    # Merge provenance_summary
    ps_a = (data_a.get("provenance_summary") or {}).get("by_source") or {}
    ps_b = (data_b.get("provenance_summary") or {}).get("by_source") or {}
    merged_by_source = dict(ps_a)
    for src, count in ps_b.items():
        merged_by_source[src] = merged_by_source.get(src, 0) + count
    merged["provenance_summary"] = {
        "total_evidence_items": len(merged["evidence"]),
        "by_source": merged_by_source,
    }

    # Merge metrics_context
    mc_a = data_a.get("metrics_context") or {}
    mc_b = data_b.get("metrics_context") or {}
    merged["metrics_context"] = {**mc_a, **mc_b}

    return merged


def handle_compound(intents: list[tuple[str, dict]], **handler_kwargs) -> dict:
    """Execute multiple intents and merge their results.

    Runs each intent's handler, merges narratives and data contexts,
    and returns a combined response with the minimum confidence score.
    """
    if not intents:
        return {"narrative": "", "intent": "general", "data": None}

    results: list[dict] = []
    for intent, params in intents:
        handler_fn = _INTENT_DISPATCH.get(intent)
        if handler_fn is None:
            logger.warning("No dispatch entry for intent %s, skipping", intent)
            continue
        try:
            result = handler_fn(params, **handler_kwargs)
            results.append(result)
        except Exception as exc:
            logger.warning("Compound intent handler failed for %s: %s", intent, exc)

    if not results:
        return {"narrative": "", "intent": "general", "data": None}

    if len(results) == 1:
        return results[0]

    # Merge narratives
    narratives = [r.get("narrative", "") for r in results if r.get("narrative")]
    combined_narrative = "\n\n---\n\n".join(narratives)

    # Merge data contexts
    merged_data = results[0].get("data")
    for r in results[1:]:
        merged_data = _merge_data_contexts(merged_data, r.get("data"))

    # Confidence is min of all results
    confidences = [r["confidence"] for r in results if "confidence" in r]
    confidence = min(confidences) if confidences else None

    # Intent label is a joined string
    intent_labels = [r.get("intent", "general") for r in results]
    compound_intent = "+".join(intent_labels)

    payload = {
        "narrative": combined_narrative,
        "intent": compound_intent,
        "data": merged_data,
    }
    if confidence is not None:
        payload["confidence"] = confidence

    return payload
