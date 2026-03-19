"""Graph traversal API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from typing import Optional

from api.deps import get_graph
from api.schemas import SubgraphResponse, GraphNodeResponse, GraphEdgeResponse, EntitySummaryResponse
from services.graph import GraphTraversal

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
    svc: GraphTraversal = Depends(get_graph),
):
    """1-hop neighborhood of an entity."""
    sg = svc.neighborhood(entity_id, entity_type)
    return _subgraph_to_response(sg)


@router.get("/traverse/{entity_type}/{entity_id}", response_model=SubgraphResponse)
def traverse(
    entity_type: str,
    entity_id: str,
    hops: int = Query(2, ge=1, le=4),
    max_nodes: int = Query(100, ge=1, le=500),
    link_types: Optional[str] = Query(None, description="Comma-separated link types"),
    svc: GraphTraversal = Depends(get_graph),
):
    """N-hop BFS traversal from an entity."""
    lt = link_types.split(",") if link_types else None
    sg = svc.traverse(entity_id, entity_type, hops=hops, link_types=lt, max_nodes=max_nodes)
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
