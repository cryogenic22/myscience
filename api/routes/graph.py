"""Graph traversal and analytics API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from typing import Optional

from api.deps import get_graph, get_graph_analytics
from api.schemas import SubgraphResponse, GraphNodeResponse, GraphEdgeResponse, EntitySummaryResponse
from services.graph import GraphTraversal
from services.graph_analytics import GraphAnalytics

router = APIRouter(prefix="/graph", tags=["graph"])


def _subgraph_to_response(sg) -> SubgraphResponse:
    return SubgraphResponse(
        nodes=[GraphNodeResponse(
            entity_id=n.entity_id, entity_type=n.entity_type, label=n.label,
        ) for n in sg.nodes],
        edges=[GraphEdgeResponse(
            source_id=e.source_id, target_id=e.target_id,
            link_type=e.link_type, confidence=e.confidence,
            via=e.via, source=e.source,
        ) for e in sg.edges],
        center_entity_id=sg.center_entity_id,
        node_count=len(sg.nodes),
        edge_count=len(sg.edges),
    )


@router.get("/neighborhood/{entity_type}/{entity_id}", response_model=SubgraphResponse)
def neighborhood(
    entity_type: str,
    entity_id: str,
    link_types: Optional[str] = Query(None, description="Comma-separated link types to filter"),
    min_confidence: Optional[float] = Query(None, ge=0, le=1, description="Minimum edge confidence"),
    svc: GraphTraversal = Depends(get_graph),
):
    """1-hop neighborhood of an entity."""
    lt = link_types.split(",") if link_types else None
    sg = svc.neighborhood(entity_id, entity_type, link_types=lt, min_confidence=min_confidence)
    return _subgraph_to_response(sg)


@router.get("/traverse/{entity_type}/{entity_id}", response_model=SubgraphResponse)
def traverse(
    entity_type: str,
    entity_id: str,
    hops: int = Query(2, ge=1, le=4),
    max_nodes: int = Query(100, ge=1, le=500),
    link_types: Optional[str] = Query(None, description="Comma-separated link types to filter"),
    min_confidence: Optional[float] = Query(None, ge=0, le=1, description="Minimum edge confidence"),
    svc: GraphTraversal = Depends(get_graph),
):
    """N-hop BFS traversal from an entity."""
    lt = link_types.split(",") if link_types else None
    sg = svc.traverse(
        entity_id, entity_type, hops=hops,
        link_types=lt, min_confidence=min_confidence, max_nodes=max_nodes,
    )
    return _subgraph_to_response(sg)


@router.get("/summary/{entity_type}/{entity_id}", response_model=EntitySummaryResponse)
def entity_summary(
    entity_type: str,
    entity_id: str,
    svc: GraphTraversal = Depends(get_graph),
):
    """Rich entity summary with connection counts."""
    return svc.entity_summary(entity_id, entity_type)


@router.get("/path")
def path_between(
    source_id: str = Query(...),
    source_type: str = Query(...),
    target_id: str = Query(...),
    target_type: str = Query(...),
    max_hops: int = Query(4, ge=1, le=6),
    svc: GraphTraversal = Depends(get_graph),
):
    """Shortest path between two entities."""
    edges = svc.path_between(source_id, source_type, target_id, target_type, max_hops=max_hops)
    if edges is None:
        return {"path": None, "message": "No path found"}
    return {
        "path": [
            {"source": e.source_id, "target": e.target_id,
             "type": e.link_type, "confidence": e.confidence}
            for e in edges
        ],
        "hops": len(edges),
    }


# ── Graph analytics endpoints ──


@router.get("/analytics/influence/{entity_id}")
def entity_influence(
    entity_id: str,
    entity_type: str = Query("drug", description="Entity type"),
    svc: GraphAnalytics = Depends(get_graph_analytics),
):
    """PageRank-inspired influence score (0-1) for an entity."""
    score = svc.entity_influence(entity_id, entity_type)
    return {
        "entity_id": entity_id,
        "entity_type": entity_type,
        "influence": round(score, 4),
    }


@router.get("/analytics/clusters")
def competitive_clusters(
    mechanism_id: Optional[str] = Query(None, description="Filter by mechanism UUID"),
    therapeutic_area_id: Optional[str] = Query(None, description="Filter by TA UUID"),
    svc: GraphAnalytics = Depends(get_graph_analytics),
):
    """Competitive clusters: drugs grouped by shared mechanism + TA."""
    clusters = svc.competitive_clusters(
        mechanism_id=mechanism_id,
        therapeutic_area_id=therapeutic_area_id,
    )
    return {"clusters": clusters, "count": len(clusters)}


@router.get("/analytics/centrality")
def entity_centrality(
    entity_type: str = Query("drug", description="Entity type to rank"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    svc: GraphAnalytics = Depends(get_graph_analytics),
):
    """Top entities by influence score for a given type."""
    results = svc.entity_centrality_batch(entity_type=entity_type, limit=limit)
    return {"entities": results, "count": len(results)}


@router.get("/analytics/weighted-path")
def weighted_path(
    source_id: str = Query(..., description="Source entity UUID"),
    target_id: str = Query(..., description="Target entity UUID"),
    max_hops: int = Query(4, ge=1, le=6, description="Maximum path length"),
    svc: GraphAnalytics = Depends(get_graph_analytics),
):
    """Confidence-weighted path between two entities."""
    path = svc.weighted_path(source_id, target_id, max_hops=max_hops)
    if not path:
        return {"path": [], "message": "No path found", "hops": 0}
    return {"path": path, "hops": len(path)}
