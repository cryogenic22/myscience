"""PB-SL07 — mint signals from facts (unify the two sensing stores)."""
from __future__ import annotations

from services.fact_signals import (
    build_signal_row,
    mint_signals_from_facts,
    SIGNAL_WORTHY,
)


def _fact(**kw):
    base = {
        "id": "fact-1",
        "predicate": "safety_signal",
        "subject_entity_type": "drug",
        "subject_entity_id": "drug-sema",
        "object_value": {"description": "Boxed warning: risk of thyroid C-cell tumors"},
        "fact_class": "corporate",
        "confidence": 0.8,
        "source_doc_id": "evid-1",
        "entity_name": "semaglutide",
    }
    base.update(kw)
    return base


# ── build_signal_row (pure) ──────────────────────────────────────────────────

def test_safety_signal_builds_high_impact_signal():
    row = build_signal_row(_fact())
    assert row is not None
    assert row["impact_tier"] == "high"
    assert row["impact_score"] >= 0.8
    assert row["confidence_tier"] == "reported"          # corporate → reported
    assert row["primary_entity_id"] == "drug-sema"
    assert row["primary_entity_name"] == "semaglutide"
    assert row["evidence_document_ids"] == ["evid-1"]    # provenance preserved
    assert row["kbq_tags"] == ["clinical"]               # safety → clinical_profile
    assert row["rule_version_id"] == "fact_signal_v1"
    assert row["status"] == "candidate"   # auto-minted awaits review
    assert "Boxed warning" in row["headline"]


def test_confidence_tier_mapping():
    assert build_signal_row(_fact(fact_class="reference"))["confidence_tier"] == "confirmed"
    assert build_signal_row(_fact(fact_class="inferred"))["confidence_tier"] == "inferred"


def test_non_signal_worthy_predicate_returns_none():
    assert build_signal_row(_fact(predicate="mechanism_of_action")) is None
    assert build_signal_row(_fact(predicate="clinical_trial")) is None
    assert "mechanism_of_action" not in SIGNAL_WORTHY


def test_fact_without_evidence_returns_none():
    # no source_doc_id → cannot satisfy evidence_document_ids >= 1
    assert build_signal_row(_fact(source_doc_id=None)) is None


def test_trial_result_routes_clinical_high():
    row = build_signal_row(_fact(predicate="trial_result",
                                 object_value={"description": "REDEFINE 4: NI not met"}))
    assert row["impact_tier"] == "high"
    assert row["kbq_tags"] == ["clinical"]


def test_headline_is_clipped_to_120():
    long = "x" * 300
    row = build_signal_row(_fact(object_value={"description": long}))
    assert len(row["headline"]) <= 120


# ── mint flow (fake DB) ──────────────────────────────────────────────────────

class _FakeDB:
    def __init__(self, facts):
        self._facts = facts
        self.inserted_signals = []
        self.links = []
        self._next = 0

    def fetch_all(self, sql, params=None):
        return self._facts

    def fetch_one(self, sql, params=None):
        self._next += 1
        self.inserted_signals.append(params)
        return {"id": f"signal-{self._next}"}

    def execute(self, sql, params=None):
        self.links.append(params)


def test_mint_inserts_signal_and_link_per_fact():
    db = _FakeDB([_fact(id="f1"), _fact(id="f2", source_doc_id="evid-2")])
    stats = mint_signals_from_facts(db)
    assert stats.minted == 2
    assert len(db.inserted_signals) == 2
    # each minted signal gets a signal_facts produces-link to its fact
    linked_fact_ids = {p[1] for p in db.links}
    assert linked_fact_ids == {"f1", "f2"}


def test_mint_skips_facts_without_evidence():
    db = _FakeDB([_fact(id="f1", source_doc_id=None)])
    stats = mint_signals_from_facts(db)
    assert stats.minted == 0
    assert stats.skipped_no_evidence == 1
