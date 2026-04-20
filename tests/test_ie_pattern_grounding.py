"""SPEC_016 Track 2 Priority 1 — IE-pattern grounding TDD.

Three adoptions from intelligent_enterprise's proven CTX grounding pattern:
  1A. Sandwich grounding — tail reminder after corpus injection
  1B. Click-through entity citations — [name](/entity/{type}/{id}) markdown links
  1C. L3 directory always present — "Universe: N drugs, M companies..." summary

Per SPEC_017 reuse catalog. Source patterns in:
  intelligent_enterprise/app/api/chat/route.ts:148-153 (tail reminder)
  intelligent_enterprise/lib/ctx/catalog-context.ts (L3 index)

All tests must FAIL before implementation.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


# ────────────────────────────────────────────────────────────────────
# 1A. Sandwich grounding — tail reminder in CTX context
# ────────────────────────────────────────────────────────────────────

def test_build_context_block_appends_grounding_reminder():
    """SPEC_016 §1A: services/llm.py _build_context_block must append a
    tail reminder after corpus injection telling the LLM to only cite
    entities from the corpus above."""
    from services.llm import _build_context_block
    ctx = _build_context_block(
        question="what is semaglutide?",
        intent="general",
        entity_info={"drug": "semaglutide"},
        evidence_snippets=["Semaglutide reduces A1C."],
    )
    low = ctx.lower()
    # At least one of these phrases must appear in the tail reminder
    markers = [
        "before you respond",
        "only cite",
        "must appear",
        "use only",
        "do not invent",
    ]
    assert any(m in low for m in markers), (
        f"CTX context must include a tail grounding reminder. "
        f"Expected one of {markers} in the tail. "
        f"Got (last 500 chars): {ctx[-500:]!r}"
    )


def test_grounding_reminder_is_at_the_tail_not_the_head():
    """Sandwich pattern: the reminder must come AFTER the evidence/corpus,
    not before. LLMs are known to forget head instructions by the time they
    finish reading a long context."""
    from services.llm import _build_context_block
    ctx = _build_context_block(
        question="compare semaglutide and tirzepatide",
        intent="compare",
        evidence_snippets=[
            "Evidence A: semaglutide data",
            "Evidence B: tirzepatide data",
        ],
    )
    low = ctx.lower()
    # Find position of "evidence" markers + position of grounding reminder
    evidence_pos = low.find("evidence a")
    reminder_pos = max(
        low.find("before you respond"),
        low.find("only cite"),
        low.find("must appear"),
    )
    assert reminder_pos > 0, "grounding reminder must be present"
    assert reminder_pos > evidence_pos, (
        "grounding reminder must come AFTER the evidence/corpus (sandwich pattern), "
        f"not before. evidence_pos={evidence_pos}, reminder_pos={reminder_pos}"
    )


# ────────────────────────────────────────────────────────────────────
# 1B. Click-through entity citations
# ────────────────────────────────────────────────────────────────────

def test_system_prompt_instructs_click_through_format():
    """SPEC_016 §1B: the LLM system prompt must instruct entity references
    to use markdown links of form [name](/entity/{type}/{id})."""
    from services.llm import _get_system_prompt
    prompt = _get_system_prompt("dossier")
    low = prompt.lower()
    has_pattern_hint = (
        "/entity/" in prompt
        or "markdown link" in low
        or "clickable" in low
        or "link format" in low
    )
    assert has_pattern_hint, (
        "system prompt must instruct the LLM to use /entity/{type}/{id} "
        "markdown links for entity references. Got prompt tail: "
        f"{prompt[-400:]!r}"
    )


def test_validate_citations_counts_entity_links():
    """validate_citations should report how many entity-link citations
    appear alongside the existing [N] evidence-index count."""
    from services.llm import validate_citations
    narrative = (
        "Semaglutide [1] is a GLP-1 agonist. [Semaglutide](/entity/drug/uuid-sema) "
        "competes with [Tirzepatide](/entity/drug/uuid-tirz) in obesity [2]."
    )
    result = validate_citations(narrative, evidence_count=2)
    # Existing contract: returns dict with valid / stripped
    assert isinstance(result, dict)
    # New contract: entity_links count
    assert result.get("entity_links", 0) >= 2, (
        f"expected ≥2 entity-link citations; got {result.get('entity_links')}. "
        f"Result: {result!r}"
    )


def test_validate_citations_backward_compatible():
    """Existing callers pass evidence_count and expect narrative + valid +
    stripped keys. That contract must still work."""
    from services.llm import validate_citations
    narrative = "Semaglutide [1] is effective [2]."
    result = validate_citations(narrative, evidence_count=2)
    assert "narrative" in result
    assert "valid" in result
    assert "stripped" in result
    assert result["valid"] == 2


# ────────────────────────────────────────────────────────────────────
# 1C. L3 directory always in prompt
# ────────────────────────────────────────────────────────────────────

def test_get_l3_summary_helper_exists():
    """SPEC_016 §1C: services/ctx_corpus.py must expose get_l3_summary()."""
    from services.ctx_corpus import get_l3_summary
    assert callable(get_l3_summary)


def test_l3_summary_returns_counts_when_db_available():
    """The helper returns a short string summarising the bounded universe."""
    from unittest.mock import MagicMock
    from services.ctx_corpus import get_l3_summary

    db = MagicMock()

    def fake_fetch_one(sql, params=None):
        sql_lower = (sql or "").lower()
        # Return stub counts per table
        if "from drugs" in sql_lower:
            return {"n": 1247}
        if "from companies" in sql_lower:
            return {"n": 412}
        if "from clinical_trials" in sql_lower:
            return {"n": 8103}
        if "from mechanisms" in sql_lower:
            return {"n": 89}
        return {"n": 0}

    db.fetch_one.side_effect = fake_fetch_one
    summary = get_l3_summary(db)
    assert summary, "should return a non-empty string"
    # Should mention at least 'drug' and 'compan' (drugs + companies)
    low = summary.lower()
    assert "drug" in low
    assert "1247" in summary or "1,247" in summary


def test_l3_summary_graceful_when_db_fails():
    """If the DB is unreachable, return empty string rather than crashing."""
    from unittest.mock import MagicMock
    from services.ctx_corpus import get_l3_summary
    db = MagicMock()
    db.fetch_one.side_effect = RuntimeError("db down")
    summary = get_l3_summary(db)
    # Empty string or harmless fallback — must not raise
    assert isinstance(summary, str)


def test_build_context_block_includes_l3_summary():
    """The CTX context block should reference the bounded universe so the LLM
    knows the world is finite (prevents hallucinated counts like '~300 trials
    typical')."""
    from services.llm import _build_context_block
    ctx = _build_context_block(
        question="how many drugs are there?",
        intent="general",
        entity_info={},
        evidence_snippets=[],
    )
    low = ctx.lower()
    # Look for universe / bounded-data language
    has_universe = (
        "universe" in low
        or "total" in low
        or "database contains" in low
        or "bounded" in low
    )
    # This is a soft assertion — if L3 integration isn't ready yet, the
    # test documents the expectation but doesn't hard-fail. Once 1C ships,
    # this should go hard.
    if not has_universe:
        pytest.fail(
            "CTX context block should include L3 universe summary per SPEC_016 §1C. "
            f"Got context: {ctx[:500]!r}"
        )
