"""PB-H07 — related entities carry resolved names (not bare UUIDs).

The dossier KB composes related entities into the competitive domain + scenario
triggers, so they need server-side names. This verifies _resolve_related_names
batches a lookup per type and fills in `name`.
"""
from __future__ import annotations

from services.dossier import _resolve_related_names


class _FakeDB:
    """Returns id→name rows for whichever table the query hits."""

    def __init__(self, names_by_table: dict[str, dict[str, str]]):
        self.names_by_table = names_by_table

    def fetch_all(self, sql: str, params=None):
        ids = params[0] if params else []
        for table, mapping in self.names_by_table.items():
            if f"FROM {table} " in sql:
                return [{"id": i, "name": mapping[i]} for i in ids if i in mapping]
        return []


def test_resolve_related_names_fills_names_per_type():
    related = [
        {"id": "d1", "type": "drug", "name": None, "relation": "COMPETES_WITH", "edge_count": 5},
        {"id": "c1", "type": "company", "name": None, "relation": "OWNS", "edge_count": 2},
        {"id": "d2", "type": "drug", "name": None, "relation": "COMPETES_WITH", "edge_count": 1},
    ]
    db = _FakeDB({
        "drugs": {"d1": "tirzepatide", "d2": "semaglutide"},
        "companies": {"c1": "Novo Nordisk"},
    })
    _resolve_related_names(db, related)
    by = {r["id"]: r["name"] for r in related}
    assert by == {"d1": "tirzepatide", "c1": "Novo Nordisk", "d2": "semaglutide"}


def test_resolve_related_names_leaves_unknown_type_none():
    related = [{"id": "x1", "type": "weird_type", "name": None, "relation": "R", "edge_count": 1}]
    _resolve_related_names(_FakeDB({}), related)
    assert related[0]["name"] is None      # unknown type → untouched, no crash


def test_resolve_related_names_unresolved_id_stays_none():
    related = [{"id": "d9", "type": "drug", "name": None, "relation": "COMPETES_WITH", "edge_count": 1}]
    _resolve_related_names(_FakeDB({"drugs": {"d1": "tirzepatide"}}), related)
    assert related[0]["name"] is None      # id not in table → stays None
