"""CTX-based context assembly for LLM synthesis.

Replaces the ad-hoc _build_context_block with structured, multi-resolution
CTX documents that exploit salience ordering and lost-in-middle mitigation.

The threshold gate (MIN_TOKENS_FOR_CTX) handles small payloads by falling
back to legacy format automatically. Set MZ_CTX_MODE=legacy to force the
old format for debugging.

Usage:
    builder = CTXContextBuilder(mode="ctx")  # or "legacy"
    result = builder.build(question, intent, metrics=..., evidence=...)
    # result.text    — the assembled context string
    # result.tokens  — estimated token count
"""

from __future__ import annotations

import json
import logging
import sys
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── Token threshold ──
# Skip CTX AST reformatting when the source payload is below this token count.
# CTX header + section markers add ~50 tokens of overhead, making compression
# counterproductive on small inputs (the "11% larger" problem).
MIN_TOKENS_FOR_CTX = 300

# Add ctxpack to path if not installed




try:
    from ctxpack.core.model import (
        CTXDocument, Header, Layer, Section, KeyValue,
        PlainLine, Provenance,
    )
    from ctxpack.core.serializer import serialize
    CTX_AVAILABLE = True
except ImportError:
    CTX_AVAILABLE = False
    logger.warning("ctxpack not available — CTX context pipeline disabled")


# ── Token estimation ──

def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English."""
    return max(1, len(text) // 4)


# ── Result dataclass ──

@dataclass
class ContextResult:
    """Result of context assembly with benchmarking metrics."""
    text: str                          # The assembled context string for LLM
    mode: str                          # "ctx" or "legacy"
    tokens: int = 0                    # Estimated token count
    source_tokens: int = 0             # Tokens before compression
    compression_ratio: float = 1.0     # source_tokens / tokens
    build_time_ms: float = 0.0         # Assembly latency
    sections: int = 0                  # Number of CTX sections (ctx mode)


# ── Legacy context builder (current approach) ──

def _build_legacy_context(
    question: str,
    intent: str,
    entity_info: Optional[dict] = None,
    metrics: Optional[dict] = None,
    graph_summary: Optional[dict] = None,
    evidence_snippets: Optional[list[str]] = None,
    extra_context: Optional[str] = None,
) -> ContextResult:
    """Original flat JSON context assembly (baseline for comparison)."""
    t0 = time.perf_counter()

    parts = [f"USER QUESTION: {question}", f"INTENT: {intent}"]
    if entity_info:
        parts.append(f"ENTITY: {json.dumps(entity_info, default=str)}")
    if metrics:
        parts.append(f"METRICS: {json.dumps(metrics, default=str)}")
    if graph_summary:
        parts.append(f"GRAPH CONTEXT: {json.dumps(graph_summary, default=str)}")
    if evidence_snippets:
        parts.append("EVIDENCE:")
        for i, snippet in enumerate(evidence_snippets[:10], 1):
            parts.append(f"  [{i}] {snippet}")
    if extra_context:
        parts.append(f"ADDITIONAL CONTEXT: {extra_context}")

    text = "\n\n".join(parts)
    elapsed = (time.perf_counter() - t0) * 1000
    tokens = _estimate_tokens(text)

    return ContextResult(
        text=text,
        mode="legacy",
        tokens=tokens,
        source_tokens=tokens,
        compression_ratio=1.0,
        build_time_ms=elapsed,
        sections=0,
    )


# ── CTX context builder ──

def _build_ctx_context(
    question: str,
    intent: str,
    entity_info: Optional[dict] = None,
    metrics: Optional[dict] = None,
    graph_summary: Optional[dict] = None,
    evidence_snippets: Optional[list[str]] = None,
    extra_context: Optional[str] = None,
) -> ContextResult:
    """Build structured CTX L2 context with salience ordering.

    Layout (lost-in-middle mitigation):
      START:  High-salience — question, intent, key entity, warnings
      MIDDLE: Medium-salience — metrics, graph, evidence
      END:    High-salience — constraints, extra context, rules
    """
    if not CTX_AVAILABLE:
        return _build_legacy_context(
            question, intent, entity_info, metrics,
            graph_summary, evidence_snippets, extra_context,
        )

    # Estimate source tokens from raw inputs
    raw_parts = [question, intent]
    if entity_info:
        raw_parts.append(json.dumps(entity_info, default=str))
    if metrics:
        raw_parts.append(json.dumps(metrics, default=str))
    if graph_summary:
        raw_parts.append(json.dumps(graph_summary, default=str))
    if evidence_snippets:
        raw_parts.extend(evidence_snippets[:10])
    if extra_context:
        raw_parts.append(extra_context)
    source_tokens = _estimate_tokens("\n".join(raw_parts))

    # ── Threshold gate: skip CTX for small payloads ──
    if source_tokens < MIN_TOKENS_FOR_CTX:
        logger.debug(
            "Source payload below CTX threshold (%d < %d tokens), using legacy",
            source_tokens, MIN_TOKENS_FOR_CTX,
        )
        return _build_legacy_context(
            question, intent, entity_info, metrics,
            graph_summary, evidence_snippets, extra_context,
        )

    t0 = time.perf_counter()

    # Build CTX document sections
    body_sections: list[Section | KeyValue | PlainLine] = []

    # ── START: High salience (question + entity) ──
    query_children: list = [
        KeyValue(key="QUESTION", value=question),
        KeyValue(key="INTENT", value=intent),
    ]
    body_sections.append(Section(
        name="QUERY",
        depth=0,
        children=tuple(query_children),
    ))

    if entity_info:
        entity_children: list = []
        name = entity_info.get("name", entity_info.get("generic_name", ""))
        etype = entity_info.get("type", "unknown")
        if name:
            entity_children.append(KeyValue(key="NAME", value=name))
        if etype:
            entity_children.append(KeyValue(key="TYPE", value=etype))

        # Add key properties in compact CTX notation
        skip_keys = {"name", "type", "generic_name"}
        for k, v in entity_info.items():
            if k in skip_keys or v is None:
                continue
            val = str(v) if not isinstance(v, (dict, list)) else json.dumps(v, default=str)
            # Truncate very long values
            if len(val) > 300:
                val = val[:297] + "..."
            entity_children.append(KeyValue(key=k.upper(), value=val))

        body_sections.append(Section(
            name=f"ENTITY-{etype.upper()}",
            subtitles=(name,) if name else (),
            depth=0,
            children=tuple(entity_children),
        ))

    # ── MIDDLE: Medium salience (metrics, graph, evidence) ──
    if metrics:
        metrics_children: list = []
        _flatten_metrics(metrics, metrics_children, max_depth=2)
        if metrics_children:
            body_sections.append(Section(
                name="METRICS",
                depth=0,
                children=tuple(metrics_children),
            ))

    if graph_summary:
        graph_children: list = [
            KeyValue(key="NODES", value=str(graph_summary.get("node_count", 0))),
            KeyValue(key="EDGES", value=str(graph_summary.get("edge_count", 0))),
        ]
        # Add connected entity labels (the key improvement over legacy)
        connected = graph_summary.get("connected_entities", {})
        if connected:
            for etype, labels in connected.items():
                if labels:
                    graph_children.append(
                        KeyValue(key=etype.upper(), value=" + ".join(labels[:8]))
                    )
        conn_by_type = graph_summary.get("connections_by_type", {})
        if conn_by_type:
            graph_children.append(
                KeyValue(key="LINK_TYPES", value=" + ".join(
                    f"{k}({v})" for k, v in conn_by_type.items()
                ))
            )
        body_sections.append(Section(
            name="GRAPH",
            depth=0,
            children=tuple(graph_children),
        ))

    if evidence_snippets:
        ev_children: list = []
        for i, snippet in enumerate(evidence_snippets[:10], 1):
            # Compress evidence: strip redundant whitespace, cap length
            compressed = " ".join(snippet.split())
            if len(compressed) > 250:
                compressed = compressed[:247] + "..."
            ev_children.append(PlainLine(text=f"[{i}] {compressed}"))
        body_sections.append(Section(
            name="EVIDENCE",
            depth=0,
            children=tuple(ev_children),
        ))

    # ── END: High salience (extra context, constraints) ──
    if extra_context:
        extra_children: list = []
        for line in extra_context.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            if ":" in line and not line.startswith("[") and not line.startswith("-"):
                k, _, v = line.partition(":")
                extra_children.append(KeyValue(key=k.strip().upper(), value=v.strip()))
            else:
                extra_children.append(PlainLine(text=line))
        if extra_children:
            body_sections.append(Section(
                name="CONTEXT",
                depth=0,
                children=tuple(extra_children),
            ))

    # Assemble document
    header = Header(
        magic="§CTX",
        version="1.0",
        layer=Layer.L2,
        status_fields=(
            KeyValue(key="DOMAIN", value="pharma-intelligence"),
            KeyValue(key="SOURCE_TOKENS", value=f"~{source_tokens}"),
        ),
        metadata=(
            KeyValue(key="SCOPE", value=f"{intent}-synthesis"),
        ),
    )

    doc = CTXDocument(header=header, body=tuple(body_sections))

    # Serialize with ASCII mode for maximum LLM compatibility
    ctx_text = serialize(doc, ascii_mode=True)
    elapsed = (time.perf_counter() - t0) * 1000
    compressed_tokens = _estimate_tokens(ctx_text)
    ratio = source_tokens / compressed_tokens if compressed_tokens > 0 else 1.0

    return ContextResult(
        text=ctx_text,
        mode="ctx",
        tokens=compressed_tokens,
        source_tokens=source_tokens,
        compression_ratio=round(ratio, 2),
        build_time_ms=elapsed,
        sections=len([s for s in body_sections if isinstance(s, Section)]),
    )


def _flatten_metrics(obj: dict, children: list, max_depth: int = 2, prefix: str = "") -> None:
    """Recursively flatten metrics dict into compact KeyValue pairs."""
    if max_depth <= 0:
        return
    for k, v in obj.items():
        key = f"{prefix}{k}".upper() if not prefix else f"{prefix}.{k}".upper()
        if isinstance(v, dict):
            # For nested dicts, try to create a single compact line
            if len(v) <= 5 and all(not isinstance(vv, (dict, list)) for vv in v.values()):
                compact = " ".join(f"{kk}:{vv}" for kk, vv in v.items() if vv is not None)
                if compact:
                    children.append(KeyValue(key=key, value=compact))
            else:
                _flatten_metrics(v, children, max_depth - 1, prefix=key + ".")
        elif isinstance(v, list):
            if len(v) <= 8 and all(isinstance(item, (str, int, float)) for item in v):
                children.append(KeyValue(key=key, value=" + ".join(str(item) for item in v)))
            elif v and isinstance(v[0], dict):
                # List of dicts (e.g., pipeline list) — show top 3 compactly
                for i, item in enumerate(v[:3]):
                    name = item.get("drug_name") or item.get("mechanism_name") or item.get("company_name") or f"#{i+1}"
                    compact_vals = []
                    for ik, iv in item.items():
                        if iv is not None and ik not in ("drug_id", "mechanism_id", "therapeutic_area_id", "company_id"):
                            compact_vals.append(f"{ik}:{iv}")
                    children.append(KeyValue(key=f"{key}.{name}", value=" ".join(compact_vals[:8])))
                if len(v) > 3:
                    children.append(PlainLine(text=f"... +{len(v)-3} more"))
        elif v is not None:
            children.append(KeyValue(key=key, value=str(v)))


# ── Main builder class ──

class CTXContextBuilder:
    """Context builder for LLM synthesis.

    Modes:
        "ctx"    — Use CTX pipeline (default), log metrics
        "legacy" — Use legacy flat-JSON pipeline (for debugging)
    """

    def __init__(self, mode: str = "ctx"):
        if mode == "ctx" and not CTX_AVAILABLE:
            logger.warning("CTX not available, falling back to legacy mode")
            mode = "legacy"
        self.mode = mode

    def build(
        self,
        question: str,
        intent: str,
        entity_info: Optional[dict] = None,
        metrics: Optional[dict] = None,
        graph_summary: Optional[dict] = None,
        evidence_snippets: Optional[list[str]] = None,
        extra_context: Optional[str] = None,
    ) -> ContextResult:
        """Build context and return a ContextResult.

        Respects MIN_TOKENS_FOR_CTX threshold — small payloads always use
        legacy format regardless of mode setting.
        """

        if self.mode == "legacy":
            return _build_legacy_context(
                question, intent, entity_info, metrics,
                graph_summary, evidence_snippets, extra_context,
            )

        # Default: CTX mode
        result = _build_ctx_context(
            question, intent, entity_info, metrics,
            graph_summary, evidence_snippets, extra_context,
        )
        logger.info(
            "CTX context: %d tokens (from ~%d source), ratio %.1fx, %.1fms, %d sections",
            result.tokens, result.source_tokens, result.compression_ratio,
            result.build_time_ms, result.sections,
        )
        return result
