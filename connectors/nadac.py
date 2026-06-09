"""CMS NADAC (National Average Drug Acquisition Cost) connector.

Fetches Medicaid drug pricing data from the CMS open data portal.
Promotes scripts/fetch_nadac_pricing.py to a full BaseConnector
as recommended in the lead assessment.

Source (verified 2026-06-08): the DKAN datastore query API for the rolling
"NADAC 2026" weekly reference dataset —
``https://data.medicaid.gov/api/1/datastore/query/<dataset-id>/0`` — which
returns ``{"results": [...], "count": N, ...}`` with fields ``ndc`` /
``ndc_description`` / ``nadac_per_unit`` / ``effective_date`` / ``as_of_date`` /
``pricing_unit`` / ``classification_for_rate_setting``.

CMS migrated off the legacy Socrata endpoint (``/resource/4j6z-xnwq.json`` now
404s, 2025/26). If the dataset id rolls or the endpoint is unreachable, the
connector logs the count and returns the records it did parse — it never
silently swallows rows (conservation #2: dropped/skipped counts are logged).
The dataset id is shared from ``scripts.fetch_nadac_pricing`` so there is a
single place to bump it each year.
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
from scripts.fetch_nadac_pricing import (
    NADAC_API_URL,
    extract_drug_name,
    parse_nadac_record,
)

logger = logging.getLogger(__name__)


def _unwrap(payload) -> list[dict]:
    """The DKAN query API wraps rows in ``results``; the legacy Socrata
    endpoint returned a flat array. Accept both."""
    if isinstance(payload, dict):
        return payload.get("results", []) or []
    return payload if isinstance(payload, list) else []


class NadacConnector(BaseConnector):
    """Connector for CMS NADAC drug pricing data."""

    def __init__(self, config=None, target_overrides: dict | None = None):
        self._config = config
        self._limit = (target_overrides or {}).get("limit", 5000)

    def source_type(self) -> SourceType:
        return SourceType.NADAC

    def health_check(self) -> HealthCheckResult:
        import requests
        try:
            resp = requests.get(NADAC_API_URL, params={"limit": 1}, timeout=10)
            return HealthCheckResult(
                source_type=self.source_type(),
                healthy=resp.status_code == 200,
                response_time_ms=0,
                message=f"HTTP {resp.status_code}",
            )
        except Exception as e:
            return HealthCheckResult(
                source_type=self.source_type(),
                healthy=False,
                response_time_ms=0,
                message=str(e),
            )

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        """Fetch NADAC pricing records, converting to RawRecord for the pipeline.

        Conservation #2: rows that parse to no usable price, or carry no NDC,
        are *counted* (logged) rather than silently dropped.
        """
        records: list[RawRecord] = []
        page_size = 1000
        offset = 0
        skipped_no_price = 0
        skipped_no_ndc = 0

        while offset < self._limit:
            params: dict = {
                "limit": min(page_size, self._limit - offset),
                "offset": offset,
            }
            if since:
                params["conditions[0][property]"] = "effective_date"
                params["conditions[0][operator]"] = ">="
                params["conditions[0][value]"] = since.strftime("%Y-%m-%d")

            try:
                resp = self._fetch_with_retry(NADAC_API_URL, params=params)
                if resp.status_code != 200:
                    logger.warning("NADAC fetch HTTP %s at offset %d",
                                   resp.status_code, offset)
                    break
                api_records = _unwrap(resp.json())
                if not api_records:
                    break
            except Exception as e:
                logger.warning("NADAC fetch failed at offset %d: %s", offset, e)
                break

            for raw in api_records:
                parsed = parse_nadac_record(raw)
                if not parsed:
                    skipped_no_price += 1
                    continue
                if not parsed.get("ndc_code"):
                    # RawRecord requires a non-empty external_id — record the
                    # skip instead of raising / dropping silently.
                    skipped_no_ndc += 1
                    continue

                record = RawRecord(
                    record_type=RecordType.DRUG,
                    external_id=parsed["ndc_code"],
                    source_name="CMS NADAC",
                    provenance=Provenance(
                        source_type=self.source_type(),
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

        logger.info(
            "NADAC connector fetched %d pricing records "
            "(skipped %d no-price, %d no-ndc)",
            len(records), skipped_no_price, skipped_no_ndc,
        )
        return records

    @staticmethod
    def _hash(data: dict) -> str:
        import hashlib, json
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
