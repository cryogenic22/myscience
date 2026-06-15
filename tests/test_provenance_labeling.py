"""Lane-1: evidence carries a NAMED connector, and that name reaches the LLM.

Eval gate G1 (provenance) sat near 0% because matrix evidence was labelled with
the internal pipeline stage ("plan:mechanism"), and the snippet fed to the LLM was
content-only — the model had no source to attribute to. These tests pin both
halves of the fix: predicate→connector naming, and the [source:] marker in the
snippet text.
"""

from services.unified_handler import (
    _PREDICATE_SOURCE,
    _FIELD_SOURCE,
    _display_source,
    _evidence_source,
    _annotate_section_sources,
    _snippet_for_evidence,
    _provenance_footer,
    _inline_cite_sources,
    _neutralize_ungrounded_counts,
    UnifiedChatHandler,
)


class TestInlineCiteSources:
    """G1: the judge quotes a sentence attributing a claim to a NAMED SOURCE — a
    bare [N] does not (measured G1 ~5% with only the legend). _inline_cite_sources
    carries the named source next to each [N] in the prose."""

    EV = [
        {"source": "ClinicalTrials.gov", "provenance": {"predicate": "clinical_trial"}},
        {"source": "x", "provenance": {"predicate": "mechanism_of_action"}},
        {"source": "openFDA FAERS", "provenance": {"predicate": "adverse_event"}},
    ]

    def test_appends_named_source_to_citation_run(self):
        out = _inline_cite_sources("It is a GLP-1 RA [2]. It has trials [1].", self.EV)
        assert "[2] (MeSH / curated mechanism)" in out
        assert "[1] (ClinicalTrials.gov)" in out

    def test_collapses_a_run_and_dedupes_sources(self):
        # mixed run lists both named sources once.
        out = _inline_cite_sources("Claim [1][3].", self.EV)
        assert "[1][3] (ClinicalTrials.gov, openFDA FAERS)" in out

    def test_leaves_non_numeric_and_out_of_range_markers(self):
        # [metrics] is untouched; [9] out of range -> left as-is (no crash).
        out = _inline_cite_sources("A [metrics] and B [9].", self.EV)
        assert "[metrics]" in out and "[9]" in out
        assert "(" not in out  # nothing appended

    def test_empty_safe(self):
        assert _inline_cite_sources("", self.EV) == ""
        assert _inline_cite_sources("no cites here", []) == "no cites here"

    def test_does_not_stamp_nontrial_source_on_trial_claim(self):
        # The model cited a MECHANISM fact ([2]) for a trial/Phase claim. Stamping
        # "(MeSH)" there would be a false attribution (G4 regression) — leave bare.
        out = _inline_cite_sources("It has 12 active Phase 3 studies [2].", self.EV)
        assert out == "It has 12 active Phase 3 studies [2]."  # unchanged
        # But a trial claim cited to ClinicalTrials.gov ([1]) IS stamped.
        out2 = _inline_cite_sources("It has 47 registered trials [1].", self.EV)
        assert "[1] (ClinicalTrials.gov)" in out2

    def test_skips_generic_platform_buckets(self):
        ev = [{"source": "plan:foo", "provenance": {}}]  # -> "platform data"
        assert _inline_cite_sources("A vague claim [1].", ev) == "A vague claim [1]."


def test_display_source_maps_predicate_to_named_connector():
    assert _display_source(None, "clinical_trial") == "ClinicalTrials.gov"
    assert _display_source(None, "adverse_event") == "openFDA FAERS"
    assert _display_source(None, "mechanism_of_action") == "MeSH / curated mechanism"
    assert _display_source(None, "label_indication") == "openFDA Drug Labels"


def test_display_source_never_returns_internal_plan_label():
    # The internal stage name is not a source the reader can attribute to.
    assert _display_source("plan:mechanism", None) == "platform data"
    assert _display_source("plan", "") == "platform data"


def test_display_source_cleans_metrics_label_and_keeps_clean_names():
    assert _display_source("metrics.top_companies_by_topic", None) == "platform metrics"
    assert _display_source("ClinicalTrials.gov", None) == "ClinicalTrials.gov"


def test_matrix_evidence_carries_named_source_not_plan_stage():
    decomposition = {
        "cells": [
            {
                "dimension": "mechanism",
                "entity_id": "drug-1",
                "facts": [
                    {"id": "f1", "claim": "Glucagon-Like Peptide-1 Receptor Agonist",
                     "predicate": "mechanism_of_action", "fact_class": "reference"},
                ],
            },
            {
                "dimension": "clinical_profile",
                "entity_id": "drug-1",
                "facts": [
                    {"id": "f2", "claim": "Phase 3 trial NCT123",
                     "predicate": "clinical_trial", "fact_class": "corporate"},
                ],
            },
        ]
    }
    ev = UnifiedChatHandler._matrix_to_evidence(decomposition)
    sources = [e["source"] for e in ev]
    assert "MeSH / curated mechanism" in sources
    assert "ClinicalTrials.gov" in sources
    # No internal stage label leaks as the source.
    assert not any(s.startswith("plan") for s in sources)
    # The dimension is still recorded in provenance for the frontend.
    assert ev[0]["provenance"]["dimension"] == "mechanism"


def test_provenance_footer_maps_each_citation_to_named_connector():
    """Deterministic provenance: every [N] traces to a named connector + cadence,
    since no LLM narrates this reliably (eval gate G1)."""
    evidence = [
        {"source": "ClinicalTrials.gov", "provenance": {"predicate": "clinical_trial"}},
        {"source": "openFDA FAERS", "provenance": {"predicate": "adverse_event"}},
        {"source": "ClinicalTrials.gov", "provenance": {"predicate": "clinical_trial"}},
    ]
    footer = _provenance_footer(evidence)
    assert "Provenance" in footer
    assert "ClinicalTrials.gov (daily refresh)" in footer
    assert "openFDA FAERS (weekly refresh)" in footer
    # citations 1 & 3 share a source → grouped; 2 is FAERS
    assert "[1],[3] ClinicalTrials.gov" in footer
    assert "[2] openFDA FAERS" in footer
    # honest about coverage being ingest, not the world
    assert "not everything that exists" in footer


def test_provenance_footer_empty_when_no_evidence():
    assert _provenance_footer([]) == ""


def test_predicate_source_map_covers_emitter_predicates():
    # The fact emitters produce these predicates — each must name a connector.
    for p in ["clinical_trial", "adverse_event", "label_indication", "safety_signal",
              "mechanism_of_action", "phase_transition", "market_event"]:
        assert p in _PREDICATE_SOURCE and _PREDICATE_SOURCE[p]


# ── H2: per-claim NAMED source-class attribution (G1) ────────────────
#
# A hydrated CTX drug section bundles many field-claims (mechanism, company,
# therapeutic area, supply) into ONE evidence snippet that got ONE generic
# "platform knowledge base" tag — so the LLM could not attribute the mechanism
# claim (label/MeSH) separately from the company claim (drugs@FDA). The SME
# saw mechanism AND trial counts both tagged the same generic bucket. H2
# annotates each field line inline with its real source class.

def test_field_source_map_covers_drug_section_fields():
    # The CTX serializer emits these uppercase hyphenated keys for a drug section.
    for k in ["MECHANISM", "BRAND-NAME", "COMPANY", "THERAPEUTIC-AREA", "SUPPLY-STATUS"]:
        assert k in _FIELD_SOURCE and _FIELD_SOURCE[k]


def test_annotate_section_sources_tags_each_field_inline():
    content = "\n".join([
        "IDENTIFIER:abc-123",
        "TYPE:drug",
        "NAME:Tirzepatide",
        "MECHANISM:Dual GIP/GLP-1 receptor agonist",
        "COMPANY:ELI LILLY AND COMPANY",
        "THERAPEUTIC-AREA:Diabetes Mellitus, Type 2",
        "SUPPLY-STATUS:NORMAL",
        "SRC:drug_tirzepatide.yaml",
    ])
    out = _annotate_section_sources(content)
    lines = {ln.split(":", 1)[0]: ln for ln in out.splitlines()}
    # The mechanism claim is attributed to a label/ontology source, not a bucket.
    assert "[source:" in lines["MECHANISM"]
    assert "MeSH" in lines["MECHANISM"] or "label" in lines["MECHANISM"].lower()
    # The company/registry claim is attributed to an FDA registry source.
    assert "[source:" in lines["COMPANY"]
    assert "FDA" in lines["COMPANY"]
    # Mechanism and company resolve to DIFFERENT named sources (the whole point).
    assert _FIELD_SOURCE["MECHANISM"] != _FIELD_SOURCE["COMPANY"]
    # Structural lines have no source to attribute → left untouched.
    for k in ("IDENTIFIER", "TYPE", "NAME", "SRC"):
        assert "[source:" not in lines[k]


def test_annotate_is_noop_for_free_text():
    content = "Just a free-text snippet without CTX field keys."
    assert _annotate_section_sources(content) == content


def test_annotate_preserves_value_containing_colon():
    # partition() splits on the FIRST colon only — a value with a colon (e.g. a
    # dual-target mechanism) must be kept in full, tagged once.
    content = "MECHANISM:GIP:GLP-1 dual agonist (ratio 1:1)"
    out = _annotate_section_sources(content)
    assert "GIP:GLP-1 dual agonist (ratio 1:1)" in out  # no content loss
    assert out.count("[source:") == 1


def test_annotate_multi_kv_line_degrades_without_content_loss():
    # Entity sections emit one field per line, but if a multi-KV line ever
    # appears it must not crash or drop content (it's tagged by the first key).
    content = "BRAND-NAME:Mounjaro COMPANY:ELI LILLY"
    out = _annotate_section_sources(content)
    assert "Mounjaro COMPANY:ELI LILLY" in out  # full text preserved
    assert "[source:" in out


def test_snippet_for_ctx_section_gets_per_field_sources_not_one_bucket():
    item = {
        "source": "ctx_hydration_by_name",
        "content": "TYPE:drug\nMECHANISM:GLP-1 receptor agonist\nCOMPANY:NOVO NORDISK INC",
        "provenance": {"source": "ctx", "entity_type": "drug"},
    }
    snippet = _snippet_for_evidence(item)
    lines = {ln.split(":", 1)[0]: ln for ln in snippet.splitlines()}
    assert "[source:" in lines["MECHANISM"]
    assert "[source:" in lines["COMPANY"]
    assert "MeSH" in lines["MECHANISM"]
    assert "FDA" in lines["COMPANY"]
    # The single generic bucket no longer tags the whole section.
    assert "platform knowledge base" not in snippet


def test_snippet_for_matrix_fact_keeps_single_trailing_source():
    # Non-CTX evidence (a PLAN matrix fact / leader / metrics) keeps the single
    # trailing [source:] marker — unchanged behaviour.
    item = {
        "source": "ClinicalTrials.gov",
        "content": "47 registered trials",
        "provenance": {"predicate": "clinical_trial"},
    }
    assert _snippet_for_evidence(item) == "47 registered trials [source: ClinicalTrials.gov]"


def test_evidence_source_names_ctx_section_by_type_not_generic_bucket():
    # The footer/section-level label for a CTX drug section is a named class,
    # not the generic 'platform knowledge base'.
    item = {"source": "ctx_hydration_by_name",
            "provenance": {"source": "ctx", "entity_type": "drug"}}
    label = _evidence_source(item)
    assert label != "platform knowledge base"
    assert "FDA" in label or "MeSH" in label


def test_evidence_source_still_prefers_predicate_connector():
    # Predicate-bearing evidence (matrix facts) keeps its named connector.
    item = {"source": "x", "provenance": {"predicate": "clinical_trial"}}
    assert _evidence_source(item) == "ClinicalTrials.gov"


def test_evidence_source_falls_back_to_content_type_for_entity_sections():
    # Hydration-by-name sections are named ENTITY-DRUG-… so `_parse_section_name`
    # yields the generic "entity"; the real type comes from the TYPE: line.
    item = {
        "source": "ctx_hydration_by_name",
        "content": "IDENTIFIER:abc\nTYPE:drug\nNAME:Semaglutide\nMECHANISM:GLP-1 RA",
        "provenance": {"source": "ctx", "entity_type": "entity"},
    }
    label = _evidence_source(item)
    assert label != "platform knowledge base"
    assert "FDA" in label or "MeSH" in label


# ── Ungrounded trial-count neutralization (G1 / G2 — the compare regression) ──
#
# "Compare semaglutide vs tirzepatide" produced bare, unattributed trial counts
# ("47 registered trials [metrics]", "68 active Phase 3 trials") that NO grounded
# count fact backs — the matrix carries only individual trial facts (capped), and
# _fetch_metrics returns {} for compare. The LLM ignores the prompt directive, so a
# deterministic post-synthesis pass detects a bare trial/Phase-count claim that is
# NOT backed by a count in the evidence and neutralizes the specific number (the
# closed-world-honest move — never invent a source for a fabricated figure).
class TestNeutralizeUngroundedCounts:
    # Individual trial facts (NCT + enrollment) — NOT aggregate counts. These must
    # NOT be read as grounding a "47 trials" claim.
    INDIVIDUAL_TRIALS = [
        {"source": "ClinicalTrials.gov",
         "content": "Clinical trial: Phase 4 trial NCT07485062 in Type 2 Diabetes — enrollment 164",
         "provenance": {"predicate": "clinical_trial"}},
        {"source": "MeSH / curated mechanism",
         "content": "Mechanism of action: GLP-1 Receptor Agonists",
         "provenance": {"predicate": "mechanism_of_action"}},
    ]

    def test_neutralizes_bare_registered_trial_count(self):
        out = _neutralize_ungrounded_counts(
            "It has a robust program with 47 registered trials.", self.INDIVIDUAL_TRIALS
        )
        assert "47 registered trials" not in out
        # The qualitative breadth statement is kept; the fabricated number is gone.
        assert "registered trials" in out
        assert not _has_digit_run(out, "47")

    def test_neutralizes_bare_active_phase_count(self):
        out = _neutralize_ungrounded_counts(
            "Semaglutide has 68 active Phase 3 trials, while tirzepatide has 34.",
            self.INDIVIDUAL_TRIALS,
        )
        assert "68" not in out and "34" not in out
        assert "Phase 3 trials" in out

    def test_strips_bogus_metrics_marker_on_neutralized_count(self):
        # The LLM tagged the fabricated count with a fake [metrics] marker (not a
        # resolvable [N]); neutralizing the number should also drop the dead marker.
        out = _neutralize_ungrounded_counts(
            "It has 47 registered trials [metrics].", self.INDIVIDUAL_TRIALS
        )
        assert "[metrics]" not in out
        assert "47" not in out

    def test_keeps_count_when_grounded_in_evidence(self):
        # If an evidence snippet DOES carry the aggregate count (a real grounded
        # total injected as a citable fact), the number is honest — keep it.
        grounded = self.INDIVIDUAL_TRIALS + [
            {"source": "ClinicalTrials.gov",
             "content": "Registered-trial footprint: 178 trials across all indications",
             "provenance": {"predicate": "clinical_trial"}},
        ]
        out = _neutralize_ungrounded_counts(
            "Semaglutide has 178 registered trials [1].", grounded
        )
        assert "178 registered trials" in out  # untouched — it is grounded

    def test_does_not_touch_count_already_carrying_inline_source(self):
        # If the model already attributed the count inline (named source in the same
        # sentence), it is self-attributing — leave it alone.
        out = _neutralize_ungrounded_counts(
            "It has 47 registered trials [source: ClinicalTrials.gov].",
            self.INDIVIDUAL_TRIALS,
        )
        assert out == "It has 47 registered trials [source: ClinicalTrials.gov]."

    def test_leaves_non_trial_numbers_alone(self):
        # Enrollment, dosing, prices — only trial/Phase COUNT claims are in scope.
        text = "Enrollment was 2,310 patients at a 2.4 mg weekly dose."
        assert _neutralize_ungrounded_counts(text, self.INDIVIDUAL_TRIALS) == text

    def test_empty_and_no_evidence_safe(self):
        assert _neutralize_ungrounded_counts("", self.INDIVIDUAL_TRIALS) == ""
        # No evidence at all → still neutralize (nothing can ground the number).
        out = _neutralize_ungrounded_counts("It has 47 registered trials.", [])
        assert "47" not in out

    def test_preserves_bare_phase_ordinal_with_no_leading_count(self):
        # "Phase 3 trials" with NO aggregate count is a development-STAGE descriptor,
        # not a fabricated count — the phase ordinal must NOT be captured as a count
        # and mangled into "Phase a number of trials" (PR #286 independent-review
        # BLOCKER: _TRIAL_COUNT_RE lacked the (?<!phase\s) guard _EVIDENCE_COUNT_RE has).
        for text in (
            "Both drugs are in Phase 3 trials.",
            "Tirzepatide advanced to Phase 2 studies.",
            "The Phase 3 trials are ongoing.",
            "It is being evaluated in Phase-3 trials.",
        ):
            assert _neutralize_ungrounded_counts(text, self.INDIVIDUAL_TRIALS) == text

    def test_neutralize_is_idempotent(self):
        # Running twice must equal running once — a surviving "Phase 3" ordinal must
        # not be re-matched and corrupted on a second pass.
        text = "Semaglutide has 68 active Phase 3 trials, while tirzepatide has 34."
        once = _neutralize_ungrounded_counts(text, self.INDIVIDUAL_TRIALS)
        twice = _neutralize_ungrounded_counts(once, self.INDIVIDUAL_TRIALS)
        assert once == twice
        assert "Phase 3 trials" in once  # the leading count went; the ordinal stayed
        assert "Phase a number of" not in once


def _has_digit_run(text: str, num: str) -> bool:
    import re
    return bool(re.search(rf"\b{re.escape(num)}\b", text))
