"""Fact governance & trust model — pure, DB-free unit tests (Lane 1).

These tests pin the trust model down BEFORE the implementation exists (TDD
RED→GREEN). They cover each scored dimension, the composite trust_score blend,
the review_status auto-rules, and the monotonicity of freshness decay.

The trust model must be EXPLAINABLE and COMPUTED, never cosmetic — an agent
reading a fact must be able to tell a regulatory-grounded structured fact from
an LLM guess off a stale deck purely from these fields.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from services.fact_governance import (
    SOURCE_RELIABILITY,
    FactGovernance,
    freshness_decay,
    score_fact,
)

NOW = datetime(2026, 6, 8, tzinfo=timezone.utc)


def _fact(**kw):
    """A minimal fact dict mirroring the ledger row shape."""
    base = {
        "fact_class": "corporate",
        "created_by": "fact_emitter",
        "confidence": 0.9,
        "valid_from": NOW - timedelta(days=10),
        "created_at": NOW - timedelta(days=10),
        "object_value": {},
    }
    base.update(kw)
    return base


# ── source_reliability ────────────────────────────────────────────────

def test_source_reliability_map_has_all_fact_classes():
    for cls in ("reference", "corporate", "signal", "inferred"):
        assert cls in SOURCE_RELIABILITY
        assert 0.0 <= SOURCE_RELIABILITY[cls] <= 1.0


def test_source_reliability_ordering_reference_highest_inferred_lowest():
    assert (
        SOURCE_RELIABILITY["reference"]
        > SOURCE_RELIABILITY["corporate"]
        > SOURCE_RELIABILITY["signal"]
        > SOURCE_RELIABILITY["inferred"]
    )


def test_score_fact_source_reliability_from_fact_class():
    g = score_fact(_fact(fact_class="reference"), now=NOW)
    assert g.source_reliability == pytest.approx(SOURCE_RELIABILITY["reference"])
    g2 = score_fact(_fact(fact_class="inferred"), now=NOW)
    assert g2.source_reliability == pytest.approx(SOURCE_RELIABILITY["inferred"])


def test_score_fact_unknown_fact_class_falls_back_to_signal_reliability():
    g = score_fact(_fact(fact_class="bogus"), now=NOW)
    assert g.source_reliability == pytest.approx(SOURCE_RELIABILITY["signal"])


# ── extraction_confidence ─────────────────────────────────────────────

def test_structured_connector_fact_full_extraction_confidence():
    g = score_fact(_fact(created_by="fact_emitter"), now=NOW)
    assert g.extraction_confidence == pytest.approx(1.0)


def test_llm_document_extracted_fact_uses_its_confidence():
    """An LLM/document-extracted fact's extraction_confidence reflects the model's
    own confidence, not a blanket 1.0."""
    g = score_fact(
        _fact(created_by="document_facts", confidence=0.7,
              object_value={"emitter": "document_facts"}),
        now=NOW,
    )
    assert g.extraction_confidence < 1.0
    assert g.extraction_confidence == pytest.approx(0.7)


# ── resolver_confidence ───────────────────────────────────────────────

def test_resolver_confidence_passthrough():
    g = score_fact(_fact(), resolver_conf=0.55, now=NOW)
    assert g.resolver_confidence == pytest.approx(0.55)


def test_resolver_confidence_default_when_unknown():
    g = score_fact(_fact(), resolver_conf=None, now=NOW)
    assert 0.0 < g.resolver_confidence <= 1.0  # a sensible non-zero default


# ── freshness ─────────────────────────────────────────────────────────

def test_freshness_decay_monotonic_decreasing_with_age():
    fresh = freshness_decay(0)
    week = freshness_decay(7)
    year = freshness_decay(365)
    decade = freshness_decay(3650)
    assert fresh >= week >= year >= decade
    assert fresh == pytest.approx(1.0)
    assert 0.0 <= decade <= year


def test_freshness_decay_bounded_unit_interval():
    for age in (0, 1, 30, 365, 100000):
        assert 0.0 <= freshness_decay(age) <= 1.0


def test_freshness_at_defaults_to_valid_from():
    vf = NOW - timedelta(days=30)
    g = score_fact(_fact(valid_from=vf, created_at=NOW - timedelta(days=5)), now=NOW)
    assert g.freshness_at == vf


def test_freshness_at_falls_back_to_created_at_when_no_valid_from():
    ca = NOW - timedelta(days=20)
    g = score_fact(_fact(valid_from=None, created_at=ca), now=NOW)
    assert g.freshness_at == ca


def test_older_fact_has_lower_trust_all_else_equal():
    fresh = score_fact(_fact(valid_from=NOW - timedelta(days=1)), now=NOW)
    stale = score_fact(_fact(valid_from=NOW - timedelta(days=2000)), now=NOW)
    assert fresh.trust_score > stale.trust_score


# ── composite trust_score ─────────────────────────────────────────────

def test_trust_score_in_unit_interval():
    g = score_fact(_fact(), now=NOW)
    assert 0.0 <= g.trust_score <= 1.0


def test_regulatory_structured_fresh_fact_scores_high():
    g = score_fact(
        _fact(fact_class="reference", created_by="fact_emitter",
              confidence=1.0, valid_from=NOW - timedelta(days=2)),
        resolver_conf=0.98, now=NOW,
    )
    assert g.trust_score > 0.8


def test_inferred_stale_lowconf_fact_scores_low():
    g = score_fact(
        _fact(fact_class="inferred", created_by="agent",
              confidence=0.3, valid_from=NOW - timedelta(days=3000),
              object_value={"emitter": "agent"}),
        resolver_conf=0.3, now=NOW,
    )
    assert g.trust_score < 0.3


def test_trust_score_drops_when_any_dimension_drops():
    base = score_fact(_fact(fact_class="corporate"), resolver_conf=0.9, now=NOW)
    worse_resolver = score_fact(_fact(fact_class="corporate"), resolver_conf=0.2, now=NOW)
    assert worse_resolver.trust_score < base.trust_score


# ── review_status auto-rules ──────────────────────────────────────────

def test_high_trust_structured_auto_approved():
    g = score_fact(
        _fact(fact_class="reference", created_by="fact_emitter",
              confidence=1.0, valid_from=NOW - timedelta(days=1)),
        resolver_conf=0.97, now=NOW,
    )
    assert g.review_status == "auto_approved"


def test_llm_extracted_fact_unreviewed():
    g = score_fact(
        _fact(fact_class="corporate", created_by="document_facts",
              confidence=0.75, object_value={"emitter": "document_facts"}),
        resolver_conf=0.9, now=NOW,
    )
    assert g.review_status == "unreviewed"


def test_very_low_trust_fact_flagged():
    g = score_fact(
        _fact(fact_class="inferred", created_by="agent",
              confidence=0.1, valid_from=NOW - timedelta(days=4000)),
        resolver_conf=0.1, now=NOW,
    )
    assert g.review_status == "flagged"


def test_review_status_is_one_of_four_states():
    valid = {"unreviewed", "auto_approved", "human_approved", "flagged"}
    for fc in ("reference", "corporate", "signal", "inferred"):
        g = score_fact(_fact(fact_class=fc), now=NOW)
        assert g.review_status in valid


# ── schema_version + dataclass shape ──────────────────────────────────

def test_schema_version_set():
    g = score_fact(_fact(), now=NOW)
    assert isinstance(g.schema_version, int)
    assert g.schema_version >= 1


def test_factgovernance_has_all_six_plus_trust_fields():
    g = score_fact(_fact(), now=NOW)
    assert isinstance(g, FactGovernance)
    for attr in ("source_reliability", "extraction_confidence",
                 "resolver_confidence", "freshness_at", "review_status",
                 "schema_version", "trust_score"):
        assert hasattr(g, attr)
