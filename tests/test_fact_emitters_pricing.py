"""DR-2 — tests for the pricing fact emitter (drug_pricing -> facts ledger).

Pure mapping (row_to_facts, build_claim) needs no DB. Routing is asserted
against the real dossier predicate router so the facts actually land in the
pricing_and_access domain. Conservation: rows with no resolved drug_id must be
counted as skipped_no_subject (never silently dropped). Mirrors the
conventions in tests/test_fact_emitters_dr3_dr4.py.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from services.dossier_kb import route_predicate_to_domain
from services.fact_emitters.base import get_emitters, run_emitter
from services.fact_emitters.pricing import PricingEmitter, build_claim


# ── MockDB (matches the project pattern) ───────────────────────────

class MockDB:
    def __init__(self):
        self._results: dict[str, list[dict]] = {}
        self.executed: list[tuple[str, list]] = []
        self.inserted_facts: list[dict] = []

    def set_results(self, key: str, results: list[dict]):
        self._results[key] = results

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower()
        # Existence check against the facts table -> always empty (nothing yet).
        if "from facts" in sql_lower:
            return []
        if "from drug_pricing" in sql_lower:
            return self._results.get("drug_pricing", [])
        for key, results in self._results.items():
            if key in sql_lower:
                return results
        return []

    def fetch_one(self, sql: str, params=None) -> dict | None:
        sql_lower = sql.lower()
        if "evidence_records" in sql_lower and "insert" in sql_lower:
            self.executed.append((sql, list(params or [])))
            return {"evidence_id": "ev-001"}
        if "evidence_records" in sql_lower:
            return None
        if "insert into facts" in sql_lower:
            self.inserted_facts.append({"sql": sql, "params": params})
            return {"id": "fact-001"}
        rows = self.fetch_all(sql, params)
        return rows[0] if rows else None

    def execute(self, sql: str, params=None) -> None:
        self.executed.append((sql, list(params or [])))


def _row(**over):
    row = {
        "id": "price-1",
        "drug_id": "drug-sema",
        "drug_name": "Semaglutide",
        "ndc_code": "00169-4150-13",
        "price_type": "nadac",
        "unit_price": 89.1234,
        "unit": "per unit",
        "currency": "USD",
        "country": "US",
        "source_api": "cms_nadac",
        "source_url": "https://data.medicaid.gov/api/1/datastore/query/x/0",
        "effective_date": date(2026, 1, 7),
    }
    row.update(over)
    return row


# ── Pure mapping ───────────────────────────────────────────────────

class TestPricingMapping:
    def test_build_claim_includes_price_unit_and_currency(self):
        claim = build_claim(_row())
        assert "89.1234" in claim
        assert "USD" in claim
        assert "per unit" in claim

    def test_row_to_facts_emits_corporate_nadac_fact(self):
        f = PricingEmitter().row_to_facts(_row())[0]
        assert f.predicate == "nadac_per_unit"
        assert f.fact_class == "corporate"
        assert f.subject_entity_type == "drug"
        assert f.subject_entity_id == "drug-sema"
        assert f.source_row_id == "price-1"
        assert f.object_value["unit_price"] == 89.1234
        assert f.object_value["currency"] == "USD"
        assert f.object_value["ndc_code"] == "00169-4150-13"
        assert f.valid_from == datetime(2026, 1, 7, tzinfo=timezone.utc)
        assert f.evidence_text  # evidence-bearing

    def test_no_drug_id_emits_no_subject_fact_not_dropped(self):
        """Conservation #2: an unlinked pricing row is NOT silently dropped.

        row_to_facts still yields a fact, but with an empty subject so the
        ledger records it as skipped_no_subject (counted), never lost."""
        facts = PricingEmitter().row_to_facts(_row(drug_id=None))
        assert len(facts) == 1
        assert facts[0].subject_entity_id == ""

    def test_no_price_emits_nothing(self):
        assert PricingEmitter().row_to_facts(_row(unit_price=None)) == []

    def test_routes_to_pricing_and_access(self):
        assert route_predicate_to_domain("nadac_per_unit") == "pricing_and_access"


# ── Idempotency + conservation via the ledger ──────────────────────

class TestPricingEmitterRun:
    def test_run_asserts_linked_and_counts_unlinked(self):
        db = MockDB()
        db.set_results("drug_pricing", [
            _row(id="price-1", drug_id="drug-sema"),
            _row(id="price-2", drug_id=None, drug_name="Unknown XYZ"),
        ])
        stats = run_emitter(db, PricingEmitter())
        assert stats.asserted == 1            # the linked row landed
        assert stats.skipped_no_subject == 1  # the unlinked row counted, not dropped
        assert stats.scanned == 2

    def test_idempotent_skip_on_existing(self):
        """If the fact already exists, re-run skips it (no duplicate)."""
        db = MockDB()

        # Make the existence check return a hit for everything.
        def fetch_all(sql, params=None):
            if "from facts" in sql.lower():
                return [{"id": "existing"}]
            if "from drug_pricing" in sql.lower():
                return [_row()]
            return []

        db.fetch_all = fetch_all  # type: ignore[assignment]
        stats = run_emitter(db, PricingEmitter())
        assert stats.asserted == 0
        assert stats.skipped_existing == 1


class TestRegistry:
    def test_pricing_emitter_registered(self):
        assert "pricing" in get_emitters()
