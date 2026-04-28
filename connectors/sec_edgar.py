"""
SEC EDGAR Connector.

Fetches company filings from the SEC EDGAR system. For each target company
(by CIK), downloads recent 10-K and 10-Q filings and extracts key sections
(Risk Factors, MD&A) as text chunks for the knowledge layer.

Also fetches:
  - XBRL financial facts (revenue, R&D, profit, assets, cash) via companyfacts API
  - Full-text search for drug mentions in SEC filings

Produces:
  - COMPANY records (enriched with SEC metadata + XBRL financials)
  - DOCUMENT_CHUNK records (filing text sections)
  - EVENT records (drug mentions in filings via full-text search)

IMPORTANT: SEC requires a User-Agent header with company name + email.
Rate limit: 10 requests/second (strictly enforced).

API docs: https://www.sec.gov/edgar/sec-api-documentation
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote

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

SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
XBRL_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
EFTS_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
FILING_BASE_URL = "https://www.sec.gov/Archives/edgar/data"

# Filing types we care about
TARGET_FILING_TYPES = {"10-K", "10-Q", "10-K/A", "10-Q/A"}

# Max filings to process per company
MAX_FILINGS_PER_COMPANY = 4

# Sections to extract from filings
SECTION_PATTERNS = {
    "Risk Factors": (
        r"(?:Item\s*1A\.?\s*Risk\s*Factors)",
        r"(?:Item\s*1B\.?\s*Unresolved\s*Staff\s*Comments|Item\s*2\.?\s*Properties)",
    ),
    "MD&A": (
        r"(?:Item\s*7\.?\s*Management.{0,30}Discussion)",
        r"(?:Item\s*7A\.?\s*Quantitative|Item\s*8\.?\s*Financial\s*Statements)",
    ),
    "Business Overview": (
        r"(?:Item\s*1\.?\s*Business)",
        r"(?:Item\s*1A\.?\s*Risk\s*Factors|Item\s*2\.?\s*Properties)",
    ),
}

# Max results from EFTS full-text search
MAX_SEARCH_RESULTS = 20

# XBRL concept → canonical metric name mapping
# US-GAAP concepts
US_GAAP_METRICS: dict[str, str] = {
    "Revenues": "revenue",
    "RevenueFromContractWithCustomerExcludingAssessedTax": "revenue",
    "ResearchAndDevelopmentExpense": "rd_expense",
    "NetIncomeLoss": "profit",
    "CostOfGoodsSold": "cost_of_sales",
    "CostOfGoodsAndServicesSold": "cost_of_sales",
    "Assets": "total_assets",
    "CashAndCashEquivalentsAtCarryingValue": "cash",
    "CommonStockSharesOutstanding": "shares_outstanding",
}

# IFRS concepts
IFRS_METRICS: dict[str, str] = {
    "Revenue": "revenue",
    "ResearchAndDevelopmentExpense": "rd_expense",
    "ProfitLoss": "profit",
    "CostOfSales": "cost_of_sales",
    "Assets": "total_assets",
    "CashAndCashEquivalents": "cash",
}

# Text chunk size for embedding
CHUNK_SIZE = 2000  # characters
CHUNK_OVERLAP = 200


class SECEdgarConnector(BaseConnector):
    """
    Fetches SEC EDGAR filings for target pharma companies.

    Strategy: For each CIK, fetch the filing index, download recent
    10-K/10-Q filings, extract key text sections, chunk them for
    embedding.
    """

    def __init__(self, config=None, target_overrides=None):
        self.config = config
        self.company_name = "MarketZero"
        self.contact_email = "contact@marketzero.com"
        self.request_delay = 0.15  # ~6.6 req/sec (well under SEC 10 limit)
        self.target_ciks: list[str] = []
        self.target_drugs: list[str] = []

        if config:
            self.company_name = config.connectors.edgar_company_name
            self.contact_email = config.connectors.edgar_contact_email
            self.target_ciks = config.target_company_ciks
            self.request_delay = max(0.15, config.connectors.default_request_delay_seconds)

        # Allow dynamic target overrides for TA onboarding
        overrides = target_overrides or {}
        if overrides.get("ciks"):
            self.target_ciks = overrides["ciks"]
        if overrides.get("drugs"):
            self.target_drugs = overrides["drugs"]

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": f"{self.company_name}/1.0 {self.contact_email}",
            "Accept-Encoding": "gzip, deflate",
        })

    def source_type(self) -> SourceType:
        return SourceType.SEC_EDGAR

    def health_check(self) -> HealthCheckResult:
        start = time.time()
        try:
            # Test with Novo Nordisk CIK
            url = SUBMISSIONS_URL.format(cik="0001000694")
            resp = self.session.get(url, timeout=15)
            elapsed = (time.time() - start) * 1000
            if resp.status_code == 200:
                return HealthCheckResult(
                    healthy=True,
                    source_type=self.source_type(),
                    message="SEC EDGAR API reachable",
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
        """Fetch filings, XBRL financials, and drug mentions for all target companies."""
        records: list[RawRecord] = []

        if not self.target_ciks:
            logger.warning("No target CIKs configured for SEC EDGAR")
            return records

        # Step 1: Existing filing metadata + text chunks
        for cik in self.target_ciks:
            logger.info("Fetching EDGAR data for CIK: %s", cik)
            try:
                company_records = self._fetch_company(cik)
                records.extend(company_records)
            except Exception as e:
                logger.error("Error fetching CIK %s: %s", cik, e)

        # Step 2: XBRL financial facts for each CIK
        for cik in self.target_ciks:
            logger.info("Fetching XBRL facts for CIK: %s", cik)
            try:
                xbrl_records = self.fetch_xbrl_facts(cik)
                records.extend(xbrl_records)
            except Exception as e:
                logger.error("Error fetching XBRL for CIK %s: %s", cik, e)

        # Step 3: Full-text search for target drug names
        for drug in self.target_drugs:
            logger.info("Searching EDGAR filings for drug: %s", drug)
            try:
                search_records = self.search_filings(drug)
                records.extend(search_records)
            except Exception as e:
                logger.error("Error searching filings for %s: %s", drug, e)

        logger.info("SEC EDGAR fetch complete: %d records", len(records))
        return records

    def _fetch_company(self, cik: str) -> list[RawRecord]:
        """Fetch submissions for a single company and extract filing text."""
        records: list[RawRecord] = []
        now = datetime.utcnow()

        # Step 1: Get company submission index
        url = SUBMISSIONS_URL.format(cik=cik)
        resp = self.session.get(url, timeout=30)
        time.sleep(self.request_delay)

        if resp.status_code != 200:
            logger.warning("EDGAR returned %d for CIK %s", resp.status_code, cik)
            return records

        sub_data = resp.json()

        # Extract company metadata
        company_name = sub_data.get("name", "")
        ticker_list = sub_data.get("tickers", [])
        ticker = ticker_list[0] if ticker_list else None
        sic_code = sub_data.get("sic", "")
        sic_desc = sub_data.get("sicDescription", "")
        state = sub_data.get("stateOfIncorporation", "")
        fiscal_year_end = sub_data.get("fiscalYearEnd", "")

        raw_bytes = json.dumps(sub_data, sort_keys=True).encode()[:10000]
        resp_hash = Provenance.hash_response(raw_bytes)

        prov_company = Provenance(
            source_type=SourceType.SEC_EDGAR,
            api_endpoint=url,
            query_params={"cik": cik},
            retrieved_at=now,
            raw_response_hash=resp_hash,
        )

        # ---- COMPANY record ----
        company_data = {
            "company_name": company_name,
            "cik": cik,
            "ticker": ticker,
            "sic_code": sic_code,
            "region": state,
            "fiscal_year_end": fiscal_year_end,
            "country": "US",  # EDGAR companies are US-listed
        }

        records.append(RawRecord(
            record_type=RecordType.COMPANY,
            external_id=cik,
            source_name="SEC EDGAR",
            provenance=prov_company,
            data=company_data,
            text_content=f"{company_name}. SIC: {sic_code} - {sic_desc}",
            identifiers={"cik": cik, "company_name": company_name},
        ))

        # Step 2: Find recent target filings
        recent_filings = sub_data.get("filings", {}).get("recent", {})
        if not recent_filings:
            return records

        forms = recent_filings.get("form", [])
        accessions = recent_filings.get("accessionNumber", [])
        dates = recent_filings.get("filingDate", [])
        primary_docs = recent_filings.get("primaryDocument", [])

        filing_count = 0
        cik_clean = cik.lstrip("0")

        for i in range(len(forms)):
            if filing_count >= MAX_FILINGS_PER_COMPANY:
                break

            form_type = forms[i]
            if form_type not in TARGET_FILING_TYPES:
                continue

            accession = accessions[i] if i < len(accessions) else ""
            filing_date = dates[i] if i < len(dates) else ""
            primary_doc = primary_docs[i] if i < len(primary_docs) else ""

            if not accession or not primary_doc:
                continue

            # Download and parse the filing
            accession_clean = accession.replace("-", "")
            filing_url = f"{FILING_BASE_URL}/{cik_clean}/{accession_clean}/{primary_doc}"

            try:
                chunk_records = self._process_filing(
                    filing_url=filing_url,
                    accession=accession,
                    form_type=form_type,
                    filing_date=filing_date,
                    company_name=company_name,
                    cik=cik,
                )
                records.extend(chunk_records)
                filing_count += 1
            except Exception as e:
                logger.error("Error processing filing %s: %s", accession, e)

        return records

    def _process_filing(
        self,
        filing_url: str,
        accession: str,
        form_type: str,
        filing_date: str,
        company_name: str,
        cik: str,
    ) -> list[RawRecord]:
        """Download a filing and extract text chunks from key sections."""
        records: list[RawRecord] = []
        now = datetime.utcnow()

        logger.info("Downloading filing: %s (%s)", accession, form_type)
        resp = self.session.get(filing_url, timeout=60)
        time.sleep(self.request_delay)

        if resp.status_code != 200:
            logger.warning("Filing download returned %d: %s", resp.status_code, filing_url)
            return records

        # Get raw text (strip HTML tags if present)
        text = self._strip_html(resp.text)
        if not text or len(text) < 1000:
            logger.warning("Filing too short or empty: %s", accession)
            return records

        raw_bytes = resp.content[:10000]
        resp_hash = Provenance.hash_response(raw_bytes)

        prov = Provenance(
            source_type=SourceType.SEC_EDGAR,
            api_endpoint=filing_url,
            query_params={"accession": accession, "form_type": form_type},
            retrieved_at=now,
            raw_response_hash=resp_hash,
        )

        # Extract sections
        for section_name, (start_pattern, end_pattern) in SECTION_PATTERNS.items():
            section_text = self._extract_section(text, start_pattern, end_pattern)
            if not section_text or len(section_text) < 200:
                continue

            # Chunk the section
            chunks = self._chunk_text(section_text)

            for idx, chunk in enumerate(chunks):
                chunk_data = {
                    "accession_number": accession,
                    "company_name": company_name,
                    "cik": cik,
                    "filing_type": form_type,
                    "filing_date": filing_date,
                    "section_name": section_name,
                    "chunk_text": chunk,
                    "chunk_index": idx,
                }

                ext_id = f"{accession}|{section_name}|{idx}"
                records.append(RawRecord(
                    record_type=RecordType.DOCUMENT_CHUNK,
                    external_id=ext_id,
                    source_name="SEC EDGAR",
                    provenance=prov,
                    data=chunk_data,
                    text_content=chunk,
                    identifiers={"cik": cik, "company_name": company_name},
                ))

        logger.info(
            "  Extracted %d chunks from %s %s",
            len(records), form_type, accession,
        )

        # Cycle 1: 8-K → run through α1+α2+α3 pipeline (events / deals /
        # roles_history). Feature-flagged via MZ_8K_PIPELINE_ENABLED.
        # Errors logged inside the runner; never propagate to this loop.
        self._maybe_run_8k_pipeline(
            text=text,
            cik=cik,
            company_name=company_name,
            accession=accession,
            form_type=form_type,
            filing_date=filing_date,
        )

        return records

    def _maybe_run_8k_pipeline(
        self,
        *,
        text: str,
        cik: str,
        company_name: str,
        accession: str,
        form_type: str,
        filing_date: str,
    ) -> None:
        """Run the 8-K filing through the orchestrator if applicable.

        Gating handled inside connectors.sec_edgar_8k_runner — this method
        only checks the form-type filter and converts filing_date to a
        date object before delegating.
        """
        try:
            from connectors.sec_edgar_8k_runner import (
                run_8k_through_pipeline,
                should_run_pipeline_for_form,
            )
        except ImportError:
            # Module not available (e.g., older deploy missing files);
            # silently skip rather than break the connector.
            return

        if not should_run_pipeline_for_form(form_type):
            return

        # Database access — the connector instance has a config; the
        # actual Database is the one configured at import time.
        db = self._get_db_for_pipeline()
        if db is None:
            return

        try:
            from datetime import datetime as _dt
            parsed_date = _dt.fromisoformat(filing_date).date() \
                if filing_date else _dt.utcnow().date()
        except ValueError:
            parsed_date = datetime.utcnow().date()

        result = run_8k_through_pipeline(
            filing_text=text,
            cik=cik,
            company_name=company_name,
            accession=accession,
            filing_date=parsed_date,
            db=db,
        )
        if result is not None:
            logger.info(
                "  8-K pipeline: events=%d deals=%d roles=%d dupes=%d errors=%d",
                result.events_emitted,
                result.deals_emitted,
                result.roles_appended,
                result.duplicates_skipped,
                len(result.errors),
            )

    def _get_db_for_pipeline(self):
        """Return a Database handle for the 8-K pipeline, or None.

        Splits this out so tests + alternative wiring can override.
        """
        try:
            from db import Database
            from config import config
            db = Database(config.db.dsn)
            db.connect()
            return db
        except Exception as exc:
            logger.warning(
                "8-K pipeline: could not get Database handle: %s", exc,
            )
            return None

    # ------------------------------------------------------------------ #
    # XBRL Financial Facts
    # ------------------------------------------------------------------ #

    def fetch_xbrl_facts(self, cik: str) -> list[RawRecord]:
        """Fetch structured XBRL financial data for a company.

        Calls the SEC companyfacts API to extract key financial metrics
        (revenue, R&D expense, profit, assets, cash) from both US-GAAP
        and IFRS taxonomies. Only annual (FY) data points are returned.

        Args:
            cik: SEC Central Index Key (zero-padded 10-digit string).

        Returns:
            List of RawRecord objects with record_type=COMPANY containing
            one record per (fiscal_year, metric_name) pair.
        """
        records: list[RawRecord] = []
        now = datetime.utcnow()

        url = XBRL_FACTS_URL.format(cik=cik)
        resp = self.session.get(url, timeout=30)
        time.sleep(self.request_delay)

        if resp.status_code != 200:
            logger.warning("XBRL facts returned %d for CIK %s", resp.status_code, cik)
            return records

        data = resp.json()
        entity_name = data.get("entityName", "")
        facts = data.get("facts", {})

        raw_bytes = json.dumps(data, sort_keys=True).encode()[:10000]
        resp_hash = Provenance.hash_response(raw_bytes)

        prov = Provenance(
            source_type=SourceType.SEC_EDGAR,
            api_endpoint=url,
            query_params={"cik": cik},
            retrieved_at=now,
            raw_response_hash=resp_hash,
        )

        # Try US-GAAP taxonomy first, then IFRS
        taxonomy_maps = [
            ("us-gaap", US_GAAP_METRICS),
            ("ifrs-full", IFRS_METRICS),
        ]

        seen: set[tuple[int, str]] = set()  # (fiscal_year, metric_name) dedup

        for taxonomy, metric_map in taxonomy_maps:
            taxonomy_facts = facts.get(taxonomy, {})
            if not taxonomy_facts:
                continue

            for concept_name, canonical_name in metric_map.items():
                concept_data = taxonomy_facts.get(concept_name)
                if not concept_data:
                    continue

                # Iterate over all unit types (USD, DKK, shares, etc.)
                units_dict = concept_data.get("units", {})
                for currency, data_points in units_dict.items():
                    for dp in data_points:
                        fp = dp.get("fp", "")
                        fy = dp.get("fy")

                        # Only annual data
                        if fp != "FY" or fy is None:
                            continue

                        dedup_key = (fy, canonical_name)
                        if dedup_key in seen:
                            continue
                        seen.add(dedup_key)

                        metric_data = {
                            "cik": cik,
                            "company_name": entity_name,
                            "fiscal_year": fy,
                            "fiscal_period": "FY",
                            "metric_name": canonical_name,
                            "metric_value": dp.get("val"),
                            "currency": currency,
                            "filed_date": dp.get("filed"),
                        }

                        ext_id = f"xbrl|{cik}|{fy}|{canonical_name}"
                        records.append(RawRecord(
                            record_type=RecordType.COMPANY,
                            external_id=ext_id,
                            source_name="SEC EDGAR",
                            provenance=prov,
                            data=metric_data,
                            text_content=(
                                f"{entity_name} {canonical_name} FY{fy}: "
                                f"{dp.get('val')} {currency}"
                            ),
                            identifiers={"cik": cik, "company_name": entity_name},
                        ))

        logger.info("  XBRL: extracted %d financial data points for CIK %s", len(records), cik)
        return records

    # ------------------------------------------------------------------ #
    # Full-Text Search (EFTS)
    # ------------------------------------------------------------------ #

    def search_filings(self, drug_name: str) -> list[RawRecord]:
        """Search SEC filings for mentions of a drug name.

        Uses the EDGAR Full-Text Search System (EFTS) to find 10-K, 10-Q,
        and 8-K filings that mention the given drug name.

        Args:
            drug_name: Drug name to search for (exact phrase match).

        Returns:
            List of RawRecord objects with record_type=EVENT, capped at
            MAX_SEARCH_RESULTS (20).
        """
        records: list[RawRecord] = []
        now = datetime.utcnow()

        url = EFTS_SEARCH_URL
        params = {
            "q": f'"{drug_name}"',
            "forms": "10-K,10-Q,8-K",
        }

        resp = self.session.get(url, params=params, timeout=30)
        time.sleep(self.request_delay)

        if resp.status_code != 200:
            logger.warning("EFTS search returned %d for '%s'", resp.status_code, drug_name)
            return records

        data = resp.json()

        raw_bytes = json.dumps(data, sort_keys=True).encode()[:10000]
        resp_hash = Provenance.hash_response(raw_bytes)

        prov = Provenance(
            source_type=SourceType.SEC_EDGAR,
            api_endpoint=url,
            query_params=params,
            retrieved_at=now,
            raw_response_hash=resp_hash,
        )

        hits = data.get("hits", {}).get("hits", [])

        for hit in hits[:MAX_SEARCH_RESULTS]:
            source = hit.get("_source", {})
            hit_id = hit.get("_id", "")

            company_name = source.get("entity_name", "")
            form_type = source.get("form_type", "")
            file_date = source.get("file_date", "")
            display_names = source.get("display_names", [])
            description = display_names[0] if display_names else company_name

            filing_data = {
                "drug_name": drug_name,
                "company_name": company_name,
                "form_type": form_type,
                "file_date": file_date,
                "description": f"{drug_name} mentioned in {form_type} by {description}",
            }

            ext_id = f"efts|{drug_name}|{hit_id}" if hit_id else f"efts|{drug_name}|{company_name}|{file_date}"
            records.append(RawRecord(
                record_type=RecordType.EVENT,
                external_id=ext_id,
                source_name="SEC EDGAR",
                provenance=prov,
                data=filing_data,
                text_content=f"{drug_name} mentioned in {form_type} filing by {company_name} ({file_date})",
                identifiers={"drug_name": drug_name, "company_name": company_name},
            ))

        logger.info("  EFTS: found %d filings mentioning '%s'", len(records), drug_name)
        return records

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _extract_section(self, text: str, start_pattern: str, end_pattern: str) -> str:
        """Extract text between two section header patterns."""
        start_match = re.search(start_pattern, text, re.IGNORECASE)
        if not start_match:
            return ""

        end_match = re.search(end_pattern, text[start_match.end():], re.IGNORECASE)
        if end_match:
            section = text[start_match.start():start_match.end() + end_match.start()]
        else:
            # Take up to 50K chars if no end boundary found
            section = text[start_match.start():start_match.start() + 50000]

        return section.strip()

    def _chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks for embedding."""
        chunks = []
        start = 0
        while start < len(text):
            end = start + CHUNK_SIZE
            chunk = text[start:end]

            # Try to break at sentence boundary
            if end < len(text):
                last_period = chunk.rfind(". ")
                if last_period > CHUNK_SIZE // 2:
                    chunk = chunk[:last_period + 1]
                    end = start + last_period + 1

            chunk = chunk.strip()
            if chunk:
                chunks.append(chunk)

            start = end - CHUNK_OVERLAP
            if start <= 0 and end >= len(text):
                break

        return chunks

    def _strip_html(self, text: str) -> str:
        """Remove HTML tags and normalize whitespace."""
        # Remove style and script blocks
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Decode common HTML entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&nbsp;", " ").replace("&#160;", " ")
        # Normalize whitespace
        text = re.sub(r"\s+", " ", text)
        text = re.sub(r"\n\s*\n", "\n\n", text)
        return text.strip()
