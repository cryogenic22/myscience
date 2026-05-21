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
)

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
        assert classify_kbq("approval", None) == ["regulatory"]
        assert classify_kbq("regulatory_setback", None) == ["regulatory"]
        assert classify_kbq("trial_readout", None) == ["clinical"]
        assert classify_kbq("safety_signal", None) == ["clinical"]
        assert set(classify_kbq("ma_deal", None)) == {"ma", "strategic"}
        assert set(classify_kbq("supply_disruption", None)) == {"access", "product"}

    def test_general_uses_description_keywords(self):
        assert "regulatory" in classify_kbq("general", "FDA approval granted for label expansion")
        assert "clinical" in classify_kbq("general", "Phase 3 trial readout met primary endpoint")
        assert "access" in classify_kbq("general", "New WAC price and formulary payer coverage")
        assert "financial" in classify_kbq("general", "Q1 revenue and guidance raised")
        assert "ma" in classify_kbq("general", "announces acquisition of biotech")

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

    def test_quality_gate_skips_event_with_no_entity(self):
        row = build_signal_row(_event(primary_entity_id=None, primary_entity_type=None, drug_id=None))
        assert row is None

    def test_falls_back_to_drug_id_when_primary_entity_missing(self):
        row = build_signal_row(_event(primary_entity_id=None, primary_entity_type=None, drug_id="drug-9"))
        assert row is not None
        assert row["primary_entity_id"] == "drug-9"
        assert row["primary_entity_type"] == "drug"


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

    def test_skips_events_without_entity(self):
        good = _event(event_type="approval")
        bad = _event(primary_entity_id=None, primary_entity_type=None, drug_id=None)
        db = _make_db([good, bad])
        res = promote_events(db)
        assert res.promoted == 1
        assert res.skipped_no_entity == 1

    def test_writes_to_db(self):
        events = [_event(event_type="approval")]
        db = _make_db(events)
        promote_events(db)
        # producer must have issued at least one insert
        assert db.execute.called or db.executemany.called
