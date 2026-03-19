"""
MCP Server for Market-Zero: 6 tools exposing the pharma intelligence layer.

Tools:
    search_knowledge    - Hybrid metadata + vector search across entity types
    get_entity          - Entity details with graph summary
    get_metrics         - Pharma KPIs (pipeline, success rate, evidence, competitive, portfolio)
    explore_graph       - N-hop graph traversal from an entity
    query_knowledge     - Full GraphRAG query (search + graph + metrics)
    get_entity_dossier  - Comprehensive entity dossier

Run:
    python -m api.mcp_server
"""

from __future__ import annotations

import json
import logging
import sys

sys.path.insert(0, ".")

from mcp.server import FastMCP

from db import Database
from config import config
from services.search import HybridSearch
from services.graph import GraphTraversal
from services.metrics import PharmaMetrics
from services.query_engine import QueryEngine

logger = logging.getLogger(__name__)

# ---- Service initialization ----

db = Database(config.db.dsn)
db.connect()

search_svc = HybridSearch(db, config)
graph_svc = GraphTraversal(db, config)
metrics_svc = PharmaMetrics(db, config)
query_engine = QueryEngine(db, config, search_svc, graph_svc, metrics_svc)

# ---- MCP Server ----

mcp = FastMCP(
    "Market-Zero",
    instructions=(
        "Pharmaceutical intelligence platform. Search drugs, trials, literature, "
        "companies. Query pipeline metrics, graph relationships, and competitive landscape. "
        "All data sourced from FDA, ClinicalTrials.gov, PubMed, SEC EDGAR."
    ),
)


def _serialize(obj):
    """Convert non-serializable types for JSON output."""
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    if hasattr(obj, "__dataclass_fields__"):
        return {k: _serialize(v) for k, v in obj.__dict__.items()}
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    from decimal import Decimal
    if isinstance(obj, Decimal):
        return float(obj)
    return obj


@mcp.tool(
    name="search_knowledge",
    description=(
        "Search the pharma knowledge base using natural language. "
        "Combines metadata filtering with semantic vector search. "
        "Searches across drugs, clinical trials, PubMed articles, and companies. "
        "Returns ranked results with provenance."
    ),
)
def search_knowledge(
    query: str,
    entity_types: str = "",
    filters: str = "",
    limit: int = 10,
) -> str:
    """Search the knowledge base.

    Args:
        query: Natural language search (e.g., 'GLP-1 receptor agonist obesity Phase 3')
        entity_types: Comma-separated types to search: drug, trial, literature, company (default: all)
        filters: JSON string of filters, e.g. '{"phase": "Phase 3", "status": "RECRUITING"}'
        limit: Max results (1-50)
    """
    types = [t.strip() for t in entity_types.split(",") if t.strip()] or None
    filt = json.loads(filters) if filters else None
    limit = min(max(limit, 1), 50)

    results = search_svc.search(query=query, entity_types=types, filters=filt, limit=limit)
    output = []
    for r in results:
        output.append({
            "entity_id": r.entity_id,
            "entity_type": r.entity_type,
            "title": r.title,
            "similarity": round(r.similarity, 3),
            "metadata": _serialize(r.metadata),
            "provenance": _serialize(r.provenance),
        })
    return json.dumps(output, indent=2, default=str)


@mcp.tool(
    name="get_entity",
    description=(
        "Get details for a specific entity (drug, trial, company, etc.) "
        "including its properties and graph connection summary."
    ),
)
def get_entity(entity_id: str, entity_type: str) -> str:
    """Get entity details with graph summary.

    Args:
        entity_id: Entity UUID or trial NCT ID
        entity_type: One of: drug, trial, literature, company, event, therapeutic_area, mechanism
    """
    summary = graph_svc.entity_summary(entity_id, entity_type)
    return json.dumps(_serialize(summary), indent=2, default=str)


@mcp.tool(
    name="get_metrics",
    description=(
        "Get pre-computed pharmaceutical KPIs. Available metrics: "
        "pipeline (drug pipeline strength by trial phase), "
        "success_rate (trial completion vs termination rates), "
        "evidence (PubMed article density per drug), "
        "competitive (drugs per mechanism per therapeutic area), "
        "portfolio (company-level rollup). "
        "All metrics are pre-computed from materialized views for accuracy."
    ),
)
def get_metrics(
    metric_type: str,
    drug_id: str = "",
    company_id: str = "",
    therapeutic_area: str = "",
    mechanism_id: str = "",
    limit: int = 20,
) -> str:
    """Get pharma KPI metrics.

    Args:
        metric_type: One of: pipeline, success_rate, evidence, competitive, portfolio
        drug_id: Filter by drug UUID (for pipeline, success_rate, evidence)
        company_id: Filter by company UUID (for portfolio)
        therapeutic_area: Filter by TA name (for pipeline, success_rate)
        mechanism_id: Filter by mechanism UUID (for competitive)
        limit: Max results
    """
    limit = min(max(limit, 1), 200)

    if metric_type == "pipeline":
        data = metrics_svc.drug_pipeline_strength(
            drug_id=drug_id or None, therapeutic_area=therapeutic_area or None, limit=limit,
        )
    elif metric_type == "success_rate":
        data = metrics_svc.trial_success_rate(
            drug_id=drug_id or None, therapeutic_area=therapeutic_area or None, limit=limit,
        )
    elif metric_type == "evidence":
        data = metrics_svc.evidence_density(drug_id=drug_id or None, limit=limit)
    elif metric_type == "competitive":
        data = metrics_svc.competitive_landscape(
            therapeutic_area_id=therapeutic_area or None,
            mechanism_id=mechanism_id or None, limit=limit,
        )
    elif metric_type == "portfolio":
        data = metrics_svc.company_portfolio(company_id=company_id or None, limit=limit)
    else:
        return json.dumps({"error": f"Unknown metric_type: {metric_type}. Use: pipeline, success_rate, evidence, competitive, portfolio"})

    return json.dumps(_serialize(data), indent=2, default=str)


@mcp.tool(
    name="explore_graph",
    description=(
        "Explore the knowledge graph around an entity. "
        "Returns connected entities (drugs, trials, companies, articles) "
        "within N hops. Useful for understanding relationships like "
        "'what trials investigate this drug' or 'what companies sponsor these trials'."
    ),
)
def explore_graph(
    entity_id: str,
    entity_type: str,
    hops: int = 2,
    max_nodes: int = 50,
) -> str:
    """Traverse the knowledge graph.

    Args:
        entity_id: Starting entity UUID or NCT ID
        entity_type: One of: drug, trial, literature, company, event
        hops: Traversal depth (1-4)
        max_nodes: Maximum edges to return (1-200)
    """
    hops = min(max(hops, 1), 4)
    max_nodes = min(max(max_nodes, 1), 200)

    subgraph = graph_svc.traverse(entity_id, entity_type, hops=hops, max_nodes=max_nodes)
    output = {
        "center": entity_id,
        "hops": subgraph.hops,
        "node_count": len(subgraph.nodes),
        "edge_count": len(subgraph.edges),
        "nodes": [
            {"entity_id": n.entity_id, "entity_type": n.entity_type, "label": n.label}
            for n in subgraph.nodes
        ],
        "edges": [
            {"source": e.source_id, "target": e.target_id,
             "type": e.link_type, "confidence": e.confidence}
            for e in subgraph.edges
        ],
    }
    return json.dumps(output, indent=2, default=str)


@mcp.tool(
    name="query_knowledge",
    description=(
        "Answer complex pharma questions using GraphRAG: "
        "combines vector search, graph traversal, and pre-computed metrics "
        "into a single context package with provenance. "
        "Use this for questions like 'What is the competitive landscape for GLP-1 agonists?' "
        "or 'How strong is Novo Nordisk's pipeline?'"
    ),
)
def query_knowledge(
    question: str,
    entity_hints: str = "",
    focus_types: str = "",
    max_evidence: int = 10,
) -> str:
    """Full GraphRAG query.

    Args:
        question: Natural language question about pharma landscape
        entity_hints: Comma-separated known entity names (e.g., 'semaglutide, Novo Nordisk')
        focus_types: Comma-separated entity types to focus on (default: all)
        max_evidence: Maximum evidence items (1-30)
    """
    hints = [h.strip() for h in entity_hints.split(",") if h.strip()] or None
    types = [t.strip() for t in focus_types.split(",") if t.strip()] or None
    max_evidence = min(max(max_evidence, 1), 30)

    result = query_engine.query(
        question=question, entity_hints=hints, focus_types=types, max_evidence=max_evidence,
    )
    output = {
        "question": result.question,
        "evidence": [
            {"source": e.source, "entity_type": e.entity_type,
             "content": e.content, "relevance": round(e.relevance, 3),
             "provenance": _serialize(e.provenance)}
            for e in result.evidence
        ],
        "graph_context": {
            "node_count": result.graph_context.get("node_count", 0),
            "edge_count": result.graph_context.get("edge_count", 0),
        },
        "metrics": _serialize(result.metrics_context),
        "entity_focus": result.entity_focus,
        "provenance_summary": result.provenance_summary,
    }
    return json.dumps(output, indent=2, default=str)


@mcp.tool(
    name="get_entity_dossier",
    description=(
        "Get a comprehensive dossier for a single entity: "
        "properties, graph neighborhood, pipeline metrics, success rates, "
        "evidence density, similar entities, and recent related evidence. "
        "This is the 'tell me everything about X' query."
    ),
)
def get_entity_dossier(entity_id: str, entity_type: str) -> str:
    """Comprehensive entity dossier.

    Args:
        entity_id: Entity UUID or NCT ID
        entity_type: One of: drug, trial, literature, company
    """
    result = query_engine.entity_dossier(entity_id, entity_type)
    output = {
        "entity": result.entity_focus[0] if result.entity_focus else None,
        "graph_summary": {
            "node_count": result.graph_context.get("node_count", 0),
            "edge_count": result.graph_context.get("edge_count", 0),
            "connections_by_type": result.graph_context.get("connections_by_type", {}),
            "total_connections": result.graph_context.get("total_connections", 0),
        },
        "metrics": _serialize(result.metrics_context),
        "evidence_count": len(result.evidence),
        "evidence": [
            {"source": e.source, "entity_type": e.entity_type,
             "content": e.content, "relevance": round(e.relevance, 3)}
            for e in result.evidence[:15]
        ],
        "provenance_summary": result.provenance_summary,
    }
    return json.dumps(output, indent=2, default=str)


if __name__ == "__main__":
    mcp.run()
