"""Conversation memory with token-budgeted eviction and entity tracking.

Provides CTX-inspired rolling state management for pharma intelligence
conversations. Tracks entities across turns, resolves coreferences like
"this drug" or "that company", and enforces a token budget via
oldest-first eviction.

Usage:
    mem = ConversationMemory(token_budget=4000)
    mem.add_exchange("What is semaglutide?", "Semaglutide is a GLP-1 agonist.", entities=["semaglutide"])
    context = mem.get_context()           # compressed context string for LLM
    entities = mem.get_entities_discussed() # ranked entity list
    resolved = mem.resolve_reference("What trials does this drug have?")
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class _Exchange:
    """A single question/response pair with metadata."""

    turn: int
    question: str
    response: str
    intent: str
    entities: list[str]

    def to_dict(self) -> dict:
        return {
            "turn": self.turn,
            "question": self.question,
            "response": self.response,
            "intent": self.intent,
            "entities": self.entities,
        }

    @classmethod
    def from_dict(cls, d: dict) -> _Exchange:
        return cls(
            turn=d["turn"],
            question=d["question"],
            response=d["response"],
            intent=d.get("intent", ""),
            entities=d.get("entities", []),
        )


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: word count * 1.3, with minimum of 1."""
    if not text:
        return 0
    return max(1, int(len(text.split()) * 1.3))


def _extract_bold_entities(text: str) -> list[str]:
    """Extract **bold** text as entity names from assistant responses."""
    return re.findall(r"\*\*([^*]+)\*\*", text)


class ConversationMemory:
    """Token-budgeted conversation memory with entity tracking and coreference resolution.

    Follows CTX AgentSession principles:
    - Incremental accumulation of conversation state
    - Token budget enforcement via oldest-first eviction
    - Entity tracking across turns (survives eviction)
    - Snapshot/restore for persistence

    Args:
        token_budget: Maximum estimated tokens for get_context() output.
    """

    def __init__(self, token_budget: int = 4000) -> None:
        self.token_budget = token_budget
        self._exchanges: list[_Exchange] = []
        self._turn_counter: int = 0
        # Global entity tracking: name -> mention count (survives eviction)
        self._entity_counts: Counter = Counter()

    def add_exchange(
        self,
        question: str,
        response: str,
        intent: str = "",
        entities: list[str] | None = None,
    ) -> None:
        """Add a question/response pair to memory.

        Args:
            question: User's question text.
            response: Assistant's response text.
            intent: Detected intent classification (e.g. "compare", "pipeline").
            entities: Explicit entity names mentioned. If None, attempts to
                      extract bold entities from the response.
        """
        self._turn_counter += 1
        all_entities = list(entities) if entities else []

        # Also extract bold entities from response text
        bold = _extract_bold_entities(response)
        for name in bold:
            if name not in all_entities:
                all_entities.append(name)

        exchange = _Exchange(
            turn=self._turn_counter,
            question=question,
            response=response,
            intent=intent,
            entities=all_entities,
        )
        self._exchanges.append(exchange)

        # Track entities globally (survives eviction)
        for name in all_entities:
            self._entity_counts[name] += 1

        # Enforce budget after adding
        self._enforce_budget()

    def get_context(self) -> str:
        """Return compressed conversation context suitable for LLM prompts.

        Returns a string summarizing recent exchanges plus entity/intent
        metadata, staying within the token budget.
        """
        if not self._exchanges:
            return ""

        parts: list[str] = []

        # Build context from exchanges (most recent first in construction,
        # but output in chronological order)
        exchange_texts: list[str] = []
        for ex in self._exchanges:
            lines = []
            lines.append(f"[user] {ex.question}")
            lines.append(f"[assistant] {ex.response}")
            if ex.intent:
                lines.append(f"[intent] {ex.intent}")
            if ex.entities:
                lines.append(f"[entities] {', '.join(ex.entities)}")
            exchange_texts.append("\n".join(lines))

        # Add exchanges newest-first, checking budget
        selected: list[str] = []
        running_tokens = 0
        # Reserve some tokens for the entity summary footer
        footer_reserve = 30

        for text in reversed(exchange_texts):
            text_tokens = _estimate_tokens(text)
            if running_tokens + text_tokens > self.token_budget - footer_reserve:
                break
            selected.append(text)
            running_tokens += text_tokens

        # Reverse back to chronological order
        selected.reverse()
        parts.extend(selected)

        # Add entity summary if we have tracked entities
        top_entities = self.get_entities_discussed()[:8]
        if top_entities:
            parts.append(f"[context] Entities discussed: {', '.join(top_entities)}")

        return "\n".join(parts)

    def get_entities_discussed(self) -> list[str]:
        """Return unique entity names ranked by frequency (most discussed first).

        Entity tracking is global and survives eviction of exchange text.
        """
        if not self._entity_counts:
            return []
        # Sort by count descending, then alphabetically for stability
        return [
            name
            for name, _count in sorted(
                self._entity_counts.items(),
                key=lambda x: (-x[1], x[0]),
            )
        ]

    def resolve_reference_with_map(self, question: str) -> tuple[str, dict]:
        """Resolve coreferences AND return the substitution map.

        Returns
        -------
        (resolved_question, coreference_resolution)

        ``coreference_resolution`` is a dict shaped::

            {
                "<original phrase>": "<resolved entity>",
                ...
                "from_turn": <int 1-based source turn>,
            }

        Empty dict when no substitutions occurred. Intended for surfacing
        in the chat response so the frontend can render a branch
        indicator under user messages (BE-15 acceptance shape).
        """
        if not self._exchanges:
            return question, {}

        q_lower = question.lower()
        has_ref = re.search(
            r"\b(this|that|these|those|its|their|the same|it)\b", q_lower
        )
        if not has_ref:
            return question, {}

        last_entity = ""
        source_turn: int | None = None
        for ex in reversed(self._exchanges):
            if ex.entities:
                last_entity = ex.entities[0]
                source_turn = ex.turn
                break
            bold = _extract_bold_entities(ex.response)
            if bold:
                last_entity = bold[0]
                source_turn = ex.turn
                break
        if not last_entity:
            return question, {}

        coreference_map: dict[str, str] = {}

        def _record(pattern: str, replacement: str, *, capture_after_word: bool = False):
            """Apply a regex sub and record every match in coreference_map."""
            nonlocal resolved
            for m in re.finditer(pattern, resolved, flags=re.IGNORECASE):
                phrase = m.group(0)
                # The replacement string contains the entity; if the regex
                # has a captured word group we want the displayable phrase.
                coreference_map[phrase] = replacement.split()[0] if capture_after_word else replacement
            if capture_after_word:
                resolved = re.sub(pattern, f"{last_entity} \\2", resolved, flags=re.IGNORECASE)
            else:
                resolved = re.sub(pattern, replacement, resolved, flags=re.IGNORECASE)

        resolved = question
        _record(r"\b(this|that)\s+(drug|compound|molecule|medication|therapy|treatment)\b", last_entity)
        _record(r"\b(this|that)\s+(company|firm|manufacturer|pharma)\b", last_entity)
        _record(
            r"\b(these|those)\s+(drugs?|compounds?|companies|entities|mechanisms?)\b",
            last_entity,
            capture_after_word=True,
        )
        _record(
            r"\b(its?|their)\s+(pipeline|portfolio|trials?|landscape|safety profile|efficacy|mechanism)\b",
            last_entity,
            capture_after_word=True,
        )

        if not coreference_map:
            return question, {}

        coreference_map["from_turn"] = source_turn  # type: ignore[assignment]
        return resolved, coreference_map

    def resolve_reference(self, question: str) -> str:
        """Resolve coreferences like 'this drug', 'that company', 'its pipeline'.

        Replaces demonstrative/pronoun references with the most recently
        mentioned entity from conversation history.

        Args:
            question: User's current question with potential coreferences.

        Returns:
            Resolved question with entity names substituted, or original
            question if no history or no references found.
        """
        if not self._exchanges:
            return question

        q_lower = question.lower()
        # Check for demonstrative/pronoun patterns
        has_ref = re.search(
            r"\b(this|that|these|those|its|their|the same|it)\b", q_lower
        )
        if not has_ref:
            return question

        # Find the most recent entity from conversation history
        last_entity = ""
        for ex in reversed(self._exchanges):
            if ex.entities:
                last_entity = ex.entities[0]
                break
            # Fall back to bold extraction from response
            bold = _extract_bold_entities(ex.response)
            if bold:
                last_entity = bold[0]
                break

        if not last_entity:
            return question

        resolved = question
        # Replace "this/that drug/compound" patterns
        resolved = re.sub(
            r"\b(this|that)\s+(drug|compound|molecule|medication|therapy|treatment)\b",
            last_entity,
            resolved,
            flags=re.IGNORECASE,
        )
        # Replace "that/this company/firm" patterns
        resolved = re.sub(
            r"\b(this|that)\s+(company|firm|manufacturer|pharma)\b",
            last_entity,
            resolved,
            flags=re.IGNORECASE,
        )
        # Replace "these/those drugs/companies" patterns
        resolved = re.sub(
            r"\b(these|those)\s+(drugs?|compounds?|companies|entities|mechanisms?)\b",
            f"{last_entity} \\2",
            resolved,
            flags=re.IGNORECASE,
        )
        # Replace "its/their pipeline/portfolio" patterns
        resolved = re.sub(
            r"\b(its?|their)\s+(pipeline|portfolio|trials?|landscape|products?)\b",
            f"{last_entity} \\2",
            resolved,
            flags=re.IGNORECASE,
        )

        return resolved

    def snapshot(self) -> str:
        """Serialize the full memory state to a JSON string for persistence.

        Returns:
            JSON string containing all exchanges and entity counts.
        """
        state = {
            "token_budget": self.token_budget,
            "turn_counter": self._turn_counter,
            "exchanges": [ex.to_dict() for ex in self._exchanges],
            "entity_counts": dict(self._entity_counts),
        }
        return json.dumps(state)

    def restore(self, state: str) -> None:
        """Restore memory from a snapshot string.

        Args:
            state: JSON string from a previous snapshot() call.
        """
        data = json.loads(state)
        self.token_budget = data.get("token_budget", self.token_budget)
        self._turn_counter = data.get("turn_counter", 0)
        self._exchanges = [
            _Exchange.from_dict(d) for d in data.get("exchanges", [])
        ]
        self._entity_counts = Counter(data.get("entity_counts", {}))

    def _enforce_budget(self) -> None:
        """Evict oldest exchanges to keep context within token budget.

        Entities from evicted exchanges are preserved in the global
        entity counter so they remain discoverable.
        """
        while len(self._exchanges) > 1:
            ctx = self._build_raw_context()
            tokens = _estimate_tokens(ctx)
            if tokens <= self.token_budget:
                break
            # Evict oldest exchange
            self._exchanges.pop(0)

    def _build_raw_context(self) -> str:
        """Build raw context string for budget estimation (no truncation)."""
        parts: list[str] = []
        for ex in self._exchanges:
            parts.append(f"[user] {ex.question}")
            parts.append(f"[assistant] {ex.response}")
            if ex.intent:
                parts.append(f"[intent] {ex.intent}")
            if ex.entities:
                parts.append(f"[entities] {', '.join(ex.entities)}")
        return "\n".join(parts)
