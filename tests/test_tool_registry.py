"""Tests for the agent tool registry."""

import pytest

from services.agent.registry import ToolDefinition, ToolRegistry, create_default_registry


# ── ToolDefinition ──────────────────────────────────────────────


class TestToolDefinition:
    def test_default_values(self):
        td = ToolDefinition(name="test_tool")
        assert td.name == "test_tool"
        assert td.version == "1.0.0"
        assert td.description == ""
        assert td.input_schema == {}
        assert td.output_schema == {}
        assert td.side_effects == "none"
        assert td.trust_tier == "standard"
        assert td.timeout_ms == 5000
        assert td.retryable is True
        assert td.tags == []

    def test_custom_values(self):
        td = ToolDefinition(
            name="custom",
            version="2.0.0",
            description="A custom tool",
            input_schema={"type": "object"},
            output_schema={"type": "array"},
            side_effects="write",
            trust_tier="elevated",
            timeout_ms=30000,
            retryable=False,
            tags=["etl", "pipeline"],
        )
        assert td.name == "custom"
        assert td.version == "2.0.0"
        assert td.description == "A custom tool"
        assert td.input_schema == {"type": "object"}
        assert td.output_schema == {"type": "array"}
        assert td.side_effects == "write"
        assert td.trust_tier == "elevated"
        assert td.timeout_ms == 30000
        assert td.retryable is False
        assert td.tags == ["etl", "pipeline"]


# ── ToolRegistry ────────────────────────────────────────────────


class TestToolRegistry:
    def test_register_and_get(self):
        reg = ToolRegistry()
        td = ToolDefinition(name="alpha", description="first tool")
        reg.register(td)
        retrieved = reg.get("alpha")
        assert retrieved is td
        assert retrieved.description == "first tool"

    def test_get_returns_none_for_unknown(self):
        reg = ToolRegistry()
        assert reg.get("nonexistent") is None

    def test_get_by_tags(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="a", tags=["search", "graph"]))
        reg.register(ToolDefinition(name="b", tags=["metrics"]))
        reg.register(ToolDefinition(name="c", tags=["search", "semantic"]))

        search_tools = reg.get_by_tags(["search"])
        names = {t.name for t in search_tools}
        assert names == {"a", "c"}

        graph_or_metrics = reg.get_by_tags(["graph", "metrics"])
        names = {t.name for t in graph_or_metrics}
        assert names == {"a", "b"}

    def test_get_by_tier_public(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="pub", trust_tier="public"))
        reg.register(ToolDefinition(name="std", trust_tier="standard"))
        reg.register(ToolDefinition(name="elv", trust_tier="elevated"))

        public_only = reg.get_by_tier("public")
        names = {t.name for t in public_only}
        assert names == {"pub"}

    def test_get_by_tier_standard(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="pub", trust_tier="public"))
        reg.register(ToolDefinition(name="std", trust_tier="standard"))
        reg.register(ToolDefinition(name="elv", trust_tier="elevated"))

        up_to_standard = reg.get_by_tier("standard")
        names = {t.name for t in up_to_standard}
        assert names == {"pub", "std"}

    def test_get_by_tier_elevated(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="pub", trust_tier="public"))
        reg.register(ToolDefinition(name="std", trust_tier="standard"))
        reg.register(ToolDefinition(name="elv", trust_tier="elevated"))
        reg.register(ToolDefinition(name="sys", trust_tier="system"))

        up_to_elevated = reg.get_by_tier("elevated")
        names = {t.name for t in up_to_elevated}
        assert names == {"pub", "std", "elv"}

    def test_list_all(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="x"))
        reg.register(ToolDefinition(name="y"))
        reg.register(ToolDefinition(name="z"))
        assert len(reg.list_all()) == 3
        names = {t.name for t in reg.list_all()}
        assert names == {"x", "y", "z"}

    def test_count(self):
        reg = ToolRegistry()
        assert reg.count() == 0
        reg.register(ToolDefinition(name="one"))
        assert reg.count() == 1
        reg.register(ToolDefinition(name="two"))
        assert reg.count() == 2

    def test_register_overwrites_same_name(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="dup", description="first"))
        reg.register(ToolDefinition(name="dup", description="second"))
        assert reg.count() == 1
        assert reg.get("dup").description == "second"

    def test_get_by_tags_empty_returns_nothing(self):
        reg = ToolRegistry()
        reg.register(ToolDefinition(name="a", tags=["search"]))
        assert reg.get_by_tags([]) == []


# ── Default Registry ────────────────────────────────────────────


class TestDefaultRegistry:
    @pytest.fixture()
    def registry(self):
        return create_default_registry()

    def test_default_has_query_tools(self, registry):
        for name in ("graph_search", "metrics_query", "rag_search", "sql_query"):
            tool = registry.get(name)
            assert tool is not None, f"Missing query tool: {name}"
            assert "query" in tool.tags

    def test_default_has_pipeline_tools(self, registry):
        for name in ("pipeline_run", "source_refresh"):
            tool = registry.get(name)
            assert tool is not None, f"Missing pipeline tool: {name}"
            assert "pipeline" in tool.tags or "connector" in tool.tags

    def test_default_has_curation_tools(self, registry):
        for name in ("steward_curate", "entity_merge", "entity_exclude"):
            tool = registry.get(name)
            assert tool is not None, f"Missing curation tool: {name}"
            assert "curation" in tool.tags

    def test_default_has_analytics_tools(self, registry):
        for name in ("entity_influence", "competitive_clusters", "fair_score"):
            tool = registry.get(name)
            assert tool is not None, f"Missing analytics tool: {name}"

    def test_elevated_tools_declared(self, registry):
        pipeline_run = registry.get("pipeline_run")
        entity_merge = registry.get("entity_merge")
        assert pipeline_run.trust_tier == "elevated"
        assert entity_merge.trust_tier == "elevated"

    def test_public_tools_are_read_only(self, registry):
        public_tools = registry.get_by_tier("public")
        assert len(public_tools) > 0
        for tool in public_tools:
            assert tool.side_effects in ("none", "read"), (
                f"Public tool {tool.name} has side_effects={tool.side_effects}, expected none or read"
            )

    def test_total_tool_count(self, registry):
        # 4 query + 2 pipeline + 3 curation + 1 maintenance + 3 analytics = 13
        assert registry.count() == 13

    def test_pipeline_run_has_long_timeout(self, registry):
        tool = registry.get("pipeline_run")
        assert tool.timeout_ms == 300000
