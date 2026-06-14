"""C1 (conservation floor) — clinical_trials → drug relink, pure/DB-free units.

The authoritative drug for a trial is what's in its `interventions` field, NOT its
title prose (a drug named in the title may be a comparator or background condition).
This tests the pure intervention-text parser + the junk-name exclusion that keeps the
linkage HIGH PRECISION — a false link is silent corruption, worse than a NULL.

Reuses the deterministic name-index matcher from scripts/relink_literature.py (anti-slop:
no duplicate matcher); these tests pin the new trial-specific parsing + the hardened
stop-list that drops polluted drug rows (literal `intervention` / `medication` /
`titration` / `no intervention` / `active control`) the prod probe surfaced.
"""
from __future__ import annotations

from scripts.relink_literature import build_name_index, compile_matcher, match_drug_in_text
from scripts.relink_trials import intervention_text


# ── intervention_text: strip ClinicalTrials.gov TYPE: prefixes, keep names ──

class TestInterventionText:
    def test_strips_type_prefixes_and_joins(self):
        raw = '{"BIOLOGICAL: Semaglutide","DRUG: Metformin"}'
        out = intervention_text(raw)
        assert "semaglutide" in out.lower()
        assert "metformin" in out.lower()
        assert "biological:" not in out.lower()  # prefix stripped

    def test_behavioral_device_contribute_non_drug_text_only(self):
        raw = '{"OTHER: Resistance exercise","BEHAVIORAL: Diet Counseling","DEVICE: pump"}'
        out = intervention_text(raw)
        # the (non-drug) descriptions survive but carry no drug name
        assert "resistance exercise" in out.lower()
        assert "other:" not in out.lower()

    def test_empty_and_none(self):
        assert intervention_text(None) == ""
        assert intervention_text("") == ""

    def test_untyped_item_kept(self):
        assert "aspirin" in intervention_text('{"aspirin"}').lower()


# ── junk-name exclusion (precision: never link to a polluted drug row) ──

_JUNK_NAMES = ["intervention", "medication", "titration", "no intervention",
               "active control", "rate control", "formulation 1"]


def _index(extra_rows):
    return build_name_index(extra_rows)


class TestJunkExclusion:
    def test_polluted_drug_rows_are_not_indexed(self):
        # Even though these exist as rows in the drugs table, they must never be
        # matchable — linking a behavioral trial to a drug named "intervention" is
        # silent corruption.
        rows = [{"drug_id": f"id{i}", "name": nm, "richness": 5}
                for i, nm in enumerate(_JUNK_NAMES)]
        idx = _index(rows)
        for nm in _JUNK_NAMES:
            assert nm not in idx, f"junk name {nm!r} must be stop-listed out of the index"

    def test_real_drug_still_indexed_and_matched(self):
        rows = [{"drug_id": "d1", "name": "semaglutide", "richness": 9},
                {"drug_id": "x", "name": "intervention", "richness": 99}]
        idx = _index(rows)
        assert "semaglutide" in idx
        matcher = compile_matcher(idx)
        # an OTHER-coded behavioral item that merely says "intervention" must NOT match
        assert match_drug_in_text("acupuncture lifestyle intervention", idx, matcher) is None
        # a real drug name in the interventions text DOES match
        hit = match_drug_in_text("semaglutide ; metformin", idx, matcher)
        assert hit is not None and hit.name == "semaglutide"
