"""DI-4 — link/source route execution tests.

In DI-2 only `predicate:` routes were executed; `link:` and `source:` routes
were recorded in `routes_skipped`. These tests cover the executors that now run
them so a dimension can be grounded by graph edges (e.g. COMPETES_WITH) and
structured source tables (e.g. regulatory_milestones) — not just the ledger.

DB-free: fake graph + fake DB return canned edges/rows so we assert the cell
shape, grounding (every fact cites the link/row), and dedup — without prod.
A live-DB gate (in the report) proves it on real tirzepatide.
"""

from __future__ import annotations

from services.domain_intelligence.playbook import Route
from services.domain_intelligence.route_executors import (
    execute_link_route,
    execute_source_route,
    SOURCE_ROUTES,
    _clean_via,
)


class TestCleanVia:
    def test_strips_uuids(self):
        v = ("shared mechanism 770c784f-2c23-44d2-aa8e-54e37ccedd36 "
             "in TA 520b1096-d18c-4d1d-a7eb-4a7999ccc586")
        out = _clean_via(v)
        assert "770c784f" not in out
        assert "520b1096" not in out
        assert "shared mechanism" in out

    def test_empty(self):
        assert _clean_via("") == ""


# ── fakes ──────────────────────────────────────────────────────────


class _Node:
    def __init__(self, eid, label, etype="drug"):
        self.entity_id = eid
        self.label = label
        self.entity_type = etype


class _Edge:
    def __init__(self, src, tgt, link_type="COMPETES_WITH", confidence=0.85, via=""):
        self.source_id = src
        self.target_id = tgt
        self.link_type = link_type
        self.confidence = confidence
        self.via = via


class _Subgraph:
    def __init__(self, nodes, edges):
        self.nodes = nodes
        self.edges = edges


class FakeGraph:
    """Mimics GraphTraversal.neighborhood for one center entity."""

    def __init__(self, center, neighbors):
        # neighbors: [(neighbor_id, neighbor_label, via, conf)]
        self.center = center
        self._neighbors = neighbors
        self.calls = []

    def neighborhood(self, entity_id, entity_type, link_types=None, min_confidence=None):
        self.calls.append((entity_id, entity_type, tuple(link_types or ())))
        nodes = [_Node(self.center, "tirzepatide")]
        edges = []
        for nid, nlabel, via, conf in self._neighbors:
            nodes.append(_Node(nid, nlabel))
            edges.append(_Edge(self.center, nid, link_types[0] if link_types else "COMPETES_WITH",
                               confidence=conf, via=via))
        return _Subgraph(nodes, edges)


class FakeDB:
    def __init__(self, rows):
        self._rows = rows
        self.last_sql = None
        self.last_params = None

    def fetch_all(self, sql, params=None):
        self.last_sql = sql
        self.last_params = params
        return list(self._rows)


# ── link route ─────────────────────────────────────────────────────


class TestLinkRoute:
    def test_traverses_link_and_grounds_each_competitor(self):
        graph = FakeGraph("tz", [
            ("c1", "semaglutide", "shared mechanism", 0.85),
            ("c2", "dulaglutide", "shared mechanism", 0.85),
        ])
        facts = execute_link_route(
            graph, Route("link", "COMPETES_WITH"), "drug", "tz", limit=6,
        )
        assert len(facts) == 2
        names = {f["claim"] for f in facts}
        assert any("semaglutide" in c for c in names)
        assert any("dulaglutide" in c for c in names)
        # grounded: every fact carries the link as provenance
        for f in facts:
            assert f["fact_class"] in ("reference", "corporate", "signal", "inferred")
            assert "COMPETES_WITH" in (f["source_label"] or "")
            assert f["predicate"] == "link:COMPETES_WITH"

    def test_excludes_self_and_dedups(self):
        graph = FakeGraph("tz", [
            ("tz", "tirzepatide", "self", 0.85),       # self → excluded
            ("c1", "semaglutide", "x", 0.85),
            ("c1b", "semaglutide", "y", 0.85),         # dup name → once
        ])
        facts = execute_link_route(
            graph, Route("link", "COMPETES_WITH"), "drug", "tz", limit=6,
        )
        names = [f["claim"] for f in facts]
        assert sum("tirzepatide" in n for n in names) == 0
        assert sum("semaglutide" in n for n in names) == 1

    def test_respects_limit(self):
        graph = FakeGraph("tz", [(f"c{i}", f"rival{i}", "x", 0.85) for i in range(20)])
        facts = execute_link_route(
            graph, Route("link", "COMPETES_WITH"), "drug", "tz", limit=5,
        )
        assert len(facts) == 5

    def test_no_graph_returns_empty(self):
        facts = execute_link_route(None, Route("link", "COMPETES_WITH"), "drug", "tz")
        assert facts == []


# ── source route ───────────────────────────────────────────────────


class TestSourceRoute:
    def test_regulatory_milestones_is_registered(self):
        assert "regulatory_milestones" in SOURCE_ROUTES

    def test_reads_named_table_and_grounds_rows(self):
        db = FakeDB([
            {"submission_type": "ORIG", "submission_number": "1",
             "submission_status": "AP", "submission_status_date": "2022-05-13",
             "review_priority": "PRIORITY", "source_url": "https://fda/x"},
            {"submission_type": "SUPPL", "submission_number": "5",
             "submission_status": "AP", "submission_status_date": "2023-11-08",
             "review_priority": "STANDARD", "source_url": "https://fda/y"},
        ])
        facts = execute_source_route(
            db, Route("source", "regulatory_milestones"), "drug", "did", limit=6,
        )
        assert len(facts) == 2
        for f in facts:
            assert f["predicate"] == "source:regulatory_milestones"
            assert f["claim"]
            assert f["fact_class"] in ("reference", "corporate", "signal", "inferred")
        # carries the row's source_url for drill-through
        assert any(f["source_url"] == "https://fda/x" for f in facts)

    def test_unknown_source_table_returns_empty(self):
        db = FakeDB([{"x": 1}])
        facts = execute_source_route(
            db, Route("source", "not_a_real_table"), "drug", "did",
        )
        assert facts == []
        # never queried an unwhitelisted table
        assert db.last_sql is None

    def test_no_rows_returns_empty(self):
        db = FakeDB([])
        facts = execute_source_route(
            db, Route("source", "regulatory_milestones"), "drug", "did",
        )
        assert facts == []
