"""
PubMed Central (PMC) Full-Text Connector.

Fetches full-text articles from PMC for PubMed articles already in the database.
Two-step process:
  1. For each PMID in pubmed_articles, check if a PMC full-text exists via elink.
  2. Fetch full article XML from PMC via efetch.

Flags protocol papers (article-type="protocol" or title contains "protocol")
and systematic reviews for downstream analysis.

Produces:
  - PMC_ARTICLE records (one per full-text article)

API docs: https://www.ncbi.nlm.nih.gov/books/NBK25497/
"""

from __future__ import annotations

import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any, Optional

import requests

from connectors.base import (
    BaseConnector,
    ConnectorError,
    HealthCheckResult,
    Provenance,
    RawRecord,
    RecordType,
    SourceType,
)

logger = logging.getLogger(__name__)

ELINK_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"

# Target drugs — used to search PMC directly when no DB connection is available.
TARGET_DRUGS = [
    "semaglutide", "tirzepatide", "liraglutide", "dulaglutide", "exenatide",
    "empagliflozin", "dapagliflozin", "canagliflozin",
    "sitagliptin", "linagliptin", "saxagliptin",
    "metformin", "pioglitazone",
    "sacubitril", "valsartan", "finerenone", "vericiguat", "ivabradine",
    "carvedilol", "metoprolol", "enalapril", "losartan",
    "spironolactone", "eplerenone",
]

MAX_ARTICLES_PER_DRUG = 20  # Limit per drug to keep total manageable
BATCH_SIZE = 3  # Keep small — PMC efetch is unreliable with large batches

# Patterns for detecting protocol and systematic review articles
PROTOCOL_TITLE_PATTERNS = [
    re.compile(r"\bprotocol\b", re.IGNORECASE),
    re.compile(r"\bstudy design\b", re.IGNORECASE),
]
REVIEW_TITLE_PATTERNS = [
    re.compile(r"\bsystematic review\b", re.IGNORECASE),
    re.compile(r"\bmeta-analysis\b", re.IGNORECASE),
    re.compile(r"\bmeta analysis\b", re.IGNORECASE),
]


class PMCConnector(BaseConnector):
    """
    Fetches full-text articles from PubMed Central.

    Strategy: Search PMC for target drug names to find articles with
    open-access full text. For each article, fetch the XML, extract
    the body text, and classify as protocol/review when applicable.

    When a database connection is provided via config, it can also
    look up existing PMIDs from pubmed_articles and find their
    PMC equivalents via elink.
    """

    def __init__(self, config=None):
        self.config = config
        self.api_key = ""
        self.request_delay = 0.34  # ~3 req/sec without key
        if config:
            self.api_key = config.connectors.ncbi_api_key
            if self.api_key:
                self.request_delay = 0.1  # 10 req/sec with key
            else:
                self.request_delay = max(
                    0.34, config.connectors.default_request_delay_seconds
                )
        self.session = requests.Session()

    def source_type(self) -> SourceType:
        return SourceType.PMC

    def health_check(self) -> HealthCheckResult:
        start = time.time()
        try:
            params: dict[str, Any] = {
                "db": "pmc",
                "term": "semaglutide",
                "retmax": 1,
                "retmode": "json",
            }
            if self.api_key:
                params["api_key"] = self.api_key
            resp = self.session.get(ESEARCH_URL, params=params, timeout=15)
            elapsed = (time.time() - start) * 1000
            if resp.status_code == 200:
                return HealthCheckResult(
                    healthy=True,
                    source_type=self.source_type(),
                    message="PMC E-Utilities reachable",
                    response_time_ms=elapsed,
                )
            return HealthCheckResult(
                healthy=False,
                source_type=self.source_type(),
                message=f"HTTP {resp.status_code}",
                response_time_ms=elapsed,
            )
        except Exception as e:
            return HealthCheckResult(
                healthy=False,
                source_type=self.source_type(),
                message=str(e),
            )

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        """
        Fetch full-text articles from PMC for target drugs.

        Uses esearch to find PMC articles directly by drug name,
        then efetch to get the full XML.
        """
        records: list[RawRecord] = []
        seen_pmc_ids: set[str] = set()

        for drug_name in TARGET_DRUGS:
            logger.info("PMC search: %s", drug_name)
            try:
                pmc_ids = self._search_pmc(drug_name, since)
            except Exception as e:
                logger.error("PMC search failed for %s: %s", drug_name, e)
                continue

            # Deduplicate
            new_ids = [pid for pid in pmc_ids if pid not in seen_pmc_ids]
            seen_pmc_ids.update(new_ids)

            if not new_ids:
                continue

            # Fetch in batches
            for batch_start in range(0, len(new_ids), BATCH_SIZE):
                batch = new_ids[batch_start:batch_start + BATCH_SIZE]
                try:
                    articles = self._fetch_pmc_articles(batch)
                    for pmc_id, article_elem in articles:
                        record = self._parse_article(pmc_id, article_elem, drug_name)
                        if record:
                            records.append(record)
                except Exception as e:
                    logger.error("PMC efetch failed for batch: %s", e)

                time.sleep(self.request_delay)

        logger.info(
            "PMC fetch complete: %d unique PMC IDs -> %d records",
            len(seen_pmc_ids), len(records),
        )
        return records

    def _search_pmc(self, drug_name: str, since: Optional[datetime] = None) -> list[str]:
        """Search PMC for open-access full-text articles by drug name."""
        query = f'"{drug_name}"[Title/Abstract] AND "open access"[filter]'
        if since:
            date_str = since.strftime("%Y/%m/%d")
            query += f' AND ("{date_str}"[PDAT] : "3000"[PDAT])'

        params: dict[str, Any] = {
            "db": "pmc",
            "term": query,
            "retmax": MAX_ARTICLES_PER_DRUG,
            "retmode": "json",
            "sort": "date",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        resp = self.session.get(ESEARCH_URL, params=params, timeout=30)
        time.sleep(self.request_delay)

        if resp.status_code != 200:
            logger.warning("PMC esearch returned %d", resp.status_code)
            return []

        data = resp.json()
        result = data.get("esearchresult", {})
        pmc_ids = result.get("idlist", [])
        total = int(result.get("count", 0))
        logger.info("  Found %d PMC articles (total: %d)", len(pmc_ids), total)
        return pmc_ids

    def _fetch_pmc_articles(self, pmc_ids: list[str]) -> list[tuple[str, ET.Element]]:
        """Fetch full XML for a batch of PMC articles."""
        params: dict[str, Any] = {
            "db": "pmc",
            "id": ",".join(pmc_ids),
            "rettype": "xml",
            "retmode": "xml",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        resp = self.session.get(EFETCH_URL, params=params, timeout=120)
        time.sleep(self.request_delay)

        if resp.status_code != 200:
            logger.warning("PMC efetch returned %d", resp.status_code)
            return []

        root = ET.fromstring(resp.content)
        results = []

        for article_elem in root.findall(".//article"):
            # Extract PMC ID from article-id elements
            pmc_id = None
            for aid in article_elem.findall(".//article-id"):
                if aid.get("pub-id-type") == "pmc":
                    pmc_id = aid.text
                    break
            if pmc_id:
                # Ensure PMC prefix
                if not pmc_id.startswith("PMC"):
                    pmc_id = f"PMC{pmc_id}"
                results.append((pmc_id, article_elem))

        return results

    def _parse_article(
        self, pmc_id: str, article_elem: ET.Element, searched_drug: str
    ) -> Optional[RawRecord]:
        """Parse a PMC full-text XML article into a RawRecord."""
        now = datetime.utcnow()

        # Article metadata from front matter
        front = article_elem.find(".//front")
        if front is None:
            return None

        article_meta = front.find(".//article-meta")
        if article_meta is None:
            return None

        # Title
        title_group = article_meta.find("title-group")
        title = ""
        if title_group is not None:
            article_title = title_group.find("article-title")
            if article_title is not None:
                title = self._get_text(article_title)

        # PMID (linked)
        pmid = None
        for aid in article_meta.findall("article-id"):
            if aid.get("pub-id-type") == "pmid" and aid.text:
                pmid = aid.text

        # Article type from the root article element
        article_type = article_elem.get("article-type", "")

        # License
        license_elem = article_meta.find(".//license")
        license_text = None
        if license_elem is not None:
            license_type = license_elem.get("license-type", "")
            license_p = license_elem.find(".//license-p")
            if license_type:
                license_text = license_type
            elif license_p is not None:
                license_text = self._get_text(license_p)[:200]

        # Full text — extract from body
        body = article_elem.find(".//body")
        full_text = ""
        if body is not None:
            full_text = self._extract_body_text(body)

        if not full_text and not title:
            return None

        # Classify article
        is_protocol = self._is_protocol(title, article_type)
        is_systematic_review = self._is_systematic_review(title, article_type)

        # Build provenance
        raw_bytes = ET.tostring(article_elem, encoding="unicode").encode()
        resp_hash = Provenance.hash_response(raw_bytes)

        api_url = f"{EFETCH_URL}?db=pmc&id={pmc_id}"
        prov = Provenance(
            source_type=SourceType.PMC,
            api_endpoint=api_url,
            query_params={"pmc_id": pmc_id, "searched_drug": searched_drug},
            retrieved_at=now,
            raw_response_hash=resp_hash,
        )

        # Build data payload
        pmc_data = {
            "pmc_id": pmc_id,
            "pmid": pmid,
            "title": title,
            "full_text": full_text,
            "article_type": article_type or None,
            "is_protocol": is_protocol,
            "is_systematic_review": is_systematic_review,
            "license": license_text,
        }

        # Text content for embedding — title + truncated body
        text_for_embedding = title
        if full_text:
            # Take first ~2000 chars of body for embedding
            text_for_embedding = f"{title}. {full_text[:2000]}"

        identifiers: dict[str, Any] = {
            "pmc_id": pmc_id,
            "generic_name": searched_drug,
        }
        if pmid:
            identifiers["pmid"] = pmid

        return RawRecord(
            record_type=RecordType.PMC_ARTICLE,
            external_id=pmc_id,
            source_name="PubMed Central",
            provenance=prov,
            data=pmc_data,
            text_content=text_for_embedding,
            identifiers=identifiers,
        )

    def _extract_body_text(self, body_elem: ET.Element) -> str:
        """
        Extract readable text from the article body XML.

        Walks through sections and paragraphs, preserving section headers
        but stripping XML tags.
        """
        parts: list[str] = []

        for section in body_elem.findall(".//sec"):
            # Section title
            sec_title = section.find("title")
            if sec_title is not None:
                title_text = self._get_text(sec_title)
                if title_text:
                    parts.append(f"\n## {title_text}\n")

            # Paragraphs within this section (direct children only to avoid nesting)
            for para in section.findall("p"):
                para_text = self._get_text(para)
                if para_text:
                    parts.append(para_text)

        # If no sections found, try paragraphs directly under body
        if not parts:
            for para in body_elem.findall("p"):
                para_text = self._get_text(para)
                if para_text:
                    parts.append(para_text)

        return "\n\n".join(parts)

    @staticmethod
    def _is_protocol(title: str, article_type: str) -> bool:
        """Determine if this article is a clinical trial protocol."""
        if article_type and "protocol" in article_type.lower():
            return True
        for pattern in PROTOCOL_TITLE_PATTERNS:
            if pattern.search(title):
                return True
        return False

    @staticmethod
    def _is_systematic_review(title: str, article_type: str) -> bool:
        """Determine if this article is a systematic review or meta-analysis."""
        if article_type and "review" in article_type.lower():
            return True
        for pattern in REVIEW_TITLE_PATTERNS:
            if pattern.search(title):
                return True
        return False

    def _get_text(self, elem: Optional[ET.Element]) -> str:
        """Get all text content from an element, including mixed content."""
        if elem is None:
            return ""
        return "".join(elem.itertext()).strip()
