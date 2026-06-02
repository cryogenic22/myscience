"""Tests for drug consolidation script."""

from __future__ import annotations

import pytest

from scripts.consolidate_drugs import (
    _normalize_drug_name,
    _pick_canonical,
    combo_safe_normalize,
)


class TestComboSafeNormalize:
    def test_additive_combo_not_collapsed_to_mono(self):
        # Hyzaar must NOT normalize to "losartan" (the monotherapy).
        out = combo_safe_normalize("losartan potassium (+ hydrochlorothiazide)")
        assert out != "losartan"
        assert out == "losartan potassium (+ hydrochlorothiazide)"

    def test_plain_variant_still_normalizes(self):
        assert combo_safe_normalize("Semaglutide Oral Tablet") == "semaglutide"
        assert combo_safe_normalize("sitagliptin phosphate") == "sitagliptin"

    def test_and_combo_still_groups_identically(self):
        # "X AND Y" combos (no additive '+') group by their shared normalized
        # form so identical duplicate rows still merge.
        a = combo_safe_normalize("VALSARTAN AND HYDROCHLOROTHIAZIDE")
        b = combo_safe_normalize("valsartan and hydrochlorothiazide")
        assert a == b


class TestNormalizeDrugName:
    def test_lowercase(self):
        assert _normalize_drug_name("SEMAGLUTIDE") == "semaglutide"

    def test_strips_salt_forms(self):
        assert _normalize_drug_name("sitagliptin phosphate") == "sitagliptin"
        assert _normalize_drug_name("SITAGLIPTIN HYDROCHLORIDE ORAL") == "sitagliptin"

    def test_strips_parenthetical_brand(self):
        assert _normalize_drug_name("Sitagliptin (Januvia)") == "sitagliptin"
        assert _normalize_drug_name("Empagliflozin (Jardiance)") == "empagliflozin"

    def test_strips_dpp4i_suffix(self):
        assert _normalize_drug_name("Sitagliptin - DPP4i") == "sitagliptin"

    def test_strips_dosage_forms(self):
        assert _normalize_drug_name("Linagliptin Oral Tablet") == "linagliptin"
        assert _normalize_drug_name("Empagliflozin (oral)") == "empagliflozin"

    def test_strips_identifiers(self):
        assert _normalize_drug_name("Sitagliptin (MK0431)") == "sitagliptin"

    def test_strips_duration_tails(self):
        assert _normalize_drug_name("mk0431, sitagliptin phosphate / duration of treatment: 21 weeks") == ", sitagliptin"

    def test_preserves_simple_name(self):
        assert _normalize_drug_name("semaglutide") == "semaglutide"
        assert _normalize_drug_name("empagliflozin") == "empagliflozin"

    def test_combo_products(self):
        # Combo products should normalize but stay together
        result = _normalize_drug_name("sitagliptin and metformin")
        assert "sitagliptin" in result
        assert "metformin" in result


class TestPickCanonical:
    def _make_record(self, name, source="backfill", company_id=None, mechanism_id=None,
                     brand_name=None, therapeutic_area_id=None, link_count=0):
        return {
            "id": f"id-{name}",
            "generic_name": name,
            "source_api": source,
            "company_id": company_id,
            "mechanism_id": mechanism_id,
            "brand_name": brand_name,
            "therapeutic_area_id": therapeutic_area_id,
            "link_count": link_count,
        }

    def test_prefers_fda_source(self):
        records = [
            self._make_record("sitagliptin", source="backfill", link_count=500),
            self._make_record("SITAGLIPTIN", source="fda_orange_book", link_count=100),
        ]
        result = _pick_canonical(records)
        assert result["source_api"] == "fda_orange_book"

    def test_prefers_record_with_company(self):
        records = [
            self._make_record("sig1", source="backfill"),
            self._make_record("sig2", source="backfill", company_id="co-123"),
        ]
        result = _pick_canonical(records)
        assert result["company_id"] == "co-123"

    def test_prefers_record_with_mechanism(self):
        records = [
            self._make_record("sig1", source="backfill"),
            self._make_record("sig2", source="backfill", mechanism_id="mech-1"),
        ]
        result = _pick_canonical(records)
        assert result["mechanism_id"] == "mech-1"

    def test_tiebreak_by_link_count(self):
        records = [
            self._make_record("sig1", source="backfill", link_count=100),
            self._make_record("sig2", source="backfill", link_count=500),
        ]
        result = _pick_canonical(records)
        assert result["generic_name"] == "sig2"


class TestShouldExclude:
    """Tests for enhanced exclusion patterns."""

    def test_long_names_excluded(self):
        from scripts.clean_drug_names import _should_exclude
        assert _should_exclude("Empagliflozin + Metformin hydrochloride 5 mg/850 mg combination film-coated tablets")

    def test_administration_of_excluded(self):
        from scripts.clean_drug_names import _should_exclude
        assert _should_exclude("Administration of rosiglitazone/metformin")

    def test_test_drug_excluded(self):
        from scripts.clean_drug_names import _should_exclude
        assert _should_exclude("CKD-379(Empagliflozin+sitagliptin+metformin) Test drug")

    def test_oral_tablet_excluded(self):
        from scripts.clean_drug_names import _should_exclude
        assert _should_exclude("Hydroxychloroquine Oral Tablet")

    def test_simple_drug_not_excluded(self):
        from scripts.clean_drug_names import _should_exclude
        assert not _should_exclude("semaglutide")
        assert not _should_exclude("Empagliflozin")
        assert not _should_exclude("SITAGLIPTIN")
