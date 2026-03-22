"""Intent detection for the chat orchestration endpoint.

Classifies natural language questions into structured intents with extracted params.
"""

from __future__ import annotations

import re


class Intent:
    DEEP_RESEARCH = "deep_research"
    DOSSIER = "dossier"
    COMPARE = "compare"
    LANDSCAPE = "landscape"
    PORTFOLIO = "portfolio"
    PIPELINE = "pipeline"
    STRUCTURED_QUERY = "structured_query"
    TEAM_EVAL = "team_eval"
    GENERAL = "general"


MECHANISM_SYNONYMS = {
    "glp-1": "Glucagon-Like Peptide-1",
    "glp1": "Glucagon-Like Peptide-1",
    "sglt2": "Sodium-Glucose Transporter 2",
    "sglt-2": "Sodium-Glucose Transporter 2",
    "dpp-4": "Dipeptidyl-Peptidase IV",
    "dpp4": "Dipeptidyl-Peptidase IV",
    "ace inhibitor": "Angiotensin-Converting Enzyme",
    "arb": "Angiotensin II Type 1 Receptor",
    "beta blocker": "Adrenergic beta-Antagonist",
    "pde": "Phosphodiesterase",
    "mra": "Mineralocorticoid Receptor",
}


def detect_format_hint(question: str) -> str | None:
    """Detect if the user explicitly asks for a specific output format."""
    q = question.lower()
    if re.search(r'\b(table|tabular|rows|columns|spreadsheet|csv|breakdown|list all|show all|data export)\b', q):
        return "table"
    if re.search(r'\b(chart|graph|plot|visualize|bar chart|pie chart|histogram)\b', q):
        return "chart"
    return None


def detect_intent(question: str) -> tuple[str, dict]:
    """Classify question into an intent with extracted params."""
    q = question.lower().strip()

    # ── Guard: detect article / study titles (contain colon or long phrases) ──
    # If the query looks like a paper title, treat as general lookup rather than
    # letting "versus" trigger a drug comparison.
    _looks_like_title = (
        (':' in q and len(q) > 60)
        or re.search(r'(?:study|trial|randomized|multicenter|real-world|meta-analysis|systematic review)\b', q)
    )

    # Compare: "compare X vs Y", "X versus Y", "X and Y comparison"
    # Skip if query looks like a literature title.
    vs_match = re.search(
        r'(?:compare\s+)?(.+?)\s+(?:vs\.?|versus|compared?\s+(?:to|with))\s+(.+?)(?:\s+in\s+|\?|$)',
        q
    )
    if not _looks_like_title and (vs_match or ('compare' in q and 'landscape' not in q)):
        if vs_match:
            return Intent.COMPARE, {"entities": [vs_match.group(1).strip(), vs_match.group(2).strip()]}
        return Intent.COMPARE, {"entities": []}

    # Landscape: "competitive landscape", "market landscape", "GLP-1 landscape"
    # Must come before dossier to avoid "what is the competitive landscape" -> dossier
    if any(w in q for w in ['landscape', 'competitive', 'market segments', 'market overview']):
        # Extract topic: "GLP-1 landscape" → "GLP-1", "competitive landscape for diabetes" → "diabetes"
        topic = ""
        topic_match = re.search(r'(?:landscape|competitive|market\s+(?:segments|overview))\s+(?:for|in|of)\s+(.+?)(?:\?|$)', q)
        if topic_match:
            topic = topic_match.group(1).strip()
        else:
            # Try prefix: "GLP-1 landscape", "obesity competitive landscape"
            prefix_match = re.search(r'^(.+?)\s+(?:landscape|competitive|market)', q)
            if prefix_match:
                topic = prefix_match.group(1).strip()
                # Strip filler words
                topic = re.sub(r'^(?:show\s+me\s+(?:the\s+)?|what\s+is\s+(?:the\s+)?|the\s+|tabular\s+(?:breakdown\s+(?:of\s+)?)?(?:the\s+)?)', '', topic).strip()
        return Intent.LANDSCAPE, {"topic": topic}

    # Portfolio: "company portfolio", "Novo Nordisk portfolio"
    if 'portfolio' in q:
        name_match = re.search(r'(\w[\w\s]+?)\s+portfolio', q)
        return Intent.PORTFOLIO, {"company_name": name_match.group(1).strip() if name_match else ""}

    # Pipeline: "pipeline", "drug pipeline", "obesity pipeline", "heart failure pipeline"
    if 'pipeline' in q:
        ta_match = re.search(r'(.+?)\s+pipeline', q)
        ta = ta_match.group(1).strip() if ta_match else ""
        # Strip leading filler words
        ta = re.sub(r'^(?:show\s+me\s+(?:the\s+)?|what\s+is\s+(?:the\s+)?|the\s+|drug\s+)', '', ta).strip()
        return Intent.PIPELINE, {"therapeutic_area": ta}

    # Structured query: signals that need SQL-computed answers
    try:
        from services.agent.graphs.query_graph import has_structured_signals
        if has_structured_signals(q):
            return Intent.STRUCTURED_QUERY, {}
    except ImportError:
        pass

    # Dossier: "tell me about X", "dossier on X", "what is X"
    dossier_match = re.search(
        r'(?:tell me about|dossier on|what is|who is|describe|profile of|about)\s+(.+?)(?:\?|$)',
        q
    )
    if dossier_match:
        return Intent.DOSSIER, {"entity_name": dossier_match.group(1).strip()}

    # Bare entity name fallback: if the query is short (1-4 words) and doesn't
    # look like a question, treat it as a dossier request. This catches queries
    # like "semaglutide", "Novo Nordisk", "tirzepatide obesity" etc.
    word_count = len(q.split())
    if 1 <= word_count <= 4 and not re.search(r'\b(how|why|when|where|which|what|who|is|are|do|does|can|show|list|get)\b', q):
        return Intent.DOSSIER, {"entity_name": q}

    return Intent.GENERAL, {}
