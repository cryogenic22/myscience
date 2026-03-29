"""
OpenFDA Drug Labels Connector.

Fetches FDA drug labeling (structured product labels) from the openFDA
drug/label API. These contain the official prescribing information:
indications, contraindications, warnings, boxed warnings, dosing, etc.

Produces:
  - DRUG_LABEL records (one per unique SPL set_id)

API docs: https://open.fda.gov/apis/drug/label/
Rate limits:
  - Without API key: 240 requests/minute, 1000/day
  - With API key: 240 requests/minute, 120000/day
"""

from __future__ import annotations

import json
import logging
import time
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

API_BASE = "https://api.fda.gov/drug/label.json"

# Target drugs to search — by openfda.generic_name in the label API.
TARGET_DRUGS = [
    "semaglutide", "tirzepatide", "liraglutide", "dulaglutide", "exenatide",
    "empagliflozin", "dapagliflozin", "canagliflozin",
    "sitagliptin", "linagliptin", "saxagliptin",
    "metformin", "pioglitazone",
    "sacubitril", "valsartan", "finerenone", "vericiguat", "ivabradine",
    "carvedilol", "metoprolol", "enalapril", "losartan",
    "spironolactone", "eplerenone",
]

MAX_LABELS_PER_DRUG = 10  # Most drugs have few distinct labels


class OpenFDALabelsConnector(BaseConnector):
    """
    Fetches FDA drug labeling from openFDA drug/label API.

    Strategy: For each target drug, query by openfda.generic_name,
    deduplicate by set_id (DailyMed SPL identifier), and extract
    structured label sections.
    """

    def __init__(self, config=None, target_overrides=None):
        self.config = config
        self.api_key = ""
        self.request_delay = 0.25  # ~4 req/sec (conservative under 240/min)
        if config:
            self.api_key = config.connectors.openfda_api_key
            self.request_delay = config.connectors.default_request_delay_seconds
        self.session = requests.Session()

        # Allow dynamic target overrides for TA onboarding
        overrides = target_overrides or {}
        self._drugs = overrides.get("drugs", TARGET_DRUGS)
        self._batch_size = overrides.get("batch_size", 8)  # 8 drugs per run
        self._batch_index = overrides.get("batch_index", 0)

    def source_type(self) -> SourceType:
        return SourceType.OPENFDA_LABELS

    def health_check(self) -> HealthCheckResult:
        start = time.time()
        try:
            params: dict[str, Any] = {
                "search": 'openfda.generic_name:"semaglutide"',
                "limit": 1,
            }
            if self.api_key:
                params["api_key"] = self.api_key
            resp = self.session.get(API_BASE, params=params, timeout=15)
            elapsed = (time.time() - start) * 1000
            if resp.status_code == 200:
                return HealthCheckResult(
                    healthy=True,
                    source_type=self.source_type(),
                    message="openFDA drug/label API reachable",
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
        Fetch drug labels for all target drugs.

        Args:
            since: If provided, only fetch labels with effective_date after
                   this date (incremental mode).
        """
        records: list[RawRecord] = []
        seen_set_ids: set[str] = set()

        # Chunk: process batch_size drugs per run
        start = self._batch_index * self._batch_size
        batch_drugs = self._drugs[start:start + self._batch_size]
        if not batch_drugs:
            batch_drugs = self._drugs[:self._batch_size]
        logger.info("Labels batch: drugs %d-%d of %d",
                     start, start + len(batch_drugs), len(self._drugs))

        for drug_name in batch_drugs:
            logger.info("Label search: %s", drug_name)
            try:
                labels = self._search_labels(drug_name, since)
            except Exception as e:
                logger.error("Label search failed for %s: %s", drug_name, e)
                continue

            for label in labels:
                set_id = label.get("set_id", "")
                if not set_id or set_id in seen_set_ids:
                    continue
                seen_set_ids.add(set_id)

                try:
                    record = self._parse_label(label, drug_name)
                    if record:
                        records.append(record)
                except Exception as e:
                    logger.error("Error parsing label %s: %s", set_id, e)

        logger.info(
            "Labels fetch complete: %d unique labels -> %d records",
            len(seen_set_ids), len(records),
        )
        return records

    def _search_labels(self, drug_name: str, since: Optional[datetime] = None) -> list[dict]:
        """Search openFDA drug/label API by generic name."""
        all_results: list[dict] = []
        skip = 0
        limit = 100

        # Build search query
        search = f'openfda.generic_name:"{drug_name}"'
        if since:
            date_str = since.strftime("%Y%m%d")
            search += f"+AND+effective_time:[{date_str}+TO+20991231]"

        while True:
            params: dict[str, Any] = {
                "search": search,
                "limit": limit,
                "skip": skip,
            }
            if self.api_key:
                params["api_key"] = self.api_key

            resp = self.session.get(API_BASE, params=params, timeout=30)

            if resp.status_code == 404:
                # No labels for this drug
                break
            if resp.status_code != 200:
                logger.warning(
                    "Label API returned %d for %s (skip=%d)",
                    resp.status_code, drug_name, skip,
                )
                break

            data = resp.json()
            results = data.get("results", [])
            if not results:
                break

            all_results.extend(results)

            total = data.get("meta", {}).get("results", {}).get("total", 0)
            skip += limit
            if skip >= total or len(all_results) >= MAX_LABELS_PER_DRUG:
                break

            time.sleep(self.request_delay)

        return all_results[:MAX_LABELS_PER_DRUG]

    def _parse_label(self, label: dict, searched_drug: str) -> Optional[RawRecord]:
        """Parse a single drug label result into a RawRecord."""
        now = datetime.utcnow()

        set_id = label.get("set_id", "")
        if not set_id:
            return None

        openfda = label.get("openfda", {})

        # Extract label sections — openFDA returns these as arrays of strings
        indications = self._join_section(label.get("indications_and_usage"))
        contraindications = self._join_section(label.get("contraindications"))
        warnings = self._join_section(label.get("warnings_and_precautions"))
        boxed_warning = self._join_section(label.get("boxed_warning"))
        dosage = self._join_section(label.get("dosage_and_administration"))
        adverse_reactions = self._join_section(label.get("adverse_reactions"))
        drug_interactions = self._join_section(label.get("drug_interactions"))
        clinical_pharm = self._join_section(label.get("clinical_pharmacology"))

        # If warnings_and_precautions is empty, try the plain warnings field
        if not warnings:
            warnings = self._join_section(label.get("warnings"))

        # Effective date
        effective_time = label.get("effective_time", "")
        effective_date = None
        if effective_time and len(effective_time) >= 8:
            effective_date = (
                f"{effective_time[:4]}-{effective_time[4:6]}-{effective_time[6:8]}"
            )

        # SPL version
        spl_version = label.get("version")
        if spl_version:
            try:
                spl_version = int(spl_version)
            except (ValueError, TypeError):
                spl_version = None

        # Manufacturer
        manufacturer_names = openfda.get("manufacturer_name", [])
        manufacturer = manufacturer_names[0] if manufacturer_names else None

        # Drug name from openfda fields
        generic_names = openfda.get("generic_name", [])
        brand_names = openfda.get("brand_name", [])
        drug_name = generic_names[0] if generic_names else searched_drug

        # Build provenance
        raw_bytes = json.dumps(label, sort_keys=True).encode()
        resp_hash = Provenance.hash_response(raw_bytes)

        api_url = f'{API_BASE}?search=set_id:"{set_id}"'
        prov = Provenance(
            source_type=SourceType.OPENFDA_LABELS,
            api_endpoint=api_url,
            query_params={"set_id": set_id, "searched_drug": searched_drug},
            retrieved_at=now,
            raw_response_hash=resp_hash,
        )

        # Build data payload
        label_data = {
            "set_id": set_id,
            "spl_version": spl_version,
            "drug_name": drug_name,
            "brand_name": brand_names[0] if brand_names else None,
            "indications": indications,
            "contraindications": contraindications,
            "warnings_and_precautions": warnings,
            "boxed_warning": boxed_warning,
            "dosage_and_administration": dosage,
            "adverse_reactions_text": adverse_reactions,
            "drug_interactions_text": drug_interactions,
            "clinical_pharmacology": clinical_pharm,
            "effective_date": effective_date,
            "manufacturer": manufacturer,
            "rxcui": openfda.get("rxcui", [None])[0] if openfda.get("rxcui") else None,
            "nui": openfda.get("nui", []),
            "pharm_class_epc": openfda.get("pharm_class_epc", []),
        }

        # Build text content for embedding — key label sections
        text_parts = []
        if drug_name:
            text_parts.append(f"Drug: {drug_name}")
        if indications:
            text_parts.append(f"Indications: {indications[:500]}")
        if boxed_warning:
            text_parts.append(f"Boxed Warning: {boxed_warning[:500]}")
        if warnings:
            text_parts.append(f"Warnings: {warnings[:500]}")
        if contraindications:
            text_parts.append(f"Contraindications: {contraindications[:300]}")
        text_content = " | ".join(text_parts) if text_parts else f"Label for {drug_name}"

        identifiers: dict[str, Any] = {
            "generic_name": searched_drug,
            "set_id": set_id,
        }
        if brand_names:
            identifiers["brand_name"] = brand_names[0]

        return RawRecord(
            record_type=RecordType.DRUG_LABEL,
            external_id=set_id,
            source_name="FDA Drug Labels (openFDA)",
            provenance=prov,
            data=label_data,
            text_content=text_content,
            identifiers=identifiers,
        )

    @staticmethod
    def _join_section(section: Optional[list[str]]) -> Optional[str]:
        """
        Join an openFDA label section (array of strings) into a single string.
        Returns None if empty.
        """
        if not section:
            return None
        joined = " ".join(s.strip() for s in section if s and s.strip())
        return joined if joined else None
