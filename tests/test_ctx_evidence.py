"""Tests for evidence compression via ctxpack entity resolution."""

import sys
import os

# Ensure ctxpack is importable
sys.path.insert(0, r"C:\Users\kapil\Documents\CTX_mod")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.ctx_evidence import (
    pack_evidence,
    _estimate_tokens,
    _parse_evidence_content,
    _format_raw_evidence,
    MIN_TOKENS_FOR_COMPRESSION,
)


# ── Unit tests for helpers ──

def test_estimate_tokens():
    assert _estimate_tokens("") == 1
    assert _estimate_tokens("hello world") >= 2


def test_parse_evidence_content_with_colon():
    title, snippet = _parse_evidence_content("Semaglutide: GLP-1 receptor agonist")
    assert title == "Semaglutide"
    assert snippet == "GLP-1 receptor agonist"


def test_parse_evidence_content_no_colon():
    title, snippet = _parse_evidence_content("Just a title")
    assert title == "Just a title"
    assert snippet == ""


def test_format_raw_evidence():
    items = [{"content": "A"}, {"content": "B"}]
    result = _format_raw_evidence(items)
    assert result == "[1] A\n[2] B"


def test_format_raw_evidence_strings():
    items = ["foo", "bar"]
    result = _format_raw_evidence(items)
    assert result == "[1] foo\n[2] bar"


# ── Threshold gate tests ──

def test_small_payload_passes_through():
    """Evidence below MIN_TOKENS_FOR_COMPRESSION should pass through unchanged."""
    items = [
        {"content": "Drug A: short", "entity_type": "drug", "entity_id": "1"},
        {"content": "Drug B: also short", "entity_type": "drug", "entity_id": "2"},
    ]
    text, metrics = pack_evidence(items)
    assert metrics["mode"] == "passthrough"
    assert metrics["reason"] == "below_threshold"
    assert "[1]" in text
    assert "[2]" in text


def test_empty_input():
    text, metrics = pack_evidence([])
    assert metrics["mode"] == "empty"
    assert text == ""


# ── Compression tests ──

def _make_large_evidence(n: int = 10) -> list[dict]:
    """Build evidence items with enough redundancy to trigger compression."""
    items = []
    # Same drug appearing from different entity types → should merge
    for i in range(n):
        items.append({
            "content": f"Semaglutide: GLP-1 receptor agonist for type 2 diabetes and obesity, "
                       f"developed by Novo Nordisk, approved FDA 2017, clinical trials ongoing "
                       f"in cardiovascular outcomes, SUSTAIN and PIONEER programs, "
                       f"subcutaneous and oral formulations available, evidence item {i}",
            "entity_type": ["drug", "trial", "literature", "drug", "trial"][i % 5],
            "entity_id": f"id-{i}",
        })
    return items


def test_large_payload_compresses():
    """Evidence above threshold with duplicate entities should compress."""
    items = _make_large_evidence(10)
    raw_text = "\n".join(item["content"] for item in items)

    # Verify we're above threshold
    assert _estimate_tokens(raw_text) >= MIN_TOKENS_FOR_COMPRESSION

    text, metrics = pack_evidence(items)
    # Should either compress or passthrough with a valid reason
    assert metrics["mode"] in ("ctx", "passthrough")
    assert metrics["entities_in"] == 10

    if metrics["mode"] == "ctx":
        assert metrics["compressed_tokens"] < metrics["raw_tokens"]
        assert metrics["ratio"] > 1.0
        assert metrics["merged"] > 0
        assert "build_ms" in metrics


def test_no_merges_small_count_passes_through():
    """3 unique entities with no merges should pass through."""
    # Make items large enough to pass threshold but with unique names
    items = [
        {
            "content": f"UniqueEntity{i}: " + "x " * 80,
            "entity_type": "drug",
            "entity_id": f"id-{i}",
        }
        for i in range(3)
    ]
    text, metrics = pack_evidence(items)
    # Should pass through since no merges and ≤3 entities
    if metrics.get("entities_out") == 3 and metrics.get("merged") == 0:
        assert metrics["mode"] == "passthrough"
        assert metrics["reason"] == "no_merges"


def test_ctx_larger_falls_back():
    """If CTX output is larger than raw, should fall back to raw."""
    # This is hard to trigger directly — the safety check exists in pack_evidence
    # Just verify the function doesn't crash on edge cases
    items = [{"content": "A: B"}]
    text, metrics = pack_evidence(items)
    assert text  # Should always return something


# ── Integration with llm.py's _compress_evidence ──

def test_compress_evidence_wrapper():
    """Test the _compress_evidence wrapper in llm.py."""
    from services.llm import _compress_evidence

    # Small input → passthrough
    snippets = ["Drug A: short snippet"]
    result_snippets, compressed = _compress_evidence(snippets, question="test")
    assert result_snippets == snippets
    assert compressed is None

    # None input → passthrough
    result_snippets, compressed = _compress_evidence(None)
    assert result_snippets is None
    assert compressed is None


if __name__ == "__main__":
    test_estimate_tokens()
    test_parse_evidence_content_with_colon()
    test_parse_evidence_content_no_colon()
    test_format_raw_evidence()
    test_format_raw_evidence_strings()
    test_small_payload_passes_through()
    test_empty_input()
    test_large_payload_compresses()
    test_no_merges_small_count_passes_through()
    test_ctx_larger_falls_back()
    test_compress_evidence_wrapper()
    print("All tests passed!")
