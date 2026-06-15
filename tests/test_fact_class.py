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


# ── D-Q1 (COORDINATION §8.2, Design A): fact_class by SOURCE ───────
# A registry/regulatory record (ClinicalTrials.gov, FDA Orange Book / SPL labels
# / shortage feeds) is authoritative ground truth = `reference`-grade, NOT the
# `corporate` default these facts historically fell into. We classify by SOURCE,
# not predicate, so a registry trial readout is distinguished from a news mention
# — and a fact classed DELIBERATELY (`signal`/`inferred`, or `corporate` from a
# non-authoritative source) is never over-upgraded.

class TestResolveFactClassBySource:
    def test_ctgov_corporate_upgrades_to_reference(self):
        from services.fact_emitters.base import resolve_fact_class
        assert resolve_fact_class("clinical_trials_gov", "corporate") == "reference"

    def test_fda_orange_book_upgrades_to_reference(self):
        from services.fact_emitters.base import resolve_fact_class
        assert resolve_fact_class("fda_orange_book", "corporate") == "reference"

    def test_openfda_labels_upgrades_to_reference(self):
        from services.fact_emitters.base import resolve_fact_class
        assert resolve_fact_class("openfda_labels", "corporate") == "reference"

    def test_news_source_stays_corporate(self):
        from services.fact_emitters.base import resolve_fact_class
        assert resolve_fact_class("pharma_news", "corporate") == "corporate"

    def test_faers_signal_is_not_upgraded(self):
        # FAERS spontaneous reports are weak evidence — a deliberate `signal`,
        # not the `corporate` default, so it is never upgraded.
        from services.fact_emitters.base import resolve_fact_class
        assert resolve_fact_class("openfda_faers", "signal") == "signal"

    def test_authoritative_inferred_is_not_upgraded(self):
        # phase_transitions' approval_event is a deliberate inference FROM CT.gov:
        # authoritative source but intentionally `inferred` — keep it.
        from services.fact_emitters.base import resolve_fact_class
        assert resolve_fact_class("clinical_trials_gov", "inferred") == "inferred"

    def test_source_is_case_and_whitespace_insensitive(self):
        from services.fact_emitters.base import resolve_fact_class
        assert resolve_fact_class(" Clinical_Trials_Gov ", "corporate") == "reference"

    def test_missing_source_stays_corporate(self):
        from services.fact_emitters.base import resolve_fact_class
        assert resolve_fact_class(None, "corporate") == "corporate"
        assert resolve_fact_class("", "corporate") == "corporate"

    def test_authoritative_sources_membership(self):
        from services.fact_emitters.base import AUTHORITATIVE_SOURCES
        assert "clinical_trials_gov" in AUTHORITATIVE_SOURCES
        assert "pharma_news" not in AUTHORITATIVE_SOURCES
        assert "openfda_faers" not in AUTHORITATIVE_SOURCES


class TestEmitOneAppliesSourceClass:
    """The forward chokepoint (emit_one) actually STORES the source-resolved class."""

    def _db(self):
        db = MagicMock()
        db.fetch_all = MagicMock(return_value=[])           # no existing fact
        db.fetch_one = MagicMock(return_value={"evidence_id": "ev1", "id": "f1"})
        return db

    def _emit(self, db, source_id, predicate="clinical_trial"):
        from services.fact_emitters.base import emit_one, EmittedFact
        fact = EmittedFact(
            predicate=predicate, subject_entity_type="drug",
            subject_entity_id="d1", object_value={}, source_row_id="r1",
            fact_class="corporate", source_id=source_id, evidence_text="text",
        )
        return emit_one(db, "emitter", fact)

    def _stored_fact_class(self, db):
        params = [c.args[1] for c in db.fetch_one.call_args_list
                  if isinstance(c.args[1], dict) and "fact_class" in c.args[1]]
        assert params, "assert_fact INSERT params not captured"
        return params[-1]["fact_class"]

    def test_emit_one_stores_reference_for_authoritative_source(self):
        db = self._db()
        status, _ = self._emit(db, "clinical_trials_gov")
        assert status == "asserted"
        assert self._stored_fact_class(db) == "reference"

    def test_emit_one_keeps_corporate_for_news_source(self):
        db = self._db()
        self._emit(db, "pharma_news", predicate="market_event")
        assert self._stored_fact_class(db) == "corporate"


# ── D-Q1: _coerce_fact_class honest default (signal → corporate) ───

class TestCoerceFactClassDefault:
    def test_valid_classes_pass_through(self):
        from services.dossier_kb import _coerce_fact_class
        for c in ("reference", "corporate", "signal", "inferred"):
            assert _coerce_fact_class(c) == c

    def test_unknown_class_defaults_to_corporate(self):
        # Honest CONTEXTUAL default (matches facts_ledger.DEFAULT_FACT_CLASS),
        # never the lowest-trust `signal` (§8.2).
        from services.dossier_kb import _coerce_fact_class
        assert _coerce_fact_class("outcome") == "corporate"
        assert _coerce_fact_class(None) == "corporate"
        assert _coerce_fact_class("") == "corporate"

    def test_reference_survives_read_coerce(self):
        # D-Q1 regression sentinel: a registry/regulatory `reference` fact must
        # never silently collapse to `signal` on the dossier read path.
        from services.dossier_kb import _coerce_fact_class
        assert _coerce_fact_class("reference") == "reference"
