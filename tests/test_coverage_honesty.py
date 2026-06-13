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


def _texts(question: str, db=None) -> list[str]:
    return [t for t, _flag in _coverage_limitations(question, db)]


def _flags(question: str, db=None) -> set[str]:
    return {f for _t, f in _coverage_limitations(question, db)}


class _FakeDB:
    """Stands in for the NADAC-dedicated drug_pricing COUNT query (MZ-XR-002)."""

    def __init__(self, nadac_rows: int):
        self._n = nadac_rows

    def fetch_one(self, sql, params=None):
        assert "drug_pricing" in sql and "source_api" in sql
        return {"n": self._n}


class TestCoverageLimitations:
    def test_ema_eu_query_flags_ema_not_ingested(self):
        # REG-01: EMA vs OpenFDA label divergence — EMA product info is NOT ingested.
        q = "Identify drugs where the EMA product information and the OpenFDA label diverge on indication."
        assert any("EMA" in t for t in _texts(q)), "must flag EMA/EU not ingested"
        # MZ-XR-002: source-specific flag, not the generic SOURCE_COVERAGE_GAP.
        assert "EMA_PRODUCT_INFO_NOT_INGESTED" in _flags(q)

    def test_payer_access_query_flags_no_payer_source(self):
        q = "Are GLP-1s covered by payers, and what is the formulary tier?"
        assert any("payer" in t.lower() for t in _texts(q)), "must flag no payer/formulary source"
        assert "NO_PAYER_SOURCE" in _flags(q)

    def test_biosimilar_query_flags_purple_book_gap(self):
        q = "Which Orange Book drugs face near-term biosimilar competition?"
        assert any(("purple book" in t.lower() or "biosimilar" in t.lower()) for t in _texts(q))
        assert "NO_BIOSIMILAR_SOURCE" in _flags(q)

    def test_no_generic_source_coverage_gap_flag_remains(self):
        # The generic bucket is fully replaced by source-specific flags.
        q = "payer coverage, EMA label, biosimilar, sales and pricing for tirzepatide"
        assert "SOURCE_COVERAGE_GAP" not in _flags(q)

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


class TestPricingIsSourceStateDriven:
    """MZ-XR-20260613-002: pricing honesty is bound to LIVE NADAC state, not a
    hardcoded 'sparse or empty' that drifts once the data lane revives NADAC."""

    PRICING_Q = "What is the WAC list price of Ozempic?"

    def test_no_db_falls_back_to_no_net_price_source(self):
        # Unit/no-DB: conservative deterministic wording, source-specific flag.
        assert "NO_NET_PRICE_SOURCE" in _flags(self.PRICING_Q)

    def test_nadac_empty_says_no_rows(self):
        flags = _flags(self.PRICING_Q, _FakeDB(0))
        texts = _texts(self.PRICING_Q, _FakeDB(0))
        assert "NADAC_NO_ROWS" in flags
        assert any("no rows" in t.lower() for t in texts)

    def test_nadac_with_rows_says_acquisition_cost_not_net_price(self):
        # The drift case: NADAC HAS rows now → must NOT say "sparse or empty",
        # and must still refuse to give a list/net price (acquisition cost only).
        db = _FakeDB(4200)
        flags = _flags(self.PRICING_Q, db)
        texts = _texts(self.PRICING_Q, db)
        assert "NADAC_HAS_ROWS" in flags
        assert any("acquisition" in t.lower() for t in texts)
        assert not any("sparse or empty" in t.lower() for t in texts)

    def test_three_pricing_states_are_distinguishable(self):
        # Exit criterion: no-payer vs NADAC-empty vs NADAC-has-rows are distinct.
        assert "NO_PAYER_SOURCE" in _flags("formulary tier")
        assert "NADAC_NO_ROWS" in _flags(self.PRICING_Q, _FakeDB(0))
        assert "NADAC_HAS_ROWS" in _flags(self.PRICING_Q, _FakeDB(10))
