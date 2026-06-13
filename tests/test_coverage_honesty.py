"""H1 — deterministic coverage-limitation layer (eval gate G2: closed-world honesty).

TDD: written BEFORE the implementation.

The specialist judge fails G2 (7%) because the system answers confidently about
sources the platform does NOT ingest (EMA product information, payer/formulary,
WAC/list pricing, Purple Book/biosimilars) or only thinly ingests. The fix is
NOT to hope the LLM hedges — it is to compute, deterministically, which
not-ingested/thin source a query implicates and ALWAYS emit an honest limitation
+ review_flag. A missing source can then never silently become a confident answer.

Run: pytest tests/test_coverage_honesty.py -v
"""

from __future__ import annotations

from services.unified_handler import _coverage_limitations


def _texts(question: str) -> list[str]:
    return [t for t, _flag in _coverage_limitations(question)]


def _flags(question: str) -> set[str]:
    return {f for _t, f in _coverage_limitations(question)}


class TestCoverageLimitations:
    def test_ema_eu_query_flags_ema_not_ingested(self):
        # REG-01: EMA vs OpenFDA label divergence — EMA product info is NOT ingested.
        q = "Identify drugs where the EMA product information and the OpenFDA label diverge on indication."
        assert any("EMA" in t for t in _texts(q)), "must flag EMA/EU not ingested"
        assert "SOURCE_COVERAGE_GAP" in _flags(q)

    def test_payer_access_query_flags_no_payer_source(self):
        q = "Are GLP-1s covered by payers, and what is the formulary tier?"
        assert any("payer" in t.lower() for t in _texts(q)), "must flag no payer/formulary source"
        assert "SOURCE_COVERAGE_GAP" in _flags(q)

    def test_pricing_query_flags_pricing_coverage(self):
        q = "What is the WAC list price of Ozempic?"
        ts = _texts(q)
        assert any(("nadac" in t.lower() or "wac" in t.lower() or "price" in t.lower()) for t in ts)
        assert "SOURCE_COVERAGE_GAP" in _flags(q)

    def test_biosimilar_query_flags_purple_book_gap(self):
        q = "Which Orange Book drugs face near-term biosimilar competition?"
        assert any(("purple book" in t.lower() or "biosimilar" in t.lower()) for t in _texts(q))

    def test_pure_clinical_query_has_no_false_limitations(self):
        # A query fully within ingested sources must NOT be over-hedged.
        assert _coverage_limitations("What is the mechanism of action of semaglutide?") == []

    def test_returns_text_and_flag_pairs(self):
        out = _coverage_limitations("payer coverage and pricing for tirzepatide")
        assert isinstance(out, list) and out
        for item in out:
            assert isinstance(item, tuple) and len(item) == 2
            text, flag = item
            assert isinstance(text, str) and text
            assert isinstance(flag, str) and flag
