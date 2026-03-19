"""
FDA Drug Shortages / Enforcement Connector.

Fetches drug enforcement actions from the openFDA drug/enforcement API.
These include recalls, market withdrawals, and safety alerts that serve
as proxy signals for supply disruptions.

Produces:
  - EVENT records (market events: recalls, enforcement actions)

API docs: https://open.fda.gov/apis/drug/enforcement/
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

API_BASE = "https://api.fda.gov/drug/enforcement.json"

# Target drug generic names — aligned with our therapeutic areas.
TARGET_SEARCH_TERMS = [
    # ── Diabetes / Obesity ──
    "semaglutide",
    "liraglutide",
    "tirzepatide",
    "dulaglutide",
    "exenatide",
    "empagliflozin",
    "dapagliflozin",
    "canagliflozin",
    "sitagliptin",
    "linagliptin",
    "saxagliptin",
    "metformin",
    "pioglitazone",
    "insulin",
    "glargine",
    "lispro",
    "aspart",
    "degludec",
    # ── Cardiovascular / Heart Failure ──
    "sacubitril",
    "valsartan",
    "finerenone",
    "vericiguat",
    "ivabradine",
    "carvedilol",
    "metoprolol",
    "enalapril",
    "losartan",
    "spironolactone",
    "eplerenone",
]


class FDAShortagesConnector(BaseConnector):
    """
    Fetches drug enforcement actions from the openFDA enforcement API.

    Strategy: Search by product_description for each target drug name.
    Each enforcement action becomes an EVENT record linked to the drug.
    """

    def __init__(self, config=None):
        self.config = config
        self.api_key = ""
        self.request_delay = 0.5
        if config:
            self.api_key = config.connectors.openfda_api_key
            self.request_delay = config.connectors.default_request_delay_seconds
        self.session = requests.Session()

    def source_type(self) -> SourceType:
        return SourceType.FDA_SHORTAGES

    def health_check(self) -> HealthCheckResult:
        start = time.time()
        try:
            resp = self.session.get(
                API_BASE,
                params={"search": 'product_description:"metformin"', "limit": 1},
                timeout=15,
            )
            elapsed = (time.time() - start) * 1000
            if resp.status_code == 200:
                return HealthCheckResult(
                    healthy=True,
                    source_type=self.source_type(),
                    message="FDA enforcement API reachable",
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
        """Fetch enforcement actions for target drugs."""
        records: list[RawRecord] = []
        seen_ids: set[str] = set()

        for term in TARGET_SEARCH_TERMS:
            logger.info("Fetching enforcement actions for: %s", term)
            try:
                actions = self._search_enforcement(term)
            except Exception as e:
                logger.error("Error fetching %s: %s", term, e)
                continue

            for action in actions:
                recall_number = action.get("recall_number", "")
                if not recall_number or recall_number in seen_ids:
                    continue
                seen_ids.add(recall_number)

                try:
                    record = self._parse_action(action, term)
                    if record:
                        records.append(record)
                except Exception as e:
                    logger.error("Error parsing %s: %s", recall_number, e)

            time.sleep(self.request_delay)

        logger.info(
            "FDA enforcement fetch complete: %d actions → %d records",
            len(seen_ids), len(records),
        )
        return records

    def _search_enforcement(self, term: str) -> list[dict]:
        """Search enforcement API for a drug term, paginate."""
        all_results = []
        skip = 0
        limit = 100

        while True:
            params: dict[str, Any] = {
                "search": f'product_description:"{term}"',
                "limit": limit,
                "skip": skip,
            }
            if self.api_key:
                params["api_key"] = self.api_key

            resp = self.session.get(API_BASE, params=params, timeout=30)

            if resp.status_code == 404:
                break
            if resp.status_code != 200:
                logger.warning("FDA enforcement API returned %d for %s", resp.status_code, term)
                break

            data = resp.json()
            results = data.get("results", [])
            if not results:
                break

            all_results.extend(results)

            total = data.get("meta", {}).get("results", {}).get("total", 0)
            skip += limit
            if skip >= total or skip >= 500:
                break

            time.sleep(self.request_delay)

        return all_results

    def _parse_action(self, action: dict, search_term: str) -> Optional[RawRecord]:
        """Parse an enforcement action into an EVENT record."""
        now = datetime.utcnow()
        recall_number = action.get("recall_number", "")
        if not recall_number:
            return None

        raw_bytes = json.dumps(action, sort_keys=True).encode()
        resp_hash = Provenance.hash_response(raw_bytes)

        prov = Provenance(
            source_type=SourceType.FDA_SHORTAGES,
            api_endpoint=f"{API_BASE}?search=recall_number:{recall_number}",
            query_params={"recall_number": recall_number, "search_term": search_term},
            retrieved_at=now,
            raw_response_hash=resp_hash,
        )

        # Determine event type and impact
        classification = action.get("classification", "")
        status = action.get("status", "")
        voluntary = action.get("voluntary_mandated", "")

        event_type = self._classify_event(classification, status)
        impact_score = self._estimate_impact(classification, action)

        # Extract company name from recalling_firm
        company_name = action.get("recalling_firm", "")

        # Try to extract generic drug name from product_description
        product_desc = action.get("product_description", "")
        generic_name = self._extract_generic_name(product_desc, search_term)

        # Build description
        reason = action.get("reason_for_recall", "")
        description = f"{classification} {status}: {reason}".strip()
        if action.get("distribution_pattern"):
            description += f" Distribution: {action['distribution_pattern']}"

        raw_date = action.get("report_date") or action.get("recall_initiation_date") or action.get("center_classification_date")
        event_date = self._parse_fda_date(raw_date)

        event_data = {
            "generic_name": generic_name,
            "company_name": company_name,
            "event_type": event_type,
            "description": description,
            "event_date": event_date,
            "impact_score": impact_score,
            "status": status,
            "shortage_reason": reason,
        }

        identifiers: dict[str, Any] = {}
        if generic_name:
            identifiers["generic_name"] = generic_name
        if company_name:
            identifiers["company_name"] = company_name

        return RawRecord(
            record_type=RecordType.EVENT,
            external_id=recall_number,
            source_name="FDA Enforcement Actions",
            provenance=prov,
            data=event_data,
            text_content=f"{product_desc}. {reason}",
            identifiers=identifiers,
        )

    def _classify_event(self, classification: str, status: str) -> str:
        """Classify the enforcement action into an event type."""
        if "Class I" in classification:
            return "RECALL_CLASS_I"
        elif "Class II" in classification:
            return "RECALL_CLASS_II"
        elif "Class III" in classification:
            return "RECALL_CLASS_III"
        return "ENFORCEMENT_ACTION"

    def _estimate_impact(self, classification: str, action: dict) -> float:
        """Estimate impact score (0-1) based on classification and scope."""
        base_score = {
            "Class I": 0.9,
            "Class II": 0.6,
            "Class III": 0.3,
        }.get(classification, 0.5)

        # Boost for nationwide distribution
        dist = action.get("distribution_pattern", "").lower()
        if "nationwide" in dist or "worldwide" in dist:
            base_score = min(1.0, base_score + 0.1)

        return round(base_score, 2)

    def _parse_fda_date(self, date_str: Optional[str]) -> Optional[str]:
        """Parse FDA date formats (YYYYMMDD) into ISO date (YYYY-MM-DD)."""
        if not date_str:
            return None
        date_str = date_str.strip()
        if len(date_str) == 8 and date_str.isdigit():
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
        if len(date_str) == 10 and "-" in date_str:
            return date_str  # Already ISO format
        return None

    def _extract_generic_name(self, description: str, search_term: str) -> str:
        """Extract the generic drug name from product description."""
        desc_lower = description.lower()
        # If the search term appears in the description, use it
        if search_term.lower() in desc_lower:
            return search_term.lower()
        return search_term.lower()
