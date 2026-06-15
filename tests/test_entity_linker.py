"""Loop ① — tests for the gazetteer entity linker."""

from __future__ import annotations

from unittest.mock import MagicMock

from services.entity_linker import EntityLinker, _normalize, _tokens

COMPANIES = [
    {"id": "co-lilly", "name": "Eli Lilly and Company"},
    {"id": "co-novo", "name": "Novo Nordisk"},
    {"id": "co-savara", "name": "Savara"},
    {"id": "co-amgen", "name": "Amgen"},
    # noise that must be excluded from the gazetteer:
    {"id": "co-harvard", "name": "The Harvard Drug Group"},
    {"id": "co-timi", "name": "TIMI Study Group"},
    {"id": "co-hosp", "name": "4th Military Clinical Hospital"},
    {"id": "co-nih", "name": "National Institutes of Health Clinical Center"},
]
DRUGS = [
    {"id": "dr-sema", "generic_name": "semaglutide", "brand_name": "Wegovy"},
    {"id": "dr-tirz", "generic_name": "tirzepatide", "brand_name": "Zepbound"},
    {"id": "dr-orf", "generic_name": "orforglipron", "brand_name": None},
    {"id": "dr-bad", "generic_name": "weight loss", "brand_name": None},  # data error
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


class TestPriorityOnly:
    def _priority_linker(self):
        # DB returns a priority company for ILIKE 'Eli Lilly', a drug for
        # 'semaglutide', and noise for anything else.
        db = MagicMock()

        def fetch_all(sql, params=None):
            s = (sql or "").lower()
            p = (params or [""])[0]
            if "from companies" in s and "ilike" in s:
                if "lilly" in str(p).lower():
                    return [{"id": "co-lilly", "name": "Eli Lilly and Company"}]
                if "novo" in str(p).lower():
                    return [{"id": "co-novo", "name": "Novo Nordisk A/S"}]
                return []
            if "from drugs" in s and "ilike" in s:
                if "semaglutide" in str(p).lower():
                    return [{"id": "dr-sema", "generic_name": "semaglutide", "brand_name": "Ozempic"}]
                return []
            return []

        db.fetch_all = MagicMock(side_effect=fetch_all)
        return EntityLinker(db).load(priority_only=True)

    def test_resolves_priority_company(self):
        r = self._priority_linker().link("Lilly pens $202M deal")
        assert r is not None and r.entity_id == "co-lilly"

    def test_resolves_priority_drug(self):
        r = self._priority_linker().link("semaglutide cardiovascular outcomes")
        assert r is not None and r.entity_id == "dr-sema"

    def test_rejects_non_priority_noise(self):
        # trial-sponsor company not in priority list → no match
        r = self._priority_linker().link("Response Pharmaceuticals enrolled patients")
        assert r is None


class TestWithPriorityAliases:
    """Full gazetteer + curated priority short-forms — the mode the signal
    promoter/backfill uses. Widens recall to the whole company/drug universe
    while keeping the hand-vetted initialisms (bms, jnj…) high-confidence so a
    precision-first backfill can trust them."""

    def _full_plus(self):
        # Full company/drug list, AND _find_company ILIKE lookups for the
        # priority-alias overlay resolve the curated names.
        db = MagicMock()
        priority_rows = {
            "bristol myers squibb": {"id": "co-bms", "name": "Bristol Myers Squibb"},
            "eli lilly": {"id": "co-lilly", "name": "Eli Lilly and Company"},
            "novo nordisk": {"id": "co-novo", "name": "Novo Nordisk"},
        }

        def fetch_all(sql, params=None):
            s = (sql or "").lower()
            if "from companies" in s and "ilike" in s:
                needle = str((params or [""])[0]).strip("%").lower()
                for k, row in priority_rows.items():
                    if needle and (needle in k or k in needle):
                        return [row]
                return []
            if "from companies" in s:
                return COMPANIES + [{"id": "co-regen", "name": "Regeneron Pharmaceuticals"}]
            if "from drugs" in s:
                return DRUGS
            return []

        db.fetch_all = MagicMock(side_effect=fetch_all)
        return EntityLinker(db).load(with_priority_aliases=True)

    def test_resolves_non_priority_company_by_full_name(self):
        # Regeneron is NOT in the priority list; priority_only mode would miss it.
        # Full mode resolves it via its canonical name → high confidence.
        r = self._full_plus().link("Regeneron Pharmaceuticals reports positive Phase 3 data")
        assert r is not None and r.entity_id == "co-regen"
        assert r.confidence == EntityLinker._CONF_FULL

    def test_curated_priority_alias_is_high_confidence(self):
        # "bms" is a hand-vetted initialism dropped by the full gazetteer's
        # 4-char token rule; the overlay re-adds it at priority-alias confidence.
        r = self._full_plus().link("bms acquires obesity biotech")
        assert r is not None and r.entity_id == "co-bms"
        assert r.confidence == EntityLinker._CONF_PRIORITY_ALIAS

    def test_auto_generated_alias_stays_low_confidence(self):
        # A distinctive auto-alias ("regeneron" from "Regeneron Pharmaceuticals")
        # is useful but NOT hand-vetted → ordinary alias confidence, so a
        # precision-first backfill can exclude it.
        r = self._full_plus().link("regeneron wins fda nod")
        assert r is not None and r.entity_id == "co-regen"
        assert r.confidence == EntityLinker._CONF_ALIAS

    def test_without_flag_no_priority_overlay(self):
        # Plain full mode (flag off) must not pull in the curated initialism.
        db = MagicMock()
        db.fetch_all = MagicMock(side_effect=lambda sql, p=None: (
            COMPANIES if "from companies" in sql.lower() and "ilike" not in sql.lower()
            else DRUGS if "from drugs" in sql.lower() else []
        ))
        r = EntityLinker(db).load().link("bms acquires obesity biotech")
        assert r is None  # 'bms' only resolves with the priority overlay


class TestGazetteerHardening:
    """Junk rows the prod gazetteer carries must never become a match — they
    were the false-positives a read-before-write prod probe surfaced (drug
    classes, trial arms, generic-word companies, news-publisher rows)."""

    def _linker(self, companies, drugs):
        db = MagicMock()
        db.fetch_all = MagicMock(side_effect=lambda sql, p=None: (
            companies if "from companies" in sql.lower() and "ilike" not in sql.lower()
            else drugs if "from drugs" in sql.lower() else []
        ))
        return EntityLinker(db).load()

    def test_drug_class_and_trial_arm_rows_excluded(self):
        drugs = [
            {"id": "d1", "generic_name": "GLP-1", "brand_name": None},
            {"id": "d2", "generic_name": "Medication", "brand_name": None},
            {"id": "d3", "generic_name": "active control", "brand_name": None},
            {"id": "d4", "generic_name": "intervention", "brand_name": None},
            {"id": "d5", "generic_name": "MET", "brand_name": None},
        ]
        lk = self._linker([], drugs)
        assert lk.link("Another oral GLP-1 wins FDA approval") is None
        assert lk.link("FDA approves new blood pressure medication") is None
        assert lk.link("active control arm enrolled patients") is None
        assert lk.link("the intervention reduced events") is None
        assert lk.link("Mitapivat Met its primary endpoint") is None

    def test_generic_word_company_rows_excluded(self):
        companies = [
            {"id": "c1", "name": "MSN"},
            {"id": "c2", "name": "center"},
            {"id": "c3", "name": "LEADING"},
            {"id": "c4", "name": "Response Pharmaceuticals"},
            {"id": "c5", "name": "SWOG Cancer Research Network"},
        ]
        lk = self._linker(companies, [])
        assert lk.link("Moderna covid-flu vaccine poised for approval - MSN") is None
        assert lk.link("how to strengthen the center of the supply chain") is None
        assert lk.link("a leading european generics maker expands") is None
        assert lk.link("strong patient response observed in the trial") is None
        assert lk.link("results from the SWOG cancer research network") is None

    def test_real_word_like_company_names_still_resolve(self):
        # The hardening must NOT kill genuine (if word-ish) company names.
        companies = [{"id": "c-jazz", "name": "Jazz Pharmaceuticals"},
                     {"id": "c-incyte", "name": "Incyte"}]
        lk = self._linker(companies, [])
        assert (lk.link("Jazz and PharmaMar lung cancer drug update") or
                None) and lk.link("Jazz and PharmaMar lung cancer drug update").entity_id == "c-jazz"
        assert lk.link("Incyte highlights new Phase 3 data").entity_id == "c-incyte"


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

    def test_excludes_hospital_study_group_agency_companies(self):
        lk = _linker()
        # keyword-excluded orgs never resolve, even by full name
        assert lk.link("results from the TIMI Study Group") is None
        assert lk.link("4th Military Clinical Hospital enrolled patients") is None
        assert lk.link("National Institutes of Health Clinical Center") is None

    def test_generic_tokens_not_aliases(self):
        # generic industry words must not match a polluted company name
        lk = _linker()
        assert lk.link("a new drug was approved today") is None      # 'drug' ≠ Harvard Drug Group
        assert lk.link("the group reported strong data") is None     # 'group' ≠ any company

    def test_headline_fragment_company_names_excluded(self):
        # companies table is polluted with headline fragments — must be dropped
        db = MagicMock()
        frag = [{"id": "co-junk", "name": "Pfizer's Upjohn has merged with Mylan to form Viatris"}]
        db.fetch_all = MagicMock(side_effect=lambda sql, p=None: frag if "companies" in sql.lower() else [])
        lk = EntityLinker(db).load()
        assert lk.link("Pfizer's Upjohn has merged with Mylan to form Viatris") is None

    def test_excludes_non_drug_stoplist(self):
        # "weight loss" is a data-error drug row — must not resolve as a drug
        r = _linker().link("significant weight loss observed in the cohort")
        assert r is None
