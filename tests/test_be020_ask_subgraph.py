"""BE-20 — /ask subgraph context tests."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ════════════════════════════════════════════════════════════════════
# AskEngine.ask honours subgraph_context
# ════════════════════════════════════════════════════════════════════

class TestSubgraphPostFilter:
    def _engine_with_fake_executor(self, nodes, edges):
        """Bypass executors by stubbing parse_question and exec_*."""
        from services.ask_engine import (
            AskEngine, GraphResult, GraphNode, GraphEdge, ParsedIntent,
        )

        engine = AskEngine()

        # Build a real GraphResult shape
        graph = GraphResult(
            nodes=[GraphNode(id=nid, type="drug", label=nid) for nid in nodes],
            edges=[GraphEdge(source=s, target=t, type=lt)
                   for (s, t, lt) in edges],
        )

        # Inject a fake executor by name; we monkey-patch parse_question to
        # always return an intent with executor "_fake".
        def fake_parse(question, **kw):
            return ParsedIntent(
                matched_pattern="P-test",
                executor="fake",
                params={},
                raw_question=question,
            )

        import services.ask_engine as mod
        engine._exec_fake = lambda db, params: (graph, "FAKE-SQL")
        return engine, fake_parse, mod

    def test_subgraph_filters_to_selected_nodes(self, monkeypatch):
        eng, fake_parse, mod = self._engine_with_fake_executor(
            nodes=["a", "b", "c"],
            edges=[("a", "b", "links_to"), ("b", "c", "links_to")],
        )
        monkeypatch.setattr(mod, "parse_question", fake_parse)

        db = MagicMock()
        db.fetch_one.return_value = None

        out = eng.ask(
            db,
            question="anything",
            user_id="u-1",
            persist=False,
            subgraph_context={"node_ids": ["a", "b"]},
        )
        # 'c' must be filtered out; the b->c edge dropped (target gone)
        kept_ids = {n.id for n in out.graph.nodes}
        assert kept_ids == {"a", "b"}
        assert all(e.source in kept_ids and e.target in kept_ids for e in out.graph.edges)

    def test_subgraph_filters_edges_by_type(self, monkeypatch):
        eng, fake_parse, mod = self._engine_with_fake_executor(
            nodes=["a", "b", "c"],
            edges=[
                ("a", "b", "competes_with"),
                ("b", "c", "investigates"),
                ("a", "c", "competes_with"),
            ],
        )
        monkeypatch.setattr(mod, "parse_question", fake_parse)

        db = MagicMock()
        db.fetch_one.return_value = None

        out = eng.ask(
            db, question="anything", user_id="u-1", persist=False,
            subgraph_context={"edge_types": ["competes_with"]},
        )
        for e in out.graph.edges:
            assert e.type == "competes_with"

    def test_no_subgraph_keeps_full_result(self, monkeypatch):
        eng, fake_parse, mod = self._engine_with_fake_executor(
            nodes=["a", "b"],
            edges=[("a", "b", "x")],
        )
        monkeypatch.setattr(mod, "parse_question", fake_parse)

        db = MagicMock()
        db.fetch_one.return_value = None

        out = eng.ask(db, question="anything", user_id="u-1", persist=False)
        assert {n.id for n in out.graph.nodes} == {"a", "b"}
        assert len(out.graph.edges) == 1


class TestSubgraphValidation:
    def test_rejects_non_list_node_ids(self, monkeypatch):
        from services.ask_engine import AskEngine

        db = MagicMock()
        with pytest.raises(ValueError, match="must be lists"):
            AskEngine().ask(
                db, question="x", user_id="u-1", persist=False,
                subgraph_context={"node_ids": "not-a-list"},
            )

    def test_rejects_oversized_node_id_list(self):
        from services.ask_engine import AskEngine, MAX_NODES

        db = MagicMock()
        with pytest.raises(ValueError, match="exceeds"):
            AskEngine().ask(
                db, question="x", user_id="u-1", persist=False,
                subgraph_context={"node_ids": [str(i) for i in range(MAX_NODES + 1)]},
            )


# ════════════════════════════════════════════════════════════════════
# /ask endpoint accepts the new context block
# ════════════════════════════════════════════════════════════════════

class TestAskEndpointSubgraphBody:
    def test_pydantic_body_accepts_subgraph_context(self):
        """Defensive — the new field must accept None and the full
        nested shape without breaking older clients."""
        from api.routes.ask import AskBody

        # Legacy body
        AskBody(question="hi")
        # Empty context
        AskBody(question="hi", context={})
        # Full subgraph context
        AskBody(question="hi", context={
            "subgraph": {
                "node_ids": ["a", "b"],
                "edge_types": ["competes_with"],
            }
        })
