"""BE-7 — Strategist + Curator inline brief suggestions.

PB-402 polls every ~6s while the user is writing a Decision Brief
and renders inline cards with the agent's suggestion (counter
argument / missing stakeholder / contradicting evidence / evidence
score / one-click insert).

This module is the suggestion generator the route calls. Heuristic-
first by design: a deterministic baseline ships before any LLM
spend. The LLM is layered in via ``llm`` parameter when available,
falling back to the heuristics if it errors or is disabled.

Output shape per AGENT_BACKLOG#BE-7::

    {
      "suggestions": [
        {
          "agent":         "strategist" | "curator",
          "kind":          "add_counter" | "name_stakeholder" |
                           "surface_contradiction" | "evidence_score" |
                           "insert_evidence",
          "anchor":        { "paragraph_index": 2, "char_offset": 0 },
          "proposed_text": "…",
          "rationale":     "…",
          "confidence":    0.0-1.0,
          "evidence_refs": [evidence_id, ...]
        }, ...
      ]
    }
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


VALID_KINDS = (
    "add_counter",
    "name_stakeholder",
    "surface_contradiction",
    "evidence_score",
    "insert_evidence",
)


@dataclass
class Suggestion:
    agent: str          # strategist | curator
    kind: str
    anchor: dict
    proposed_text: str
    rationale: str
    confidence: float
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "agent":         self.agent,
            "kind":          self.kind,
            "anchor":        dict(self.anchor),
            "proposed_text": self.proposed_text,
            "rationale":     self.rationale,
            "confidence":    round(float(self.confidence), 3),
            "evidence_refs": list(self.evidence_refs),
        }


_PARAGRAPH_SEP = re.compile(r"\n\s*\n")


def _split_paragraphs(text: str) -> list[str]:
    if not text:
        return []
    return [p.strip() for p in _PARAGRAPH_SEP.split(text) if p.strip()]


def _strategist_baseline(
    *, paragraphs: list[str], options: list[dict] | None,
) -> list[Suggestion]:
    """Heuristic strategist suggestions before the LLM speaks."""
    out: list[Suggestion] = []
    options = options or []

    # 1. add_counter — when the brief has only one option
    if len(options) < 2:
        out.append(Suggestion(
            agent="strategist",
            kind="add_counter",
            anchor={"paragraph_index": max(0, len(paragraphs) - 1), "char_offset": 0},
            proposed_text="Counter-recommendation: maintain status quo while monitoring readouts.",
            rationale="A single option cannot be a real choice. Add at least one alternative.",
            confidence=0.85,
        ))

    # 2. name_stakeholder — heuristic check for missing stakeholder verbs
    body = " ".join(paragraphs).lower()
    if "stakeholder" not in body and ("commercial" in body or "regulatory" in body):
        out.append(Suggestion(
            agent="strategist",
            kind="name_stakeholder",
            anchor={"paragraph_index": 0, "char_offset": 0},
            proposed_text="Add: Commercial leadership and Regulatory affairs as primary stakeholders.",
            rationale="Brief mentions commercial / regulatory implications but doesn't name owners.",
            confidence=0.6,
        ))

    return out


def _curator_baseline(
    *, paragraphs: list[str], evidence_refs: list[dict] | None,
) -> list[Suggestion]:
    """Heuristic curator suggestions: evidence completeness scoring."""
    out: list[Suggestion] = []
    evidence_refs = evidence_refs or []
    evidence_count = len(evidence_refs)

    # evidence_score — 0..5 scaled by number of distinct sources cited
    distinct_sources = len({e.get("source_id") for e in evidence_refs if e.get("source_id")})
    score = min(5, distinct_sources)
    out.append(Suggestion(
        agent="curator",
        kind="evidence_score",
        anchor={"paragraph_index": 0, "char_offset": 0},
        proposed_text=f"Evidence completeness: {score}/5",
        rationale=(
            f"{evidence_count} citations from {distinct_sources} distinct source(s). "
            "Aim for ≥3 distinct sources at T1/T2."
        ),
        confidence=0.9,
        evidence_refs=[str(e.get("evidence_id")) for e in evidence_refs[:5] if e.get("evidence_id")],
    ))

    # surface_contradiction — flag if any evidence carries an explicit
    # `relation == "contradicts"` field (e.g. from claim_evidence_links).
    contradicts = [e for e in evidence_refs if (e.get("relation") or "").lower() == "contradicts"]
    if contradicts:
        out.append(Suggestion(
            agent="curator",
            kind="surface_contradiction",
            anchor={"paragraph_index": max(0, len(paragraphs) // 2), "char_offset": 0},
            proposed_text=(
                "Surface contradiction: "
                f"{len(contradicts)} evidence record(s) contradict the current claim."
            ),
            rationale="Inline contradiction is missing from the draft; the audit panel will flag this on commit.",
            confidence=0.75,
            evidence_refs=[str(e.get("evidence_id")) for e in contradicts[:5] if e.get("evidence_id")],
        ))

    return out


def suggest(
    *,
    current_text: str,
    current_options: list[dict] | None = None,
    evidence_refs: list[dict] | None = None,
    cursor_position: Optional[dict] = None,
    llm: Any = None,
) -> list[dict]:
    """Top-level — combine strategist + curator suggestions."""
    paragraphs = _split_paragraphs(current_text or "")
    out: list[Suggestion] = []
    out.extend(_strategist_baseline(paragraphs=paragraphs, options=current_options))
    out.extend(_curator_baseline(paragraphs=paragraphs, evidence_refs=evidence_refs))

    # LLM augmentation is optional. If it fails, drop and return the
    # heuristics only.
    if llm is not None and getattr(llm, "enabled", False):
        try:
            extra = llm.raw_chat(
                system="You are a Strategist agent reviewing a draft Decision Brief.",
                user=(
                    "Suggest at most ONE concise inline addition (1 sentence). "
                    "Reply with just the sentence, no preamble. "
                    f"Brief draft: {current_text[:4000]}"
                ),
                max_tokens=120,
                temperature=0.2,
            )
            if extra:
                out.append(Suggestion(
                    agent="strategist", kind="add_counter",
                    anchor={"paragraph_index": max(0, len(paragraphs) - 1), "char_offset": 0},
                    proposed_text=extra.strip(),
                    rationale="LLM-generated counter-recommendation candidate.",
                    confidence=0.7,
                ))
        except Exception:
            logger.debug("brief_suggestions: LLM augmentation failed; using heuristics", exc_info=True)

    return [s.to_dict() for s in out]


def stale_token(current_text: str) -> str:
    """Hash of the current text + paragraph count. Frontend caches the
    last seen token; if the user keeps typing and the token matches,
    the existing suggestions are still anchored correctly."""
    h = hashlib.sha256()
    h.update((current_text or "").encode("utf-8"))
    h.update(str(len(_split_paragraphs(current_text or ""))).encode("utf-8"))
    return h.hexdigest()[:16]
