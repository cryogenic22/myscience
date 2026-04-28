"""SEC 8-K Item 8.01 parser → regulatory_crl events.

SPEC-016 §7 swimlane A2.4.

Item 8.01 ("Other Events") is the catch-all 8-K item. It carries CRLs
but also litigation, product launches, strategic statements, etc. The
parser uses a CRL-detection PRE-FILTER before invoking the LLM, so most
Item 8.01s short-circuit without burning extractor spend.

Filter is a simple keyword/phrase match — false positives are caught
by the LLM extractor (which returns []), false negatives are extremely
rare given the formal language companies use to disclose CRLs.

Future work (Phase 2): expand Item 8.01 parsing to other event types
(litigation_settlement, manufacturing_event, product_launch). Would
become a multi-classifier pre-filter.
"""

from __future__ import annotations

import logging
import re
from typing import Protocol

from services.extraction.regulatory_crl import CRLExtraction

logger = logging.getLogger(__name__)


_ITEM_8_01_START = re.compile(
    r"^Item\s+8\.01\b[^\n]*",
    re.IGNORECASE | re.MULTILINE,
)
_ANY_ITEM_HEADER = re.compile(
    r"^Item\s+(\d+)\.(\d+)\b",
    re.IGNORECASE | re.MULTILINE,
)


def detect_item_8_01_blocks(text: str) -> list[str]:
    """Return narrative blocks for each Item 8.01 occurrence."""
    if not text:
        return []
    blocks: list[str] = []
    for start_match in _ITEM_8_01_START.finditer(text):
        start = start_match.start()
        scan_from = start_match.end()
        end = len(text)
        for m in _ANY_ITEM_HEADER.finditer(text, pos=scan_from):
            major, minor = m.group(1), m.group(2)
            if (major, minor) != ("8", "01"):
                end = m.start()
                break
        block = text[start:end].strip()
        if block:
            blocks.append(block)
    return blocks


# ────────────────────────────────────────────────────────────────────
# CRL pre-filter — saves LLM spend on the ~80% of Item 8.01s that
# aren't CRLs (litigation, launches, etc.)
# ────────────────────────────────────────────────────────────────────

# Phrase patterns. Order doesn't matter — first match wins.
_CRL_PATTERNS: tuple[re.Pattern, ...] = (
    re.compile(r"complete\s+response\s+letter", re.IGNORECASE),
    re.compile(r"\bCRL\b"),
    re.compile(r"FDA\s+action[\s:]*complete\s+response", re.IGNORECASE),
)


def block_mentions_crl(block: str) -> bool:
    """True if `block` contains language indicating a CRL was received.

    Conservative — false positives go to the LLM, which returns [] on
    non-CRL text. False negatives (real CRL we miss) are rare because
    companies use formal phrasing.
    """
    if not block:
        return False
    return any(p.search(block) for p in _CRL_PATTERNS)


# ────────────────────────────────────────────────────────────────────
# Parser orchestration
# ────────────────────────────────────────────────────────────────────


class CRLExtractor(Protocol):
    def extract(self, block: str) -> list[CRLExtraction]:
        ...


def parse_item_8_01(
    text: str,
    *,
    extractor: CRLExtractor,
) -> list[CRLExtraction]:
    """Top-level Item 8.01 parser focused on CRL detection.

    Pipeline:
      1. detect_item_8_01_blocks
      2. block_mentions_crl filter — skip non-CRL blocks BEFORE LLM
      3. extractor.extract per qualifying block
      4. flatten results

    Per-block error isolation. Defence-in-depth schema validation.
    """
    blocks = detect_item_8_01_blocks(text)
    if not blocks:
        return []

    results: list[CRLExtraction] = []
    for i, block in enumerate(blocks):
        if not block_mentions_crl(block):
            continue
        try:
            extracted = extractor.extract(block)
        except Exception as exc:
            logger.warning(
                "Item 8.01 CRL extractor failed on block %d: %s", i, exc,
            )
            continue
        if not extracted:
            continue
        for c in extracted:
            if isinstance(c, CRLExtraction):
                results.append(c)
            else:
                try:
                    results.append(CRLExtraction.model_validate(c))
                except Exception as exc:
                    logger.warning(
                        "Skipping malformed CRLExtraction: %s", exc,
                    )

    return results
