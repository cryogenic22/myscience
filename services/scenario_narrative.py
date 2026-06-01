"""Agentic scenario narrative (PB-H16) — depth-first, fact-grounded synthesis.

User direction (1 Jun): "get closer using agentic and LLM support but need not
be exact — accuracy and depth of intelligence matter more, and quality of the
war-game and decision-making is key." So this module does NOT chase the
benchmark's hand-authored prose. It turns a scenario + the dossier facts it
cites into a `decision_output` synthesis, with two guarantees that make it
trustworthy:

  1. GROUNDING — the model is shown ONLY the facts the scenario cites, and is
     told to use nothing else.
  2. ACCURACY — every quantitative claim is verified against the source facts
     after generation; hallucinated numbers lose their emphasis, invalid
     citations are stripped. Reuses the existing, battle-tested guards in
     services/llm.py (verify_narrative_numbers / validate_citations /
     _extract_source_numbers) — no parallel implementation.

The LLM is injected (any object with `.enabled` + `.raw_chat(system, user)` —
i.e. LLMSynthesizer). When the LLM is unavailable the synthesis degrades
gracefully to None and the scenario keeps its templated trigger — never a crash,
never a fabricated narrative.
"""
from __future__ import annotations

import logging
from typing import Optional

from services.llm import (
    _extract_source_numbers,
    validate_citations,
    verify_narrative_numbers,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a pharmaceutical competitive-strategy analyst preparing a "
    "decision-forcing war-game. You are given a scenario and a numbered list of "
    "evidence drawn from the asset's dossier. Use ONLY that evidence — never "
    "introduce a number, trial, company, or claim that is not in it. Be concise "
    "and decision-oriented: say what the scenario means for the focal asset and "
    "the recommended strategic posture. Cite evidence inline as [N]."
)

_MAX_EVIDENCE = 12


def _evidence_block(facts: list) -> str:
    """Numbered evidence list from the cited dossier facts (claims only)."""
    lines = []
    for i, f in enumerate(facts[:_MAX_EVIDENCE], start=1):
        claim = getattr(f, "claim", "") or ""
        lines.append(f"[{i}] {claim}")
    return "\n".join(lines)


def build_prompt(scenario, facts: list) -> tuple[str, str]:
    """Assemble the (system, user) grounded prompt. Pure — the user message
    exposes ONLY the cited facts, so the model cannot ground in anything else."""
    user = (
        f"Scenario: {scenario.name}\n"
        f"Trigger: {scenario.trigger_event}\n\n"
        f"Evidence:\n{_evidence_block(facts)}\n\n"
        "In 2–3 sentences, synthesise what this scenario means for the focal "
        "asset and the recommended decision posture. Cite evidence as [N]. "
        "Do not state any number that is not in the evidence."
    )
    return _SYSTEM_PROMPT, user


def _source_numbers(facts: list) -> set:
    """Numbers the narrative is allowed to assert — extracted from the cited
    fact claims (reuses the llm.py extractor)."""
    return _extract_source_numbers(None, [getattr(f, "claim", "") or "" for f in facts])


def synthesize_decision_output(scenario, facts: list, synthesizer) -> Optional[str]:
    """Generate a grounded `decision_output` for one scenario. Returns None
    (graceful) when there is no evidence, no synthesizer, or the LLM is
    disabled / yields nothing. Applies the citation + numeric guards so the
    returned text contains no hallucinated numbers or dangling citations."""
    if not facts or synthesizer is None or not getattr(synthesizer, "enabled", False):
        return None
    system, user = build_prompt(scenario, facts)
    try:
        text = synthesizer.raw_chat(system, user, max_tokens=400, temperature=0.2)
    except Exception:
        logger.warning("scenario narrative raw_chat failed", exc_info=True)
        return None
    if not text:
        return None
    # Accuracy guards (reuse): strip invalid [N] citations, de-emphasise any
    # bold number that doesn't trace to the cited facts.
    text = validate_citations(text, len(facts[:_MAX_EVIDENCE]))["narrative"]
    text = verify_narrative_numbers(text, _source_numbers(facts))["narrative"]
    text = text.strip()
    return text or None


def fact_claim_map(snapshot) -> dict:
    """factId -> DossierFact across all domains of a dossier snapshot."""
    out: dict = {}
    for d in snapshot.domains:
        for f in d.facts:
            out[f.id] = f
    return out


def enrich_scenarios_with_narrative(scenarios: list, snapshot, synthesizer) -> list:
    """Populate `decision_output` for each scenario from the facts it cites.
    Best-effort + grounded: a scenario whose synthesis fails keeps its prior
    (templated) state. Mutates and returns the scenarios."""
    if synthesizer is None or not getattr(synthesizer, "enabled", False):
        return scenarios
    fmap = fact_claim_map(snapshot)
    for s in scenarios:
        cited = [fmap[e.fact_id] for e in s.evidence if e.fact_id in fmap]
        out = synthesize_decision_output(s, cited, synthesizer)
        if out:
            s.decision_output = out
    return scenarios
