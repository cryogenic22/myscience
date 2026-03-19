"""RAG search tool — wraps HybridSearch for agent use."""

from __future__ import annotations

import logging
from typing import Optional

from services.agent.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class RAGSearchTool(BaseTool):
    """Executes hybrid vector + keyword search via HybridSearch."""

    def __init__(self, search_service):
        self._search = search_service

    @property
    def name(self) -> str:
        return "rag"

    def execute(self, action: str, params: dict, prior_results: Optional[dict] = None) -> ToolResult:
        """Execute a RAG search.

        params:
            query: str — search query
            entity_types: list[str] — optional filter by entity types
            limit: int — max results (default 10)
        """
        query = params.get("query", "")
        entity_types = params.get("entity_types")
        limit = params.get("limit", 10)

        if not query:
            return ToolResult(tool="rag", success=False, error="No query provided")

        try:
            results = self._search.search(
                query=query,
                entity_types=entity_types,
                limit=limit,
            )

            evidence = []
            for r in results:
                provenance = dict(r.provenance) if isinstance(r.provenance, dict) else {}
                source_api = provenance.get("source_api") or "search"
                if "source_api" not in provenance:
                    provenance["source_api"] = source_api
                evidence.append({
                    "source": source_api,
                    "entity_type": r.entity_type,
                    "entity_id": r.entity_id,
                    "content": r.snippet or r.title,
                    "relevance": r.similarity,
                    "provenance": provenance,
                })

            return ToolResult(
                tool="rag",
                success=True,
                data=evidence,
                row_count=len(evidence),
                metadata={"query": query, "entity_types": entity_types},
            )
        except Exception as e:
            logger.warning("RAG search error: %s", e)
            return ToolResult(
                tool="rag",
                success=False,
                error=f"Search error: {str(e)[:300]}",
            )
