"""SPEC_016 Track 1 Phase 1b — intent-specific planning prompts.

Phase 1a added intent_hint to QueryAgentState and wired _classify to honour it.
Phase 1b uses the hint to bias the LLM *planner* (plan_sql / plan_hybrid) so
different intents pick different tool combinations:

  pipeline  → prefer mv_drug_pipeline_strength, filter by drug_id / TA
  landscape → prefer mv_competitive_landscape, group by mechanism × TA
  portfolio → aggregate by company_id
  dossier   → LEFT JOIN core facts scoped to one entity
  compare   → parallel metrics for multiple entities

Without hint injection, the planner produces generic SQL that often misses
MVs and defaults to expensive full-table scans. The hint is injected as an
extra line in the planner's system prompt.

All tests must FAIL before implementation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ────────────────────────────────────────────────────────────────────
# Mapping exists for each legacy intent
# ────────────────────────────────────────────────────────────────────

def test_intent_planning_hints_map_exists():
    from services.agent.graphs.query_graph import _INTENT_PLANNING_HINTS
    assert isinstance(_INTENT_PLANNING_HINTS, dict)


@pytest.mark.parametrize("intent", [
    "pipeline", "landscape", "portfolio",
    "dossier", "compare", "deep_research",
])
def test_each_structured_intent_has_planning_hint(intent):
    """Every legacy intent (except 'general', which is free-form) gets guidance."""
    from services.agent.graphs.query_graph import _INTENT_PLANNING_HINTS
    assert intent in _INTENT_PLANNING_HINTS, (
        f"Intent '{intent}' should have a planning hint in _INTENT_PLANNING_HINTS"
    )
    hint = _INTENT_PLANNING_HINTS[intent]
    assert isinstance(hint, str) and len(hint) > 10, (
        f"Planning hint for '{intent}' must be a substantive string; got {hint!r}"
    )


def test_planning_hint_for_pipeline_mentions_pipeline_strength_mv():
    """The pipeline hint should steer the planner toward mv_drug_pipeline_strength."""
    from services.agent.graphs.query_graph import _INTENT_PLANNING_HINTS
    hint = _INTENT_PLANNING_HINTS["pipeline"].lower()
    assert "pipeline_strength" in hint or "mv_drug_pipeline" in hint


def test_planning_hint_for_landscape_mentions_competitive_mv():
    from services.agent.graphs.query_graph import _INTENT_PLANNING_HINTS
    hint = _INTENT_PLANNING_HINTS["landscape"].lower()
    assert "competitive" in hint or "mv_competitive_landscape" in hint


# ────────────────────────────────────────────────────────────────────
# _plan_sql injects the hint into the system prompt
# ────────────────────────────────────────────────────────────────────

def _make_state(question: str, intent_hint: str = "") -> dict:
    return {
        "messages": [],
        "question": question,
        "conversation_context": "",
        "intent": "structured_query",
        "intent_hint": intent_hint,
        "plan": {},
        "tool_results": {},
        "presentation": {},
        "table_data": None,
        "visualizations": [],
        "narrative": "",
        "error": None,
    }


def _capture_system_prompt(llm_mock):
    """Pull the last SystemMessage content from llm.invoke calls."""
    if not llm_mock.invoke.call_args_list:
        return ""
    call = llm_mock.invoke.call_args
    messages = call.args[0] if call.args else call.kwargs.get("messages", [])
    for m in messages:
        if hasattr(m, "content") and hasattr(m, "type"):
            if getattr(m, "type", "") == "system":
                return m.content
    # Fallback: first message assumed to be system
    return getattr(messages[0], "content", "") if messages else ""


def test_plan_sql_injects_pipeline_hint_when_intent_hint_is_pipeline():
    """When state.intent_hint='pipeline', the SQL planner's system prompt
    must include pipeline-specific guidance."""
    from services.agent.graphs.query_graph import _plan_sql

    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content='{"sql": "SELECT 1", "params": [], "explanation": "x", "presentation_hint": "scalar"}')

    state = _make_state("Show pipeline for semaglutide", intent_hint="pipeline")
    _plan_sql(state, llm=llm, schema_text="drugs(id, generic_name)")

    sys_prompt = _capture_system_prompt(llm)
    low = sys_prompt.lower()
    assert "pipeline_strength" in low or "mv_drug_pipeline" in low, (
        f"plan_sql must inject pipeline-specific guidance when "
        f"intent_hint='pipeline'. System prompt: {sys_prompt[:500]!r}"
    )


def test_plan_sql_injects_landscape_hint_when_intent_hint_is_landscape():
    from services.agent.graphs.query_graph import _plan_sql

    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content='{"sql": "SELECT 1", "params": [], "explanation": "x", "presentation_hint": "bar"}')

    state = _make_state("Competitive landscape for GLP-1", intent_hint="landscape")
    _plan_sql(state, llm=llm, schema_text="drugs(id)")

    sys_prompt = _capture_system_prompt(llm).lower()
    assert "competitive" in sys_prompt or "mv_competitive_landscape" in sys_prompt, (
        f"plan_sql must inject landscape guidance; got {sys_prompt[:500]!r}"
    )


def test_plan_sql_no_hint_no_extra_guidance():
    """Backward compat: no intent_hint → planner prompt unchanged from baseline.
    Specifically, it should NOT contain the intent-specific markers."""
    from services.agent.graphs.query_graph import _plan_sql

    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content='{"sql": "SELECT 1", "params": [], "explanation": "x", "presentation_hint": "scalar"}')

    state = _make_state("How many drugs are there?", intent_hint="")
    _plan_sql(state, llm=llm, schema_text="drugs(id)")

    sys_prompt = _capture_system_prompt(llm)
    # Specifically, no intent-scoped markers
    assert "INTENT-SPECIFIC GUIDANCE" not in sys_prompt, (
        "Without intent_hint, no intent-specific guidance should be injected"
    )


def test_plan_sql_unknown_intent_hint_no_extra_guidance():
    """Defensive: unknown intent_hint values should not break the planner —
    just skip the hint injection."""
    from services.agent.graphs.query_graph import _plan_sql

    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content='{"sql": "SELECT 1", "params": [], "explanation": "x", "presentation_hint": "scalar"}')

    state = _make_state("x", intent_hint="xyznonexistent")
    _plan_sql(state, llm=llm, schema_text="drugs(id)")

    sys_prompt = _capture_system_prompt(llm)
    assert "INTENT-SPECIFIC GUIDANCE" not in sys_prompt
    # Must not crash — llm was called once with valid prompt
    assert llm.invoke.called


# ────────────────────────────────────────────────────────────────────
# _plan_hybrid also uses the hint
# ────────────────────────────────────────────────────────────────────

def test_plan_hybrid_injects_dossier_hint():
    """The hybrid planner (dossier/compare path) must also honour intent_hint."""
    from services.agent.graphs.query_graph import _plan_hybrid

    llm = MagicMock()
    llm.invoke.return_value = MagicMock(
        content='{"sql": "SELECT 1", "params": [], "rag_query": "x", "explanation": "x", "include_graph": true, "presentation_hint": "cards"}'
    )

    state = _make_state("Tell me about semaglutide", intent_hint="dossier")
    _plan_hybrid(state, llm=llm, schema_text="drugs(id)")

    sys_prompt = _capture_system_prompt(llm).lower()
    # Dossier hint should mention something like "dossier" / "profile" / "core facts"
    has_dossier_marker = any(kw in sys_prompt for kw in (
        "dossier", "profile", "core facts", "single entity", "entity-scoped",
    ))
    assert has_dossier_marker, (
        f"plan_hybrid must inject dossier guidance; got {sys_prompt[:500]!r}"
    )
