"""Metrics tool — wraps PharmaMetrics for agent use."""

from __future__ import annotations

import logging
from typing import Optional

from services.agent.tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class MetricsQueryTool(BaseTool):
    """Queries pre-computed pharma metrics."""

    def __init__(self, metrics_service):
        self._metrics = metrics_service

    @property
    def name(self) -> str:
        return "metrics"

    def execute(self, action: str, params: dict, prior_results: Optional[dict] = None) -> ToolResult:
        """Execute a metrics query.

        action: one of "pipeline", "success_rate", "evidence", "landscape", "portfolio"
        params: passed through to the underlying metrics method
        """
        try:
            if action == "pipeline":
                data = self._metrics.drug_pipeline_strength(
                    therapeutic_area=params.get("therapeutic_area"),
                    limit=params.get("limit", 20),
                )
            elif action == "success_rate":
                data = self._metrics.trial_success_rate(
                    drug_id=params.get("drug_id"),
                    limit=params.get("limit", 20),
                )
            elif action == "evidence":
                data = self._metrics.evidence_density(
                    drug_id=params.get("drug_id"),
                    limit=params.get("limit", 20),
                )
            elif action == "landscape":
                data = self._metrics.competitive_landscape(
                    limit=params.get("limit", 30),
                )
            elif action == "portfolio":
                data = self._metrics.company_portfolio(
                    company_id=params.get("company_id"),
                    limit=params.get("limit", 10),
                )
            else:
                return ToolResult(
                    tool="metrics",
                    success=False,
                    error=f"Unknown metrics action: {action}",
                )

            if not data:
                return ToolResult(
                    tool="metrics",
                    success=True,
                    data=[],
                    row_count=0,
                    metadata={"action": action},
                )

            columns = list(data[0].keys()) if data and isinstance(data[0], dict) else []
            return ToolResult(
                tool="metrics",
                success=True,
                data=data,
                columns=columns,
                row_count=len(data),
                metadata={"action": action},
            )
        except Exception as e:
            logger.warning("Metrics tool error (%s): %s", action, e)
            return ToolResult(
                tool="metrics",
                success=False,
                error=f"Metrics error: {str(e)[:300]}",
            )
