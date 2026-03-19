"""Root pytest fixtures for market-zero tests."""

from __future__ import annotations

import json
import pytest
from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import MagicMock

from services.agent.tools.base import BaseTool, ToolResult


# ── ToolCallRecorder ──

class ToolCallRecorder:
    """Wraps a BaseTool and records all execute() calls.

    Usage:
        recorder = ToolCallRecorder(real_tool)
        # pass recorder where tool is expected
        recorder.execute("search", {"query": "tirzepatide"})
        assert recorder.call_count >= 1
        assert recorder.calls[0]["action"] == "search"
    """

    def __init__(self, real_tool: BaseTool):
        self._real = real_tool
        self.calls: list[dict] = []

    def execute(self, action: str, params: dict, prior_results: Optional[dict] = None) -> ToolResult:
        self.calls.append({"action": action, "params": params})
        return self._real.execute(action, params, prior_results)

    @property
    def name(self) -> str:
        return self._real.name

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def reset(self):
        self.calls.clear()

    def get_params(self, action: str | None = None) -> list[dict]:
        """Get params for calls matching an action filter."""
        if action is None:
            return [c["params"] for c in self.calls]
        return [c["params"] for c in self.calls if c["action"] == action]


# ── Stub tools ──

class StubTool(BaseTool):
    """A tool that returns pre-configured results."""

    def __init__(self, tool_name: str, results: dict[str, ToolResult] | None = None):
        self._name = tool_name
        self._results = results or {}
        self._default = ToolResult(tool=tool_name, success=True, data=[], row_count=0)

    @property
    def name(self) -> str:
        return self._name

    def execute(self, action: str, params: dict, prior_results: Optional[dict] = None) -> ToolResult:
        return self._results.get(action, self._default)


def make_rag_result(items: list[dict]) -> ToolResult:
    """Build a ToolResult that looks like RAG search output."""
    return ToolResult(
        tool="rag",
        success=True,
        data=items,
        row_count=len(items),
        metadata={"query": "test"},
    )


def make_sql_result(rows: list[dict], columns: list[str] | None = None) -> ToolResult:
    """Build a ToolResult that looks like SQL output."""
    cols = columns or (list(rows[0].keys()) if rows else [])
    return ToolResult(
        tool="sql",
        success=True,
        data=rows,
        columns=cols,
        row_count=len(rows),
        metadata={"sql": "SELECT ..."},
    )


def make_graph_result(nodes: list[dict], edges: list[dict]) -> ToolResult:
    """Build a ToolResult that looks like graph output."""
    return ToolResult(
        tool="graph",
        success=True,
        data={"nodes": nodes, "edges": edges},
        row_count=len(nodes),
        metadata={"node_count": len(nodes), "edge_count": len(edges)},
    )


def make_metrics_result(rows: list[dict]) -> ToolResult:
    """Build a ToolResult that looks like metrics output."""
    cols = list(rows[0].keys()) if rows else []
    return ToolResult(
        tool="metrics",
        success=True,
        data=rows,
        columns=cols,
        row_count=len(rows),
        metadata={"action": "pipeline"},
    )


def make_empty_result(tool_name: str) -> ToolResult:
    return ToolResult(tool=tool_name, success=True, data=[], row_count=0)


# ── Mock LLM ──

class MockLLM:
    """A mock LLM that returns pre-configured responses.

    Can be configured with a response_fn for dynamic responses,
    or uses a static default response.
    """

    def __init__(self, default_response: str = '{}', response_fn=None):
        self.default_response = default_response
        self.response_fn = response_fn
        self.calls: list[list] = []

    def invoke(self, messages: list) -> MagicMock:
        self.calls.append(messages)
        if self.response_fn:
            content = self.response_fn(messages)
        else:
            content = self.default_response
        resp = MagicMock()
        resp.content = content
        return resp

    @property
    def call_count(self) -> int:
        return len(self.calls)


# ── Fixtures ──

@pytest.fixture
def mock_llm():
    return MockLLM()


@pytest.fixture
def stub_sql_tool():
    return StubTool("sql")


@pytest.fixture
def stub_rag_tool():
    return StubTool("rag")


@pytest.fixture
def stub_graph_tool():
    return StubTool("graph")


@pytest.fixture
def stub_metrics_tool():
    return StubTool("metrics")
