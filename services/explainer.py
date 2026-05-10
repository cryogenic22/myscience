"""BE-19 — Why-this explanation generator.

PB-606 ships a "why this?" affordance on every proactive surface
item (Pulse cards, brief proposals, agent suggestions, war-game
recs, framing-trigger fires). When clicked, the user gets a
one-paragraph plain-language explanation plus deep-links into
factor breakdowns / source registry / trigger configs.

This module is the LLM-backed generator the route calls. Pure-ish:
the only side effect is the LLM call (which is ALSO swallowable —
on any failure we fall back to a deterministic template).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


VALID_SURFACES = frozenset({
    "pulse",
    "brief_proposal",
    "agent_suggestion",
    "wargame_rec",
    "trigger_fire",
})


@dataclass
class ExplanationRequest:
    surface: str
    item_id: str
    context: dict = field(default_factory=dict)


@dataclass
class ExplanationResult:
    explanation_paragraph: str
    deep_links: dict
    method: str  # "llm" | "template"

    def to_dict(self) -> dict:
        return {
            "explanation_paragraph": self.explanation_paragraph,
            "deep_links": dict(self.deep_links),
            "method": self.method,
        }


# Per-surface boilerplate that frames the LLM prompt + the template
# fallback. Each entry's "deep_links" is the FULL set the route
# could surface; we drop entries that the request can't fulfil.
_SURFACE_BLUEPRINTS: dict[str, dict] = {
    "pulse": {
        "kind": "Pulse signal",
        "intro": "This signal surfaced on your Pulse because it scored above your watchlist threshold",
        "deep_links": ("factor_breakdown_url", "source_registry_url"),
    },
    "brief_proposal": {
        "kind": "Decision-brief proposal",
        "intro": "Sentinel proposed this brief because the framing trigger you set up matched a recent pattern",
        "deep_links": ("trigger_config_url", "factor_breakdown_url"),
    },
    "agent_suggestion": {
        "kind": "Agent suggestion",
        "intro": "An agent recommended this action based on its calibration history and the current evidence",
        "deep_links": ("factor_breakdown_url",),
    },
    "wargame_rec": {
        "kind": "War-game recommendation",
        "intro": "Strategist recommended this option after running 1,200 Monte Carlo trials with current adversary posteriors",
        "deep_links": ("factor_breakdown_url",),
    },
    "trigger_fire": {
        "kind": "Framing trigger",
        "intro": "This trigger fired because at least one signal crossed the threshold you configured",
        "deep_links": ("trigger_config_url", "factor_breakdown_url"),
    },
}


def _deep_links_for(surface: str, item_id: str, context: dict) -> dict:
    """Resolve which deep-link URLs are reachable from the given context.

    Each link is omitted unless the route can actually fulfil it (i.e.
    we have the corresponding id). Frontend then decides whether to
    render a chip per link.
    """
    blueprint = _SURFACE_BLUEPRINTS.get(surface)
    if not blueprint:
        return {}
    available_keys = blueprint["deep_links"]
    out: dict[str, str] = {}

    if "factor_breakdown_url" in available_keys:
        # Pulse / brief / agent / war-game items all carry materiality
        # factors when they were scored.
        if context.get("materiality_score") is not None or context.get("signal_id"):
            out["factor_breakdown_url"] = (
                f"/materiality/{item_id}/factors"
            )

    if "source_registry_url" in available_keys:
        source_id = context.get("source_id")
        if source_id:
            out["source_registry_url"] = f"/sources/{source_id}"

    if "trigger_config_url" in available_keys:
        trigger_id = context.get("trigger_id")
        if trigger_id:
            out["trigger_config_url"] = f"/framing-triggers/{trigger_id}"

    return out


def _template_explanation(surface: str, context: dict) -> str:
    blueprint = _SURFACE_BLUEPRINTS.get(surface)
    if not blueprint:
        return "No explanation is available for this surface."
    parts = [blueprint["intro"]]

    score = context.get("materiality_score")
    if score is not None:
        try:
            parts.append(f"with a materiality score of {int(round(float(score)))}/100")
        except (TypeError, ValueError):
            pass

    headline = context.get("headline") or context.get("question")
    if headline:
        parts.append(f"about “{headline}”")

    source = context.get("source_name") or context.get("source_id")
    if source:
        parts.append(f"sourced from {source}")

    sentence = ", ".join(parts).rstrip(",") + "."
    return sentence[0].upper() + sentence[1:]


def explain(
    request: ExplanationRequest,
    *,
    llm=None,
) -> ExplanationResult:
    """Build an ``ExplanationResult`` for the given proactive item.

    Tries the LLM if one is supplied AND `enabled`; otherwise
    deterministically renders the template fallback. The same fallback
    is used if the LLM call raises — failures must NEVER break the
    user-facing chip.
    """
    if request.surface not in VALID_SURFACES:
        raise ValueError(
            f"unknown surface: {request.surface!r} "
            f"(allowed: {sorted(VALID_SURFACES)})"
        )

    deep_links = _deep_links_for(request.surface, request.item_id, request.context)

    template_text = _template_explanation(request.surface, request.context)

    if llm is None or not getattr(llm, "enabled", False):
        return ExplanationResult(
            explanation_paragraph=template_text,
            deep_links=deep_links,
            method="template",
        )

    try:
        prompt = (
            "You are explaining why a proactive surface item matters to a "
            "pharma intelligence analyst. One short paragraph, plain "
            "language, no bullets, no jargon. Surface kind: "
            f"{_SURFACE_BLUEPRINTS[request.surface]['kind']}. Context: "
            f"{request.context}."
        )
        text = llm.raw_chat(
            system="You write concise, plain-language explanations.",
            user=prompt,
            max_tokens=200,
            temperature=0.2,
        )
        if not text:
            raise RuntimeError("empty LLM response")
        return ExplanationResult(
            explanation_paragraph=text.strip(),
            deep_links=deep_links,
            method="llm",
        )
    except Exception as exc:
        logger.warning("Why-this LLM failed (%s); using template fallback", exc)
        return ExplanationResult(
            explanation_paragraph=template_text,
            deep_links=deep_links,
            method="template",
        )
