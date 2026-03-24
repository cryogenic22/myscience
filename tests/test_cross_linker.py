"""Tests for CrossLinker — relationship detection after record storage.

Verifies link creation for each record type, idempotency via ON CONFLICT,
and graceful handling of missing foreign keys.

Run with: pytest tests/test_cross_linker.py -v
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from connectors.base import (
    LinkType,
    Provenance,
    RawRecord,
    RecordType,
    SourceType,
)
from integration.cross_linker import CrossLinker
from integration.embedder import EmbeddedRecord
from integration.entity_resolver import ResolvedLink, ResolvedRecord
from integration.normalizer import NormalizedRecord


# ============================================================
# Mock DB
# ============================================================


class MockLinkerDB:
    """Mock database for cross-linker tests.

    Tracks all upsert calls and can simulate duplicate detection
    by returning None (ON CONFLICT DO NOTHING).
    """

    def __init__(self):
        self._upsert_results: list[dict | None] = []
        self._upsert_index = 0
        self._fetch_all_routes: dict[str, list[dict]] = {}
        self._fetch_one_routes: dict[str, dict | None] = {}
        self.upsert_calls: list[tuple[str, list]] = []

    def set_upsert_result(self, result: dict | None):
        """Queue a single upsert result (returned by fetch_one on INSERT)."""
        self._upsert_results.append(result)

    def set_upsert_results(self, results: list[dict | None]):
        """Queue multiple upsert results."""
        self._upsert_results.extend(results)

    def add_fetch_all(self, pattern: str, results: list[dict]):
        self._fetch_all_routes[pattern] = results

    def add_fetch_one(self, pattern: str, result: dict | None):
        self._fetch_one_routes[pattern] = result

    def fetch_one(self, sql: str, params=None) -> dict | None:
        self.upsert_calls.append((sql, params or []))
        sql_lower = sql.lower()

        # Check pattern routes first
        for pattern, result in self._fetch_one_routes.items():
            if pattern.lower() in sql_lower:
                return result

        # For INSERT (upsert) calls, return queued results
        if "insert into entity_links" in sql_lower:
            if self._upsert_index < len(self._upsert_results):
                result = self._upsert_results[self._upsert_index]
                self._upsert_index += 1
                return result
            # Default: return a new link ID (not a duplicate)
            return {"id": f"link-{self._upsert_index}"}
        return None

    def fetch_all(self, sql: str, params=None) -> list[dict]:
        sql_lower = sql.lower()
        for pattern, results in self._fetch_all_routes.items():
            if pattern.lower() in sql_lower:
                return results
        return []

    def execute(self, sql: str, params=None):
        pass


# ============================================================
# Test helpers
# ============================================================


def _make_provenance(source_type: SourceType = SourceType.FDA_ORANGE_BOOK) -> Provenance:
    return Provenance(
        source_type=source_type,
        api_endpoint="https://test.example.com/api",
        query_params={},
        retrieved_at=datetime(2026, 3, 24),
        raw_response_hash="abc123",
    )


def _make_embedded_record(
    record_type: RecordType,
    resolved_links: dict[str, ResolvedLink] | None = None,
    ontology_links: list[ResolvedLink] | None = None,
    source_type: SourceType = SourceType.FDA_ORANGE_BOOK,
    canonical_data: dict | None = None,
) -> EmbeddedRecord:
    """Build an EmbeddedRecord with the given resolved links."""
    prov = _make_provenance(source_type)
    raw = RawRecord(
        record_type=record_type,
        external_id="TEST-001",
        source_name=source_type.value,
        provenance=prov,
        data={},
    )
    normalized = NormalizedRecord(
        raw=raw,
        canonical_data=canonical_data or {},
        identifiers={},
    )
    resolved = ResolvedRecord(
        normalized=normalized,
        resolved_links=resolved_links or {},
        ontology_links=ontology_links or [],
    )
    return EmbeddedRecord(resolved=resolved, embedding=None)


def _make_resolved_link(
    entity_type: str,
    entity_id: str,
    matched_via: str = "exact_id",
    confidence: float = 1.0,
) -> ResolvedLink:
    return ResolvedLink(
        entity_type=entity_type,
        entity_id=entity_id,
        matched_via=matched_via,
        confidence=confidence,
        matched_value="test",
    )


# ============================================================
# Drug linking: OWNS, IN_THERAPEUTIC_AREA, TARGETS_MECHANISM
# ============================================================


class TestLinkDrug:
    """Drug record creates OWNS, IN_THERAPEUTIC_AREA, TARGETS_MECHANISM links."""

    def test_owns_link_company_to_drug(self):
        """Drug with resolved company_name should create OWNS link."""
        db = MockLinkerDB()
        db.set_upsert_result({"id": "link-1"})
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.DRUG,
            resolved_links={
                "company_name": _make_resolved_link("company", "uuid-company-1"),
            },
        )

        links = linker.cross_link(record, "uuid-drug-stored")
        assert len(links) == 1
        assert links[0]["link_type"] == LinkType.OWNS.value
        assert links[0]["source_id"] == "uuid-company-1"
        assert links[0]["target_id"] == "uuid-drug-stored"

    def test_in_therapeutic_area_link(self):
        """Drug with resolved TA should create IN_THERAPEUTIC_AREA link."""
        db = MockLinkerDB()
        db.set_upsert_result({"id": "link-1"})
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.DRUG,
            resolved_links={
                "therapeutic_area": _make_resolved_link("therapeutic_area", "uuid-ta-1"),
            },
        )

        links = linker.cross_link(record, "uuid-drug-stored")
        assert len(links) == 1
        assert links[0]["link_type"] == LinkType.IN_THERAPEUTIC_AREA.value

    def test_targets_mechanism_link(self):
        """Drug with resolved mechanism should create TARGETS_MECHANISM link."""
        db = MockLinkerDB()
        db.set_upsert_result({"id": "link-1"})
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.DRUG,
            resolved_links={
                "mechanism": _make_resolved_link("mechanism", "uuid-mech-1"),
            },
        )

        links = linker.cross_link(record, "uuid-drug-stored")
        assert len(links) == 1
        assert links[0]["link_type"] == LinkType.TARGETS_MECHANISM.value

    def test_drug_creates_all_three_links(self):
        """Drug with all FK fields should create OWNS + TA + MECHANISM links."""
        db = MockLinkerDB()
        db.set_upsert_results([{"id": "link-1"}, {"id": "link-2"}, {"id": "link-3"}])
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.DRUG,
            resolved_links={
                "company_name": _make_resolved_link("company", "uuid-co"),
                "therapeutic_area": _make_resolved_link("therapeutic_area", "uuid-ta"),
                "mechanism": _make_resolved_link("mechanism", "uuid-mech"),
            },
        )

        links = linker.cross_link(record, "uuid-drug-stored")
        assert len(links) == 3
        link_types = {link["link_type"] for link in links}
        assert LinkType.OWNS.value in link_types
        assert LinkType.IN_THERAPEUTIC_AREA.value in link_types
        assert LinkType.TARGETS_MECHANISM.value in link_types


# ============================================================
# Trial linking: SPONSORS, INVESTIGATES
# ============================================================


class TestLinkTrial:
    """Trial record creates SPONSORS and INVESTIGATES links."""

    def test_sponsors_link_company_to_trial(self):
        """Trial with resolved sponsor should create SPONSORS link."""
        db = MockLinkerDB()
        db.set_upsert_result({"id": "link-1"})
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.TRIAL,
            resolved_links={
                "sponsor_name": _make_resolved_link("company", "uuid-sponsor"),
            },
            source_type=SourceType.CLINICAL_TRIALS_GOV,
        )

        links = linker.cross_link(record, "uuid-trial-stored")
        assert len(links) == 1
        assert links[0]["link_type"] == LinkType.SPONSORS.value
        assert links[0]["source_id"] == "uuid-sponsor"
        assert links[0]["target_id"] == "uuid-trial-stored"

    def test_investigates_link_trial_to_drug(self):
        """Trial with resolved drug should create INVESTIGATES link."""
        db = MockLinkerDB()
        db.set_upsert_result({"id": "link-1"})
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.TRIAL,
            resolved_links={
                "generic_name": _make_resolved_link("drug", "uuid-drug"),
            },
            source_type=SourceType.CLINICAL_TRIALS_GOV,
        )

        links = linker.cross_link(record, "uuid-trial-stored")
        assert len(links) == 1
        assert links[0]["link_type"] == LinkType.INVESTIGATES.value


# ============================================================
# Literature linking: EVIDENCE_FOR
# ============================================================


class TestLinkLiterature:
    """Literature record creates EVIDENCE_FOR links."""

    def test_evidence_for_direct_drug_link(self):
        """Article with resolved drug should create EVIDENCE_FOR link."""
        db = MockLinkerDB()
        db.set_upsert_result({"id": "link-1"})
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.LITERATURE,
            resolved_links={
                "generic_name": _make_resolved_link("drug", "uuid-drug"),
            },
            source_type=SourceType.PUBMED,
        )

        links = linker.cross_link(record, "uuid-article-stored")
        assert len(links) == 1
        assert links[0]["link_type"] == LinkType.EVIDENCE_FOR.value

    def test_evidence_for_via_mesh_ontology(self):
        """Article with MeSH ontology links should create EVIDENCE_FOR via TA-drug path."""
        db = MockLinkerDB()
        db.set_upsert_result({"id": "link-1"})
        # Drugs in the matched therapeutic area
        db.add_fetch_all("therapeutic_area_id", [{"id": "uuid-drug-in-ta"}])
        linker = CrossLinker(db)

        ontology_link = ResolvedLink(
            entity_type="therapeutic_area",
            entity_id="uuid-ta-1",
            matched_via="ontology",
            confidence=1.0,
            matched_value="D009765",
        )
        record = _make_embedded_record(
            record_type=RecordType.LITERATURE,
            ontology_links=[ontology_link],
            source_type=SourceType.PUBMED,
        )

        links = linker.cross_link(record, "uuid-article-stored")
        assert len(links) >= 1
        assert links[0]["link_type"] == LinkType.EVIDENCE_FOR.value


# ============================================================
# Event linking: SHORTAGE_AFFECTS
# ============================================================


class TestLinkEvent:
    """Market event creates SHORTAGE_AFFECTS links."""

    def test_shortage_affects_drug(self):
        """FDA shortage event with resolved drug should create SHORTAGE_AFFECTS link."""
        db = MockLinkerDB()
        db.set_upsert_result({"id": "link-1"})
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.EVENT,
            resolved_links={
                "generic_name": _make_resolved_link("drug", "uuid-drug"),
            },
            source_type=SourceType.FDA_SHORTAGES,
        )

        links = linker.cross_link(record, "uuid-event-stored")
        assert len(links) == 1
        assert links[0]["link_type"] == LinkType.SHORTAGE_AFFECTS.value


# ============================================================
# Chunk linking: MENTIONED_IN
# ============================================================


class TestLinkChunk:
    """Knowledge chunk creates MENTIONED_IN links."""

    def test_mentioned_in_company(self):
        """SEC filing chunk with resolved company should create MENTIONED_IN link."""
        db = MockLinkerDB()
        db.set_upsert_result({"id": "link-1"})
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.DOCUMENT_CHUNK,
            resolved_links={
                "cik": _make_resolved_link("company", "uuid-company"),
            },
            source_type=SourceType.SEC_EDGAR,
        )

        links = linker.cross_link(record, "uuid-chunk-stored")
        assert len(links) == 1
        assert links[0]["link_type"] == LinkType.MENTIONED_IN.value


# ============================================================
# Patent linking: HAS_PATENT
# ============================================================


class TestLinkPatent:
    """Patent creates HAS_PATENT links."""

    def test_has_patent_drug_to_patent(self):
        """Patent with resolved NDA should create HAS_PATENT link."""
        db = MockLinkerDB()
        db.set_upsert_result({"id": "link-1"})
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.PATENT,
            resolved_links={
                "nda_number": _make_resolved_link("drug", "uuid-drug"),
            },
        )

        links = linker.cross_link(record, "uuid-patent-stored")
        assert len(links) == 1
        assert links[0]["link_type"] == LinkType.HAS_PATENT.value
        assert links[0]["source_id"] == "uuid-drug"
        assert links[0]["target_id"] == "uuid-patent-stored"


# ============================================================
# Idempotency
# ============================================================


class TestIdempotency:
    """Verify duplicate links are not created (ON CONFLICT DO NOTHING)."""

    def test_duplicate_link_returns_none(self):
        """When ON CONFLICT fires, _upsert_link returns None and no link is added."""
        db = MockLinkerDB()
        # First call creates link, second returns None (duplicate)
        db.set_upsert_results([{"id": "link-1"}, None])
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.DRUG,
            resolved_links={
                "company_name": _make_resolved_link("company", "uuid-co"),
                "therapeutic_area": _make_resolved_link("therapeutic_area", "uuid-ta"),
            },
        )

        links = linker.cross_link(record, "uuid-drug-stored")
        # Only the first link should appear (second was a duplicate)
        assert len(links) == 1

    def test_all_duplicates_returns_empty(self):
        """If all links already exist, return empty list."""
        db = MockLinkerDB()
        db.set_upsert_results([None])
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.DRUG,
            resolved_links={
                "company_name": _make_resolved_link("company", "uuid-co"),
            },
        )

        links = linker.cross_link(record, "uuid-drug-stored")
        assert len(links) == 0


# ============================================================
# Missing fields
# ============================================================


class TestMissingFields:
    """Verify graceful handling when FK fields are null."""

    def test_drug_without_company_creates_no_owns_link(self):
        """Drug with no company_name resolved should create no OWNS link."""
        db = MockLinkerDB()
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.DRUG,
            resolved_links={},
        )

        links = linker.cross_link(record, "uuid-drug-stored")
        assert len(links) == 0

    def test_trial_without_sponsor_creates_no_sponsors_link(self):
        """Trial with no sponsor resolved should create no SPONSORS link."""
        db = MockLinkerDB()
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.TRIAL,
            resolved_links={},
            source_type=SourceType.CLINICAL_TRIALS_GOV,
        )

        links = linker.cross_link(record, "uuid-trial-stored")
        assert len(links) == 0

    def test_unknown_record_type_returns_empty(self):
        """Unhandled record types should return empty list gracefully."""
        db = MockLinkerDB()
        linker = CrossLinker(db)

        # ADVERSE_EVENT is not in the router
        record = _make_embedded_record(
            record_type=RecordType.ADVERSE_EVENT,
            resolved_links={},
        )

        links = linker.cross_link(record, "uuid-ae-stored")
        assert links == []

    def test_company_record_creates_no_outgoing_links(self):
        """Company records don't create outgoing links on their own."""
        db = MockLinkerDB()
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.COMPANY,
            resolved_links={},
        )

        links = linker.cross_link(record, "uuid-company-stored")
        assert links == []


# ============================================================
# Link confidence propagation
# ============================================================


class TestLinkConfidence:
    """Verify confidence scores flow from resolver to link table."""

    def test_link_carries_resolver_confidence(self):
        """The link's 'via' field should reflect the resolution method."""
        db = MockLinkerDB()
        db.set_upsert_result({"id": "link-1"})
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.DRUG,
            resolved_links={
                "company_name": _make_resolved_link("company", "uuid-co", matched_via="fuzzy", confidence=0.87),
            },
        )

        links = linker.cross_link(record, "uuid-drug-stored")
        assert len(links) == 1
        assert links[0]["via"] == "fuzzy"


# ============================================================
# Investigator linking: LED_BY, AUTHORED_BY
# ============================================================


class TestLinkInvestigator:
    """Investigator creates LED_BY and AUTHORED_BY links."""

    def test_led_by_trial_to_investigator(self):
        """Investigator with trial NCT ID should create LED_BY link."""
        db = MockLinkerDB()
        db.set_upsert_result({"id": "link-1"})
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.INVESTIGATOR,
            canonical_data={"trial_nct_id": "NCT12345678"},
            source_type=SourceType.CLINICAL_TRIALS_GOV,
        )

        links = linker.cross_link(record, "uuid-investigator-stored")
        assert len(links) == 1
        assert links[0]["link_type"] == LinkType.LED_BY.value

    def test_authored_by_article_to_investigator(self):
        """Investigator with source_pmid should create AUTHORED_BY link if article exists."""
        db = MockLinkerDB()
        db.set_upsert_result({"id": "link-1"})
        db.add_fetch_one("pubmed_articles", {"id": "uuid-article-1"})
        linker = CrossLinker(db)

        record = _make_embedded_record(
            record_type=RecordType.INVESTIGATOR,
            canonical_data={"source_pmid": "39876543"},
            source_type=SourceType.PUBMED,
        )

        links = linker.cross_link(record, "uuid-investigator-stored")
        assert len(links) == 1
        assert links[0]["link_type"] == LinkType.AUTHORED_BY.value
