"""Evaluation benchmark scorers — 5 dimensions of response quality.

Each scorer returns 0.0–1.0. Composite score is a weighted average.
Used by eval_runner to score every golden query response.
"""

from __future__ import annotations

import re
import logging

logger = logging.getLogger(__name__)

# Weights for composite score
# Per lead review: citation weight bumped (trust matters more than routing),
# intent weight reduced (correct intent with bad citations < wrong intent with good data)
WEIGHTS = {
    "intent": 0.10,
    "grounding": 0.25,
    "factual": 0.25,
    "completeness": 0.25,
    "citation": 0.15,
}

_CITATION_RE = re.compile(r"\[(\d+)\]")
_BOLD_NUMBER_RE = re.compile(r"\*\*(\d+(?:\.\d+)?%?)\*\*")


# ── Individual Scorers ──────────────────────────────────────────────


def score_intent(response: dict, expected: dict) -> float:
    """Did the system detect the correct intent?"""
    return 1.0 if response.get("intent") == expected.get("intent") else 0.0


def score_entity_grounding(response: dict, expected: dict) -> float:
    """Are expected entities present in response and must_not_mention absent?"""
    score = 0.0
    narrative = response.get("narrative", "").lower()
    data = response.get("data") or {}
    entity_focus = data.get("entity_focus") or []

    # Check expected entities in entity_focus (0-0.5)
    expected_entities = expected.get("entities", [])
    if expected_entities:
        focus_labels = {(e.get("label") or "").lower() for e in entity_focus}
        found = sum(1 for e in expected_entities if e.lower() in focus_labels or e.lower() in narrative)
        score += 0.5 * (found / len(expected_entities))
    else:
        score += 0.5  # no entity expectation → pass

    # Check must_mention terms in narrative (0-0.3)
    must_mention = expected.get("must_mention", [])
    if must_mention:
        mentioned = sum(1 for term in must_mention if term.lower() in narrative)
        score += 0.3 * (mentioned / len(must_mention))
    else:
        score += 0.3

    # Penalize must_not_mention (0-0.2)
    must_not = expected.get("must_not_mention", [])
    if must_not:
        violations = sum(1 for term in must_not if term.lower() in narrative)
        if violations == 0:
            score += 0.2
        else:
            score -= 0.1 * violations
    else:
        score += 0.2

    return round(min(1.0, max(0.0, score)), 2)


def score_factual_accuracy(response: dict) -> float:
    """Do bold numbers in narrative match source metrics?"""
    narrative = response.get("narrative", "")
    data = response.get("data") or {}
    metrics = data.get("metrics_context") or {}

    # Extract all numbers from metrics
    source_numbers: set[float] = set()
    _collect_numbers(metrics, source_numbers)

    # Extract bold numbers from narrative
    bold_matches = _BOLD_NUMBER_RE.findall(narrative)
    if not bold_matches:
        return 1.0  # nothing to verify → pass

    verified = 0
    total = 0
    for raw in bold_matches:
        clean = raw.rstrip("%")
        try:
            num = float(clean)
        except ValueError:
            continue
        total += 1
        for src in source_numbers:
            if abs(num - float(src)) <= 1.0:
                verified += 1
                break
            if 0 < float(src) < 1 and abs(num - float(src) * 100) <= 1.0:
                verified += 1
                break

    return round(verified / total, 2) if total > 0 else 1.0


def score_evidence_completeness(response: dict, expected: dict) -> float:
    """Does the response have sufficient evidence and mention required terms?"""
    score = 0.0
    narrative = response.get("narrative", "").lower()
    data = response.get("data") or {}
    evidence = data.get("evidence") or []

    # Evidence count vs minimum (0-0.5)
    min_ev = expected.get("min_evidence", 1)
    if min_ev <= 0:
        score += 0.5
    else:
        ratio = min(1.0, len(evidence) / min_ev)
        score += 0.5 * ratio

    # Must-mention terms in narrative (0-0.5)
    must_mention = expected.get("must_mention", [])
    if must_mention:
        mentioned = sum(1 for term in must_mention if term.lower() in narrative)
        score += 0.5 * (mentioned / len(must_mention))
    else:
        score += 0.5

    return round(min(1.0, score), 2)


def score_citation_validity(response: dict) -> float:
    """Are all [N] citations in the narrative valid?"""
    narrative = response.get("narrative", "")
    data = response.get("data") or {}
    evidence = data.get("evidence") or []
    evidence_count = len(evidence)

    citations = _CITATION_RE.findall(narrative)
    if not citations:
        return 1.0  # no citations → pass

    valid = sum(1 for c in citations if 1 <= int(c) <= evidence_count)
    return round(valid / len(citations), 2)


# ── Composite Score ─────────────────────────────────────────────────


def composite_score(dimensions: dict[str, float]) -> float:
    """Weighted average of all scoring dimensions."""
    total = 0.0
    for dim, weight in WEIGHTS.items():
        total += weight * dimensions.get(dim, 0.0)
    return round(total, 3)


# ── Helpers ─────────────────────────────────────────────────────────


def _collect_numbers(obj, out: set[float], depth: int = 0) -> None:
    """Recursively collect numeric values from nested dict/list."""
    if depth > 5:
        return
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out.add(float(v))
            elif isinstance(v, (dict, list)):
                _collect_numbers(v, out, depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                out.add(float(item))
            elif isinstance(item, (dict, list)):
                _collect_numbers(item, out, depth + 1)
