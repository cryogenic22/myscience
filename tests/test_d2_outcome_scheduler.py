"""SPEC-021 D2 — outcome_scheduler tick tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from services import outcome_scheduler as os_mod


def _decision(decision_id="dec-1", *, status="open", auto_checked_at=None,
              war_room_id="wr-1", source_signal_id=None,
              move_type="trial_readout"):
    return {
        "id": decision_id,
        "war_room_round_id": "rnd-1",
        "war_room_id": war_room_id,
        "source_signal_id": source_signal_id,
        "move_type": move_type,
        "target_value": "+3pp",
        "deadline": date(2026, 12, 31),
        "confidence_at_commit": 0.6,
        "created_at": datetime(2026, 5, 1, tzinfo=timezone.utc),
        "outcome_auto_checked_at": auto_checked_at,
    }


def _signal(sid="sig-1", *, kbq=("clinical",), entity_id="ent-novo",
            created=datetime(2026, 8, 1, tzinfo=timezone.utc)):
    return {
        "id": sid,
        "headline": f"Signal {sid}",
        "summary": "summary",
        "kbq_tags": list(kbq),
        "primary_entity_id": entity_id,
        "primary_entity_name": "Novo",
        "related_entity_ids": [],
        "created_at": created,
        "confidence_tier": "reported",
        "trust_score": 0.7,
        "impact_tier": "high",
        "rule_version_id": "intel-v1.2.0",
    }


def _make_db(*, decisions=None, signals=None, war_room_entity="ent-novo"):
    decisions = decisions or []
    signals = signals or []
    inserts = []
    updates = []

    db = MagicMock()

    def fetch_one(sql, params=None):
        s = (sql or "").lower()
        if "primary_entity_id from war_rooms" in s:
            return {"primary_entity_id": war_room_entity}
        return None

    def fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from decisions" in s and "outcome_auto_checked_at" in s:
            return decisions
        if "from signals" in s:
            return signals
        return []

    def execute(sql, params=None):
        s = (sql or "").lower()
        if "insert into outcome_proposals" in s:
            inserts.append(params)
        elif "update decisions" in s and "outcome_auto_checked_at" in s:
            updates.append(params)
        return None

    db.fetch_one.side_effect = fetch_one
    db.fetch_all.side_effect = fetch_all
    db.execute.side_effect = execute
    return db, inserts, updates


def test_disabled_returns_early(monkeypatch):
    monkeypatch.setenv("MZ_OUTCOME_SCHEDULER_DISABLED", "true")
    db, inserts, _ = _make_db()
    out = os_mod.tick(db)
    assert out["disabled"] is True
    assert inserts == []


def test_no_due_decisions_returns_zero(monkeypatch):
    monkeypatch.delenv("MZ_OUTCOME_SCHEDULER_DISABLED", raising=False)
    db, inserts, updates = _make_db(decisions=[])
    out = os_mod.tick(db)
    assert out["decisions_scanned"] == 0
    assert out["proposals_created"] == 0
    assert inserts == []


def test_high_score_match_creates_proposal(monkeypatch):
    monkeypatch.delenv("MZ_OUTCOME_SCHEDULER_DISABLED", raising=False)
    db, inserts, updates = _make_db(
        decisions=[_decision()],
        signals=[_signal()],  # entity match + KBQ match + temporal → ≥0.75
    )
    out = os_mod.tick(db)
    assert out["decisions_scanned"] == 1
    assert out["proposals_created"] == 1
    assert len(inserts) == 1
    assert len(updates) == 1  # marked checked


def test_low_score_match_does_not_create_proposal(monkeypatch):
    monkeypatch.delenv("MZ_OUTCOME_SCHEDULER_DISABLED", raising=False)
    db, inserts, _ = _make_db(
        decisions=[_decision()],
        # Wrong entity, wrong KBQ → low score
        signals=[_signal(entity_id="ent-other", kbq=["pricing_access"])],
    )
    out = os_mod.tick(db)
    assert out["decisions_scanned"] == 1
    assert out["proposals_created"] == 0


def test_source_signal_excluded_from_proposals(monkeypatch):
    monkeypatch.delenv("MZ_OUTCOME_SCHEDULER_DISABLED", raising=False)
    # The decision's source signal should never be re-proposed as outcome
    db, inserts, _ = _make_db(
        decisions=[_decision(source_signal_id="sig-1")],
        signals=[_signal("sig-1")],  # would otherwise score high
    )
    out = os_mod.tick(db)
    assert out["proposals_created"] == 0


def test_multiple_decisions_processed(monkeypatch):
    monkeypatch.delenv("MZ_OUTCOME_SCHEDULER_DISABLED", raising=False)
    db, inserts, updates = _make_db(
        decisions=[_decision("dec-1"), _decision("dec-2")],
        signals=[_signal()],
    )
    out = os_mod.tick(db)
    assert out["decisions_scanned"] == 2
    assert out["proposals_created"] == 2
    assert len(updates) == 2  # both marked checked
