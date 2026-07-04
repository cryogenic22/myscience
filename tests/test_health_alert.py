"""P2 — connector-health alert decision logic (DB-free).

build_alert turns a connector_health --json report into an idempotent issue:
RED present -> alert; all-green -> no alert (workflow closes any open issue);
deferred sources never alert (legitimate-empty != broken-empty).
"""
from __future__ import annotations

from scripts.health_alert import ALERT_TITLE, _unwrap, build_alert


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


# ── Ledger + DLQ surfacing (the 27-Jun freeze reddened nothing a human saw) ──


def _ledger(source, healthy):
    return {"source": source, "table": "facts", "healthy": healthy,
            "over_sla": not healthy, "age_days": 12.0 if not healthy else 0.2,
            "sla_days": 3, "rows": 15051}


def test_frozen_ledger_alerts_even_with_all_sources_green():
    """A ledger freeze must alert on its own — every source can be GREEN while the
    spine every lens reads has stopped converging."""
    r = build_alert([_s("a", "GREEN")], ledger=[_ledger("facts_ledger", healthy=False)])
    assert r["should_alert"] is True
    assert r["ledger"] == ["facts_ledger"]
    assert "Ledger FROZEN" in r["body"] and "`facts_ledger`" in r["body"]
    assert "All active sources GREEN" not in r["body"]


def test_fresh_ledger_does_not_alert():
    r = build_alert([_s("a", "GREEN")], ledger=[_ledger("facts_ledger", healthy=True)])
    assert r["should_alert"] is False
    assert r["ledger"] == []


def test_dlq_red_alerts_and_renders():
    r = build_alert([_s("a", "GREEN")], dlq={"verdict": "RED", "pending_total": 3200})
    assert r["should_alert"] is True and r["dlq_red"] is True
    assert "DLQ bleed" in r["body"] and "3200" in r["body"]


def test_dlq_amber_does_not_alert():
    r = build_alert([_s("a", "GREEN")], dlq={"verdict": "AMBER", "pending_total": 40})
    assert r["should_alert"] is False and r["dlq_red"] is False


def test_unwrap_accepts_envelope_and_legacy_list():
    s, l, d = _unwrap({"sources": [1], "ledger": [2], "dlq": {"verdict": "GREEN"}})
    assert s == [1] and l == [2] and d == {"verdict": "GREEN"}
    # legacy bare list (an old connector_health checkout) still parses
    s, l, d = _unwrap([{"source": "a"}])
    assert s == [{"source": "a"}] and l == [] and d is None
