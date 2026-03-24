"""Tests for EntityResolver 6-strategy cascade.

Verifies each resolution strategy in isolation and the cascade ordering.
All DB and OpenAI calls are mocked — no external dependencies.

Run with: pytest tests/test_entity_resolver_cascade.py -v
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pytest

from connectors.base import Provenance, RawRecord, RecordType, SourceType
from integration.entity_resolver import (
    AUTO_CREATE_SOURCES,
    EMBEDDING_COLUMNS,
    EXACT_LOOKUP_MAP,
    FUZZY_MATCH_FIELDS,
    EntityResolver,
    ResolvedLink,
    ResolvedRecord,
    ResolutionCandidate,
    ResolutionTrace,
)
from integration.normalizer import NormalizedRecord


# ============================================================
# Mock DB with per-query routing
# ============================================================


class MockResolverDB:
    """Mock database that routes queries by SQL pattern matching.

    Routes are matched in order; the first match wins. This lets you
    register more specific patterns before broader ones.
    """

    def __init__(self):
        self._fetch_one_routes: list[tuple[str, dict | None]] = []
        self._fetch_all_routes: list[tuple[str, list[dict]]] = []
        self._executed: list[tuple[str, list]] = []

    def add_fetch_one(self, pattern: str, result: dict | None):
        """Register a fetch_one response for queries matching pattern."""
        self._fetch_one_routes.append((pattern, result))

    def add_fetch_all(self, pattern: str, results: list[dict]):
        """Register a fetch_all response for queries matching pattern."""
        self._fetch_all_routes.append((pattern, results))

    def fetch_one(self, sql: str, params=None) -> dict | None:
        sql_lower = sql.lower().strip()
        for pattern, result in self._fetch_one_routes:
            if pattern.lower() in sql_lower:
                return result
        return None

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower().strip()
        for pattern, results in self._fetch_all_routes:
            if pattern.lower() in sql_lower:
                return results
        return []

    def execute(self, sql: str, params=None):
        self._executed.append((sql, params or []))


# ============================================================
# Test config and record helpers
# ============================================================


def _make_config(**overrides):
    """Build a minimal AppConfig-compatible mock for EntityResolver."""
    from config import PipelineConfig, EmbeddingConfig

    pipeline = PipelineConfig()
    # Apply overrides
    for k, v in overrides.items():
        if hasattr(pipeline, k):
            setattr(pipeline, k, v)

    config = MagicMock()
    config.pipeline = pipeline
    config.embedding = EmbeddingConfig()
    return config


def _make_record(
    record_type: RecordType = RecordType.TRIAL,
    external_id: str = "NCT00000001",
    source_type: SourceType = SourceType.CLINICAL_TRIALS_GOV,
    identifiers: dict | None = None,
    data: dict | None = None,
) -> NormalizedRecord:
    """Build a NormalizedRecord for testing."""
    prov = Provenance(
        source_type=source_type,
        api_endpoint="https://test.example.com/api",
        query_params={},
        retrieved_at=datetime(2026, 3, 24),
        raw_response_hash="abc123",
    )
    raw = RawRecord(
        record_type=record_type,
        external_id=external_id,
        source_name=source_type.value,
        provenance=prov,
        data=data or {},
        identifiers=identifiers or {},
    )
    return NormalizedRecord(
        raw=raw,
        canonical_data=data or {},
        identifiers=identifiers or {},
    )


# ============================================================
# Strategy 1: Exact ID lookup
# ============================================================


class TestExactIdLookup:
    """Strategy 1: Direct lookup on globally unique IDs (NCT, PMID, CIK)."""

    def test_nct_id_exact_match_returns_trial(self):
        """NCT ID should resolve to the trial's UUID with confidence 1.0."""
        db = MockResolverDB()
        db.add_fetch_one("clinical_trials", {"id": "uuid-trial-1"})
        resolver = EntityResolver(db, _make_config())

        record = _make_record(identifiers={"nct_id": "NCT12345678"})
        result = resolver.resolve(record)

        link = result.resolved_links.get("nct_id")
        assert link is not None
        assert link.entity_id == "uuid-trial-1"
        assert link.matched_via == "exact_id"
        assert link.confidence == 1.0
        assert link.entity_type == "trial"

    def test_pmid_exact_match_returns_literature(self):
        """PMID should resolve to literature entity."""
        db = MockResolverDB()
        db.add_fetch_one("pubmed_articles", {"id": "uuid-lit-1"})
        resolver = EntityResolver(db, _make_config())

        record = _make_record(identifiers={"pmid": "39876543"})
        result = resolver.resolve(record)

        link = result.resolved_links.get("pmid")
        assert link is not None
        assert link.entity_type == "literature"
        assert link.confidence == 1.0

    def test_cik_exact_match_returns_company(self):
        """CIK should resolve to company entity."""
        db = MockResolverDB()
        db.add_fetch_one("companies", {"id": "uuid-co-1"})
        resolver = EntityResolver(db, _make_config())

        record = _make_record(identifiers={"cik": "0001234567"})
        result = resolver.resolve(record)

        link = result.resolved_links.get("cik")
        assert link is not None
        assert link.entity_type == "company"

    def test_exact_lookup_miss_returns_none(self):
        """When no row matches the ID, the link should not be created."""
        db = MockResolverDB()
        # No routes registered — fetch_one returns None
        resolver = EntityResolver(db, _make_config())

        record = _make_record(identifiers={"nct_id": "NCT99999999"})
        result = resolver.resolve(record)

        assert "nct_id" not in result.resolved_links

    def test_exact_lookup_trace_includes_reasoning(self):
        """The trace should contain human-readable reasoning."""
        db = MockResolverDB()
        db.add_fetch_one("clinical_trials", {"id": "uuid-trial-1"})
        resolver = EntityResolver(db, _make_config())

        record = _make_record(identifiers={"nct_id": "NCT12345678"})
        result = resolver.resolve(record)

        link = result.resolved_links["nct_id"]
        assert link.trace is not None
        assert "exact_id" in link.trace.method
        assert "NCT12345678" in link.trace.reasoning


# ============================================================
# Strategy 2: Alias table lookup
# ============================================================


class TestAliasLookup:
    """Strategy 2: Previously confirmed alias resolves instantly."""

    def test_alias_match_returns_entity(self):
        """Known alias should resolve to the canonical entity."""
        db = MockResolverDB()
        # Alias table returns a match
        db.add_fetch_one("entity_aliases", {"entity_id": "uuid-drug-1", "confidence": 0.95})
        resolver = EntityResolver(db, _make_config(resolution_audit_enabled=False))

        record = _make_record(identifiers={"generic_name": "ozempic"})
        result = resolver.resolve(record)

        link = result.resolved_links.get("generic_name")
        assert link is not None
        assert link.entity_id == "uuid-drug-1"
        assert link.matched_via == "alias"
        assert link.confidence == 0.95

    def test_alias_miss_falls_through_to_fuzzy(self):
        """When alias table has no match, resolver should try fuzzy next."""
        db = MockResolverDB()
        # Alias miss, fuzzy hit
        db.add_fetch_all("similarity", [
            {"id": "uuid-drug-2", "name": "semaglutide", "sim": 0.92}
        ])
        resolver = EntityResolver(db, _make_config(resolution_audit_enabled=False))

        record = _make_record(identifiers={"generic_name": "semaglatide"})
        result = resolver.resolve(record)

        link = result.resolved_links.get("generic_name")
        assert link is not None
        assert link.matched_via == "fuzzy"


# ============================================================
# Strategy 3: Fuzzy match (pg_trgm)
# ============================================================


class TestFuzzyLookup:
    """Strategy 3: Trigram similarity matching."""

    def test_fuzzy_match_above_threshold(self):
        """Similarity above threshold should match."""
        db = MockResolverDB()
        db.add_fetch_all("similarity", [
            {"id": "uuid-drug-1", "name": "tirzepatide", "sim": 0.88}
        ])
        resolver = EntityResolver(db, _make_config(
            fuzzy_match_threshold=0.85,
            resolution_audit_enabled=False,
        ))

        record = _make_record(identifiers={"generic_name": "tirzepatid"})
        result = resolver.resolve(record)

        link = result.resolved_links.get("generic_name")
        assert link is not None
        assert link.matched_via == "fuzzy"
        assert link.confidence == pytest.approx(0.88)

    def test_fuzzy_match_returns_best_candidate(self):
        """When multiple candidates, the highest similarity should win."""
        db = MockResolverDB()
        db.add_fetch_all("similarity", [
            {"id": "uuid-drug-1", "name": "semaglutide", "sim": 0.90},
            {"id": "uuid-drug-2", "name": "liraglutide", "sim": 0.72},
        ])
        resolver = EntityResolver(db, _make_config(
            fuzzy_match_threshold=0.70,
            resolution_audit_enabled=False,
        ))

        record = _make_record(identifiers={"generic_name": "semaglutid"})
        result = resolver.resolve(record)

        link = result.resolved_links.get("generic_name")
        assert link is not None
        assert link.entity_id == "uuid-drug-1"

    def test_fuzzy_match_below_threshold_returns_none(self):
        """Similarity below threshold should not match."""
        db = MockResolverDB()
        # No fuzzy results above threshold
        db.add_fetch_all("similarity", [])
        resolver = EntityResolver(db, _make_config(
            fuzzy_match_threshold=0.85,
            auto_create_entities=False,
            resolution_audit_enabled=False,
        ))

        record = _make_record(identifiers={"generic_name": "zzzznonexistent"})
        result = resolver.resolve(record)

        assert "generic_name" not in result.resolved_links

    def test_fuzzy_trace_records_all_candidates(self):
        """The trace should include all candidates considered, not just the best."""
        db = MockResolverDB()
        db.add_fetch_all("similarity", [
            {"id": "uuid-1", "name": "semaglutide", "sim": 0.90},
            {"id": "uuid-2", "name": "liraglutide", "sim": 0.75},
            {"id": "uuid-3", "name": "dulaglutide", "sim": 0.72},
        ])
        resolver = EntityResolver(db, _make_config(
            fuzzy_match_threshold=0.70,
            resolution_audit_enabled=False,
        ))

        record = _make_record(identifiers={"generic_name": "semaglutid"})
        result = resolver.resolve(record)

        link = result.resolved_links["generic_name"]
        assert link.trace is not None
        assert len(link.trace.candidates) == 3


# ============================================================
# Strategy 4: Embedding similarity search
# ============================================================


class TestEmbeddingLookup:
    """Strategy 4: Vector cosine similarity."""

    def test_embedding_match_above_threshold(self):
        """High cosine similarity should resolve the entity."""
        db = MockResolverDB()
        # No alias, no fuzzy match
        db.add_fetch_all("similarity", [])  # fuzzy returns empty
        db.add_fetch_one("cosine_sim", {"id": "uuid-drug-1", "name": "semaglutide", "cosine_sim": 0.91})
        resolver = EntityResolver(db, _make_config(
            embedding_similarity_threshold=0.82,
            resolution_audit_enabled=False,
        ))

        # Mock OpenAI embedding client
        mock_openai = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = [MagicMock(embedding=[0.1] * 128)]
        mock_openai.embeddings.create.return_value = mock_resp
        resolver.openai_client = mock_openai

        record = _make_record(identifiers={"generic_name": "some drug name"})
        result = resolver.resolve(record)

        link = result.resolved_links.get("generic_name")
        assert link is not None
        assert link.matched_via == "embedding"
        assert link.confidence == pytest.approx(0.91)

    def test_embedding_below_threshold_returns_none(self):
        """Low cosine similarity should not match."""
        db = MockResolverDB()
        db.add_fetch_all("similarity", [])
        db.add_fetch_one("cosine_sim", {"id": "uuid-drug-1", "name": "unrelated", "cosine_sim": 0.50})
        resolver = EntityResolver(db, _make_config(
            embedding_similarity_threshold=0.82,
            llm_resolution_enabled=False,
            auto_create_entities=False,
            resolution_audit_enabled=False,
        ))

        mock_openai = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = [MagicMock(embedding=[0.1] * 128)]
        mock_openai.embeddings.create.return_value = mock_resp
        resolver.openai_client = mock_openai

        record = _make_record(identifiers={"generic_name": "totally different"})
        result = resolver.resolve(record)

        assert "generic_name" not in result.resolved_links

    def test_embedding_caches_vectors(self):
        """Subsequent calls with the same text should use the cache."""
        db = MockResolverDB()
        db.add_fetch_all("similarity", [])
        db.add_fetch_one("cosine_sim", {"id": "uuid-drug-1", "name": "semaglutide", "cosine_sim": 0.91})
        resolver = EntityResolver(db, _make_config(
            embedding_similarity_threshold=0.82,
            resolution_audit_enabled=False,
        ))

        mock_openai = MagicMock()
        mock_resp = MagicMock()
        mock_resp.data = [MagicMock(embedding=[0.1] * 128)]
        mock_openai.embeddings.create.return_value = mock_resp
        resolver.openai_client = mock_openai

        # Call twice with the same value
        resolver._get_embedding("semaglutide")
        resolver._get_embedding("semaglutide")

        # Should only call OpenAI once
        assert mock_openai.embeddings.create.call_count == 1


# ============================================================
# Strategy 5: LLM-based analysis
# ============================================================


class TestLLMLookup:
    """Strategy 5: GPT-4o-mini picks from candidates."""

    def test_llm_match_with_high_confidence(self):
        """LLM match with confidence above threshold should resolve."""
        db = MockResolverDB()
        # Fuzzy (WHERE >= threshold) returns empty — no fuzzy match
        db.add_fetch_all("where similarity", [])
        # LLM candidate fetch (ORDER BY, no WHERE threshold) returns candidates
        db.add_fetch_all("order by similarity", [
            {"id": "uuid-drug-1", "name": "semaglutide", "sim": 0.40},
            {"id": "uuid-drug-2", "name": "liraglutide", "sim": 0.35},
        ])
        resolver = EntityResolver(db, _make_config(
            llm_resolution_enabled=True,
            llm_confidence_threshold=0.75,
            resolution_audit_enabled=False,
        ))

        # Mock the LLM response
        mock_openai = MagicMock()
        llm_response = MagicMock()
        llm_message = MagicMock()
        llm_message.content = json.dumps({
            "match_index": 0,
            "confidence": 0.85,
            "reasoning": "Semaglutide is the correct match based on context.",
        })
        llm_response.choices = [MagicMock(message=llm_message)]
        mock_openai.chat.completions.create.return_value = llm_response
        # Also mock embeddings to return None (skip embedding strategy)
        mock_openai.embeddings.create.side_effect = Exception("skip embedding")
        resolver.openai_client = mock_openai

        record = _make_record(identifiers={"generic_name": "sema drug"})
        result = resolver.resolve(record)

        link = result.resolved_links.get("generic_name")
        assert link is not None
        assert link.matched_via == "llm"
        assert link.confidence == pytest.approx(0.85)

    def test_llm_match_below_threshold_rejects(self):
        """LLM match with low confidence should be rejected."""
        db = MockResolverDB()
        db.add_fetch_all("where similarity", [])
        db.add_fetch_all("order by similarity", [
            {"id": "uuid-drug-1", "name": "semaglutide", "sim": 0.40},
        ])
        resolver = EntityResolver(db, _make_config(
            llm_resolution_enabled=True,
            llm_confidence_threshold=0.75,
            auto_create_entities=False,
            resolution_audit_enabled=False,
        ))

        mock_openai = MagicMock()
        llm_response = MagicMock()
        llm_message = MagicMock()
        llm_message.content = json.dumps({
            "match_index": 0,
            "confidence": 0.40,
            "reasoning": "Not sure about this one.",
        })
        llm_response.choices = [MagicMock(message=llm_message)]
        mock_openai.chat.completions.create.return_value = llm_response
        mock_openai.embeddings.create.side_effect = Exception("skip")
        resolver.openai_client = mock_openai

        record = _make_record(identifiers={"generic_name": "mystery drug"})
        result = resolver.resolve(record)

        assert "generic_name" not in result.resolved_links

    def test_llm_null_match_index_rejects(self):
        """LLM returning null match_index should reject all candidates."""
        db = MockResolverDB()
        db.add_fetch_all("where similarity", [])
        db.add_fetch_all("order by similarity", [
            {"id": "uuid-drug-1", "name": "semaglutide", "sim": 0.40},
        ])
        resolver = EntityResolver(db, _make_config(
            llm_resolution_enabled=True,
            llm_confidence_threshold=0.75,
            auto_create_entities=False,
            resolution_audit_enabled=False,
        ))

        mock_openai = MagicMock()
        llm_response = MagicMock()
        llm_message = MagicMock()
        llm_message.content = json.dumps({
            "match_index": None,
            "confidence": 0.90,
            "reasoning": "None of the candidates match.",
        })
        llm_response.choices = [MagicMock(message=llm_message)]
        mock_openai.chat.completions.create.return_value = llm_response
        mock_openai.embeddings.create.side_effect = Exception("skip")
        resolver.openai_client = mock_openai

        record = _make_record(identifiers={"generic_name": "brand new compound"})
        result = resolver.resolve(record)

        assert "generic_name" not in result.resolved_links


# ============================================================
# Strategy 6: Auto-create entity
# ============================================================


class TestAutoCreate:
    """Strategy 6: Create new entity from credible source data."""

    def test_auto_create_drug_from_credible_source(self):
        """Drug from clinical_trials_gov should be auto-created."""
        db = MockResolverDB()
        # No alias, no fuzzy, no embedding, no LLM — all return None
        # auto_create: no existing drug, INSERT succeeds
        db.add_fetch_one("insert into drugs", {"id": "uuid-new-drug"})
        resolver = EntityResolver(db, _make_config(
            auto_create_entities=True,
            llm_resolution_enabled=False,
            resolution_audit_enabled=False,
        ))

        record = _make_record(
            identifiers={"generic_name": "noveldrugname"},
            source_type=SourceType.CLINICAL_TRIALS_GOV,
        )
        result = resolver.resolve(record)

        link = result.resolved_links.get("generic_name")
        assert link is not None
        assert link.matched_via == "auto_create"
        assert link.confidence == 1.0

    def test_auto_create_company_from_credible_source(self):
        """Sponsor from clinical_trials_gov should be auto-created."""
        db = MockResolverDB()
        db.add_fetch_one("insert into companies", {"id": "uuid-new-co"})
        resolver = EntityResolver(db, _make_config(
            auto_create_entities=True,
            llm_resolution_enabled=False,
            resolution_audit_enabled=False,
        ))

        record = _make_record(
            identifiers={"sponsor_name": "BrandNew Therapeutics Inc."},
            source_type=SourceType.CLINICAL_TRIALS_GOV,
        )
        result = resolver.resolve(record)

        link = result.resolved_links.get("sponsor_name")
        assert link is not None
        assert link.matched_via == "auto_create"

    def test_auto_create_normalizes_drug_name(self):
        """Auto-created drug should use normalized name, not raw mention."""
        db = MockResolverDB()
        db.add_fetch_one("insert into drugs", {"id": "uuid-new-drug"})
        resolver = EntityResolver(db, _make_config(
            auto_create_entities=True,
            llm_resolution_enabled=False,
            resolution_audit_enabled=False,
        ))

        record = _make_record(
            identifiers={"generic_name": "SEMAGLUTIDE 0.5 MG INJECTION"},
            source_type=SourceType.CLINICAL_TRIALS_GOV,
        )
        result = resolver.resolve(record)

        link = result.resolved_links.get("generic_name")
        assert link is not None
        # matched_value should be normalized
        assert "0.5" not in link.matched_value
        assert "injection" not in link.matched_value.lower()

    def test_auto_create_skips_placebo(self):
        """Placebo should be excluded from auto-creation."""
        db = MockResolverDB()
        resolver = EntityResolver(db, _make_config(
            auto_create_entities=True,
            llm_resolution_enabled=False,
            resolution_audit_enabled=False,
        ))

        record = _make_record(
            identifiers={"generic_name": "Placebo"},
            source_type=SourceType.CLINICAL_TRIALS_GOV,
        )
        result = resolver.resolve(record)

        assert "generic_name" not in result.resolved_links

    def test_auto_create_skips_short_names(self):
        """Very short names (< 3 chars) should not create entities."""
        db = MockResolverDB()
        resolver = EntityResolver(db, _make_config(
            auto_create_entities=True,
            llm_resolution_enabled=False,
            resolution_audit_enabled=False,
        ))

        record = _make_record(
            identifiers={"generic_name": "AB"},
            source_type=SourceType.CLINICAL_TRIALS_GOV,
        )
        result = resolver.resolve(record)

        assert "generic_name" not in result.resolved_links

    def test_auto_create_finds_existing_icase(self):
        """If normalized name matches existing entity (case-insensitive), reuse it."""
        db = MockResolverDB()
        # The case-insensitive SELECT matches
        db.add_fetch_one("lower(generic_name)", {"id": "uuid-existing", "generic_name": "semaglutide"})
        resolver = EntityResolver(db, _make_config(
            auto_create_entities=True,
            llm_resolution_enabled=False,
            resolution_audit_enabled=False,
        ))

        record = _make_record(
            identifiers={"generic_name": "Semaglutide 2.4mg"},
            source_type=SourceType.CLINICAL_TRIALS_GOV,
        )
        result = resolver.resolve(record)

        link = result.resolved_links.get("generic_name")
        assert link is not None
        assert link.entity_id == "uuid-existing"
        assert link.matched_via == "exact_name_icase"

    def test_auto_create_creates_alias_when_normalized_differs(self):
        """When raw mention is different from normalized, an alias should be stored."""
        db = MockResolverDB()
        db.add_fetch_one("insert into drugs", {"id": "uuid-new-drug"})
        resolver = EntityResolver(db, _make_config(
            auto_create_entities=True,
            llm_resolution_enabled=False,
            resolution_audit_enabled=False,
        ))

        record = _make_record(
            identifiers={"generic_name": "SEMAGLUTIDE 0.5 MG"},
            source_type=SourceType.CLINICAL_TRIALS_GOV,
        )
        resolver.resolve(record)

        # Check that _create_alias was called via db.execute
        alias_inserts = [
            (sql, params) for sql, params in db._executed
            if "entity_aliases" in sql
        ]
        assert len(alias_inserts) >= 1


# ============================================================
# Cascade ordering
# ============================================================


class TestCascadeOrder:
    """Verify strategies are tried in strict priority order."""

    def test_exact_id_takes_priority_over_all(self):
        """Exact ID match should be used even if alias/fuzzy would also match."""
        db = MockResolverDB()
        db.add_fetch_one("clinical_trials", {"id": "uuid-exact"})
        db.add_fetch_one("entity_aliases", {"entity_id": "uuid-alias", "confidence": 0.95})
        resolver = EntityResolver(db, _make_config(resolution_audit_enabled=False))

        record = _make_record(identifiers={"nct_id": "NCT12345678"})
        result = resolver.resolve(record)

        link = result.resolved_links["nct_id"]
        assert link.matched_via == "exact_id"
        assert link.entity_id == "uuid-exact"

    def test_alias_takes_priority_over_fuzzy(self):
        """Alias match should be used before fuzzy."""
        db = MockResolverDB()
        db.add_fetch_one("entity_aliases", {"entity_id": "uuid-alias", "confidence": 0.95})
        db.add_fetch_all("similarity", [
            {"id": "uuid-fuzzy", "name": "semaglutide", "sim": 0.92}
        ])
        resolver = EntityResolver(db, _make_config(resolution_audit_enabled=False))

        record = _make_record(identifiers={"generic_name": "sema"})
        result = resolver.resolve(record)

        link = result.resolved_links["generic_name"]
        assert link.matched_via == "alias"

    def test_all_strategies_fail_logs_unresolved(self):
        """When every strategy fails, the record should go to unresolved queue."""
        db = MockResolverDB()
        # Add a similarity result for unresolved logging
        db.add_fetch_one("order by sim", {"id": "uuid-1", "name": "something", "sim": 0.35})
        resolver = EntityResolver(db, _make_config(
            auto_create_entities=False,
            llm_resolution_enabled=False,
            resolution_audit_enabled=False,
        ))

        record = _make_record(identifiers={"generic_name": "totally_unknown_drug"})
        result = resolver.resolve(record)

        assert "generic_name" not in result.resolved_links
        # Check unresolved_entities was written
        unresolved_inserts = [
            (sql, params) for sql, params in db._executed
            if "unresolved_entities" in sql
        ]
        assert len(unresolved_inserts) >= 1


# ============================================================
# Confidence propagation
# ============================================================


class TestConfidencePropagation:
    """Verify each strategy returns appropriate confidence levels."""

    def test_exact_id_confidence_is_1(self):
        """Exact ID match should always have confidence 1.0."""
        db = MockResolverDB()
        db.add_fetch_one("clinical_trials", {"id": "uuid-1"})
        resolver = EntityResolver(db, _make_config(resolution_audit_enabled=False))

        record = _make_record(identifiers={"nct_id": "NCT00000001"})
        result = resolver.resolve(record)

        assert result.resolved_links["nct_id"].confidence == 1.0

    def test_alias_confidence_from_table(self):
        """Alias confidence should come from the stored value in the alias table."""
        db = MockResolverDB()
        db.add_fetch_one("entity_aliases", {"entity_id": "uuid-1", "confidence": 0.88})
        resolver = EntityResolver(db, _make_config(resolution_audit_enabled=False))

        record = _make_record(identifiers={"generic_name": "test drug"})
        result = resolver.resolve(record)

        assert result.resolved_links["generic_name"].confidence == pytest.approx(0.88)

    def test_fuzzy_confidence_is_similarity_score(self):
        """Fuzzy confidence should be the trigram similarity score."""
        db = MockResolverDB()
        db.add_fetch_all("similarity", [
            {"id": "uuid-1", "name": "semaglutide", "sim": 0.87}
        ])
        resolver = EntityResolver(db, _make_config(
            fuzzy_match_threshold=0.85,
            resolution_audit_enabled=False,
        ))

        record = _make_record(identifiers={"generic_name": "semagltide"})
        result = resolver.resolve(record)

        assert result.resolved_links["generic_name"].confidence == pytest.approx(0.87)


# ============================================================
# MentionNormalizer integration
# ============================================================


class TestMentionNormalizerIntegration:
    """Verify the resolver uses MentionNormalizer during auto-create."""

    def test_drug_dosage_stripped_before_creation(self):
        """'SEMAGLUTIDE 0.5 MG' should become 'semaglutide' for entity creation."""
        db = MockResolverDB()
        db.add_fetch_one("insert into drugs", {"id": "uuid-new"})
        resolver = EntityResolver(db, _make_config(
            auto_create_entities=True,
            llm_resolution_enabled=False,
            resolution_audit_enabled=False,
        ))

        record = _make_record(
            identifiers={"generic_name": "SEMAGLUTIDE 0.5 MG"},
            source_type=SourceType.CLINICAL_TRIALS_GOV,
        )
        result = resolver.resolve(record)

        link = result.resolved_links.get("generic_name")
        assert link is not None
        assert link.matched_value == "semaglutide"

    def test_company_suffix_stripped_before_creation(self):
        """'Novo Nordisk A/S' should become 'novo nordisk' for entity creation."""
        db = MockResolverDB()
        db.add_fetch_one("insert into companies", {"id": "uuid-new-co"})
        resolver = EntityResolver(db, _make_config(
            auto_create_entities=True,
            llm_resolution_enabled=False,
            resolution_audit_enabled=False,
        ))

        record = _make_record(
            identifiers={"sponsor_name": "Novo Nordisk A/S"},
            source_type=SourceType.CLINICAL_TRIALS_GOV,
        )
        result = resolver.resolve(record)

        link = result.resolved_links.get("sponsor_name")
        assert link is not None
        assert link.matched_value == "novo nordisk"


# ============================================================
# Empty / edge cases
# ============================================================


class TestEdgeCases:
    """Edge cases and graceful degradation."""

    def test_empty_identifiers_returns_empty_resolved(self):
        """Record with no identifiers should resolve to empty links."""
        db = MockResolverDB()
        resolver = EntityResolver(db, _make_config(resolution_audit_enabled=False))

        record = _make_record(identifiers={})
        result = resolver.resolve(record)

        assert len(result.resolved_links) == 0

    def test_unknown_id_key_is_ignored(self):
        """Unrecognized identifier keys should be silently ignored."""
        db = MockResolverDB()
        resolver = EntityResolver(db, _make_config(resolution_audit_enabled=False))

        record = _make_record(identifiers={"unknown_field": "value123"})
        result = resolver.resolve(record)

        assert len(result.resolved_links) == 0

    def test_ontology_lookup_for_mesh_ids(self):
        """MeSH IDs should be resolved via ontology lookup."""
        db = MockResolverDB()
        db.add_fetch_all("therapeutic_areas", [{"id": "uuid-ta-1"}])
        db.add_fetch_all("mechanisms_of_action", [])
        resolver = EntityResolver(db, _make_config(resolution_audit_enabled=False))

        record = _make_record(identifiers={"mesh_ids": ["D009765"]})
        result = resolver.resolve(record)

        assert len(result.ontology_links) >= 1
        assert result.ontology_links[0].entity_type == "therapeutic_area"
        assert result.ontology_links[0].matched_via == "ontology"

    def test_auto_alias_created_for_high_confidence_fuzzy(self):
        """High-confidence fuzzy match should auto-create an alias for future lookups."""
        db = MockResolverDB()
        db.add_fetch_all("similarity", [
            {"id": "uuid-drug-1", "name": "semaglutide", "sim": 0.96}
        ])
        resolver = EntityResolver(db, _make_config(
            fuzzy_match_threshold=0.85,
            auto_alias_threshold=0.95,
            resolution_audit_enabled=False,
        ))

        record = _make_record(identifiers={"generic_name": "semagltide"})
        resolver.resolve(record)

        # Check alias creation via db.execute
        alias_inserts = [
            (sql, params) for sql, params in db._executed
            if "entity_aliases" in sql
        ]
        assert len(alias_inserts) >= 1
