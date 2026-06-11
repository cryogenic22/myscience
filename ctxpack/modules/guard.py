"""Context Guard — post-response hallucination detection.

Extends the passive ``needs_rehydration()`` pattern from
``ctxpack.core.hydrator`` to active response checking with
entity-name validation and correction message generation.

This module implements M3 of the CtxPack module roadmap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# ── Data Structures ──


@dataclass
class GuardResult:
    """Outcome of a post-response guard check."""

    low_confidence: bool
    signals_detected: list[str] = field(default_factory=list)
    unknown_entities: list[str] = field(default_factory=list)
    recommendation: str = "ok"  # "ok", "warn", "retry", "new_session"
    # Dominance/leadership claims whose subject is grounded in NEITHER the
    # retrieved context NOR the known-entity catalog ("Medtronic dominates …").
    ungrounded_claims: list[str] = field(default_factory=list)


# ── Default hallucination signals ──

_DEFAULT_SIGNALS: list[str] = [
    "not found in",
    "from industry experience",
    "based on my training",
    "generally speaking",
    "typically in",
]

# Pattern for ENTITY-XXX names (all-caps with hyphens)
_ENTITY_NAME_RE = re.compile(r"\bENTITY-[A-Z][A-Z0-9-]+\b")

# Pattern for ID-like tokens: 2-3 uppercase letters, hyphen, 1+ digits
_ID_PATTERN_RE = re.compile(r"\b[A-Z]{2,3}-\d+\b")

# A dominance/leadership claim: a Capitalized subject (1-4 words) immediately
# before a dominance verb. Used to verify the subject is grounded — the
# "Medtronic Diabetes dominates …" hallucination class.
_DOMINANCE_RE = re.compile(
    r"([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,3})\s+"
    r"(?:dominates?|dominating|leads?\b|is\s+(?:the\s+)?(?:dominant|leading|top|largest|biggest)\b)"
)
# Generic subject tokens that don't identify an entity (skip when grounding).
_GROUNDING_STOP: set[str] = {
    "the", "this", "that", "these", "those", "their", "there", "with", "drug",
    "drugs", "market", "space", "area", "field", "company", "companies", "it",
    "they", "which", "currently", "overall", "both", "each", "other", "data",
}


class ContextGuard:
    """Post-response guard that detects hallucination signals and unknown entities.

    Usage::

        guard = ContextGuard(known_entity_names={"ENTITY-CUSTOMER", "ENTITY-ORDER"})
        result = guard.check(llm_response)
        if result.recommendation != "ok":
            correction = guard.build_correction(result)
    """

    def __init__(
        self,
        *,
        known_entity_names: Optional[set[str]] = None,
        custom_signals: Optional[list[str]] = None,
        on_low_confidence: str = "warn",
    ) -> None:
        self._known_entity_names = known_entity_names
        self._on_low_confidence = on_low_confidence
        self._known_tokens_cache: Optional[set[str]] = None

        # Build signal list: defaults + custom (custom extends, never replaces)
        self._signals = list(_DEFAULT_SIGNALS)
        if custom_signals:
            self._signals.extend(custom_signals)

    def check(self, response: str, hydrated_context: str = "") -> GuardResult:
        """Check a response for hallucination signals and unknown entities.

        Args:
            response: The LLM's response text to check.
            hydrated_context: The hydrated .ctx text that was injected (unused
                for now, reserved for future context-aware checking).

        Returns:
            GuardResult with confidence assessment and recommendations.
        """
        # Empty / whitespace-only response
        if not response or not response.strip():
            return GuardResult(
                low_confidence=True,
                signals_detected=[],
                unknown_entities=[],
                recommendation="warn",
            )

        lower = response.lower()

        # Detect hallucination signals
        signals_found: list[str] = []
        for signal in self._signals:
            if signal.lower() in lower:
                signals_found.append(signal)

        # Detect unknown entity names (only if known set is provided)
        unknown: list[str] = []
        if self._known_entity_names is not None:
            # Find ENTITY-XXX names in response
            entity_names_in_response = set(_ENTITY_NAME_RE.findall(response))
            for name in sorted(entity_names_in_response):
                if name not in self._known_entity_names:
                    unknown.append(name)

            # Find ID patterns (XX-NN) in response
            id_patterns_in_response = set(_ID_PATTERN_RE.findall(response))
            for pattern in sorted(id_patterns_in_response):
                if pattern not in self._known_entity_names:
                    unknown.append(pattern)

        # Content grounding: dominance claims whose subject is in neither the
        # retrieved context nor the known-entity catalog.
        ungrounded = self._ungrounded_claims(response, hydrated_context)

        low_confidence = bool(signals_found) or bool(unknown) or bool(ungrounded)

        # Recommendation logic
        recommendation = self._compute_recommendation(signals_found, unknown, ungrounded)

        return GuardResult(
            low_confidence=low_confidence,
            signals_detected=signals_found,
            unknown_entities=unknown,
            recommendation=recommendation,
            ungrounded_claims=ungrounded,
        )

    def _known_tokens(self) -> set[str]:
        """Lowercase significant tokens drawn from the known-entity catalog, so a
        named subject can be matched even when the section name differs in form."""
        if self._known_tokens_cache is not None:
            return self._known_tokens_cache
        tokens: set[str] = set()
        for name in (self._known_entity_names or set()):
            for tok in re.split(r"[^a-z0-9]+", str(name).lower()):
                if len(tok) >= 4 and tok not in _GROUNDING_STOP:
                    tokens.add(tok)
        self._known_tokens_cache = tokens
        return tokens

    def _ungrounded_claims(self, response: str, context: str) -> list[str]:
        """Find 'X dominates/leads' claims whose subject X is grounded in neither
        the retrieved context nor the known-entity catalog (high precision —
        a real or context-present player is never flagged)."""
        if not response:
            return []
        text = response.replace("*", "")
        ctx = (context or "").lower()
        known = self._known_tokens()
        out: list[str] = []
        seen: set[str] = set()
        for m in _DOMINANCE_RE.finditer(text):
            subject = m.group(1).strip()
            tokens = [
                t for t in re.split(r"[^a-z0-9]+", subject.lower())
                if len(t) >= 4 and t not in _GROUNDING_STOP
            ]
            if not tokens:
                continue
            grounded = any(t in ctx or t in known for t in tokens)
            if not grounded and subject.lower() not in seen:
                seen.add(subject.lower())
                out.append(subject)
        return out

    def build_correction(self, result: GuardResult) -> str:
        """Build a correction message for injection into the next turn.

        Args:
            result: A GuardResult from a previous ``check()`` call.

        Returns:
            Correction message string, or empty string if result is "ok".
        """
        if result.recommendation == "ok":
            return ""

        parts: list[str] = []

        if result.unknown_entities and self._known_entity_names:
            sorted_known = sorted(self._known_entity_names)
            entity_list = ", ".join(sorted_known)
            parts.append(
                "Note: The previous response may contain entity names not in "
                f"the catalog. Use ONLY the following entities: [{entity_list}]"
            )

        if result.signals_detected and not parts:
            parts.append(
                "Note: The previous response contained low-confidence signals. "
                "Please answer using ONLY information from the provided context."
            )

        return "\n".join(parts)

    @staticmethod
    def _compute_recommendation(
        signals: list[str],
        unknown_entities: list[str],
        ungrounded_claims: Optional[list[str]] = None,
    ) -> str:
        """Determine recommendation based on detected issues.

        Logic:
        - No issues → "ok"
        - Signals or ungrounded dominance claims only → "warn"
        - 1 unknown entity → "retry"
        - 2+ unknown entities → "new_session"
        """
        if unknown_entities:
            if len(unknown_entities) >= 2:
                return "new_session"
            return "retry"
        if signals or ungrounded_claims:
            return "warn"
        return "ok"
