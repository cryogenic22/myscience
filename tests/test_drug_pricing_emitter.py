"""DR-pricing — tests for the drug_pricing fact emitter (pure, DB-free)."""

from __future__ import annotations

from services.fact_emitters.drug_pricing import DrugPricingEmitter, build_claim


def _row(**over):
    base = {
        "id": "p1", "drug_id": "d1", "drug_name": "Acarbose", "ndc_code": "00093",
        "price_type": "nadac", "unit_price": 0.1234, "unit": "per unit",
        "currency": "USD", "source_api": "cms_nadac", "source_url": "https://cms.gov/x",
        "effective_date": "2025-12-17",
    }
    base.update(over)
    return base


class TestDrugPricingEmitter:
    def test_emits_one_net_price_fact(self):
        facts = DrugPricingEmitter().row_to_facts(_row())
        assert len(facts) == 1
        f = facts[0]
        assert f.predicate == "net_price"
        assert f.subject_entity_type == "drug"
        assert f.subject_entity_id == "d1"
        assert f.object_value["value"] == 0.1234
        assert f.object_value["currency"] == "USD"
        assert f.source_id == "cms_nadac"
        assert f.source_row_id == "p1"

    def test_carries_nadac_basis_so_not_read_as_list_price(self):
        f = DrugPricingEmitter().row_to_facts(_row())[0]
        # the precise basis must travel with the fact — NADAC is acquisition cost,
        # never WAC/list price.
        assert f.object_value["price_type"] == "nadac"
        assert f.object_value["basis"] == "medicaid_acquisition_cost"

    def test_cms_nadac_is_reference_class(self):
        f = DrugPricingEmitter().row_to_facts(_row())[0]
        assert f.fact_class == "reference"

    def test_no_fact_without_price(self):
        assert DrugPricingEmitter().row_to_facts(_row(unit_price=None)) == []

    def test_no_fact_without_drug(self):
        assert DrugPricingEmitter().row_to_facts(_row(drug_id=None)) == []

    def test_registered_in_get_emitters(self):
        from services.fact_emitters.base import get_emitters
        emitters = get_emitters()
        assert "drug_pricing" in emitters
        assert emitters["drug_pricing"].__class__.__name__ == "DrugPricingEmitter"

    def test_claim_is_transparent_about_nadac(self):
        claim = build_claim(_row())
        assert "NADAC" in claim and "acquisition" in claim.lower()
