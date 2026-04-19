"""SPEC_016 Phase 3.5 — pipeline-intent hotfix.

The PIPELINE intent today extracts the WRONG token as therapeutic_area:
"show pipeline for semaglutide" → ta="show" (the prefix before "pipeline")
because the regex `(.+?)\\s+pipeline` matches lazily on the smallest prefix.

Net effect: handle_pipeline calls drug_pipeline_strength(therapeutic_area="show")
which has no match → "No pipeline data available for this query".

Fix:
1. PIPELINE intent must support "pipeline for X" / "pipeline of X" patterns
   and extract X (the entity AFTER "for"), not the prefix.
2. Extracted entity should be classified: drug (use drug_id) vs TA (use therapeutic_area).
3. handle_pipeline must accept drug_id and pass it to drug_pipeline_strength.

Tests must FAIL before implementation. TDD discipline.
"""

from __future__ import annotations

import re

import pytest

from services.chat_handlers.intent import detect_intent, Intent


# ────────────────────────────────────────────────────────────────────
# Intent detection — extract entity AFTER "for" / "of"
# ────────────────────────────────────────────────────────────────────

def test_pipeline_for_drug_extracts_entity_name():
    """SPEC_016 Phase 3.5: 'pipeline for semaglutide' must extract 'semaglutide'.

    Today this returns ta='show' (or empty after strip). After fix it should
    surface 'semaglutide' as either drug_name or therapeutic_area in params.
    """
    intent, params = detect_intent("show pipeline for semaglutide")
    assert intent == Intent.PIPELINE
    extracted = (
        params.get("drug_name")
        or params.get("entity_name")
        or params.get("therapeutic_area")
    )
    assert extracted and extracted.lower() == "semaglutide", (
        f"PIPELINE intent must extract 'semaglutide' from 'pipeline for X'. "
        f"Got params={params}"
    )


def test_pipeline_for_drug_other_phrasing():
    """Variant: 'show the full pipeline for tirzepatide'."""
    intent, params = detect_intent("show the full pipeline for tirzepatide")
    assert intent == Intent.PIPELINE
    extracted = (
        params.get("drug_name")
        or params.get("entity_name")
        or params.get("therapeutic_area")
    )
    assert extracted and "tirzepatide" in extracted.lower()


def test_pipeline_for_therapeutic_area_still_works():
    """Regression: 'pipeline for diabetes' must still extract 'diabetes' as TA."""
    intent, params = detect_intent("show me the pipeline for diabetes")
    assert intent == Intent.PIPELINE
    extracted = (
        params.get("drug_name")
        or params.get("entity_name")
        or params.get("therapeutic_area")
    )
    assert extracted and "diabetes" in extracted.lower()


def test_pipeline_x_pipeline_form_still_works():
    """Regression: 'obesity pipeline' (TA prefix) must still work."""
    intent, params = detect_intent("show me the obesity pipeline")
    assert intent == Intent.PIPELINE
    extracted = (
        params.get("drug_name")
        or params.get("entity_name")
        or params.get("therapeutic_area")
    )
    assert extracted and "obesity" in extracted.lower()


# ────────────────────────────────────────────────────────────────────
# handle_pipeline accepts drug_id
# ────────────────────────────────────────────────────────────────────

def test_handle_pipeline_can_route_to_drug_specific_query():
    """SPEC_016 Phase 3.5: handle_pipeline must support drug-specific routing.

    Either (a) directly via a drug_id param, or (b) via params['drug_id'] in the
    dict, or (c) by accepting a canonicalizer that classifies entity_name. Any
    of these unblocks "Show pipeline for X" where X is a drug.
    """
    import inspect
    from services.chat_handlers.handlers import handle_pipeline
    sig = inspect.signature(handle_pipeline)
    param_names = set(sig.parameters.keys())
    has_drug_routing = (
        "drug_id" in param_names
        or "drug_name" in param_names
        or "entity_id" in param_names
        or "canonicalizer" in param_names
    )
    assert has_drug_routing, (
        "handle_pipeline must support drug-specific routing via one of: "
        "drug_id, drug_name, entity_id, or canonicalizer. "
        f"Current params: {list(param_names)}"
    )

    # Also check the source for the routing logic — params['drug_id'] usage
    # OR canonicalizer.canonicalize() call indicates the handler can switch
    # between drug and TA modes.
    import inspect as _inspect
    src = _inspect.getsource(handle_pipeline)
    routes_to_drug = (
        "drug_id" in src
        or "canonicalize" in src
    )
    assert routes_to_drug, (
        "handle_pipeline body must route to drug_pipeline_strength(drug_id=...) "
        "when entity is a drug. Body must reference drug_id or canonicalize()."
    )


def test_drug_pipeline_strength_accepts_drug_id():
    """The metrics service must support drug_id filter for single-drug queries."""
    import inspect
    from services.metrics import PharmaMetrics
    sig = inspect.signature(PharmaMetrics.drug_pipeline_strength)
    assert "drug_id" in sig.parameters, (
        "PharmaMetrics.drug_pipeline_strength must accept drug_id "
        "for single-drug pipeline queries"
    )


# ────────────────────────────────────────────────────────────────────
# End-to-end: chat route routes drug-pipeline queries correctly
# ────────────────────────────────────────────────────────────────────

def test_chat_route_passes_drug_routing_context_to_pipeline_handler():
    """STATIC: chat.py must pass drug-routing context to handle_pipeline so it
    can classify entity_name as drug vs TA. Acceptable context: drug_id /
    drug_name / canon_map / entity_id / canonicalizer.
    """
    from pathlib import Path
    chat_src = Path("api/routes/chat.py").read_text(encoding="utf-8")
    handler_calls = re.findall(r"handle_pipeline\([^)]+\)", chat_src, re.DOTALL)
    assert handler_calls, "expected handle_pipeline call in chat.py"
    # Every call should pass drug-routing context (canonicalizer is most general)
    routing_keywords = ("drug_id", "drug_name", "canon_map", "entity_id", "canonicalizer")
    for call in handler_calls:
        assert any(kw in call for kw in routing_keywords), (
            f"chat.py handle_pipeline call missing drug-routing context. "
            f"Call: {call!r}"
        )
