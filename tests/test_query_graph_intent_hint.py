"""SPEC_016 Track 1 Phase 1a — intent_hint in query_graph TDD.

Today the query_graph's _classify node uses regex pattern-counting + an
optional LLM fallback. Drug-specific queries like "Show pipeline for
semaglutide" hit zero structured_query patterns and default to
knowledge_search (RAG) — wrong tool for a structured pipeline question.

Phase 1a: add `intent_hint` field to QueryAgentState. When the chat route
already knows the intent (from regex detection or user explicit flag),
it can pass the hint through so _classify picks the right pathway.

Intent → classifier mapping:
  dossier, compare        → hybrid (entity facts + evidence)
  landscape, portfolio,
  pipeline                → structured_query (metrics / MV queries)
  general, deep_research  → hybrid (flexible; LLM plans the calls)
  structured_query,
  team_eval               → pass through (they already work)

All tests must FAIL before implementation.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ────────────────────────────────────────────────────────────────────
# Helpers — minimal mocks so _classify runs without deps
# ────────────────────────────────────────────────────────────────────

def _make_state(question: str = "x", intent_hint: str = "") -> dict:
    """Build a QueryAgentState dict (TypedDict is dict-compatible)."""
    return {
        "messages": [],
        "question": question,
        "conversation_context": "",
        "intent": "",
        "intent_hint": intent_hint,
        "plan": {},
        "tool_results": {},
        "presentation": {},
        "table_data": None,
        "visualizations": [],
        "narrative": "",
        "error": None,
    }


# ────────────────────────────────────────────────────────────────────
# Schema — state must carry intent_hint
# ────────────────────────────────────────────────────────────────────

def test_query_agent_state_has_intent_hint_field():
    """SPEC_016 Phase 1a: QueryAgentState must declare intent_hint."""
    from services.agent.graphs.query_graph import QueryAgentState
    annotations = getattr(QueryAgentState, "__annotations__", {})
    assert "intent_hint" in annotations, (
        "QueryAgentState must include intent_hint: str field so chat.py can "
        "pass the detected intent as a classifier bias"
    )


# ────────────────────────────────────────────────────────────────────
# _classify honours intent_hint for structured intents
# ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("hint", ["landscape", "portfolio", "pipeline"])
def test_classify_routes_structured_intents_to_structured_query(hint):
    """landscape / portfolio / pipeline → structured_query (MV / SQL path)."""
    from services.agent.graphs.query_graph import _classify
    state = _make_state(question="Show pipeline for semaglutide", intent_hint=hint)
    result = _classify(state, llm=None)
    assert result.get("intent") == "structured_query", (
        f"intent_hint={hint!r} should route to structured_query; "
        f"got {result.get('intent')!r}"
    )


@pytest.mark.parametrize("hint", ["dossier", "compare"])
def test_classify_routes_entity_intents_to_hybrid(hint):
    """dossier / compare → hybrid (SQL facts + RAG evidence)."""
    from services.agent.graphs.query_graph import _classify
    state = _make_state(question="Tell me about semaglutide", intent_hint=hint)
    result = _classify(state, llm=None)
    assert result.get("intent") == "hybrid", (
        f"intent_hint={hint!r} should route to hybrid; "
        f"got {result.get('intent')!r}"
    )


@pytest.mark.parametrize("hint", ["general", "deep_research"])
def test_classify_routes_flexible_intents_to_hybrid(hint):
    """general / deep_research → hybrid (planner decides tool mix)."""
    from services.agent.graphs.query_graph import _classify
    state = _make_state(question="What about semaglutide?", intent_hint=hint)
    result = _classify(state, llm=None)
    assert result.get("intent") == "hybrid", (
        f"intent_hint={hint!r} should route to hybrid; "
        f"got {result.get('intent')!r}"
    )


def test_classify_passes_through_already_classified_intents():
    """intent_hint='structured_query' → pass through.
    team_eval belongs to a separate graph (team_eval_graph) and should be
    dispatched by the chat router before reaching query_graph; not in
    _INTENT_HINT_MAP.
    """
    from services.agent.graphs.query_graph import _classify
    state = _make_state(question="x", intent_hint="structured_query")
    result = _classify(state, llm=None)
    assert result.get("intent") == "structured_query"


# ────────────────────────────────────────────────────────────────────
# Backward compatibility — no hint → existing regex/LLM path
# ────────────────────────────────────────────────────────────────────

def test_classify_ignores_empty_intent_hint_and_uses_existing_logic():
    """No intent_hint → existing regex pattern-counting kicks in.
    'How many Phase 3 trials does semaglutide have?' hits 2+ structural
    patterns today and classifies as structured_query."""
    from services.agent.graphs.query_graph import _classify
    state = _make_state(
        question="How many Phase 3 trials does semaglutide have?",
        intent_hint="",
    )
    result = _classify(state, llm=None)
    assert result.get("intent") == "structured_query"


def test_classify_ignores_empty_intent_hint_knowledge_search():
    """A narrative question without structural patterns + no hint →
    knowledge_search (existing behaviour)."""
    from services.agent.graphs.query_graph import _classify
    state = _make_state(
        question="What is the strategic outlook for GLP-1 drugs?",
        intent_hint="",
    )
    result = _classify(state, llm=None)
    # Without hint, this question has few structural signals → knowledge_search
    assert result.get("intent") in ("knowledge_search", "hybrid")


def test_classify_unknown_intent_hint_falls_through_to_existing_logic():
    """Unknown/bogus intent_hint values should not override — fall back
    to existing pattern-counting logic."""
    from services.agent.graphs.query_graph import _classify
    state = _make_state(
        question="How many Phase 3 trials does semaglutide have?",
        intent_hint="this-is-not-a-real-intent",
    )
    result = _classify(state, llm=None)
    # Should use the existing classification (structured_query for this query)
    assert result.get("intent") == "structured_query"


# ────────────────────────────────────────────────────────────────────
# Flip the xfail — smoke test should now pass after Phase 1a
# ────────────────────────────────────────────────────────────────────

def test_smoke_test_xfail_should_be_fixed_after_phase_1a():
    """The smoke test file had test_query_graph_intent_hint_not_yet_supported
    marked xfail. After Phase 1a, intent_hint IS supported — the xfail should
    either flip to passing or be removed."""
    from services.agent.graphs.query_graph import QueryAgentState
    annotations = getattr(QueryAgentState, "__annotations__", {})
    assert "intent_hint" in annotations, (
        "After Phase 1a the xfail in test_query_graph_smoke.py should no "
        "longer mark intent_hint as 'not yet supported'. Update that test."
    )
