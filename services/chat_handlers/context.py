"""Conversation context building and follow-up resolution for chat."""

from __future__ import annotations

import re

from services.chat_handlers.intent import detect_intent


def build_conversation_context(history: list[dict]) -> str:
    """Build a compact text summary of the last 3 exchange pairs for follow-up resolution.

    Includes entities discussed, metrics shown, and SQL context from prior turns
    so the LLM can provide richer, more contextual follow-up answers.
    """
    if not history:
        return ""
    # Take last 6 messages (3 exchange pairs)
    recent = history[-6:]
    parts: list[str] = []
    all_entities: list[str] = []
    all_metrics: list[str] = []

    for msg in recent:
        role = msg.get("role", "unknown")
        content = str(msg.get("content", ""))[:500]
        sql_ctx = msg.get("sql_context", "")
        line = f"[{role}] {content}"
        if sql_ctx:
            line += f"\n  Prior SQL: {str(sql_ctx)[:300]}"
        parts.append(line)

        # Collect entity and metric context from assistant messages
        entities = msg.get("entities", [])
        if isinstance(entities, list):
            all_entities.extend(str(e) for e in entities[:5])
        metrics_types = msg.get("metrics_types", [])
        if isinstance(metrics_types, list):
            all_metrics.extend(str(m) for m in metrics_types[:5])

    # Append semantic summary
    if all_entities:
        unique_entities = list(dict.fromkeys(all_entities))[:8]
        parts.append(f"[context] Entities discussed: {', '.join(unique_entities)}")
    if all_metrics:
        unique_metrics = list(dict.fromkeys(all_metrics))[:6]
        parts.append(f"[context] Metrics shown: {', '.join(unique_metrics)}")

    return "\n".join(parts)


def resolve_followup_question(question: str, history: list[dict]) -> str:
    """Expand ambiguous follow-up references using prior conversation context.

    Detects patterns like "this space", "that drug", "those companies", "its pipeline"
    and replaces them with the actual entity/topic from the most recent assistant message.
    """
    if not history:
        return question

    q = question.lower().strip()
    # Only attempt resolution for short follow-up questions with pronouns/demonstratives
    has_ref = re.search(
        r'\b(this|that|these|those|its|their|the same|above|it)\b', q
    )
    if not has_ref:
        return question

    # Extract the most recent topic from assistant messages
    prior_topic = ""
    prior_intent = ""
    for msg in reversed(history):
        if msg.get("role") != "assistant":
            continue
        content = str(msg.get("content", ""))
        # Try to extract the primary entity/topic from bold markers
        bold_matches = re.findall(r'\*\*([^*]+)\*\*', content)
        if bold_matches:
            prior_topic = bold_matches[0]
            break
        # Fall back to first sentence entity
        if content:
            prior_topic = content[:60].split(".")[0]
            break

    # Extract prior intent from the most recent user question
    for msg in reversed(history):
        if msg.get("role") == "user":
            prev_q = str(msg.get("content", "")).lower()
            _, prev_params = detect_intent(prev_q)
            prior_intent = prev_params.get("topic", "") or prev_params.get("entity_name", "") or prev_params.get("therapeutic_area", "")
            if not prior_intent and prior_topic:
                prior_intent = prior_topic
            break

    if not prior_intent and not prior_topic:
        return question

    topic = prior_intent or prior_topic

    # Replace references with the resolved topic
    resolved = question
    resolved = re.sub(r'\b(this|that)\s+(space|area|market|landscape|field|domain|segment)\b',
                      topic, resolved, flags=re.IGNORECASE)
    resolved = re.sub(r'\b(these|those)\s+(drugs?|compounds?|entities|companies|mechanisms?)\b',
                      f'{topic} \\2', resolved, flags=re.IGNORECASE)
    resolved = re.sub(r'\b(its?|their)\s+(pipeline|portfolio|trials?|landscape)\b',
                      f'{topic} \\2', resolved, flags=re.IGNORECASE)

    return resolved
