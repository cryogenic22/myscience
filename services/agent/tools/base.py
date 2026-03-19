"""Base classes for agent tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolResult:
    """Standardized result from any agent tool."""

    tool: str                           # "sql", "rag", "graph", "metrics"
    success: bool
    data: Any = None                    # rows, search results, graph data, etc.
    columns: list[str] = field(default_factory=list)   # column names for tabular data
    row_count: int = 0
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)        # extra info (query, timing, etc.)

    @property
    def is_scalar(self) -> bool:
        """True if the result is a single value."""
        return self.row_count == 1 and len(self.columns) == 1

    @property
    def scalar_value(self) -> Any:
        """Extract scalar value if is_scalar, else None."""
        if self.is_scalar and isinstance(self.data, list) and len(self.data) == 1:
            row = self.data[0]
            if isinstance(row, dict):
                return next(iter(row.values()))
        return None

    @property
    def has_numeric_column(self) -> bool:
        """Check if any column contains numeric data."""
        if not self.data or not isinstance(self.data, list):
            return False
        for row in self.data[:5]:
            if isinstance(row, dict):
                for v in row.values():
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        return True
        return False

    @property
    def has_date_column(self) -> bool:
        """Check if any column name suggests a date."""
        date_keywords = {"date", "time", "year", "month", "day", "created", "updated", "at"}
        return any(
            any(kw in col.lower() for kw in date_keywords)
            for col in self.columns
        )


class BaseTool(ABC):
    """Abstract base for agent tools."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Tool identifier."""

    @abstractmethod
    def execute(self, action: str, params: dict, prior_results: Optional[dict] = None) -> ToolResult:
        """Execute a tool action and return a ToolResult."""
