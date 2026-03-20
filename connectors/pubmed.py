"""
PubMed Connector.

Fetches biomedical literature from NCBI PubMed using the E-Utilities API.
Two-step process: esearch (search → PMID list) + efetch (fetch → XML).

Produces:
  - LITERATURE records (one per article)
  - INVESTIGATOR records (from author lists, for key/first/last authors)

API docs: https://www.ncbi.nlm.nih.gov/books/NBK25497/
"""

from __future__ import annotations

import logging
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

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# MeSH terms and drug names to search for.
TARGET_SEARCH_QUERIES = [
    # ── Diabetes / Obesity — drug-specific ──
    '"semaglutide"[Title/Abstract]',
    '"tirzepatide"[Title/Abstract]',
    '"liraglutide"[Title/Abstract]',
    '"dulaglutide"[Title/Abstract]',
    '"exenatide"[Title/Abstract]',
    '"lixisenatide"[Title/Abstract]',
    '"empagliflozin"[Title/Abstract]',
    '"dapagliflozin"[Title/Abstract]',
    '"canagliflozin"[Title/Abstract]',
    '"ertugliflozin"[Title/Abstract]',
    '"sitagliptin"[Title/Abstract]',
    '"linagliptin"[Title/Abstract]',
    '"saxagliptin"[Title/Abstract]',
    '"alogliptin"[Title/Abstract]',
    '"pioglitazone"[Title/Abstract]',
    # ── Diabetes / Obesity — MeSH-based ──
    '"GLP-1 receptor agonist"[Title/Abstract] AND "type 2 diabetes"[Title/Abstract]',
    '"SGLT2 inhibitor"[Title/Abstract] AND "type 2 diabetes"[Title/Abstract]',
    '"DPP-4 inhibitor"[Title/Abstract] AND "type 2 diabetes"[Title/Abstract]',
    # ── Cardiovascular / Heart Failure — drug-specific ──
    '"sacubitril valsartan"[Title/Abstract]',
    '"finerenone"[Title/Abstract]',
    '"vericiguat"[Title/Abstract]',
    '"ivabradine"[Title/Abstract]',
    '"carvedilol"[Title/Abstract] AND "heart failure"[Title/Abstract]',
    '"metoprolol"[Title/Abstract] AND "heart failure"[Title/Abstract]',
    '"spironolactone"[Title/Abstract] AND "heart failure"[Title/Abstract]',
    '"eplerenone"[Title/Abstract] AND "heart failure"[Title/Abstract]',
    '"enalapril"[Title/Abstract] AND "heart failure"[Title/Abstract]',
    '"losartan"[Title/Abstract] AND "heart failure"[Title/Abstract]',
    # ── Cardiovascular / Heart Failure — class-based ──
    '"SGLT2 inhibitor"[Title/Abstract] AND "heart failure"[Title/Abstract]',
    '"GLP-1 receptor agonist"[Title/Abstract] AND "cardiovascular"[Title/Abstract]',
    '"ARNI"[Title/Abstract] AND "heart failure"[Title/Abstract]',
    '"mineralocorticoid receptor antagonist"[Title/Abstract] AND "heart failure"[Title/Abstract]',
    '"heart failure"[Title/Abstract] AND "reduced ejection fraction"[Title/Abstract]',
    '"heart failure"[Title/Abstract] AND "preserved ejection fraction"[Title/Abstract]',
    # ── Protocols & Systematic Reviews ──
    '"study protocol"[Title] AND ("semaglutide" OR "tirzepatide" OR "empagliflozin" OR "dapagliflozin")',
    '"study protocol"[Title] AND ("sacubitril" OR "finerenone" OR "heart failure")',
    '"systematic review"[Title] AND "GLP-1"[Title/Abstract]',
    '"systematic review"[Title] AND "SGLT2"[Title/Abstract]',
    '"systematic review"[Title] AND "heart failure"[Title/Abstract] AND ("pharmacotherapy" OR "drug" OR "treatment")',
    '"meta-analysis"[Publication Type] AND "semaglutide"[Title/Abstract]',
    '"meta-analysis"[Publication Type] AND "SGLT2 inhibitor"[Title/Abstract]',
    '"meta-analysis"[Publication Type] AND "heart failure"[Title/Abstract] AND "mortality"[Title/Abstract]',
    '"randomized controlled trial"[Publication Type] AND "tirzepatide"[Title/Abstract]',
    '"randomized controlled trial"[Publication Type] AND "sacubitril valsartan"[Title/Abstract]',
    '"clinical trial protocol"[Publication Type] AND ("GLP-1" OR "SGLT2" OR "heart failure")',
]

MAX_ARTICLES_PER_QUERY = 50  # Keep total manageable


class PubMedConnector(BaseConnector):
    """
    Fetches biomedical literature from PubMed.

    Strategy: For each target query, search PubMed, get PMIDs,
    then fetch article metadata in batches via efetch XML.
    """

    def __init__(self, config=None, target_overrides=None):
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

        # Allow dynamic target overrides for TA onboarding
        overrides = target_overrides or {}
        self._queries = overrides.get("queries", TARGET_SEARCH_QUERIES)

    def source_type(self) -> SourceType:
        return SourceType.PUBMED

    def health_check(self) -> HealthCheckResult:
        start = time.time()
        try:
            params = {
                "db": "pubmed",
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
                    message="PubMed E-Utilities reachable",
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
        """Fetch articles for all target queries."""
        records: list[RawRecord] = []
        seen_pmids: set[str] = set()

        for query in self._queries:
            logger.info("PubMed search: %s", query)
            try:
                pmids = self._esearch(query)
            except Exception as e:
                logger.error("esearch failed for %s: %s", query, e)
                continue

            # Deduplicate
            new_pmids = [p for p in pmids if p not in seen_pmids]
            seen_pmids.update(new_pmids)

            if not new_pmids:
                continue

            # Fetch in batches of 50
            for batch_start in range(0, len(new_pmids), 50):
                batch = new_pmids[batch_start:batch_start + 50]
                try:
                    articles = self._efetch(batch)
                    for article in articles:
                        article_records = self._parse_article(article)
                        records.extend(article_records)
                except Exception as e:
                    logger.error("efetch failed: %s", e)

                time.sleep(self.request_delay)

        logger.info(
            "PubMed fetch complete: %d unique PMIDs → %d records",
            len(seen_pmids), len(records),
        )
        return records

    def _esearch(self, query: str) -> list[str]:
        """Search PubMed and return list of PMIDs."""
        params: dict[str, Any] = {
            "db": "pubmed",
            "term": query,
            "retmax": MAX_ARTICLES_PER_QUERY,
            "retmode": "json",
            "sort": "date",
            "datetype": "pdat",
            "reldate": 730,  # Last 2 years
        }
        if self.api_key:
            params["api_key"] = self.api_key

        resp = self.session.get(ESEARCH_URL, params=params, timeout=30)
        time.sleep(self.request_delay)

        if resp.status_code != 200:
            logger.warning("esearch returned %d", resp.status_code)
            return []

        data = resp.json()
        result = data.get("esearchresult", {})
        pmids = result.get("idlist", [])
        total = int(result.get("count", 0))
        logger.info("  Found %d PMIDs (total: %d)", len(pmids), total)
        return pmids

    def _efetch(self, pmids: list[str]) -> list[ET.Element]:
        """Fetch article XML for a batch of PMIDs."""
        params: dict[str, Any] = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "xml",
            "retmode": "xml",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        resp = self.session.get(EFETCH_URL, params=params, timeout=60)
        time.sleep(self.request_delay)

        if resp.status_code != 200:
            logger.warning("efetch returned %d", resp.status_code)
            return []

        root = ET.fromstring(resp.content)
        return list(root.findall(".//PubmedArticle"))

    def _parse_article(self, article_elem: ET.Element) -> list[RawRecord]:
        """Parse a PubmedArticle XML element into records."""
        records: list[RawRecord] = []
        now = datetime.utcnow()

        medline = article_elem.find("MedlineCitation")
        if medline is None:
            return records

        # PMID
        pmid_elem = medline.find("PMID")
        pmid = pmid_elem.text if pmid_elem is not None else ""
        if not pmid:
            return records

        article = medline.find("Article")
        if article is None:
            return records

        # Title
        title_elem = article.find("ArticleTitle")
        title = self._get_text(title_elem)

        # Abstract
        abstract_elem = article.find("Abstract")
        abstract_parts = []
        if abstract_elem is not None:
            for text in abstract_elem.findall("AbstractText"):
                label = text.get("Label", "")
                content = self._get_text(text)
                if label and content:
                    abstract_parts.append(f"{label}: {content}")
                elif content:
                    abstract_parts.append(content)
        abstract = " ".join(abstract_parts)

        # Authors
        authors = []
        author_details = []
        author_list = article.find("AuthorList")
        if author_list is not None:
            for author_elem in author_list.findall("Author"):
                last = self._get_elem_text(author_elem, "LastName")
                first = self._get_elem_text(author_elem, "ForeName")
                if last:
                    name = f"{last}, {first}" if first else last
                    authors.append(name)

                    # Collect detailed author info for investigator records
                    affiliations = []
                    for aff in author_elem.findall("AffiliationInfo/Affiliation"):
                        if aff.text:
                            affiliations.append(aff.text)

                    orcid = None
                    for ident in author_elem.findall("Identifier"):
                        if ident.get("Source") == "ORCID" and ident.text:
                            orcid = ident.text.replace("https://orcid.org/", "").replace("http://orcid.org/", "")

                    author_details.append({
                        "name": name,
                        "affiliation": affiliations[0] if affiliations else None,
                        "orcid": orcid,
                    })

        # Journal
        journal_elem = article.find("Journal")
        journal = ""
        if journal_elem is not None:
            journal_title = journal_elem.find("Title")
            if journal_title is not None and journal_title.text:
                journal = journal_title.text

        # Publication date
        pub_date = self._extract_pub_date(article)

        # MeSH terms
        mesh_terms = []
        mesh_ids = []
        mesh_list = medline.find("MeshHeadingList")
        if mesh_list is not None:
            for heading in mesh_list.findall("MeshHeading"):
                descriptor = heading.find("DescriptorName")
                if descriptor is not None:
                    if descriptor.text:
                        mesh_terms.append(descriptor.text)
                    uid = descriptor.get("UI", "")
                    if uid:
                        mesh_ids.append(uid)

        # DOI
        doi = None
        article_ids = article_elem.find("PubmedData/ArticleIdList")
        if article_ids is not None:
            for aid in article_ids.findall("ArticleId"):
                if aid.get("IdType") == "doi" and aid.text:
                    doi = aid.text

        # Publication type
        pub_types = []
        pub_type_list = article.find("PublicationTypeList")
        if pub_type_list is not None:
            for pt in pub_type_list.findall("PublicationType"):
                if pt.text:
                    pub_types.append(pt.text)

        # Grant agencies
        grant_agencies = []
        grant_list = article.find("GrantList")
        if grant_list is not None:
            for grant in grant_list.findall("Grant"):
                agency = self._get_elem_text(grant, "Agency")
                if agency and agency not in grant_agencies:
                    grant_agencies.append(agency)

        # Keywords
        keywords = []
        kw_list = medline.find("KeywordList")
        if kw_list is not None:
            for kw in kw_list.findall("Keyword"):
                if kw.text:
                    keywords.append(kw.text)

        # Build provenance
        import hashlib
        raw_bytes = ET.tostring(article_elem, encoding="unicode").encode()
        resp_hash = Provenance.hash_response(raw_bytes)

        prov = Provenance(
            source_type=SourceType.PUBMED,
            api_endpoint=f"{EFETCH_URL}?db=pubmed&id={pmid}",
            query_params={"pmid": pmid},
            retrieved_at=now,
            raw_response_hash=resp_hash,
        )

        # ---- LITERATURE record ----
        article_data = {
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "authors": ", ".join(authors) if authors else None,
            "journal": journal,
            "publication_date": pub_date,
            "mesh_terms": mesh_terms if mesh_terms else None,
            "mesh_descriptor_ids": mesh_ids if mesh_ids else None,
            "doi": doi,
            "publication_type": pub_types[0] if pub_types else None,
            "grant_agencies": grant_agencies if grant_agencies else None,
            "keywords": keywords if keywords else None,
        }

        identifiers: dict[str, Any] = {"pmid": pmid}
        if mesh_ids:
            identifiers["mesh_ids"] = mesh_ids

        text_content = f"{title}. {abstract}" if abstract else title

        records.append(RawRecord(
            record_type=RecordType.LITERATURE,
            external_id=pmid,
            source_name="PubMed",
            provenance=prov,
            data=article_data,
            text_content=text_content,
            identifiers=identifiers,
        ))

        # ---- INVESTIGATOR records (first and last authors only, to limit volume) ----
        key_authors = []
        if author_details:
            key_authors.append(author_details[0])  # first author
            if len(author_details) > 1:
                key_authors.append(author_details[-1])  # last/senior author

        for author in key_authors:
            if not author["name"]:
                continue

            inv_data = {
                "author_name": author["name"],
                "author_affiliation": author["affiliation"],
                "author_orcid": author.get("orcid"),
                "source_pmid": pmid,
            }

            ext_id = f"INV|PMID:{pmid}|{author['name'][:40]}"
            records.append(RawRecord(
                record_type=RecordType.INVESTIGATOR,
                external_id=ext_id,
                source_name="PubMed",
                provenance=prov,
                data=inv_data,
                identifiers={"investigator_name": author["name"]},
            ))

        return records

    def _get_text(self, elem: Optional[ET.Element]) -> str:
        """Get all text content from an element, including mixed content."""
        if elem is None:
            return ""
        return "".join(elem.itertext()).strip()

    def _get_elem_text(self, parent: ET.Element, tag: str) -> str:
        """Get text of a child element."""
        elem = parent.find(tag)
        return elem.text.strip() if elem is not None and elem.text else ""

    def _extract_pub_date(self, article: ET.Element) -> Optional[str]:
        """Extract publication date in YYYY-MM-DD format."""
        # Try ArticleDate first (electronic publication)
        for date_elem in article.findall("ArticleDate"):
            year = self._get_elem_text(date_elem, "Year")
            month = self._get_elem_text(date_elem, "Month")
            day = self._get_elem_text(date_elem, "Day")
            if year:
                month = month.zfill(2) if month else "01"
                day = day.zfill(2) if day else "01"
                return f"{year}-{month}-{day}"

        # Fall back to Journal PubDate
        pub_date = article.find("Journal/JournalIssue/PubDate")
        if pub_date is not None:
            year = self._get_elem_text(pub_date, "Year")
            month = self._get_elem_text(pub_date, "Month")
            if year:
                month_num = self._month_to_num(month)
                return f"{year}-{month_num}-01"

        return None

    def _month_to_num(self, month: str) -> str:
        """Convert month name or number to 2-digit number."""
        month_map = {
            "jan": "01", "feb": "02", "mar": "03", "apr": "04",
            "may": "05", "jun": "06", "jul": "07", "aug": "08",
            "sep": "09", "oct": "10", "nov": "11", "dec": "12",
        }
        if month.isdigit():
            return month.zfill(2)
        return month_map.get(month.lower()[:3], "01")
