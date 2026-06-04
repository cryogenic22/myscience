"""L7 / Tier 2 — product-level sales facts from uploaded financial docs.

A fake StructuredCall stands in for the LLM; a fake resolver stands in for the
drug spine. No DB, no network.

The honesty contract under test: a product-sales fact only ever attaches a
dollar figure to a *resolved drug* (product-level grain). Company-level totals
are out of scope here — they belong to a company-subject SEC path.
"""
from __future__ import annotations

from services.dossier_kb import route_predicate_to_domain
from services.extraction.product_sales import ProductSalesExtraction
from services.fact_emitters.document_facts import (
    build_product_sales_fact,
    extract_product_sales_facts,
)
from services.kbq_views import _PREDICATE_KBQ


def _sales_dict(**kw):
    base = {
        "product_name": "Wegovy",
        "company_name": "Novo Nordisk",
        "period_label": "Q1 2026",
        "period_end": "2026-03-31",
        "net_sales_usd": 2_500_000_000.0,
        "currency": "USD",
        "yoy_change_pct": 41.0,
        "headline_summary": "Wegovy Q1 2026 net sales DKK 17.4bn (~$2.5bn), +41% YoY.",
    }
    base.update(kw)
    return base


def _call_returning(payload):
    def _call(system_prompt, user_prompt, json_schema):
        return payload
    return _call


def _resolver_ok(name):
    return ("drug", "drug-semaglutide")


def _resolver_none(name):
    return None


# ── schema ───────────────────────────────────────────────────────────────────

def test_schema_requires_product_grain_and_value():
    s = ProductSalesExtraction.model_validate(_sales_dict())
    assert s.product_name == "Wegovy"
    assert s.net_sales_usd == 2_500_000_000.0
    assert s.yoy_change_pct == 41.0


# ── build_product_sales_fact (pure mapping) ──────────────────────────────────

def test_build_fact_shape_and_routing():
    s = ProductSalesExtraction.model_validate(_sales_dict())
    fact = build_product_sales_fact(s, subject_entity_id="drug-1",
                                    source_url="upload://earnings.pdf")
    assert fact.predicate == "product_sales"
    assert route_predicate_to_domain(fact.predicate) == "commercial_operational"
    assert fact.fact_class == "corporate"        # company self-reported
    assert fact.confidence == 0.7
    assert "$2,500,000,000" in fact.object_value["description"]
    assert "Q1 2026" in fact.object_value["description"]
    assert "+41" in fact.object_value["description"]
    assert fact.object_value["net_sales_usd"] == 2_500_000_000.0
    assert fact.object_value["product_name"] == "Wegovy"
    assert fact.source_url == "upload://earnings.pdf"
    assert "net sales" in fact.evidence_text.lower()


def test_predicate_is_kbq5():
    """KBQ-5 'Sales & Sentiment' was empty (no fact predicate mapped). Tier 2
    fills it."""
    assert _PREDICATE_KBQ["product_sales"] == 5


def test_source_row_id_deterministic_for_idempotency():
    s = ProductSalesExtraction.model_validate(_sales_dict())
    a = build_product_sales_fact(s, subject_entity_id="drug-1")
    b = build_product_sales_fact(s, subject_entity_id="drug-1")
    assert a.source_row_id == b.source_row_id
    # different period -> different key (a new quarter is a new fact)
    c = build_product_sales_fact(
        ProductSalesExtraction.model_validate(_sales_dict(period_label="Q2 2026")),
        subject_entity_id="drug-1")
    assert c.source_row_id != a.source_row_id
    # different drug -> different key
    d = build_product_sales_fact(s, subject_entity_id="drug-2")
    assert d.source_row_id != a.source_row_id


def test_negative_yoy_renders_with_minus_sign():
    s = ProductSalesExtraction.model_validate(_sales_dict(yoy_change_pct=-12.0))
    fact = build_product_sales_fact(s, subject_entity_id="drug-1")
    assert "-12" in fact.object_value["description"]


def test_missing_yoy_omits_delta_clause():
    d = _sales_dict()
    d.pop("yoy_change_pct")
    s = ProductSalesExtraction.model_validate(d)
    fact = build_product_sales_fact(s, subject_entity_id="drug-1")
    assert "YoY" not in fact.object_value["description"]


# ── extract_product_sales_facts (LLM + resolver wiring) ──────────────────────

def test_extract_emits_fact_when_sales_and_resolver_ok():
    facts = extract_product_sales_facts(
        "…earnings deck text…",
        structured_call=_call_returning(_sales_dict()),
        resolver=_resolver_ok,
    )
    assert len(facts) == 1
    assert facts[0].subject_entity_id == "drug-semaglutide"


def test_extract_skips_when_drug_unresolved():
    """Honesty guard: no dollar figure ever lands on an unresolved subject."""
    facts = extract_product_sales_facts(
        "…earnings deck text…",
        structured_call=_call_returning(_sales_dict()),
        resolver=_resolver_none,
    )
    assert facts == []


def test_extract_returns_empty_when_llm_returns_nothing():
    facts = extract_product_sales_facts(
        "a clinical readout slide, not financials",
        structured_call=_call_returning(None),
        resolver=_resolver_ok,
    )
    assert facts == []


def test_extract_returns_empty_on_blank_text():
    facts = extract_product_sales_facts(
        "   ", structured_call=_call_returning(_sales_dict()),
        resolver=_resolver_ok,
    )
    assert facts == []


def test_extract_is_exception_safe_on_bad_llm_payload():
    facts = extract_product_sales_facts(
        "…", structured_call=_call_returning({"garbage": 1}),
        resolver=_resolver_ok,
    )
    assert facts == []


# ── KBQ-5 wiring: a product_sales fact reaches the Sales & Sentiment view ─────

class _FakeDb:
    """Branches on SQL: signals query → none; facts query → controlled set."""

    def __init__(self, facts):
        self._facts = facts

    def fetch_all(self, sql, params=None):
        s = sql.lower()
        if "from signals" in s:
            return []
        if "from ranked" in s or "from facts" in s:
            return list(self._facts)
        return []


def test_product_sales_fact_lands_in_kbq5():
    from services.kbq_views import build_entity_kbqs

    facts = [
        {"id": "f1", "predicate": "product_sales", "fact_class": "corporate",
         "claim": "Wegovy Q1 2026 net sales $2,500,000,000, +41% YoY",
         "confidence": 0.7, "valid_from": None, "source_id": "user_document",
         "source_url": "upload://earnings.pdf"},
        # a clinical fact must not leak into KBQ-5
        {"id": "f2", "predicate": "clinical_trial", "fact_class": "corporate",
         "claim": "Phase 3 SUSTAIN-6", "confidence": 0.9, "valid_from": None,
         "source_id": "ctgov", "source_url": None},
    ]
    out = build_entity_kbqs(_FakeDb(facts), "drug", "drug-semaglutide")
    kbq5 = next(k for k in out["kbqs"] if k["kbq"] == 5)
    claims = [i["claim"] for i in kbq5["items"]]
    assert any("net sales" in c for c in claims)
    assert all("SUSTAIN-6" not in c for c in claims)
    assert kbq5["status"] == "fresh"
