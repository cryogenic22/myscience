"""
Base connector contract for Market-Zero data layer.

Every data source -- FDA, PubMed, SEC, or a user-uploaded PDF -- implements
BaseConnector and produces RawRecord objects. The integration pipeline
downstream is source-agnostic: it receives list[RawRecord] and processes
them identically regardless of origin.
"""

from __future__ import annotations

import hashlib
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ============================================================
# Enums
# ============================================================


class SourceType(str, Enum):
    """Registered data sources. Adding a new source = adding one entry here."""

    MESH_ONTOLOGY = "mesh_ontology"
    FDA_ORANGE_BOOK = "fda_orange_book"
    CLINICAL_TRIALS_GOV = "clinical_trials_gov"
    FDA_SHORTAGES = "fda_shortages"
    SEC_EDGAR = "sec_edgar"
    PUBMED = "pubmed"
    OPENFDA_FAERS = "openfda_faers"
    OPENFDA_LABELS = "openfda_labels"
    PMC = "pmc"
    EMA = "ema"
    NADAC = "nadac"
    NEWS = "pharma_news"
    CHEMBL = "chembl"
    PUBCHEM = "pubchem"
    OPEN_TARGETS = "open_targets"
    USER_DOCUMENT = "user_document"
    USER_URL = "user_url"


class RecordType(str, Enum):
    """What kind of entity this record represents in the knowledge layer."""

    DRUG = "drug"
    COMPANY = "company"
    TRIAL = "trial"
    EVENT = "event"
    LITERATURE = "literature"
    ONTOLOGY_TERM = "ontology_term"
    ADVERSE_EVENT = "adverse_event"
    DRUG_LABEL = "drug_label"
    PMC_ARTICLE = "pmc_article"
    DOCUMENT_CHUNK = "document_chunk"
    PATENT = "patent"
    REGULATORY_MILESTONE = "regulatory_milestone"
    TRIAL_OUTCOME = "trial_outcome"
    TRIAL_LOCATION = "trial_location"
    INVESTIGATOR = "investigator"
    MOLECULAR_TARGET = "molecular_target"
    BIOACTIVITY = "bioactivity"


class LinkType(str, Enum):
    """Relationship types in the entity_links graph."""

    OWNS = "OWNS"
    SPONSORS = "SPONSORS"
    INVESTIGATES = "INVESTIGATES"
    TARGETS_MECHANISM = "TARGETS_MECHANISM"
    IN_THERAPEUTIC_AREA = "IN_THERAPEUTIC_AREA"
    EVIDENCE_FOR = "EVIDENCE_FOR"
    MENTIONED_IN = "MENTIONED_IN"
    COMPETES_WITH = "COMPETES_WITH"
    PATENT_BLOCKS = "PATENT_BLOCKS"
    SHORTAGE_AFFECTS = "SHORTAGE_AFFECTS"
    USER_LINKED = "USER_LINKED"
    HAS_PATENT = "HAS_PATENT"
    HAS_MILESTONE = "HAS_MILESTONE"
    HAS_OUTCOME = "HAS_OUTCOME"
    LOCATED_AT = "LOCATED_AT"
    LED_BY = "LED_BY"
    AUTHORED_BY = "AUTHORED_BY"
    TAGGED = "TAGGED"
    HAS_ADVERSE_EVENT = "HAS_ADVERSE_EVENT"
    HAS_LABEL = "HAS_LABEL"
    HAS_FULL_TEXT = "HAS_FULL_TEXT"
    BINDS_TO = "BINDS_TO"
    GENETIC_ASSOCIATION = "GENETIC_ASSOCIATION"
    TARGET_OF_MECHANISM = "TARGET_OF_MECHANISM"


# ============================================================
# Provenance
# ============================================================


@dataclass(frozen=True)
class Provenance:
    """
    Every record carries its full provenance. This is the mechanism
    that enforces the "no fabricated data" principle.

    Fields:
        source_type: Which connector produced this record.
        api_endpoint: The exact URL or file path used.
        query_params: The exact parameters sent to the API.
        retrieved_at: When this data was fetched.
        raw_response_hash: SHA-256 of the raw API response for audit.
        etl_run_id: UUID of the ETL run that produced this record (set by pipeline).
    """

    source_type: SourceType
    api_endpoint: str
    query_params: dict[str, Any]
    retrieved_at: datetime
    raw_response_hash: str
    etl_run_id: Optional[str] = None

    @staticmethod
    def hash_response(raw_bytes: bytes) -> str:
        """Compute SHA-256 hash of raw API response for audit trail."""
        return hashlib.sha256(raw_bytes).hexdigest()


# ============================================================
# RawRecord
# ============================================================


@dataclass
class RawRecord:
    """
    The universal output of every connector.

    This is the contract between the connector layer and the integration layer.
    The integration pipeline does not import any connector-specific classes --
    it only works with RawRecord objects.

    Fields:
        record_type: What kind of entity this represents.
        external_id: Source-native identifier (NCT number, PMID, NDA number, MeSH ID).
        source_name: Human-readable source name for display.
        provenance: Full provenance chain.
        data: Source-specific payload dict. Normalized by the integration layer.
        text_content: Free text for embedding (abstract, filing section, etc.).
                      None for purely structured records (e.g., drug patent data).
        identifiers: Cross-link keys used by entity resolution.
                     Examples: {"mesh_ids": ["D009765"], "nda_number": "215256",
                               "generic_name": "semaglutide", "company_name": "Novo Nordisk"}
    """

    record_type: RecordType
    external_id: str
    source_name: str
    provenance: Provenance
    data: dict[str, Any]
    text_content: Optional[str] = None
    identifiers: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.external_id:
            raise ValueError("RawRecord must have a non-empty external_id")
        if not self.provenance.api_endpoint:
            raise ValueError("Provenance must have a non-empty api_endpoint")


# ============================================================
# BaseConnector
# ============================================================


class BaseConnector(ABC):
    """
    Every connector implements this interface.

    Adding a new data source to Market-Zero:
    1. Create a new class that extends BaseConnector.
    2. Implement fetch(), source_type(), and health_check().
    3. Register it in CONNECTOR_REGISTRY (connectors/__init__.py).

    That's it. Zero changes to the integration pipeline, schema, or semantic layer.
    """

    @abstractmethod
    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        """
        Fetch records from the source.

        Args:
            since: If provided, only fetch records updated after this timestamp
                   (incremental/delta mode). If None, perform a full backfill.

        Returns:
            List of RawRecord objects with full provenance.

        Raises:
            ConnectorError: If the source is unreachable or returns invalid data.
        """
        ...

    @abstractmethod
    def source_type(self) -> SourceType:
        """Return the SourceType enum for this connector."""
        ...

    @abstractmethod
    def health_check(self) -> HealthCheckResult:
        """
        Verify the source is reachable and responding correctly.

        Returns:
            HealthCheckResult with status and diagnostic info.
        """
        ...

    def _fetch_with_retry(self, url: str, params: dict = None, max_retries: int = 3):
        """HTTP GET with exponential backoff for transient failures (429, 500, 502, 503, 504).

        Args:
            url: The URL to fetch.
            params: Optional query parameters.
            max_retries: Maximum number of attempts.

        Returns:
            requests.Response object.

        Raises:
            requests.exceptions.RequestException: If all retries are exhausted.
        """
        import requests

        retryable_codes = {429, 500, 502, 503, 504}
        timeout = getattr(self, "timeout", 30)
        headers = getattr(self, "headers", None)
        resp = None

        for attempt in range(max_retries):
            try:
                resp = requests.get(url, params=params, timeout=timeout, headers=headers)
                if resp.status_code not in retryable_codes:
                    return resp
                if attempt < max_retries - 1:
                    delay = (2 ** attempt) + random.uniform(0, 1)
                    logger.warning(
                        "Retryable %d from %s, retry %d/%d in %.1fs",
                        resp.status_code, url, attempt + 1, max_retries, delay,
                    )
                    time.sleep(delay)
            except requests.exceptions.RequestException as e:
                if attempt == max_retries - 1:
                    raise
                delay = (2 ** attempt) + random.uniform(0, 1)
                logger.warning(
                    "Request failed to %s, retry %d/%d: %s",
                    url, attempt + 1, max_retries, e,
                )
                time.sleep(delay)

        return resp  # Return last response even if retryable


# ============================================================
# Supporting types
# ============================================================


@dataclass
class HealthCheckResult:
    """Result of a connector health check."""

    healthy: bool
    source_type: SourceType
    message: str
    response_time_ms: Optional[float] = None
    checked_at: datetime = field(default_factory=datetime.utcnow)


class ConnectorError(Exception):
    """Raised when a connector encounters an unrecoverable error."""

    def __init__(self, source_type: SourceType, message: str, cause: Optional[Exception] = None):
        self.source_type = source_type
        self.cause = cause
        super().__init__(f"[{source_type.value}] {message}")
