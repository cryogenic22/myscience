"""Loop ① — tests for the gazetteer entity linker."""

from __future__ import annotations

from unittest.mock import MagicMock

from services.entity_linker import EntityLinker, _normalize, _tokens

COMPANIES = [
    {"id": "co-lilly", "name": "Eli Lilly and Company"},
    {"id": "co-novo", "name": "Novo Nordisk"},
    {"id": "co-savara", "name": "Savara"},
    {"id": "co-amgen", "name": "Amgen"},
]
DRUGS = [
    {"id": "dr-sema", "generic_name": "semaglutide", "brand_name": "Wegovy"},
    {"id": "dr-tirz", "generic_name": "tirzepatide", "brand_name": "Zepbound"},
    {"id": "dr-orf", "generic_name": "orforglipron", "brand_name": None},
]


def _linker():
    db = MagicMock()

    def fetch_all(sql, params=None):
        s = (sql or "").lower()
        if "from companies" in s:
            return COMPANIES
        if "from drugs" in s:
            return DRUGS
        return []

    db.fetch_all = MagicMock(side_effect=fetch_all)
    return EntityLinker(db).load()


class TestHelpers:
    def test_normalize_strips_punct(self):
        assert _normalize("Eli Lilly & Co.") == "eli lilly co"
        assert _tokens("Lilly pens $202M deal!") == ["lilly", "pens", "202m", "deal"]


class TestLink:
    def test_full_company_name(self):
        r = _linker().link("Novo Nordisk reports Q1 results")
        assert r is not None and r.entity_type == "company"
        assert r.entity_id == "co-novo"
        assert r.confidence == EntityLinker._CONF_FULL

    def test_company_short_form_alias(self):
        # "Lilly" should resolve to Eli Lilly via auto-generated alias
        r = _linker().link("Lilly pens $202M deal for DNA delivery biotech")
        assert r is not None and r.entity_id == "co-lilly"
        assert r.confidence == EntityLinker._CONF_ALIAS

    def test_drug_brand_name(self):
        r = _linker().link("Wegovy prescription volume hits 475K weekly")
        assert r is not None and r.entity_type == "drug"
        assert r.entity_id == "dr-sema"
        assert r.canonical_name == "semaglutide"  # brand resolves to generic

    def test_drug_generic_name(self):
        r = _linker().link("orforglipron Phase 3 readout positive in T2D")
        assert r is not None and r.entity_id == "dr-orf"

    def test_drug_preferred_over_company_at_equal_length(self):
        # both "Amgen" (company) and "Wegovy" (drug) present; drug wins tie only
        # at equal ngram length — here Wegovy (1) vs Amgen (1) → drug preferred
        r = _linker().link("Amgen Wegovy comparison")
        assert r is not None and r.entity_type == "drug"

    def test_longest_match_wins(self):
        # "Novo Nordisk" (2 tokens) beats the "novo" alias (1 token)
        r = _linker().link("Novo Nordisk pipeline update")
        assert r.matched_text == "novo nordisk"

    def test_unknown_returns_none(self):
        r = _linker().link("Some unrelated biotech XYZ raised a round")
        assert r is None

    def test_empty_text(self):
        assert _linker().link("") is None
        assert _linker().link(None) is None

    def test_short_tokens_not_indexed_as_alias(self):
        # "Eli" (<4 chars) must not be an alias — avoids noise
        r = _linker().link("eli was here")  # 'eli' alone shouldn't match
        assert r is None

    def test_suffix_tokens_not_indexed(self):
        # "Company"/"and" must not resolve to Eli Lilly
        r = _linker().link("the company announced earnings")
        assert r is None
