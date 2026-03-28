"""CMS NADAC (National Average Drug Acquisition Cost) connector.

Fetches Medicaid drug pricing data from the CMS open data portal.
Promotes scripts/fetch_nadac_pricing.py to a full BaseConnector
as recommended in the lead assessment.

API: https://data.medicaid.gov/resource/4j6z-xnwq.json
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from connectors.base import (
    BaseConnector,
    HealthCheckResult,
    RawRecord,
    Provenance,
    RecordType,
    SourceType,
)
from scripts.fetch_nadac_pricing import extract_drug_name, parse_nadac_record

logger = logging.getLogger(__name__)

NADAC_API_URL = "https://data.medicaid.gov/resource/4j6z-xnwq.json"


class NadacConnector(BaseConnector):
    """Connector for CMS NADAC drug pricing data."""

    def __init__(self, config=None, target_overrides: dict | None = None):
        self._config = config
        self._limit = (target_overrides or {}).get("limit", 5000)

    @property
    def source_type(self) -> SourceType:
        return SourceType.NADAC

    def health_check(self) -> HealthCheckResult:
        import requests
        try:
            resp = requests.get(NADAC_API_URL, params={"$limit": 1}, timeout=10)
            return HealthCheckResult(
                source_type=self.source_type,
                available=resp.status_code == 200,
                latency_ms=0,
                message=f"HTTP {resp.status_code}",
            )
        except Exception as e:
            return HealthCheckResult(
                source_type=self.source_type,
                available=False,
                latency_ms=0,
                message=str(e),
            )

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        """Fetch NADAC pricing records, converting to RawRecord for the pipeline."""
        records: list[RawRecord] = []
        page_size = 1000
        offset = 0

        while offset < self._limit:
            params: dict = {
                "$limit": min(page_size, self._limit - offset),
                "$offset": offset,
                "$order": "as_of_date DESC",
            }
            if since:
                params["$where"] = f"as_of_date >= '{since.strftime('%Y-%m-%d')}'"

            try:
                resp = self._fetch_with_retry(NADAC_API_URL, params=params)
                if resp.status_code != 200:
                    break
                api_records = resp.json()
                if not api_records:
                    break
            except Exception as e:
                logger.warning("NADAC fetch failed at offset %d: %s", offset, e)
                break

            for raw in api_records:
                parsed = parse_nadac_record(raw)
                if not parsed:
                    continue

                record = RawRecord(
                    record_type=RecordType.DRUG,
                    external_id=parsed["ndc_code"],
                    source_name="CMS NADAC",
                    provenance=Provenance(
                        source_type=self.source_type,
                        api_endpoint=NADAC_API_URL,
                        query_params=params,
                        retrieved_at=datetime.now(timezone.utc),
                        raw_response_hash=self._hash(raw),
                    ),
                    data={
                        "generic_name": parsed["drug_name"],
                        "ndc_code": parsed["ndc_code"],
                        "unit_price": parsed["unit_price"],
                        "unit": parsed["unit"],
                        "currency": "USD",
                        "country": "US",
                        "price_type": "nadac",
                        "effective_date": str(parsed["effective_date"]) if parsed.get("effective_date") else None,
                        "ndc_description": parsed.get("ndc_description", ""),
                    },
                    identifiers={
                        "generic_name": parsed["drug_name"],
                        "ndc_code": parsed["ndc_code"],
                    },
                )
                records.append(record)

            offset += page_size
            if len(api_records) < page_size:
                break

        logger.info("NADAC connector fetched %d pricing records", len(records))
        return records

    @staticmethod
    def _hash(data: dict) -> str:
        import hashlib, json
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
