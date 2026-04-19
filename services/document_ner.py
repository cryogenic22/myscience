"""LLM-based Named Entity Recognition for SPEC_014 (document upload).

Extracts pharma entities (drug, company, trial, mechanism, therapeutic_area,
investigator) from free text using an LLM with structured JSON output.

Design notes:
  - The JSON-extraction-with-recovery helper is ported from Proto_Demo's
    `_extract_json` (`Proto_Demo/src/llm/client.py:466`). Recovery handles
    three failure modes:
      1. Whole-text json.loads (fast path)
      2. Fenced ```json ...``` blocks (with missing-close-fence tolerance)
      3. Truncation recovery for arrays (collect complete top-level objects
         when LLM hits max_tokens mid-array)
  - Long documents are chunked at `chunk_size` chars with `overlap` overlap.
  - Mentions are deduped across chunks by (text.lower(), entity_type).
  - Defensive: any LLM exception or malformed response returns []. Upload
    flow must never crash on NER failure.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ── Constants ──────────────────────────────────────────────────────

NER_PROMPT_TEMPLATE = """Identify all pharmaceutical entities in the text below.
Return ONLY a JSON object with a "mentions" array. Each mention has:
- text: the exact substring
- entity_type: one of [drug, company, trial, mechanism, therapeutic_area, investigator]
- start: character offset where the mention begins (0-indexed)
- end: character offset where the mention ends (exclusive)

Only include entities that are clearly named (not generic terms like "the drug").
Do not include explanatory text outside the JSON.

Text:
{text}
"""

VALID_ENTITY_TYPES = {
    "drug", "company", "trial", "mechanism",
    "therapeutic_area", "investigator", "literature",
}


# ── Models ─────────────────────────────────────────────────────────

@dataclass
class EntityMention:
    """A single entity mention extracted from text.

    Optional provenance fields (source_page, extraction_method) are populated
    by the upload pipeline so downstream entity resolution can audit how each
    mention was discovered (per SPEC_017 §1.3 ProvenanceInfo pattern).
    """
    text: str
    entity_type: str
    start: int
    end: int
    source_page: Optional[int] = None
    extraction_method: Optional[str] = None


# ── JSON extraction with recovery (ported from Proto_Demo) ─────────

def extract_json_with_recovery(raw: str) -> Any:
    """Extract first JSON value from an LLM response with truncation recovery.

    Ported pattern from Proto_Demo/src/llm/client.py::_extract_json. Tries:
      1. Whole-text json.loads
      2. Fenced ```json ...``` blocks (tolerates missing close fence)
      3. raw_decode from each [ or { (longest-valid-prefix)
      4. For arrays: collect every complete top-level object up to truncation

    Returns [] when nothing parses, so callers can use a single check.
    """
    if not raw or not isinstance(raw, str):
        return []
    text = raw.strip()
    if not text:
        return []

    # 1) Whole-text fast path
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2) Fenced code blocks
    candidates: list[str] = []
    if "```" in text:
        parts = text.split("```")
        # Odd-indexed parts are inside fences
        for part in parts[1::2]:
            content = part.strip()
            if content.lower().startswith("json"):
                content = content[4:].strip()
            candidates.append(content)
        # Tail after the last opening fence (in case close was truncated)
        last_open = text.rfind("```")
        if last_open >= 0:
            tail = text[last_open + 3:].strip()
            if tail.lower().startswith("json"):
                tail = tail[4:].strip()
            candidates.append(tail)

    # Always include full text as final fallback
    candidates.append(text)

    for candidate in candidates:
        result = _parse_with_recovery(candidate)
        if result is not None:
            return result

    logger.warning(
        "Could not extract JSON from response: %s...", text[:200]
    )
    return []


def _parse_with_recovery(text: str) -> Any:
    """Try plain parse → raw_decode → partial-array recovery."""
    if not text:
        return None
    text = text.strip()

    # Plain
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()

    # raw_decode from each [ or {
    for i, ch in enumerate(text):
        if ch not in ("[", "{"):
            continue
        try:
            obj, _ = decoder.raw_decode(text[i:])
            return obj
        except json.JSONDecodeError:
            if ch == "[":
                rescued = _rescue_partial_array(text[i:], decoder)
                if rescued is not None:
                    return rescued
            continue

    return None


def _rescue_partial_array(text: str, decoder: json.JSONDecoder) -> Optional[list]:
    """Walk an array character-by-character, collecting complete objects."""
    if not text.startswith("["):
        return None
    pos = 1  # past [
    items: list = []
    n = len(text)
    while pos < n:
        # Skip whitespace and commas
        while pos < n and text[pos] in " \t\n\r,":
            pos += 1
        if pos >= n or text[pos] == "]":
            break
        try:
            obj, end = decoder.raw_decode(text[pos:])
            items.append(obj)
            pos += end
        except json.JSONDecodeError:
            break  # truncation — return what we got
    return items if items else None


# ── Public NER API ─────────────────────────────────────────────────

def extract_entities(
    text: str,
    llm: Any = None,
    chunk_size: int = 12000,
    overlap: int = 500,
) -> list[EntityMention]:
    """Extract pharma entities from free text via LLM.

    Args:
        text: input text
        llm: object with .complete_json(prompt) -> dict|str. Pass None to
             gracefully no-op (returns []).
        chunk_size: max chars per LLM call (longer text is chunked)
        overlap: chars of overlap between chunks (preserves entity boundaries)

    Returns:
        Deduped list of EntityMention. Empty on any failure (defensive —
        upload pipeline must not crash).
    """
    if not text or not text.strip():
        return []
    if llm is None:
        return []

    chunks = _chunk_text(text, chunk_size, overlap)
    seen: set[tuple[str, str]] = set()
    out: list[EntityMention] = []

    for chunk in chunks:
        try:
            response = llm.complete_json(NER_PROMPT_TEMPLATE.format(text=chunk))
        except Exception as exc:
            logger.warning("LLM call failed during NER: %s", exc)
            continue

        # Handle both dict (already parsed) and str (raw text needing recovery)
        if isinstance(response, str):
            response = extract_json_with_recovery(response)
        if not isinstance(response, dict):
            continue

        mentions = response.get("mentions")
        if not isinstance(mentions, list):
            continue

        for m in mentions:
            if not isinstance(m, dict):
                continue
            text_val = m.get("text")
            etype = m.get("entity_type") or m.get("type")
            if not text_val or not etype:
                continue
            if etype not in VALID_ENTITY_TYPES:
                continue
            key = (text_val.lower().strip(), etype)
            if key in seen:
                continue
            seen.add(key)
            try:
                out.append(EntityMention(
                    text=text_val,
                    entity_type=etype,
                    start=int(m.get("start", 0)),
                    end=int(m.get("end", len(text_val))),
                    source_page=m.get("source_page"),
                    extraction_method="llm_ner",
                ))
            except (TypeError, ValueError):
                # Malformed offsets — skip rather than crash
                continue

    return out


def _chunk_text(text: str, size: int, overlap: int) -> list[str]:
    """Split text into overlapping chunks. Single chunk when text fits."""
    if len(text) <= size:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + size])
        start += max(1, size - overlap)
    return chunks
