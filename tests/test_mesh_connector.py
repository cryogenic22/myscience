"""Tests for the MeSH ontology connector's descendant traversal.

Regression guard for the silent-thin-ontology bug: the SPARQL `_fetch_children`
query returned **zero** children for every seed because it (a) omitted the
`FROM <http://id.nlm.nih.gov/mesh>` graph clause, (b) addressed descriptors with
the `https://` scheme while the triplestore stores resource URIs as `http://`,
and (c) applied a broken `meshv:active true` filter. The net effect: the
ontology never grew past its hand-picked seeds (18 TAs, 25 mechanisms) even
though each seed has real MeSH descendants.

`FakeMeshSparqlSession` simulates the *real* endpoint's behaviour: it only
returns children when the query is correctly formed. That makes these tests fail
against the buggy query and pass once it is fixed — no network required.
"""

from __future__ import annotations

import json


# Real children of Diabetes Mellitus (D003920) per the live MeSH graph.
_KNOWN_CHILDREN = {
    "D003920": [
        ("D003924", "Diabetes Mellitus, Type 2"),
        ("D003922", "Diabetes Mellitus, Type 1"),
        ("D016640", "Diabetes, Gestational"),
        ("D011236", "Prediabetic State"),
    ],
}

_RESOURCE_PREFIX = "http://id.nlm.nih.gov/mesh"


class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.text = json.dumps(payload)

    def json(self) -> dict:
        return self._payload


class FakeMeshSparqlSession:
    """Mimics the NLM MeSH Virtuoso store for SPARQL child lookups.

    The real store returns rows ONLY when the query names the default MeSH
    graph and addresses the descriptor with the `http://` scheme. A query that
    omits the graph, uses `https://`, or filters on the (broken) `active`
    predicate comes back with zero bindings — exactly the legacy behaviour.
    """

    def __init__(self):
        self.last_query: str | None = None

    def get(self, url, params=None, timeout=None):  # noqa: D401 - test stub
        params = params or {}
        if url.endswith("/sparql"):
            query = params.get("query", "")
            self.last_query = query
            return _FakeResponse(self._sparql(query))
        # Any non-SPARQL call in these tests is unexpected.
        return _FakeResponse({}, status_code=404)

    def _sparql(self, query: str) -> dict:
        empty = {"results": {"bindings": []}}

        # Condition (a): must scope to the default MeSH graph.
        if "FROM <http://id.nlm.nih.gov/mesh>" not in query:
            return empty
        # Condition (c): the broken active filter suppresses all rows.
        if "meshv:active" in query:
            return empty

        # Condition (b): find which descriptor is being asked about, and it
        # must be addressed with the http:// resource scheme.
        for parent, children in _KNOWN_CHILDREN.items():
            http_uri = f"<{_RESOURCE_PREFIX}/{parent}>"
            https_uri = f"<https://id.nlm.nih.gov/mesh/{parent}>"
            if https_uri in query:
                # Wrong scheme — triplestore can't match it.
                return empty
            if http_uri in query:
                bindings = [
                    {
                        "d": {"value": f"{_RESOURCE_PREFIX}/{cid}"},
                        "lab": {"value": label},
                    }
                    for cid, label in children
                ]
                return {"results": {"bindings": bindings}}
        return empty


def _connector_with_fake():
    from connectors.mesh import MeSHConnector

    c = MeSHConnector()
    c._session = FakeMeshSparqlSession()
    c._delay = 0  # no politeness sleep in tests
    return c


def test_fetch_children_returns_real_descendants():
    """The corrected query must surface the seed's MeSH children."""
    c = _connector_with_fake()
    children = c._fetch_children("D003920")
    assert set(children) >= {"D003924", "D003922", "D016640", "D011236"}


def test_children_query_names_default_graph_and_http_scheme():
    """Lock the three conditions that the legacy query violated."""
    c = _connector_with_fake()
    c._fetch_children("D003920")
    query = c._session.last_query
    assert query is not None
    # (a) default graph clause present
    assert "FROM <http://id.nlm.nih.gov/mesh>" in query
    # (b) descriptor addressed with http:// (not https://) resource scheme
    assert "<http://id.nlm.nih.gov/mesh/D003920>" in query
    assert "<https://id.nlm.nih.gov/mesh/D003920>" not in query
    # (c) no broken active filter
    assert "meshv:active" not in query


def test_unknown_parent_returns_empty_not_error():
    """A descriptor with no children yields an empty list, not a crash."""
    c = _connector_with_fake()
    assert c._fetch_children("D000000") == []
