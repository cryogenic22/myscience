"""SEC 8-K Item 5.02 parser → exec_change events.

SPEC-016 §7 swimlane A2.1.

Three responsibilities:

  1. detect_item_5_02_blocks(text) — rule-based header detection that
     pulls out the Item 5.02 narrative section (or sections, on
     compound filings) without needing an LLM. Returns the raw block
     text for downstream extraction.

  2. parse_item_5_02(text, extractor) — orchestrates: detect blocks →
     call the extractor protocol on each → flatten + return list of
     ExecChangeExtraction. Catches extractor errors per-block so one
     bad block doesn't kill the whole filing.

  3. assign_transition_ids(items, company_id) — pairs related departure
     + appointment events (within 90d, same functional area, or named
     successor match) under a shared transition_id. Solo events still
     get their own ID so downstream rows can reference one consistently.

The extractor argument is a Protocol — any object with `.extract(block)
-> list[ExecChangeExtraction]`. Tests use a deterministic stub; the real
LLM wrapper sits in services/extraction_llm.py (added in a follow-up).
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import date, timedelta
from typing import Protocol

from services.extraction.exec_change import ExecChangeExtraction

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────
# 1. Header detection
# ────────────────────────────────────────────────────────────────────

# Item 5.02 header — case-insensitive, allows whitespace variants
_ITEM_5_02_START = re.compile(
    r"^Item\s+5\.02\b[^\n]*",
    re.IGNORECASE | re.MULTILINE,
)

# Any other Item header — used to find the END of the 5.02 block.
# Matches "Item N.NN" where N != 5.02 specifically (we don't want
# "Item 5.02" itself to terminate its own block).
_ANY_ITEM_HEADER = re.compile(
    r"^Item\s+(\d+)\.(\d+)\b",
    re.IGNORECASE | re.MULTILINE,
)


def detect_item_5_02_blocks(text: str) -> list[str]:
    """Return narrative blocks for each Item 5.02 occurrence in the filing.

    Empty list if Item 5.02 is not present. Each block is the text from
    the Item 5.02 header (inclusive) to the next non-5.02 Item header
    (exclusive), trimmed.

    Most filings have 0 or 1 occurrence. Compound filings (e.g.
    departure + appointment of successor disclosed together) appear as a
    SINGLE Item 5.02 block with subsection markers (b), (c), (d) inside —
    the LLM extractor handles those.
    """
    if not text:
        return []

    blocks: list[str] = []
    for start_match in _ITEM_5_02_START.finditer(text):
        start = start_match.start()

        # Find the next Item header that is NOT another 5.02 (rare but
        # possible on amendments). We can scan from the START of the
        # current 5.02 header line + the length of "Item 5.02" to skip
        # the header itself.
        scan_from = start_match.end()
        end = len(text)
        for m in _ANY_ITEM_HEADER.finditer(text, pos=scan_from):
            major, minor = m.group(1), m.group(2)
            if (major, minor) != ("5", "02"):
                end = m.start()
                break

        block = text[start:end].strip()
        if block:
            blocks.append(block)

    return blocks


# ────────────────────────────────────────────────────────────────────
# 2. Parser orchestration
# ────────────────────────────────────────────────────────────────────


class ExecChangeExtractor(Protocol):
    """Protocol for the LLM (or stub) that turns a narrative block into
    a list of ExecChangeExtraction rows."""

    def extract(self, block: str) -> list[ExecChangeExtraction]:
        ...


def parse_item_5_02(
    text: str,
    *,
    extractor: ExecChangeExtractor,
) -> list[ExecChangeExtraction]:
    """Top-level parser. Detects blocks, runs the extractor on each,
    flattens results.

    Per-block exceptions are logged and swallowed — a malformed block
    never kills the parse for the rest of the filing.
    """
    blocks = detect_item_5_02_blocks(text)
    if not blocks:
        return []

    results: list[ExecChangeExtraction] = []
    for i, block in enumerate(blocks):
        try:
            extracted = extractor.extract(block)
        except Exception as exc:
            logger.warning(
                "Item 5.02 extractor failed on block %d: %s", i, exc,
            )
            continue
        if not extracted:
            continue
        # Defence in depth: enforce the schema even if the extractor
        # claims to return ExecChangeExtraction (it might be a stub or a
        # broken LLM wrapper that returns dicts).
        for ec in extracted:
            if isinstance(ec, ExecChangeExtraction):
                results.append(ec)
            else:
                try:
                    results.append(ExecChangeExtraction.model_validate(ec))
                except Exception as exc:
                    logger.warning(
                        "Skipping malformed ExecChangeExtraction: %s", exc,
                    )

    return results


# ────────────────────────────────────────────────────────────────────
# 3. transition_id pairing
# ────────────────────────────────────────────────────────────────────

# How long after a departure can we pair an appointment under the same
# transition? Exec searches typically take 30–90 days; 120 is the upper
# bound where pairing is still informative rather than coincidental.
_PAIRING_WINDOW = timedelta(days=120)


def _new_transition_id() -> str:
    return str(uuid.uuid4())


def assign_transition_ids(
    items: list[ExecChangeExtraction],
    *,
    company_id: str,
) -> list[ExecChangeExtraction]:
    """Pair related exit + arrival events under a shared transition_id.

    Pairing rules (in order):
      1. Departure that names a successor + appointment for that name →
         same transition_id.
      2. Otherwise: departure + appointment with same functional_area
         within ±_PAIRING_WINDOW → same transition_id (first match wins).
      3. All other items get a unique solo transition_id.

    Returns NEW Pydantic instances (does not mutate the input).
    """
    if not items:
        return []

    # Work on copies — Pydantic v2 models are immutable by default
    # (model_copy returns a new instance).
    out: list[ExecChangeExtraction] = [
        item.model_copy() for item in items
    ]

    # Index for quick lookup by index
    used: set[int] = set()

    # Rule 1 — explicit successor matches
    for i, dep in enumerate(out):
        if i in used:
            continue
        if dep.change_type != "departure" or not dep.successor_name:
            continue
        for j, app in enumerate(out):
            if j in used or i == j:
                continue
            if app.change_type != "appointment":
                continue
            if _names_match(dep.successor_name, app.person_name):
                tid = _new_transition_id()
                out[i] = out[i].model_copy(update={"transition_id": tid})
                out[j] = out[j].model_copy(update={"transition_id": tid})
                used.add(i)
                used.add(j)
                break

    # Rule 2 — same functional area, within window
    for i, dep in enumerate(out):
        if i in used:
            continue
        if dep.change_type != "departure" or not dep.functional_area:
            continue
        for j, app in enumerate(out):
            if j in used or i == j:
                continue
            if app.change_type != "appointment":
                continue
            if app.functional_area != dep.functional_area:
                continue
            if abs(app.effective_date - dep.effective_date) > _PAIRING_WINDOW:
                continue
            tid = _new_transition_id()
            out[i] = out[i].model_copy(update={"transition_id": tid})
            out[j] = out[j].model_copy(update={"transition_id": tid})
            used.add(i)
            used.add(j)
            break

    # Rule 3 — solo transition_ids for the unmatched
    for i, item in enumerate(out):
        if i in used:
            continue
        if item.transition_id is None:
            out[i] = out[i].model_copy(
                update={"transition_id": _new_transition_id()}
            )

    # company_id parameter currently unused but kept in signature so
    # the caller passes it consistently — future versions may scope
    # transition_id namespacing per company. Touch it to avoid lint.
    _ = company_id

    return out


def _names_match(a: str | None, b: str | None) -> bool:
    """Loose first-and-last name match. 'Mr. Lucas Montarce' matches
    'Lucas Montarce'. Empty / None on either side → False."""
    if not a or not b:
        return False
    a_norm = _normalise_for_match(a)
    b_norm = _normalise_for_match(b)
    if not a_norm or not b_norm:
        return False
    # Full match wins
    if a_norm == b_norm:
        return True
    # Last-name + first-initial fallback
    a_parts = a_norm.split()
    b_parts = b_norm.split()
    if len(a_parts) >= 2 and len(b_parts) >= 2:
        return a_parts[-1] == b_parts[-1] and a_parts[0][0] == b_parts[0][0]
    return False


_HONORIFIC = re.compile(
    r"^(?:Mr|Mrs|Ms|Dr|Prof|Professor|Sir)\.?\s+", re.IGNORECASE,
)
_DEGREE_SUFFIX = re.compile(
    r",?\s+(?:Ph\.?D\.?|M\.?D\.?|MBA|J\.?D\.?|Esq\.?)$", re.IGNORECASE,
)


def _normalise_for_match(name: str) -> str:
    s = _HONORIFIC.sub("", name).strip()
    s = _DEGREE_SUFFIX.sub("", s).strip()
    s = re.sub(r"\s+", " ", s)
    return s.lower()
