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

from services.unified_handler import (
    _coverage_limitations,
    _matrix_gap_limitations,
    _matrix_coverage_table,
)


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


def _decomp(entities, dimensions, cells, gaps):
    return {"entities": entities, "dimensions": dimensions, "cells": cells, "gaps": gaps}


_COMPARE_DECOMP = _decomp(
    entities=[{"entity_id": "sema", "label": "semaglutide"},
              {"entity_id": "tirz", "label": "tirzepatide"}],
    dimensions=[{"key": "mechanism", "label": "Mechanism"},
                {"key": "clinical_efficacy", "label": "Clinical efficacy"},
                {"key": "pricing", "label": "Pricing & access"}],
    cells=[
        {"dimension": "mechanism", "entity_id": "sema", "coverage": "covered"},
        {"dimension": "mechanism", "entity_id": "tirz", "coverage": "covered"},
        {"dimension": "clinical_efficacy", "entity_id": "sema", "coverage": "gap"},
        {"dimension": "clinical_efficacy", "entity_id": "tirz", "coverage": "gap"},
        {"dimension": "pricing", "entity_id": "sema", "coverage": "gap"},
        {"dimension": "pricing", "entity_id": "tirz", "coverage": "covered"},
    ],
    gaps=["clinical_efficacy", "pricing"],
)


class TestMatrixCoverageTable:
    """F2/#5 — the PLAN matrix rendered as a per-lens coverage table (the
    'render from an answer matrix' lever). Deterministic, built in code."""

    def test_none_or_no_dims_returns_empty(self):
        assert _matrix_coverage_table(None) == ""
        assert _matrix_coverage_table({}) == ""
        assert _matrix_coverage_table({"dimensions": []}) == ""

    def test_renders_lens_coverage_source(self):
        decomp = {
            "entities": [{"entity_id": "sema", "label": "semaglutide"}],
            "dimensions": [
                {"key": "mechanism", "label": "Mechanism"},
                {"key": "clinical_efficacy", "label": "Clinical efficacy"},
            ],
            "coverage_summary": {"mechanism": "covered", "clinical_efficacy": "gap"},
            "cells": [
                {"dimension": "mechanism", "entity_id": "sema", "coverage": "covered",
                 "facts": [{"claim": "GLP-1 RA", "predicate": "mechanism_of_action"}]},
                {"dimension": "clinical_efficacy", "entity_id": "sema", "coverage": "gap",
                 "facts": []},
            ],
        }
        out = _matrix_coverage_table(decomp)
        # It's a markdown table with the header + both lenses.
        assert "Coverage by lens" in out
        assert "| Lens | Coverage | Source |" in out
        assert "Mechanism" in out and "Clinical efficacy" in out
        # Covered lens cites its named source (predicate→connector).
        assert "MeSH / curated mechanism" in out
        # Gap lens reads "not in retrieved evidence" (retrieval scope, not "doesn't exist").
        assert "not in retrieved evidence" in out
        # Coverage glyphs present.
        assert "covered" in out and "gap" in out

    def test_gap_source_is_retrieval_scoped_not_absent(self):
        decomp = {
            "dimensions": [{"key": "pricing", "label": "Pricing"}],
            "coverage_summary": {"pricing": "gap"},
            "cells": [{"dimension": "pricing", "entity_id": "x", "coverage": "gap", "facts": []}],
        }
        out = _matrix_coverage_table(decomp)
        assert "not in retrieved evidence" in out
        # Must NOT imply the data does not exist in the world.
        assert "does not exist" not in out.lower()


class TestMatrixGapLimitations:
    """F2 — G2 honesty driven by the PLAN matrix's OWN per-dimension gaps
    (planner coverage state), not just question keywords. A dimension the
    decomposition could not ground becomes an explicit, named gap so synthesis
    cannot quietly fill it."""

    def test_none_or_no_gaps_returns_empty(self):
        assert _matrix_gap_limitations(None) == []
        assert _matrix_gap_limitations({}) == []
        # A fully-covered decomposition produces no false limitations.
        covered = _decomp(
            entities=[{"entity_id": "sema", "label": "semaglutide"}],
            dimensions=[{"key": "mechanism", "label": "Mechanism"}],
            cells=[{"dimension": "mechanism", "entity_id": "sema", "coverage": "covered"}],
            gaps=[],
        )
        assert _matrix_gap_limitations(covered) == []

    def test_gap_dimension_becomes_named_limitation(self):
        out = _matrix_gap_limitations(_COMPARE_DECOMP)
        flags = {f for _t, f in out}
        texts = [t for t, _f in out]
        # Each gap dimension is flagged with a grounded, dimension-specific flag.
        assert "MATRIX_GAP_CLINICAL_EFFICACY" in flags
        assert "MATRIX_GAP_PRICING" in flags
        # The covered dimension is NOT flagged (no over-hedging).
        assert not any("mechanism" in t.lower() for t in texts)
        # The dimension label appears in the limitation text.
        assert any("clinical efficacy" in t.lower() for t in texts)

    def test_limitation_names_only_the_gap_entities(self):
        out = dict((f, t) for t, f in _matrix_gap_limitations(_COMPARE_DECOMP))
        # clinical_efficacy is a gap for BOTH drugs → both named.
        eff = out["MATRIX_GAP_CLINICAL_EFFICACY"].lower()
        assert "semaglutide" in eff and "tirzepatide" in eff
        # pricing is a gap only for semaglutide (tirz is covered) → only sema named.
        price = out["MATRIX_GAP_PRICING"].lower()
        assert "semaglutide" in price and "tirzepatide" not in price

    def test_returns_text_and_flag_pairs(self):
        for item in _matrix_gap_limitations(_COMPARE_DECOMP):
            assert isinstance(item, tuple) and len(item) == 2
            text, flag = item
            assert isinstance(text, str) and text
            assert flag.startswith("MATRIX_GAP_")

    def test_many_gaps_are_capped_with_transparent_overflow(self):
        # No silent truncation: when more gap dimensions exist than the cap,
        # an explicit overflow limitation states how many were omitted.
        dims = [{"key": f"d{i}", "label": f"Dim {i}"} for i in range(8)]
        cells = [{"dimension": f"d{i}", "entity_id": "x", "coverage": "gap"}
                 for i in range(8)]
        decomp = _decomp(
            entities=[{"entity_id": "x", "label": "drugX"}],
            dimensions=dims, cells=cells, gaps=[f"d{i}" for i in range(8)],
        )
        out = _matrix_gap_limitations(decomp)
        flags = {f for _t, f in out}
        assert "MATRIX_GAP_OVERFLOW" in flags
        # Capped: fewer emitted than the 8 raw gaps, but overflow is explicit.
        assert len(out) < 8
