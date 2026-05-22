"""Loop — tests for the events→signals producer (services/signal_promoter.py).

Pure-function tests need no DB; promote_events uses a MagicMock DB in the
style of tests/test_bridge_moments.py and tests/test_evidence_batch.py.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from services.signal_promoter import (
    classify_kbq,
    confidence_tier_for,
    impact_for,
    build_signal_row,
    promote_events,
    relink_market_signals,
)
from services.entity_linker import LinkResult


class _StubLinker:
    """Returns a fixed LinkResult for any text containing `needle`."""
    def __init__(self, needle, result):
        self.needle = needle
        self.result = result

    def link(self, text):
        return self.result if text and self.needle in text.lower() else None

VALID_CONFIDENCE = {"confirmed", "reported", "inferred", "disputed"}
VALID_IMPACT_TIER = {"high", "medium", "low"}
VALID_DIRECTION = {"positive", "negative", "neutral", "mixed"}


def _event(**over):
    base = {
        "id": str(uuid.uuid4()),
        "event_type": "general",
        "description": "Some pharma update happened today.",
        "source_tier": "tier_2",
        "trust_score": 0.7,
        "primary_entity_type": "company",
        "primary_entity_id": "co-1",
        "primary_entity_name": "Eli Lilly",
        "drug_id": None,
        "event_date": "2026-05-20",
    }
    base.update(over)
    return base


# ── classify_kbq ──────────────────────────────────────────────────

class TestClassifyKbq:
    def test_event_type_mapping(self):
        # canonical KBQ vocabulary the frontend filter expects (m_and_a, pricing_access)
        assert classify_kbq("approval", None) == ["regulatory"]
        assert classify_kbq("regulatory_setback", None) == ["regulatory"]
        assert classify_kbq("trial_readout", None) == ["clinical"]
        assert classify_kbq("safety_signal", None) == ["clinical"]
        assert set(classify_kbq("ma_deal", None)) == {"m_and_a", "strategic"}
        assert set(classify_kbq("supply_disruption", None)) == {"pricing_access", "product"}

    def test_general_uses_description_keywords(self):
        assert "regulatory" in classify_kbq("general", "FDA approval granted for label expansion")
        assert "clinical" in classify_kbq("general", "Phase 3 trial readout met primary endpoint")
        assert "pricing_access" in classify_kbq("general", "New WAC price and formulary payer coverage")
        assert "financial" in classify_kbq("general", "Q1 revenue and guidance raised")
        assert "m_and_a" in classify_kbq("general", "announces acquisition of biotech")

    def test_always_returns_at_least_one_tag(self):
        assert classify_kbq("general", None) == ["strategic"]
        assert classify_kbq("general", "completely unclassifiable noise") == ["strategic"]
        assert len(classify_kbq("totally_made_up", None)) >= 1


# ── confidence_tier_for ───────────────────────────────────────────

class TestConfidenceTier:
    def test_source_tier_mapping(self):
        assert confidence_tier_for("tier_1", 0.9) == "confirmed"
        assert confidence_tier_for("tier_2", 0.7) == "reported"
        assert confidence_tier_for("tier_3", 0.6) == "inferred"

    def test_low_trust_downgrades_to_disputed(self):
        assert confidence_tier_for("tier_1", 0.2) == "disputed"

    def test_unknown_tier_defaults_inferred(self):
        assert confidence_tier_for(None, 0.6) == "inferred"

    def test_result_always_valid(self):
        for st in ("tier_1", "tier_2", "tier_3", None, "weird"):
            for ts in (0.0, 0.25, 0.5, 1.0):
                assert confidence_tier_for(st, ts) in VALID_CONFIDENCE


# ── impact_for ────────────────────────────────────────────────────

class TestImpactFor:
    def test_returns_score_and_tier_in_range(self):
        score, tier = impact_for("approval", 0.9)
        assert 0.0 <= score <= 1.0
        assert tier in VALID_IMPACT_TIER

    def test_tier_thresholds(self):
        # high-significance event + high trust → high
        _, tier = impact_for("safety_signal", 0.95)
        assert tier == "high"
        # general + very low trust → low (0.7*0.4 + 0.3*0.05 = 0.295 < 0.33)
        score, tier = impact_for("general", 0.05)
        assert tier == "low"

    def test_tier_matches_score_bands(self):
        for et in ("approval", "ma_deal", "general", "trial_readout"):
            for ts in (0.1, 0.5, 0.9):
                score, tier = impact_for(et, ts)
                expected = "high" if score >= 0.66 else "medium" if score >= 0.33 else "low"
                assert tier == expected


# ── build_signal_row ──────────────────────────────────────────────

class TestBuildSignalRow:
    def test_produces_all_required_fields(self):
        row = build_signal_row(_event(event_type="approval", description="FDA approves drug X"))
        assert row is not None
        for col in (
            "event_id", "headline", "confidence_tier", "trust_score",
            "impact_tier", "impact_score", "rule_version_id",
            "primary_entity_type", "primary_entity_id", "evidence_document_ids",
            "kbq_tags", "status", "direction", "summary",
        ):
            assert col in row, f"missing {col}"

    def test_satisfies_schema_invariants(self):
        row = build_signal_row(_event())
        assert row["confidence_tier"] in VALID_CONFIDENCE
        assert row["impact_tier"] in VALID_IMPACT_TIER
        assert row["direction"] in VALID_DIRECTION
        assert 0.0 <= row["trust_score"] <= 1.0
        assert 0.0 <= row["impact_score"] <= 1.0
        assert len(row["headline"]) <= 120
        assert row["summary"] is None or len(row["summary"]) <= 500
        assert len(row["kbq_tags"]) >= 1
        assert len(row["evidence_document_ids"]) >= 1
        assert row["status"] == "candidate"

    def test_headline_never_empty_even_without_description(self):
        row = build_signal_row(_event(description=None, event_type="ma_deal"))
        assert row["headline"] and len(row["headline"]) > 0

    def test_headline_truncated_to_120(self):
        row = build_signal_row(_event(description="x" * 300))
        assert len(row["headline"]) <= 120

    def test_evidence_cites_source_event(self):
        ev = _event()
        row = build_signal_row(ev)
        assert ev["id"] in row["evidence_document_ids"]

    def test_entityless_event_falls_back_to_market_bucket(self):
        row = build_signal_row(_event(primary_entity_id=None, primary_entity_type=None, drug_id=None))
        assert row is not None
        assert row["primary_entity_type"] == "market"
        assert row["primary_entity_id"] == "market"

    def test_linker_resolves_entityless_event(self):
        linker = _StubLinker("lilly", LinkResult("company", "co-lilly", "Eli Lilly", 0.72, "lilly"))
        ev = _event(
            primary_entity_id=None, primary_entity_type=None, drug_id=None,
            description="Lilly pens $202M deal for biotech",
        )
        row = build_signal_row(ev, linker)
        assert row["primary_entity_type"] == "company"
        assert row["primary_entity_id"] == "co-lilly"
        assert row["primary_entity_name"] == "Eli Lilly"

    def test_low_confidence_link_falls_back_to_market(self):
        linker = _StubLinker("lilly", LinkResult("company", "co-lilly", "Eli Lilly", 0.4, "lilly"))
        ev = _event(primary_entity_id=None, primary_entity_type=None, drug_id=None,
                    description="Lilly maybe did something")
        row = build_signal_row(ev, linker)
        assert row["primary_entity_id"] == "market"

    def test_structured_entity_beats_linker(self):
        linker = _StubLinker("lilly", LinkResult("company", "co-lilly", "Eli Lilly", 0.9, "lilly"))
        ev = _event(description="Lilly news", primary_entity_id="co-novo", primary_entity_type="company")
        row = build_signal_row(ev, linker)
        assert row["primary_entity_id"] == "co-novo"  # structured field wins

    def test_falls_back_to_drug_id_when_primary_entity_missing(self):
        row = build_signal_row(_event(primary_entity_id=None, primary_entity_type=None, drug_id="drug-9"))
        assert row is not None
        assert row["primary_entity_id"] == "drug-9"
        assert row["primary_entity_type"] == "drug"

    def test_high_impact_auto_ships_with_audit_fields(self):
        # approval + high trust → high impact → shipped, with paired audit fields
        row = build_signal_row(_event(event_type="approval", description="FDA approves X", trust_score=0.95))
        assert row["impact_tier"] == "high"
        assert row["status"] == "shipped"
        assert row["reviewed_by"] is not None
        assert row["reviewed_at"] is not None
        assert row["shipped_at"] is not None

    def test_medium_low_stays_candidate(self):
        row = build_signal_row(_event(event_type="general", trust_score=0.5))
        assert row["impact_tier"] in ("medium", "low")
        assert row["status"] == "candidate"
        assert row["reviewed_by"] is None
        assert row["shipped_at"] is None

    def test_recall_noise_is_low_and_not_shipped(self):
        row = build_signal_row(_event(event_type="RECALL_CLASS_I", description="Class II recall", trust_score=0.6))
        assert row["status"] == "candidate"
        assert row["impact_tier"] in ("low", "medium")


# ── promote_events (mock DB) ──────────────────────────────────────

def _make_db(events, existing_event_ids=None):
    existing = set(existing_event_ids or [])

    def fake_fetch_all(sql, params=None):
        s = (sql or "").lower()
        # Order matters: the existing-signals probe selects only event_id.
        if "from signals" in s and "from market_events" not in s:
            return [{"event_id": eid} for eid in existing]
        if "from market_events" in s:
            return list(events)
        return []

    db = MagicMock()
    db.fetch_all = MagicMock(side_effect=fake_fetch_all)
    db.execute = MagicMock(return_value=None)
    db.executemany = MagicMock(return_value=None)
    return db


class TestPromoteEvents:
    def test_promotes_new_events(self):
        events = [_event(event_type="approval"), _event(event_type="safety_signal")]
        db = _make_db(events)
        res = promote_events(db)
        assert res.promoted == 2
        assert res.scanned == 2

    def test_idempotent_skips_already_signalled(self):
        events = [_event(), _event()]
        # both already have signals
        db = _make_db(events, existing_event_ids=[e["id"] for e in events])
        res = promote_events(db)
        assert res.promoted == 0
        assert res.skipped_existing == 2

    def test_entityless_events_still_promote_via_market_bucket(self):
        good = _event(event_type="approval")
        entityless = _event(primary_entity_id=None, primary_entity_type=None, drug_id=None)
        db = _make_db([good, entityless])
        res = promote_events(db)
        assert res.promoted == 2
        assert res.skipped_no_entity == 0

    def test_writes_to_db(self):
        events = [_event(event_type="approval")]
        db = _make_db(events)
        promote_events(db)
        # producer must have issued at least one insert
        assert db.execute.called or db.executemany.called

    def test_relink_updates_market_signals(self):
        # Two market signals; one mentions Lilly, one doesn't.
        market_rows = [
            {"id": "s1", "headline": "Lilly pens $202M deal", "summary": None},
            {"id": "s2", "headline": "Unknown biotech raised a round", "summary": None},
        ]
        companies = [{"id": "co-lilly", "name": "Eli Lilly and Company"}]

        def fetch_all(sql, params=None):
            s = (sql or "").lower()
            if "from signals" in s and "primary_entity_id = 'market'" in s:
                return market_rows
            if "from companies" in s:
                return companies
            if "from drugs" in s:
                return []
            return []

        db = MagicMock()
        db.fetch_all = MagicMock(side_effect=fetch_all)
        db.execute = MagicMock()
        res = relink_market_signals(db)
        assert res["scanned"] == 2
        assert res["relinked"] == 1  # only the Lilly one resolves
        # the UPDATE carried the resolved company id
        update_calls = [c for c in db.execute.call_args_list if "update signals" in (c.args[0] or "").lower()]
        assert update_calls and "co-lilly" in update_calls[0].args[1]

    def test_event_types_filter_passed_to_query(self):
        events = [_event(event_type="approval")]
        db = _make_db(events)
        promote_events(db, event_types=["approval", "trial_readout"])
        # the market_events query must carry the event_type filter param
        calls = [c for c in db.fetch_all.call_args_list if "market_events" in (c.args[0] or "").lower()]
        assert calls, "expected a market_events query"
        params = calls[0].args[1] if len(calls[0].args) > 1 else []
        assert any(isinstance(p, list) and "approval" in p for p in params)
