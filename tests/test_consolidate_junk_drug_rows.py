"""Tests for scripts/consolidate_junk_drug_rows.py — junk/dup drug-row consolidation.

Loop 3 of the data-quality push. The drugs spine accumulates entity-extraction
garbage rows — sentence fragments ("initiation of tirzepatide"), dose-arms
("Tirzepatide Dose 1"), ambiguous disjunctions ("semaglutide or tirzepatide"),
and incompletely-merged dups (status='merged' that still own trials/links). These
pollute resolution and orphan evidence. This verifies:

  * the extended ``_should_exclude`` patterns catch the fragment shapes that
    previously slipped through (without flagging real drug names), and
  * the pure ``classify`` decision: ABSORB (attributable → repoint to canonical),
    EXCLUDE (ambiguous → quarantine, reversible), SKIP (real combo / canonical /
    distinct drug).

TDD: pure-function tests, no DB.
"""

from __future__ import annotations

import pytest


# ── Extended junk-name patterns (single source of truth: clean_drug_names) ──

class TestExtendedExcludePatterns:
    def test_real_drug_names_not_excluded(self):
        from scripts.clean_drug_names import _should_exclude
        for ok in ("tirzepatide", "semaglutide", "dulaglutide", "retatrutide",
                   "metformin", "Mounjaro"):
            assert not _should_exclude(ok), f"{ok!r} wrongly excluded"

    def test_dose_arm_excluded(self):
        from scripts.clean_drug_names import _should_exclude
        assert _should_exclude("Tirzepatide Dose 1")
        assert _should_exclude("Semaglutide Dose 2")

    def test_prepositional_fragment_excluded(self):
        from scripts.clean_drug_names import _should_exclude
        assert _should_exclude("initiation of tirzepatide")
        assert _should_exclude("continuation of semaglutide")

    def test_adjunct_fragment_excluded(self):
        from scripts.clean_drug_names import _should_exclude
        assert _should_exclude("Tirzepatide as an adjunct to lifestyle intervention")

    def test_prehabilitation_fragment_excluded(self):
        from scripts.clean_drug_names import _should_exclude
        assert _should_exclude("tirzepatide prehabilitation")


# ── Pure classify decision ──

REAL_NAMES = {"tirzepatide", "semaglutide", "dulaglutide", "eloralintide"}
# normalized name -> canonical (richest active) row id
NORM_MAP = {"tirzepatide": "CANON", "semaglutide": "SEMA"}


def _verdict(name, this_id="X", norm=None):
    from scripts.consolidate_junk_drug_rows import classify, _norm
    return classify(name, REAL_NAMES, norm or _norm(name), NORM_MAP, this_id)


class TestClassify:
    def test_canonical_row_skipped(self):
        # the richest active row for its norm is the canonical — never touched
        assert _verdict("tirzepatide", this_id="CANON").action == "skip"

    def test_fragment_absorbed_into_canonical(self):
        from scripts.consolidate_junk_drug_rows import _norm
        for frag in ("initiation of tirzepatide",
                     "Tirzepatide Dose 1",
                     "Tirzepatide as an adjunct to lifestyle intervention",
                     "tirzepatide prehabilitation"):
            v = _verdict(frag, this_id="junk")
            assert v.action == "absorb", f"{frag!r} -> {v}"
            assert _norm(v.parent_name) == "tirzepatide"

    def test_ambiguous_disjunction_excluded_not_absorbed(self):
        # mentions two real drugs joined by 'or' — cannot attribute, quarantine
        v = _verdict("semaglutide or tirzepatide", this_id="junk")
        assert v.action == "exclude"

    def test_additive_combo_skipped(self):
        # a real combination product is a distinct entity, never merged into mono
        v = _verdict("Eloralintide and Tirzepatide", this_id="junk")
        assert v.action == "skip"

    def test_true_duplicate_absorbed(self):
        # plain dup name (incl. an incompletely-merged row) -> complete the merge
        assert _verdict("Tirzepatide", this_id="dup").action == "absorb"
        assert _verdict("Tirzepatide (Mounjaro)", this_id="dup2").action == "absorb"

    def test_distinct_drug_kept(self):
        # a real drug with no canonical dup is left alone
        assert _verdict("dulaglutide", this_id="dula").action == "skip"

    def test_no_embedded_real_drug_kept(self):
        # junk-shaped but unattributable & not a known dup -> skip (don't guess)
        v = _verdict("Tirzepatide Dose 1", this_id="j",
                     norm="tirzepatide dose 1")
        # still absorbable because exactly one real drug ('tirzepatide') embedded
        assert v.action == "absorb"


class TestVocabPollutionRobustness:
    """The drug spine itself contains un-excluded junk rows that pollute the
    'real drug' vocabulary (a row literally named 'intervention' with 98 links,
    and the ambiguous row matching itself). The classifier must not be fooled."""

    def test_generic_term_not_counted_as_second_drug(self):
        from scripts.consolidate_junk_drug_rows import classify, _norm
        polluted = {"tirzepatide", "semaglutide", "intervention"}
        # 'intervention' is in the vocab but must not create phantom ambiguity:
        # the fragment still resolves to exactly one real drug -> ABSORB.
        v = classify("Tirzepatide as an adjunct to lifestyle intervention",
                     polluted, _norm("Tirzepatide as an adjunct to lifestyle intervention"),
                     {"tirzepatide": "CANON"}, "junk")
        assert v.action == "absorb"
        assert _norm(v.parent_name) == "tirzepatide"

    def test_ambiguous_row_matching_itself_still_excluded(self):
        from scripts.consolidate_junk_drug_rows import classify, _norm
        name = "semaglutide or tirzepatide"
        # the row is active+non-junk so it's both in the vocab AND registered as
        # its own canonical; it must still be EXCLUDED, not skipped.
        polluted = {"tirzepatide", "semaglutide", name.lower()}
        v = classify(name, polluted, _norm(name),
                     {_norm(name): "SELF", "tirzepatide": "CANON"}, "SELF")
        assert v.action == "exclude"
