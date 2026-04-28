"""SEC 8-K Item 1.01 parser → deal_announced events.

SPEC-016 §7 swimlane A2.2.

Mirrors the A2.1 architecture exactly:
  - detect_item_1_01_blocks(text) — rule-based header detection
  - parse_item_1_01(text, extractor) — orchestrate via Protocol
  - per-block error isolation
"""

from __future__ import annotations

import logging
import re
from typing import Protocol

from services.extraction.deal_announced import DealExtraction

logger = logging.getLogger(__name__)


_ITEM_1_01_START = re.compile(
    r"^Item\s+1\.01\b[^\n]*",
    re.IGNORECASE | re.MULTILINE,
)
_ANY_ITEM_HEADER = re.compile(
    r"^Item\s+(\d+)\.(\d+)\b",
    re.IGNORECASE | re.MULTILINE,
)


def detect_item_1_01_blocks(text: str) -> list[str]:
    """Return narrative blocks for each Item 1.01 occurrence.

    Empty list if not present. Each block runs from the Item 1.01 header
    to the next non-1.01 Item header.
    """
    if not text:
        return []

    blocks: list[str] = []
    for start_match in _ITEM_1_01_START.finditer(text):
        start = start_match.start()
        scan_from = start_match.end()
        end = len(text)
        for m in _ANY_ITEM_HEADER.finditer(text, pos=scan_from):
            major, minor = m.group(1), m.group(2)
            if (major, minor) != ("1", "01"):
                end = m.start()
                break
        block = text[start:end].strip()
        if block:
            blocks.append(block)

    return blocks


class DealExtractor(Protocol):
    def extract(self, block: str) -> list[DealExtraction]:
        ...


def parse_item_1_01(
    text: str,
    *,
    extractor: DealExtractor,
) -> list[DealExtraction]:
    """Top-level Item 1.01 parser. Same shape as parse_item_5_02."""
    blocks = detect_item_1_01_blocks(text)
    if not blocks:
        return []

    results: list[DealExtraction] = []
    for i, block in enumerate(blocks):
        try:
            extracted = extractor.extract(block)
        except Exception as exc:
            logger.warning("Item 1.01 extractor failed on block %d: %s", i, exc)
            continue
        if not extracted:
            continue
        for d in extracted:
            if isinstance(d, DealExtraction):
                results.append(d)
            else:
                try:
                    results.append(DealExtraction.model_validate(d))
                except Exception as exc:
                    logger.warning(
                        "Skipping malformed DealExtraction: %s", exc,
                    )

    return results
