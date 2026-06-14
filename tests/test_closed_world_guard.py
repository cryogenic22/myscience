"""Lane-1: the closed-world / calibration guard is shipped with every synthesis
prompt, and the compare prompt no longer instructs the count fallacy.

This pins the reasoning-layer fix for the semaglutide-vs-tirzepatide class
(eval gates G2 closed-world honesty, G3 no-count-fallacy). A future edit that
silently drops the guard, or re-adds "declare the winner from trial counts",
fails here — before it ever reaches the live model.
"""

import pytest

from services.llm import (
    SYSTEM_PROMPTS,
    _CLOSED_WORLD_PROTOCOL,
    _CITATION_PROTOCOL,
    _assemble_system_prompt,
    _get_system_prompt,
)


@pytest.mark.parametrize("intent", list(SYSTEM_PROMPTS.keys()) + ["unknown_intent"])
def test_every_prompt_carries_the_closed_world_guard(intent):
    sp = _get_system_prompt(intent)
    assert "CLOSED-WORLD & CALIBRATION PROTOCOL" in sp
    assert "Absence in the data is NOT evidence of absence in reality" in sp
    assert "Counts are not quality" in sp
    # citation protocol still present too (not regressed)
    assert "CITATION PROTOCOL" in sp


def test_table_format_hint_also_carries_guard():
    sp = _get_system_prompt("dossier", format_hint="table")
    assert "CLOSED-WORLD & CALIBRATION PROTOCOL" in sp


def test_assembler_is_the_shipped_text():
    # _get_system_prompt must equal the assembler over the selected base, so the
    # prompt-registry row (which uses the assembler) is 1:1 with what ships.
    assert _get_system_prompt("compare") == _assemble_system_prompt(SYSTEM_PROMPTS["compare"])
    assert _CITATION_PROTOCOL in _assemble_system_prompt(SYSTEM_PROMPTS["default"])
    assert _CLOSED_WORLD_PROTOCOL in _assemble_system_prompt(SYSTEM_PROMPTS["default"])


def test_compare_prompt_no_longer_instructs_count_fallacy():
    compare = SYSTEM_PROMPTS["compare"]
    # The removed instructions that actively produced the failure:
    assert "Bold the winner on each dimension" not in compare
    assert "which entity is stronger/weaker and why" not in compare
    # And the new guardrails are present:
    assert "does NOT mean X is the stronger or better drug" in compare
    assert "head-to-head" in compare.lower()
    assert "never flatten it" in compare  # mechanism difference is the headline


def test_guard_forbids_negative_inference_from_absence():
    g = _CLOSED_WORLD_PROTOCOL
    assert "FORBIDDEN" in g
    assert "no competitors" in g
    assert "Surface such gaps as explicit unknowns" in g


def test_guard_demands_per_claim_inline_source_attribution():
    # H2-prose (eval gate G1): the guard must require naming the source IN the
    # sentence, with worked examples, not just "cite [N]". The judge scores G1 on
    # a sentence that attributes a claim to a named source.
    g = _CLOSED_WORLD_PROTOCOL
    assert "INLINE in the prose" in g
    assert "IN THE SENTENCE ITSELF" in g
    assert "Per ClinicalTrials.gov" in g  # a worked attribution example
    assert "INCOMPLETE" in g               # a sentence with no named source fails


def test_computed_differentials_are_neutral_not_count_fallacy():
    """The system feeds COMPUTED DIFFERENTIALS to the LLM verbatim, so the framing
    here IS the count fallacy if it crowns a winner. Pin neutral, labelled output
    (eval gate G3) — the model can't avoid a fallacy its own input asserts."""
    from services.chat_handlers.formatting import compute_comparison_insights

    resolved = [{"entity_id": "a", "label": "semaglutide"}, {"entity_id": "b", "label": "tirzepatide"}]
    metrics = {
        "a": {"pipeline": {"pipeline_score": 341.0, "total_trials": 184, "p3_count": 59}},
        "b": {"pipeline": {"pipeline_score": 215.0, "total_trials": 114, "p3_count": 33}},
    }
    out = compute_comparison_insights(resolved, metrics)
    low = out.lower()
    # The removed count-fallacy framings must not return:
    assert "stronger pipeline score" not in low
    assert "leads in phase 3" not in low
    # Neutral, labelled framing must be present:
    assert "not a measure of efficacy or strength" in low
    assert "not superiority" in low
    assert "do not rank or declare a winner" in low
    # Numbers still carried (the LLM needs the real values):
    assert "184" in out and "114" in out and "59" in out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
