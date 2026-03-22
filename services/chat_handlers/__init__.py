"""Chat handler modules — decomposed from api/routes/chat.py.

Re-exports all public symbols so callers can do:
    from services.chat_handlers import Intent, detect_intent, handle_dossier, ...
"""

from services.chat_handlers.intent import (
    Intent,
    MECHANISM_SYNONYMS,
    detect_format_hint,
    detect_intent,
)

from services.chat_handlers.context import (
    build_conversation_context,
    resolve_followup_question,
)

from services.chat_handlers.formatting import (
    apply_chat_modes,
    build_comparison_table,
    build_visualizations,
    coerce_bool,
    compute_comparison_insights,
    expand_topic_synonyms,
    generate_followups,
    normalize_scope,
    resolve_entity,
    safe_filename,
    sanitize_transcript,
    to_number,
)

from services.chat_handlers.handlers import (
    handle_compare,
    handle_deep_research,
    handle_dossier,
    handle_general,
    handle_landscape,
    handle_pipeline,
    handle_portfolio,
    handle_structured_query,
    handle_team_eval,
)

__all__ = [
    # intent
    "Intent",
    "MECHANISM_SYNONYMS",
    "detect_format_hint",
    "detect_intent",
    # context
    "build_conversation_context",
    "resolve_followup_question",
    # formatting
    "apply_chat_modes",
    "build_comparison_table",
    "build_visualizations",
    "coerce_bool",
    "compute_comparison_insights",
    "expand_topic_synonyms",
    "generate_followups",
    "normalize_scope",
    "resolve_entity",
    "safe_filename",
    "sanitize_transcript",
    "to_number",
    # handlers
    "handle_compare",
    "handle_deep_research",
    "handle_dossier",
    "handle_general",
    "handle_landscape",
    "handle_pipeline",
    "handle_portfolio",
    "handle_structured_query",
    "handle_team_eval",
]
