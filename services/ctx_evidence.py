"""Evidence compression via ctxpack entity resolution.

Compresses redundant evidence snippets (from HybridSearch across multiple
entity tables) by routing them through ctxpack's entity resolver and
compressor. Evidence items mentioning the same drug/company/trial from
different tables get merged into a single entity section with deduplicated
fields.

Includes a token threshold gate: payloads below MIN_TOKENS_FOR_COMPRESSION
pass through unchanged — CTX adds overhead on small payloads.

Usage:
    from services.ctx_evidence import pack_evidence

    compressed, metrics = pack_evidence(evidence_items, question="...")
    # compressed: str  — either raw numbered list or .ctx L2 text
    # metrics: dict    — mode, token counts, compression ratio, timings
"""

from __future__ import annotations

import logging
import sys
import time
from typing import Optional

logger = logging.getLogger(__name__)

# ── ctxpack path setup ──

_CTX_MOD_PATH = r"C:\Users\kapil\Documents\CTX_mod"
if _CTX_MOD_PATH not in sys.path:
    sys.path.insert(0, _CTX_MOD_PATH)

try:
    from ctxpack.core.packer.ir import (
        IRCorpus, IREntity, IRField, IRSource,
    )
    from ctxpack.core.packer.entity_resolver import resolve_entities
    from ctxpack.core.packer.compressor import compress
    from ctxpack.core.serializer import serialize
    CTXPACK_AVAILABLE = True
except ImportError:
    CTXPACK_AVAILABLE = False
    logger.warning("ctxpack not available — evidence compression disabled")


# ── Configuration ──

# Skip compression for payloads below this token count.
# CTX AST overhead (~50 tokens for header + section markers) makes
# compression counterproductive on small inputs.
MIN_TOKENS_FOR_COMPRESSION = 300


# ── Helpers ──

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return max(1, len(text) // 4)


def _format_raw_evidence(items: list[dict | str], max_items: int = 10) -> str:
    """Format evidence as a plain numbered list (passthrough mode)."""
    lines = []
    for i, item in enumerate(items[:max_items], 1):
        content = item.get("content", "") if isinstance(item, dict) else str(item)
        lines.append(f"[{i}] {content}")
    return "\n".join(lines)


def _parse_evidence_content(content: str) -> tuple[str, str]:
    """Parse 'Title: snippet' format into (title, snippet).

    HybridSearch produces evidence as 'EntityTitle: description snippet'.
    Split on first ': ' to extract structured fields.
    """
    if ": " in content:
        title, _, snippet = content.partition(": ")
        return title.strip(), snippet.strip()
    return content.strip(), ""


# ── Main API ──

def pack_evidence(
    evidence_items: list[dict | str],
    question: str = "",
    max_items: int = 10,
) -> tuple[str, dict]:
    """Compress evidence snippets through ctxpack entity resolution.

    Takes evidence items from HybridSearch (via QueryEngine/chat.py) and:
    1. Checks token threshold — small payloads pass through unchanged
    2. Converts items to ctxpack IREntity objects grouped by entity_type
    3. Runs entity resolution (name normalization + merge + field dedup)
    4. Compresses to L2 CTX notation
    5. Returns compressed text + metrics dict

    Args:
        evidence_items: List of EvidenceItem-like dicts with keys:
            - content (str): "Title: snippet" text
            - entity_type (str): "drug", "trial", "literature", etc.
            - entity_id (str): UUID or name
            - provenance (dict, optional): source tracking
            Or plain strings (content only).
        question: The user's query (used for salience scoring).
        max_items: Maximum items to process.

    Returns:
        (compressed_text, metrics_dict) where metrics_dict contains:
            mode: "passthrough" | "ctx" | "fallback"
            raw_tokens: token count before compression
            compressed_tokens: token count after (only in ctx mode)
            ratio: compression ratio (only in ctx mode)
            entities_in: number of input items
            entities_out: number after merge (only in ctx mode)
            build_ms: compression latency (only in ctx mode)
    """
    items = evidence_items[:max_items]
    if not items:
        return "", {"mode": "empty", "raw_tokens": 0}

    # Format raw version for threshold check and fallback
    raw_text = _format_raw_evidence(items, max_items)
    raw_tokens = _estimate_tokens(raw_text)

    # ── Threshold gate ──
    if raw_tokens < MIN_TOKENS_FOR_COMPRESSION:
        logger.debug(
            "Evidence below threshold (%d < %d tokens), passing through",
            raw_tokens, MIN_TOKENS_FOR_COMPRESSION,
        )
        return raw_text, {
            "mode": "passthrough",
            "raw_tokens": raw_tokens,
            "entities_in": len(items),
            "reason": "below_threshold",
        }

    if not CTXPACK_AVAILABLE:
        return raw_text, {
            "mode": "fallback",
            "raw_tokens": raw_tokens,
            "entities_in": len(items),
            "reason": "ctxpack_unavailable",
        }

    # ── Build IR entities from evidence items ──
    try:
        t0 = time.perf_counter()

        entities: list[IREntity] = []
        for item in items:
            if isinstance(item, dict):
                content = item.get("content", "")
                etype = item.get("entity_type", "evidence")
                eid = item.get("entity_id", "")
            else:
                content = str(item)
                etype = "evidence"
                eid = ""

            if not content:
                continue

            title, snippet = _parse_evidence_content(content)
            source = IRSource(file="search")

            # Build fields from parsed content
            fields: list[IRField] = []
            if title:
                fields.append(IRField(
                    key="name", value=title, raw_value=title, source=source,
                ))
            if snippet:
                fields.append(IRField(
                    key="description", value=snippet, raw_value=snippet, source=source,
                ))
            if eid:
                fields.append(IRField(
                    key="id", value=str(eid), raw_value=str(eid), source=source,
                ))

            # Use title as entity name for resolution (duplicates merge here)
            entity_name = title if title else f"{etype}_{len(entities)}"

            entities.append(IREntity(
                name=entity_name,
                fields=fields,
                annotations={"entity_type": etype},
                sources=[source],
            ))

        if not entities:
            return raw_text, {
                "mode": "fallback",
                "raw_tokens": raw_tokens,
                "entities_in": len(items),
                "reason": "no_parseable_entities",
            }

        # ── Entity resolution: merge duplicates ──
        corpus = IRCorpus(
            domain="pharma-intelligence",
            scope="evidence",
            entities=entities,
            source_token_count=raw_tokens,
        )
        resolve_entities(corpus)

        entities_after = len(corpus.entities)
        merged_count = len(items) - entities_after

        # If no merges happened and few entities, skip compression
        # (overhead of CTX header > savings)
        if merged_count == 0 and entities_after <= 3:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.debug(
                "No entity merges and ≤3 entities, skipping CTX (%.1fms)",
                elapsed,
            )
            return raw_text, {
                "mode": "passthrough",
                "raw_tokens": raw_tokens,
                "entities_in": len(items),
                "entities_out": entities_after,
                "merged": 0,
                "reason": "no_merges",
                "build_ms": round(elapsed, 2),
            }

        # ── Compress to CTX AST ──
        doc = compress(corpus)
        ctx_text = serialize(doc, ascii_mode=True)

        elapsed = (time.perf_counter() - t0) * 1000
        ctx_tokens = _estimate_tokens(ctx_text)

        # Safety check: if CTX is larger than raw, fall back
        if ctx_tokens >= raw_tokens:
            logger.info(
                "CTX evidence larger than raw (%d >= %d tokens), using raw",
                ctx_tokens, raw_tokens,
            )
            return raw_text, {
                "mode": "passthrough",
                "raw_tokens": raw_tokens,
                "ctx_tokens": ctx_tokens,
                "entities_in": len(items),
                "entities_out": entities_after,
                "merged": merged_count,
                "reason": "ctx_larger",
                "build_ms": round(elapsed, 2),
            }

        ratio = round(raw_tokens / max(ctx_tokens, 1), 2)
        logger.info(
            "Evidence compressed: %d → %d tokens (%.1fx), %d entities merged, %.1fms",
            raw_tokens, ctx_tokens, ratio, merged_count, elapsed,
        )

        return ctx_text, {
            "mode": "ctx",
            "raw_tokens": raw_tokens,
            "compressed_tokens": ctx_tokens,
            "ratio": ratio,
            "entities_in": len(items),
            "entities_out": entities_after,
            "merged": merged_count,
            "build_ms": round(elapsed, 2),
        }

    except Exception as e:
        logger.warning("Evidence compression failed, using raw: %s", e)
        return raw_text, {
            "mode": "fallback",
            "raw_tokens": raw_tokens,
            "entities_in": len(items),
            "reason": str(e),
        }
