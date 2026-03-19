"""Graph traversal tool — wraps GraphTraversal for agent use."""

from __future__ import annotations

import logging
from typing import Optional

from services.agent.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class GraphSearchTool(BaseTool):
    """Explores the knowledge graph via GraphTraversal."""

    def __init__(self, graph_service):
        self._graph = graph_service

    @property
    def name(self) -> str:
        return "graph"

    def execute(self, action: str, params: dict, prior_results: Optional[dict] = None) -> ToolResult:
        """Execute a graph operation.

        params:
            entity_id: str — entity to explore
            entity_type: str — entity type
            hops: int — traversal depth (default 1)
        """
        entity_id = params.get("entity_id", "")
        entity_type = params.get("entity_type", "")

        if not entity_id:
            return ToolResult(tool="graph", success=False, error="No entity_id provided")

        try:
            subgraph = self._graph.neighborhood(entity_id, entity_type)
            nodes = [
                {
                    "entity_id": n.entity_id,
                    "entity_type": n.entity_type,
                    "label": n.label,
                }
                for n in subgraph.nodes
            ]
            edges = [
                {
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "link_type": e.link_type,
                    "confidence": e.confidence,
                }
                for e in subgraph.edges
            ]

            return ToolResult(
                tool="graph",
                success=True,
                data={"nodes": nodes, "edges": edges},
                row_count=len(nodes),
                metadata={
                    "entity_id": entity_id,
                    "entity_type": entity_type,
                    "node_count": len(nodes),
                    "edge_count": len(edges),
                },
            )
        except Exception as e:
            logger.warning("Graph tool error: %s", e)
            return ToolResult(
                tool="graph",
                success=False,
                error=f"Graph traversal error: {str(e)[:300]}",
            )
