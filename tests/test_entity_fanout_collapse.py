"""L0b — entity fan-out collapse in the understand stage.

TDD: written BEFORE the implementation.

Root cause: `keyword_index.match("semaglutide")` returns every CTX section whose
name contains the token — DRUG-SEMAGLUTIDE, DRUG-SEMAGLUTIDE-INJECTION,
DRUG-SEMAGLUTIDE-PEN, DRUG-SEMAGLUTIDE-ORAL, dose/combo variants — so
`understand()` emits 50+ near-duplicate detected entities. `retrieve()` then
fans out per entity (keyword.match + entity_graph.neighbors each), PLAN resolves
each, and synthesis is fed a wall of noise → ~147s/query.

Fix: collapse configuration fragments of the same drug to the canonical base
BEFORE retrieve hydrates them. A fragment is an entity that is a word-prefix
extension of another detected (shorter) base entity. Distinct drugs and entities
named explicitly in a compare are preserved.

Run: pytest tests/test_entity_fanout_collapse.py -v
"""

from __future__ import annotations

import pytest

from services.ctx_pipeline import _collapse_entity_fragments


# ── 1. Pure collapse helper ──

class TestCollapseEntityFragments:
    def test_collapses_config_fragments_to_canonical_base(self):
        # The exact disease from the live probe: formulation/dose configurations
        # of one molecule collapse to the canonical base.
        fragments = [
            "semaglutide",
            "semaglutide injection",
            "semaglutide pen",
            "semaglutide oral",
            "semaglutide 1 mg dose",
            "semaglutide 2 mg",
        ]
        out = _collapse_entity_fragments(fragments)
        assert out == ["semaglutide"]

    def test_does_not_collapse_mono_into_combination(self):
        # Rubric hard-fail `mono_product_collapsed_into_combination`: a combo
        # product (CagriSema) is a DISTINCT entity, not a config of the mono.
        # The "/" is not a word boundary, so it survives — by design.
        out = _collapse_entity_fragments(
            ["semaglutide", "semaglutide injection", "semaglutide/cagrilintide"]
        )
        assert out == ["semaglutide", "semaglutide/cagrilintide"]

    def test_preserves_distinct_drugs(self):
        out = _collapse_entity_fragments(["semaglutide", "tirzepatide"])
        assert out == ["semaglutide", "tirzepatide"]

    def test_collapses_fragments_but_keeps_other_distinct_base(self):
        out = _collapse_entity_fragments(
            ["semaglutide", "semaglutide injection", "tirzepatide", "tirzepatide pen"]
        )
        assert out == ["semaglutide", "tirzepatide"]

    def test_dedups_exact_duplicates(self):
        out = _collapse_entity_fragments(["metformin", "metformin", "metformin"])
        assert out == ["metformin"]

    def test_preserves_original_order(self):
        out = _collapse_entity_fragments(
            ["tirzepatide", "semaglutide", "semaglutide pen"]
        )
        assert out == ["tirzepatide", "semaglutide"]

    def test_no_base_present_keeps_fragments(self):
        # If the canonical base itself was never matched, do NOT invent it and do
        # NOT over-collapse two configs that don't word-prefix each other.
        out = _collapse_entity_fragments(["semaglutide injection", "semaglutide pen"])
        assert out == ["semaglutide injection", "semaglutide pen"]

    def test_does_not_collapse_on_mere_substring(self):
        # "heart failure" must not collapse into "heart" unless "heart" is a real
        # detected base AND it is a word-prefix (it is here) — but two unrelated
        # multiword terms sharing no word-prefix base survive.
        out = _collapse_entity_fragments(["heart failure", "kidney disease"])
        assert out == ["heart failure", "kidney disease"]

    def test_word_boundary_not_raw_prefix(self):
        # "semaglutidexyz" is NOT a fragment of "semaglutide" (no space boundary).
        out = _collapse_entity_fragments(["semaglutide", "semaglutidexyz"])
        assert out == ["semaglutide", "semaglutidexyz"]

    def test_caps_runaway_distinct_entities(self):
        # A broad term can match many DISTINCT drugs; bound the list so retrieve
        # never fans out unboundedly. Cap is generous (>= any real compare).
        many = [f"drug{i}" for i in range(40)]
        out = _collapse_entity_fragments(many, max_entities=12)
        assert len(out) == 12
        assert out == many[:12]

    def test_empty(self):
        assert _collapse_entity_fragments([]) == []


# ── 2. understand() integration: fan-out is collapsed before retrieve ──

class _FanoutIndex:
    """Keyword index stub reproducing the REAL prod fan-out for "semaglutide"
    (31 sections; molecule position varies; combos present)."""

    def match(self, query: str):
        if "semaglutide" in query.lower():
            return [
                "ENTITY-DRUG-SEMAGLUTIDE",                       # canonical base
                "ENTITY-DRUG-ORAL-SEMAGLUTIDE",                  # config (molecule last)
                "ENTITY-DRUG-INJECTABLE-SEMAGLUTIDE",           # config
                "ENTITY-DRUG-SEMAGLUTIDE-(1-MG-DOSE)",          # config (molecule first)
                "ENTITY-DRUG-GRADUAL-DOSE-REDUCTION-OF-SEMAGLUTIDE",
                "ENTITY-DRUG-NEW-USE-OF-ORAL-SEMAGLUTIDE",
                "ENTITY-DRUG-CAGRILINTIDE-AND-SEMAGLUTIDE",     # COMBO — keep distinct
                "ENTITY-DRUG-METFORMIN-WITH-SEMAGLUTIDE",       # COMBO — keep distinct
                "ENTITY-DRUG-LIRAGLUTIDE-/-SEMAGLUTIDE",        # COMBO — keep distinct
            ]
        return []


@pytest.fixture
def fanout_pipeline():
    from services.ctx_pipeline import CTXQueryPipeline
    # Bare pipeline + injected fan-out index (no packed corpus needed here).
    pipe = CTXQueryPipeline.__new__(CTXQueryPipeline)
    pipe.keyword_index = _FanoutIndex()
    return pipe


def test_understand_collapses_fanout(fanout_pipeline):
    plan = fanout_pipeline.understand("Tell me about semaglutide")
    ents = plan.entities_detected
    # The 6 mono configurations collapse to the single canonical base...
    assert "drug semaglutide" in ents
    assert "drug oral semaglutide" not in ents
    assert "drug injectable semaglutide" not in ents
    assert not any("dose" in e for e in ents)
    # ...but the 3 combos are preserved as distinct entities (mono≠combo).
    assert "drug cagrilintide and semaglutide" in ents
    assert "drug metformin with semaglutide" in ents
    # Net: 1 canonical + 3 combos = 4, down from 9 (and 31 on real prod).
    assert len(ents) == 4
    assert plan.intent == "dossier"
