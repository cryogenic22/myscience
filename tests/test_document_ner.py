"""SPEC_014 Phase 4c — LLM-based Document NER TDD test contract.

Tests for services/document_ner.py: extracts pharma entities (drug, company,
trial, mechanism, therapeutic_area, investigator) from free text using LLM
with structured JSON output.

Per SPEC_017 reuse catalog: ports JSON-extraction-with-recovery pattern
from Proto_Demo's _extract_json (`Proto_Demo/src/llm/client.py:466`).

All tests must FAIL before implementation. TDD discipline.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ────────────────────────────────────────────────────────────────────
# Module / class existence
# ────────────────────────────────────────────────────────────────────

def test_module_exists():
    from pathlib import Path
    assert Path("services/document_ner.py").exists()


def test_entity_mention_dataclass():
    from services.document_ner import EntityMention
    fields = set(EntityMention.__dataclass_fields__)
    required = {"text", "entity_type", "start", "end"}
    assert required.issubset(fields)


def test_extract_entities_function_exists():
    from services.document_ner import extract_entities
    assert callable(extract_entities)


def test_extract_json_helper_exists():
    """Ports Proto_Demo's _extract_json with truncation recovery."""
    from services.document_ner import extract_json_with_recovery
    assert callable(extract_json_with_recovery)


# ────────────────────────────────────────────────────────────────────
# JSON extraction with recovery (ported pattern)
# ────────────────────────────────────────────────────────────────────

def test_extract_json_plain_object():
    from services.document_ner import extract_json_with_recovery
    result = extract_json_with_recovery('{"mentions": []}')
    assert result == {"mentions": []}


def test_extract_json_from_fenced_block():
    from services.document_ner import extract_json_with_recovery
    raw = 'Here is the result:\n```json\n{"mentions": [{"text": "x"}]}\n```\n'
    result = extract_json_with_recovery(raw)
    assert isinstance(result, dict)
    assert result.get("mentions") == [{"text": "x"}]


def test_extract_json_recovers_truncated_array():
    """Proto_Demo pattern: when LLM hits max_tokens mid-array, recover the
    objects that DID fit rather than discarding everything."""
    from services.document_ner import extract_json_with_recovery
    # Truncated mid-third-object
    raw = '[{"text":"a"},{"text":"b"},{"text":"c'
    result = extract_json_with_recovery(raw)
    # Should recover the first 2 complete objects
    assert isinstance(result, list)
    assert len(result) >= 2
    assert result[0]["text"] == "a"
    assert result[1]["text"] == "b"


def test_extract_json_returns_empty_for_garbage():
    from services.document_ner import extract_json_with_recovery
    result = extract_json_with_recovery("complete nonsense not json at all")
    # Per Proto_Demo: return [] on parse failure
    assert result in ([], None, {})


# ────────────────────────────────────────────────────────────────────
# Entity extraction
# ────────────────────────────────────────────────────────────────────

def test_extracts_drug_mention():
    """Basic NER: identifies a drug name in free text."""
    from services.document_ner import extract_entities
    fake_llm = MagicMock()
    fake_llm.complete_json.return_value = {
        "mentions": [
            {"text": "semaglutide", "entity_type": "drug", "start": 0, "end": 11},
        ]
    }
    text = "semaglutide reduces A1C in type 2 diabetes patients"
    mentions = extract_entities(text, llm=fake_llm)
    assert len(mentions) == 1
    assert mentions[0].text == "semaglutide"
    assert mentions[0].entity_type == "drug"


def test_extracts_multiple_entity_types():
    from services.document_ner import extract_entities
    fake_llm = MagicMock()
    fake_llm.complete_json.return_value = {
        "mentions": [
            {"text": "tirzepatide", "entity_type": "drug", "start": 0, "end": 11},
            {"text": "Eli Lilly", "entity_type": "company", "start": 25, "end": 34},
            {"text": "NCT05726227", "entity_type": "trial", "start": 50, "end": 61},
        ]
    }
    text = "tirzepatide is sold by Eli Lilly per trial NCT05726227"
    mentions = extract_entities(text, llm=fake_llm)
    types = {m.entity_type for m in mentions}
    assert {"drug", "company", "trial"} <= types


def test_extract_returns_empty_for_irrelevant_text():
    from services.document_ner import extract_entities
    fake_llm = MagicMock()
    fake_llm.complete_json.return_value = {"mentions": []}
    mentions = extract_entities("the weather is nice today", llm=fake_llm)
    assert mentions == []


def test_extract_handles_missing_llm_gracefully():
    """If no LLM provided, return empty (don't crash)."""
    from services.document_ner import extract_entities
    mentions = extract_entities("semaglutide is a drug", llm=None)
    assert mentions == []


# ────────────────────────────────────────────────────────────────────
# Chunking long text
# ────────────────────────────────────────────────────────────────────

def test_extract_chunks_long_text():
    """Documents longer than chunk_size are split — LLM called per chunk."""
    from services.document_ner import extract_entities
    fake_llm = MagicMock()
    fake_llm.complete_json.return_value = {"mentions": []}
    long = "drug mention. " * 5000  # ~70K chars
    extract_entities(long, llm=fake_llm, chunk_size=10000)
    # Should have called the LLM more than once
    assert fake_llm.complete_json.call_count >= 2


def test_extract_dedupes_mentions_across_chunks():
    """Same entity in multiple chunks should appear once in output."""
    from services.document_ner import extract_entities
    fake_llm = MagicMock()
    fake_llm.complete_json.side_effect = [
        {"mentions": [{"text": "Ozempic", "entity_type": "drug", "start": 0, "end": 7}]},
        {"mentions": [{"text": "Ozempic", "entity_type": "drug", "start": 0, "end": 7}]},
    ]
    long = "x" * 30000
    mentions = extract_entities(long, llm=fake_llm, chunk_size=15000)
    ozempic_mentions = [m for m in mentions if m.text == "Ozempic"]
    assert len(ozempic_mentions) == 1


# ────────────────────────────────────────────────────────────────────
# Defensive: bad LLM responses
# ────────────────────────────────────────────────────────────────────

def test_invalid_llm_response_returns_empty_not_raises():
    """Malformed LLM JSON must NOT crash the upload."""
    from services.document_ner import extract_entities
    fake_llm = MagicMock()
    fake_llm.complete_json.return_value = {"unexpected_shape": True}
    mentions = extract_entities("test", llm=fake_llm)
    assert mentions == []


def test_llm_exception_returns_empty_not_raises():
    from services.document_ner import extract_entities
    fake_llm = MagicMock()
    fake_llm.complete_json.side_effect = RuntimeError("LLM API down")
    mentions = extract_entities("semaglutide", llm=fake_llm)
    assert mentions == []


def test_llm_returns_string_instead_of_dict():
    """Some LLMs return raw text containing JSON. Helper should recover."""
    from services.document_ner import extract_entities
    fake_llm = MagicMock()
    # complete_json returns a string when LLM didn't produce parseable JSON
    fake_llm.complete_json.return_value = '{"mentions": [{"text": "drug", "entity_type": "drug", "start": 0, "end": 4}]}'
    mentions = extract_entities("drug X", llm=fake_llm)
    # Should still extract via the recovery helper
    assert len(mentions) == 1
    assert mentions[0].text == "drug"


# ────────────────────────────────────────────────────────────────────
# Mention provenance (per SPEC_017 §1.3 — port ProvenanceInfo pattern)
# ────────────────────────────────────────────────────────────────────

def test_entity_mention_carries_optional_provenance():
    """EntityMention should accept optional source_page + extraction_method
    fields so the upload pipeline can attach document context."""
    from services.document_ner import EntityMention
    m = EntityMention(
        text="semaglutide",
        entity_type="drug",
        start=0,
        end=11,
        source_page=2,
        extraction_method="llm_ner",
    )
    assert m.source_page == 2
    assert m.extraction_method == "llm_ner"
