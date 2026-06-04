"""UX11 / L12 — engagement activity timeline (read-time union over artifacts)."""
from __future__ import annotations

from unittest.mock import MagicMock

from services.engagement_activity import (
    ACTOR_HUMAN,
    ACTOR_SYSTEM,
    _classify_actor,
    list_engagement_activity,
)


def test_classify_actor():
    assert _classify_actor("system") == ACTOR_SYSTEM
    assert _classify_actor(None) == ACTOR_SYSTEM
    assert _classify_actor("fact_emitter") == ACTOR_SYSTEM
    assert _classify_actor("u-123") == ACTOR_HUMAN


def _db(by_table):
    """Fake db whose fetch_all branches on the FROM table in the SQL."""
    db = MagicMock()

    def fetch_all(sql, params=None):
        s = (sql or "").lower()
        for table, rows in by_table.items():
            if f"from {table}" in s:
                return rows
        return []

    db.fetch_all = MagicMock(side_effect=fetch_all)
    return db


def test_union_merges_and_sorts_desc():
    db = _db({
        "business_context_briefs": [
            {"at": "2026-06-01T10:00:00Z", "actor": "u1", "ref_id": "b1",
             "signed": False},
        ],
        "scenarios": [
            {"at": "2026-06-03T09:00:00Z", "actor": "system", "n": 4},
        ],
        "insights": [
            {"at": "2026-06-02T12:00:00Z", "actor": "u2", "ref_id": "i1",
             "statement": "Defend on CV outcomes"},
        ],
        "gap_remediations": [
            {"at": "2026-06-04T08:00:00Z", "actor": "u1", "ref_id": "g1",
             "gap_domain": "clinical_profile", "updated": False},
        ],
        "dossier_snapshots": [
            {"at": "2026-05-31T07:00:00Z", "actor": "system", "ref_id": "d1",
             "version": 2},
        ],
    })
    items = list_engagement_activity(db, "e1")
    kinds = [i["kind"] for i in items]
    # newest first: gap(6-04) > scenario(6-03) > insight(6-02) > brief(6-01) > dossier(5-31)
    assert kinds == ["gap", "scenario", "insight", "brief", "dossier"]
    # actor_kind classification flows through
    scen = next(i for i in items if i["kind"] == "scenario")
    assert scen["actor_kind"] == ACTOR_SYSTEM
    assert "4 scenario" in scen["summary"]
    gap = next(i for i in items if i["kind"] == "gap")
    assert gap["actor_kind"] == ACTOR_HUMAN
    assert "clinical_profile" in gap["summary"]


def test_signed_brief_emits_two_events():
    db = _db({
        "business_context_briefs": [
            {"at": "2026-06-01T10:00:00Z", "actor": "u1", "ref_id": "b1",
             "signed": True, "signed_at": "2026-06-02T10:00:00Z", "signed_by": "rev"},
        ],
    })
    items = list_engagement_activity(db, "e1")
    summaries = [i["summary"] for i in items]
    assert any("authored" in s.lower() for s in summaries)
    assert any("signed" in s.lower() for s in summaries)


def test_limit_caps_results():
    db = _db({
        "insights": [
            {"at": f"2026-06-0{i}T00:00:00Z", "actor": "u", "ref_id": str(i),
             "statement": f"insight {i}"}
            for i in range(1, 9)
        ],
    })
    items = list_engagement_activity(db, "e1", limit=3)
    assert len(items) == 3


def test_missing_table_degrades_gracefully():
    db = MagicMock()
    db.fetch_all = MagicMock(side_effect=Exception("relation does not exist"))
    # never raises — returns []
    assert list_engagement_activity(db, "e1") == []


def test_route_registered():
    from api.app import create_app
    app = create_app()
    routes = [(getattr(r, "path", ""), getattr(r, "methods", set()) or set())
              for r in app.routes]
    assert any(p == "/engagements/{eid}/activity" and "GET" in m for p, m in routes)
