"""P2 — connector-health alert decision logic (DB-free).

build_alert turns a connector_health --json report into an idempotent issue:
RED present -> alert; all-green -> no alert (workflow closes any open issue);
deferred sources never alert (legitimate-empty != broken-empty).
"""
from __future__ import annotations

from scripts.health_alert import ALERT_TITLE, build_alert


def _s(source, verdict, *, deferred=False, notes=None, table="t", rows=1):
    return {
        "source": source, "verdict": verdict, "deferred": deferred,
        "notes": notes or [], "table": table, "rows": rows,
        "age_days": 1, "sla_days": 2, "linked_pct": 90,
    }


def test_red_source_triggers_alert():
    scores = [_s("a", "GREEN"), _s("b", "RED", notes=["over SLA: 9d / 2d"])]
    r = build_alert(scores)
    assert r["should_alert"] is True
    assert r["red"] == ["b"]
    assert r["title"] == ALERT_TITLE
    assert "`b`" in r["body"] and "over SLA" in r["body"]


def test_all_green_does_not_alert():
    r = build_alert([_s("a", "GREEN"), _s("b", "GREEN")])
    assert r["should_alert"] is False
    assert r["red"] == []
    assert "All active sources GREEN" in r["body"]


def test_amber_does_not_alert_by_default():
    r = build_alert([_s("a", "AMBER")])
    assert r["should_alert"] is False
    assert r["amber"] == ["a"]


def test_amber_alerts_when_opted_in():
    r = build_alert([_s("a", "AMBER")], alert_on_amber=True)
    assert r["should_alert"] is True
    assert "`a`" in r["body"]


def test_deferred_red_source_never_alerts():
    """A deferred source (no source wired) is legitimate-empty, not rot."""
    r = build_alert([_s("nadac", "RED", deferred=True)])
    assert r["should_alert"] is False
    assert r["red"] == []


def test_title_is_stable_for_idempotent_issue_matching():
    """The title must not vary with content, so the workflow updates ONE issue."""
    a = build_alert([_s("x", "RED")])
    b = build_alert([_s("y", "RED"), _s("z", "RED")])
    assert a["title"] == b["title"] == ALERT_TITLE


def test_body_includes_counts_and_as_of():
    r = build_alert([_s("a", "RED"), _s("b", "AMBER"), _s("c", "GREEN")], as_of="2026-06-09T07:00:00Z")
    assert "1 red, 1 amber of 3 active sources" in r["body"]
    assert "2026-06-09" in r["body"]
