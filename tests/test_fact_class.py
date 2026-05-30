"""Z1 — tests for the fact_class taxonomy on the facts ledger.

Pure mapping tests for classify_predicate (no DB). Round-trip tests using
the MagicMock-DB pattern established in test_facts_ledger.py.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from services.fact_ingest import classify_predicate, event_to_fact
from services.facts_ledger import assert_fact, FACT_CLASSES

NOW = datetime(2026, 5, 30, tzinfo=timezone.utc)


# ── classify_predicate (pure) ─────────────────────────────────────

class TestClassifyPredicate:
    def test_regulatory_approval_is_corporate(self):
        assert classify_predicate("regulatory_approval") == "corporate"

    def test_regulatory_setback_is_corporate(self):
        assert classify_predicate("regulatory_setback") == "corporate"

    def test_trial_result_is_corporate(self):
        assert classify_predicate("trial_result") == "corporate"

    def test_ma_deal_is_corporate(self):
        assert classify_predicate("ma_deal") == "corporate"

    def test_safety_signal_is_signal(self):
        assert classify_predicate("safety_signal") == "signal"

    def test_pricing_intent_is_signal(self):
        assert classify_predicate("pricing_intent") == "signal"

    def test_supply_disruption_is_signal(self):
        assert classify_predicate("supply_disruption") == "signal"

    def test_unknown_predicate_defaults_to_corporate(self):
        # Default is the safe middle-ceiling class.
        assert classify_predicate("something_new") == "corporate"

    def test_empty_predicate_defaults_to_corporate(self):
        assert classify_predicate("") == "corporate"
        assert classify_predicate(None) == "corporate"

    def test_returns_only_valid_classes(self):
        # Every output must be one of the four valid values — a programmer
        # error if the mapping table ever produces something else.
        for pred in ["regulatory_approval", "safety_signal", "pricing_intent",
                     "trial_result", "ma_deal", "supply_disruption", "weird"]:
            assert classify_predicate(pred) in FACT_CLASSES


# ── event_to_fact carries fact_class ──────────────────────────────

class TestEventToFactCarriesClass:
    def _event(self, **over):
        base = {
            "id": "evt-1", "event_type": "approval",
            "description": "FDA approves drug X",
            "source_url": "https://fda.gov/x",
            "source_feed": "fda_press",
            "event_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
            "created_at": datetime(2026, 3, 2, tzinfo=timezone.utc),
            "entity_type": "drug", "entity_id": "wegovy-demo",
            "trust_score": 0.9,
        }
        base.update(over)
        return base

    def test_approval_event_gets_corporate_class(self):
        draft = event_to_fact(self._event())
        assert draft is not None
        assert draft.fact_class == "corporate"

    def test_pricing_event_gets_signal_class(self):
        draft = event_to_fact(self._event(event_type="pricing"))
        assert draft is not None
        assert draft.fact_class == "signal"

    def test_safety_signal_event_gets_signal_class(self):
        draft = event_to_fact(self._event(event_type="safety_signal"))
        assert draft is not None
        assert draft.fact_class == "signal"


# ── assert_fact accepts + persists fact_class ─────────────────────

class TestAssertFactClass:
    def test_assert_fact_persists_class(self):
        db = MagicMock()
        db.fetch_one = MagicMock(return_value={"id": "new-id"})
        fid = assert_fact(
            db, kind="point", predicate="safety_signal",
            subject_entity_type="drug", subject_entity_id="d1",
            object_value={"note": "x"},
            fact_class="signal",
        )
        assert fid
        # Inspect the call — fact_class must be in the params dict
        call = db.fetch_one.call_args
        assert call is not None
        params = call.args[1]  # second positional arg is params
        assert params.get("fact_class") == "signal"

    def test_assert_fact_defaults_to_corporate(self):
        db = MagicMock()
        db.fetch_one = MagicMock(return_value={"id": "new-id"})
        assert_fact(
            db, kind="point", predicate="some_predicate",
            subject_entity_type="drug", subject_entity_id="d1",
            object_value={},
            # fact_class omitted
        )
        params = db.fetch_one.call_args.args[1]
        assert params.get("fact_class") == "corporate"

    def test_invalid_fact_class_raises(self):
        from services.facts_ledger import InvalidFact
        with pytest.raises(InvalidFact):
            assert_fact(
                MagicMock(), kind="point", predicate="x",
                subject_entity_type="drug", subject_entity_id="d1",
                object_value={},
                fact_class="not-a-real-class",
            )
