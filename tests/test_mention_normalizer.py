"""Tests for pharma mention normalizers — drug and company name cleaning.

Covers edge cases in normalize_drug_mention() and normalize_company_mention()
that prevent false duplicates during entity resolution.

Run with: pytest tests/test_mention_normalizer.py -v
"""

from __future__ import annotations

import pytest

from domain.pharma.mention_normalizer import (
    COMPANY_SKIP_TERMS,
    DRUG_SKIP_TERMS,
    normalize_company_mention,
    normalize_drug_mention,
)


# ============================================================
# Drug normalization
# ============================================================


class TestNormalizeDrugMention:
    """Verify drug mention normalization strips dosage, form, and noise."""

    def test_dosage_stripped_from_drug_name(self):
        """'semaglutide 0.5 mg injection' should become 'semaglutide'."""
        result = normalize_drug_mention("semaglutide 0.5 mg injection")
        assert result == "semaglutide"

    def test_brand_in_parens_removed(self):
        """Parenthesized brand name '(ozempic)' should be stripped."""
        result = normalize_drug_mention("semaglutide (Ozempic)")
        assert result == "semaglutide"

    def test_uppercase_lowered(self):
        """'TIRZEPATIDE' should normalize to 'tirzepatide'."""
        result = normalize_drug_mention("TIRZEPATIDE")
        assert result == "tirzepatide"

    def test_drug_prefix_removed(self):
        """'Drug: Empagliflozin' should strip the prefix."""
        result = normalize_drug_mention("Drug: Empagliflozin")
        assert result == "empagliflozin"

    def test_experimental_prefix_removed(self):
        """'Experimental: Dapagliflozin 10mg' should strip prefix and dose."""
        result = normalize_drug_mention("Experimental: Dapagliflozin 10mg")
        assert result == "dapagliflozin"

    def test_extended_release_stripped(self):
        """'Metformin HCl Extended Release 500mg' should keep compound only."""
        result = normalize_drug_mention("Metformin HCl Extended Release 500mg")
        assert result == "metformin hcl"

    def test_complex_strength_pattern(self):
        """Strength with unit ratio like '100mg/ml' should be removed."""
        result = normalize_drug_mention("insulin glargine 100iu/ml injection")
        assert result == "insulin glargine"

    def test_bracketed_content_stripped(self):
        """Content in square brackets '[Phase 3 dose]' removed."""
        result = normalize_drug_mention("liraglutide [Phase 3 dose]")
        assert result == "liraglutide"

    def test_trademark_symbols_stripped(self):
        """Registered trademark symbols removed."""
        result = normalize_drug_mention("Ozempic\u00ae")
        # The brand name itself is kept since there's no base compound to prefer
        assert "\u00ae" not in result
        assert "\u2122" not in result

    def test_empty_string_returns_empty(self):
        """Empty input should return empty string."""
        result = normalize_drug_mention("")
        assert result == ""

    def test_whitespace_only_returns_empty_or_stripped(self):
        """Whitespace-only input should return empty or stripped version."""
        result = normalize_drug_mention("   ")
        assert result.strip() == ""

    def test_compound_name_with_hcl_salt(self):
        """Salt forms like 'HCl' should be preserved as part of compound name."""
        result = normalize_drug_mention("Metformin HCl")
        assert "metformin" in result
        assert "hcl" in result

    def test_multiple_dosage_forms_stripped(self):
        """All dosage form words should be removed, not just the first."""
        result = normalize_drug_mention("semaglutide subcutaneous injection pen")
        assert result == "semaglutide"

    def test_trailing_punctuation_removed(self):
        """Trailing commas, semicolons, colons removed."""
        result = normalize_drug_mention("semaglutide,")
        assert result == "semaglutide"


class TestDrugSkipTerms:
    """Verify that non-drug terms are present in the skip list."""

    def test_placebo_in_skip_terms(self):
        assert "placebo" in DRUG_SKIP_TERMS

    def test_standard_of_care_in_skip_terms(self):
        assert "standard of care" in DRUG_SKIP_TERMS

    def test_sham_in_skip_terms(self):
        assert "sham" in DRUG_SKIP_TERMS

    def test_behavioral_in_skip_terms(self):
        assert "behavioral" in DRUG_SKIP_TERMS

    def test_radiation_in_skip_terms(self):
        assert "radiation" in DRUG_SKIP_TERMS


# ============================================================
# Company normalization
# ============================================================


class TestNormalizeCompanyMention:
    """Verify company mention normalization strips suffixes and noise."""

    def test_a_s_suffix_removed(self):
        """'Novo Nordisk A/S' should become 'novo nordisk'."""
        result = normalize_company_mention("Novo Nordisk A/S")
        assert result == "novo nordisk"

    def test_inc_suffix_removed(self):
        """'Pfizer Inc.' should become 'pfizer'."""
        result = normalize_company_mention("Pfizer Inc.")
        assert result == "pfizer"

    def test_and_company_suffix_removed(self):
        """'Eli Lilly and Company' should become 'eli lilly'."""
        result = normalize_company_mention("Eli Lilly and Company")
        assert result == "eli lilly"

    def test_inc_with_comma_removed(self):
        """'Eli Lilly and Company, Inc.' should become 'eli lilly'."""
        result = normalize_company_mention("Eli Lilly and Company, Inc.")
        assert result == "eli lilly"

    def test_ltd_suffix_removed(self):
        """'AstraZeneca Ltd.' should become 'astrazeneca'."""
        result = normalize_company_mention("AstraZeneca Ltd.")
        assert result == "astrazeneca"

    def test_plc_suffix_removed(self):
        """'GlaxoSmithKline plc' should become 'glaxosmithkline'."""
        result = normalize_company_mention("GlaxoSmithKline plc")
        assert result == "glaxosmithkline"

    def test_pharmaceuticals_suffix_removed(self):
        """'Bayer Pharmaceuticals' should become 'bayer'."""
        result = normalize_company_mention("Bayer Pharmaceuticals")
        assert result == "bayer"

    def test_multiple_suffixes_removed(self):
        """'Roche Holdings AG' should strip both 'Holdings' and 'AG'."""
        result = normalize_company_mention("Roche Holdings AG")
        assert result == "roche"

    def test_parenthesized_content_removed(self):
        """'Sanofi (formerly Aventis)' should become 'sanofi'."""
        result = normalize_company_mention("Sanofi (formerly Aventis)")
        assert result == "sanofi"

    def test_empty_string_returns_empty(self):
        """Empty input should return empty string."""
        result = normalize_company_mention("")
        assert result == ""

    def test_whitespace_only_returns_empty_or_stripped(self):
        """Whitespace-only input should return empty or stripped version."""
        result = normalize_company_mention("   ")
        assert result.strip() == ""

    def test_gmbh_suffix_removed(self):
        """'Boehringer Ingelheim GmbH' should become 'boehringer ingelheim'."""
        result = normalize_company_mention("Boehringer Ingelheim GmbH")
        assert result == "boehringer ingelheim"

    def test_corp_suffix_removed(self):
        """'Merck Corp.' should become 'merck'."""
        result = normalize_company_mention("Merck Corp.")
        assert result == "merck"

    def test_case_insensitive_output(self):
        """All output should be lowercase."""
        result = normalize_company_mention("JOHNSON & JOHNSON")
        assert result == result.lower()


class TestCompanySkipTerms:
    """Verify non-company terms in the skip list."""

    def test_individual_in_skip_terms(self):
        assert "individual" in COMPANY_SKIP_TERMS

    def test_unknown_in_skip_terms(self):
        assert "unknown" in COMPANY_SKIP_TERMS

    def test_not_available_in_skip_terms(self):
        assert "not available" in COMPANY_SKIP_TERMS
