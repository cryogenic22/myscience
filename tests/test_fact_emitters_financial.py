"""DR-Financial — tests for the financial / commercial fact emitter.

Lifts ``company_financials`` (XBRL SEC metrics) and ``deals`` rows into the
facts ledger so the dossier's commercial domain (and KBQ "Sales"/commercial)
is no longer empty. Pure mapping (``row_to_facts``, claim builders) is DB-free;
idempotency uses the shared ``emit_one``/``run_emitter`` with a MagicMock DB in
the established style (see tests/test_fact_emitters.py).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import MagicMock

from services.dossier_kb import route_predicate_to_domain
from services.fact_emitters.base import get_emitters, run_emitter
from services.fact_emitters.financial import (
    DealEmitter,
    FinancialEmitter,
    build_financial_claim,
    build_deal_claim,
)


# ── fixtures ────────────────────────────────────────────────────────

def _financial(**over):
    base_row = {
        "id": "fin-1",
        "company_id": "co-novo",
        "company_name": "Novo Nordisk",
        "cik": "0000353278",
        "fiscal_year": 2025,
        "fiscal_period": "FY",
        "metric_name": "revenue",
        "metric_value": 42_000_000_000.0,
        "currency": "USD",
        "filed_date": date(2026, 2, 5),
        "source_api": "sec_edgar",
    }
    base_row.update(over)
    return base_row


def _deal(**over):
    base_row = {
        "id": "deal-1",
        "deal_types": ["acquisition"],
        "acquirer_id": "co-pfizer",
        "acquirer_name": "Pfizer",
        "target_id": "co-arena",
        "target_name": "Arena Pharmaceuticals",
        "licensor_id": None,
        "licensor_name": None,
        "licensee_id": None,
        "licensee_name": None,
        "currency": "USD",
        "upfront_value_usd": 6_700_000_000.0,
        "total_potential_usd": 6_700_000_000.0,
        "milestones_total_usd": None,
        "announced_date": date(2021, 12, 13),
        "closing_date": date(2022, 3, 11),
        "status": "closed",
        "press_release_url": "https://pfizer.com/arena",
        "filing_url": None,
        "notes": "Pfizer to acquire Arena Pharmaceuticals.",
    }
    base_row.update(over)
    return base_row


# ── financial-metric mapping (pure) ─────────────────────────────────

class TestFinancialMapping:
    def test_build_claim_reads_well(self):
        claim = build_financial_claim(_financial())
        assert "Revenue" in claim
        assert "FY2025" in claim
        assert "42.0B" in claim or "$42" in claim

    def test_row_to_facts_emits_one_financial_metric_fact(self):
        facts = FinancialEmitter().row_to_facts(_financial())
        assert len(facts) == 1
        f = facts[0]
        assert f.predicate == "financial_metric"
        assert f.subject_entity_type == "company"
        assert f.subject_entity_id == "co-novo"
        assert f.source_row_id == "fin-1"
        assert f.fact_class == "corporate"
        assert f.object_value["metric_name"] == "revenue"
        assert f.object_value["metric_value"] == 42_000_000_000.0
        assert f.evidence_text  # DR-5: attestable snippet present

    def test_filed_date_drives_valid_from(self):
        f = FinancialEmitter().row_to_facts(_financial())[0]
        assert f.valid_from == datetime(2026, 2, 5, tzinfo=timezone.utc)

    def test_row_without_company_emits_nothing(self):
        assert FinancialEmitter().row_to_facts(_financial(company_id=None)) == []

    def test_row_without_value_emits_nothing(self):
        assert FinancialEmitter().row_to_facts(_financial(metric_value=None)) == []


# ── deal mapping (pure) ─────────────────────────────────────────────

class TestDealMapping:
    def test_build_deal_claim_reads_well(self):
        claim = build_deal_claim(_deal())
        assert "Pfizer" in claim
        assert "Arena" in claim

    def test_row_to_facts_emits_one_deal_fact_per_party(self):
        facts = DealEmitter().row_to_facts(_deal())
        # subject on each side of the deal — acquirer + target
        subjects = {(f.subject_entity_type, f.subject_entity_id) for f in facts}
        assert ("company", "co-pfizer") in subjects
        assert ("company", "co-arena") in subjects
        for f in facts:
            assert f.predicate == "deal_announced"
            assert f.fact_class == "corporate"
            assert f.source_row_id.startswith("deal-1")
            assert f.evidence_text

    def test_deal_without_any_company_emits_nothing(self):
        assert DealEmitter().row_to_facts(
            _deal(acquirer_id=None, target_id=None,
                  licensor_id=None, licensee_id=None)) == []

    def test_idempotency_key_unique_per_subject(self):
        facts = DealEmitter().row_to_facts(_deal())
        keys = [f.source_row_id for f in facts]
        assert len(keys) == len(set(keys))  # each party row distinct


# ── predicate routing (the whole point — facts must land commercial) ──

class TestPredicateRouting:
    def test_financial_metric_routes_to_commercial(self):
        assert route_predicate_to_domain("financial_metric") == "commercial_operational"

    def test_deal_announced_routes_to_competitive(self):
        # "deal" prefix already routes to competitive; deal_announced confirms it
        assert route_predicate_to_domain("deal_announced") == "competitive"


# ── run_emitter (idempotent) ────────────────────────────────────────

class TestRunEmitter:
    def test_counts_asserted(self, monkeypatch):
        em = FinancialEmitter()
        monkeypatch.setattr(em, "fetch_rows",
                            lambda *a, **k: [_financial(id="A"), _financial(id="B")])
        db = MagicMock()
        db.fetch_all.return_value = []  # _fact_exists → no
        db.fetch_one.side_effect = [
            None, {"evidence_id": "e1"}, {"id": "f1"},   # A asserted
            None, {"evidence_id": "e2"}, {"id": "f2"},   # B asserted
        ]
        stats = run_emitter(db, em)
        assert stats.scanned == 2
        assert stats.asserted == 2
        assert stats.evidence_written == 2

    def test_idempotent_rerun_asserts_nothing(self, monkeypatch):
        em = FinancialEmitter()
        monkeypatch.setattr(em, "fetch_rows", lambda *a, **k: [_financial(id="A")])
        db = MagicMock()
        db.fetch_all.return_value = [{"id": "existing"}]  # already present
        stats = run_emitter(db, em)
        assert stats.asserted == 0
        assert stats.skipped_existing == 1


class TestRegistry:
    def test_financial_emitters_registered(self):
        reg = get_emitters()
        assert "financial" in reg
        assert "deals" in reg
