"""SEC 8-K Item 2.02 parser → financial + guidance events.

SPEC-016 §7 swimlane A2.3.

Same architecture as A2.1/A2.2:
  - detect_item_2_02_blocks(text) — rule-based header detection
  - parse_item_2_02(text, extractor) — orchestrate via Protocol

The extractor returns a TUPLE — (FinancialDisclosureExtraction | None,
list[GuidanceIssuance]) — because one Item 2.02 typically produces
both: a period-level disclosure plus 0..N guidance issuances.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional, Protocol

from services.extraction.financial_disclosure import (
    FinancialDisclosureExtraction,
    GuidanceIssuance,
)

logger = logging.getLogger(__name__)


_ITEM_2_02_START = re.compile(
    r"^Item\s+2\.02\b[^\n]*",
    re.IGNORECASE | re.MULTILINE,
)
_ANY_ITEM_HEADER = re.compile(
    r"^Item\s+(\d+)\.(\d+)\b",
    re.IGNORECASE | re.MULTILINE,
)


def detect_item_2_02_blocks(text: str) -> list[str]:
    """Return narrative blocks for each Item 2.02 occurrence."""
    if not text:
        return []
    blocks: list[str] = []
    for start_match in _ITEM_2_02_START.finditer(text):
        start = start_match.start()
        scan_from = start_match.end()
        end = len(text)
        for m in _ANY_ITEM_HEADER.finditer(text, pos=scan_from):
            major, minor = m.group(1), m.group(2)
            if (major, minor) != ("2", "02"):
                end = m.start()
                break
        block = text[start:end].strip()
        if block:
            blocks.append(block)
    return blocks


@dataclass
class Item202ParseResult:
    """Single combined return from Item 2.02 parsing."""

    financial_disclosure: Optional[FinancialDisclosureExtraction]
    guidance_issuances: list[GuidanceIssuance]


class FinancialExtractor(Protocol):
    """Returns (FinancialDisclosureExtraction | None, list[GuidanceIssuance])."""

    def extract(
        self, block: str,
    ) -> tuple[Optional[FinancialDisclosureExtraction], list[GuidanceIssuance]]:
        ...


def parse_item_2_02(
    text: str,
    *,
    extractor: FinancialExtractor,
) -> Item202ParseResult:
    """Top-level Item 2.02 parser.

    If the filing has multiple Item 2.02 blocks (rare), we use the first
    one's financial_disclosure and union the guidance issuances. Per-block
    extractor errors logged + swallowed.
    """
    blocks = detect_item_2_02_blocks(text)
    if not blocks:
        return Item202ParseResult(financial_disclosure=None, guidance_issuances=[])

    disclosure: Optional[FinancialDisclosureExtraction] = None
    guidances: list[GuidanceIssuance] = []

    for i, block in enumerate(blocks):
        try:
            f, g_list = extractor.extract(block)
        except Exception as exc:
            logger.warning(
                "Item 2.02 extractor failed on block %d: %s", i, exc,
            )
            continue

        if f is not None and disclosure is None:
            if isinstance(f, FinancialDisclosureExtraction):
                disclosure = f
            else:
                try:
                    disclosure = FinancialDisclosureExtraction.model_validate(f)
                except Exception as exc:
                    logger.warning("Bad FinancialDisclosure: %s", exc)

        for g in g_list or []:
            if isinstance(g, GuidanceIssuance):
                guidances.append(g)
            else:
                try:
                    guidances.append(GuidanceIssuance.model_validate(g))
                except Exception as exc:
                    logger.warning("Bad GuidanceIssuance: %s", exc)

    return Item202ParseResult(
        financial_disclosure=disclosure,
        guidance_issuances=guidances,
    )
