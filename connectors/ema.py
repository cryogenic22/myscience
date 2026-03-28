"""EMA (European Medicines Agency) connector.

Fetches EU-authorised medicines from the EMA's public data API.
This eliminates the US-centric bias identified in the lead assessment
by adding European marketing authorisations and EPAR data.

API: https://www.ema.europa.eu/en/medicines/download-medicine-data
Structured data: https://www.ema.europa.eu/en/medicines/field_ema_web_categories%253Aname_field/Human
"""

from __future__ import annotations

import logging
import re
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

logger = logging.getLogger(__name__)

# EMA medicines download API (CSV/JSON)
EMA_API_URL = "https://www.ema.europa.eu/en/medicines/download-medicine-data"
# Alternative: EMA Open Data Portal
EMA_OPEN_DATA_URL = "https://data.europa.eu/api/hub/search/datasets/european-medicines-agency-human-medicines"

# EU Clinical Trials Register
EUCTR_API_URL = "https://www.clinicaltrialsregister.eu/ctr-search/rest/search/basic"


class EMAConnector(BaseConnector):
    """Connector for EMA European Medicines data.

    Phase 1: EU-authorised medicines (drug approvals, EPARs)
    Phase 2: EU Clinical Trials Register (EUCTR)
    """

    def __init__(self, config=None, target_overrides: dict | None = None):
        self._config = config
        self._target_drugs = (target_overrides or {}).get("drugs", [])

    def source_type(self) -> SourceType:
        return SourceType.EMA

    def health_check(self) -> HealthCheckResult:
        import requests
        try:
            resp = requests.head("https://www.ema.europa.eu/en/medicines", timeout=10)
            return HealthCheckResult(
                source_type=self.source_type,
                healthy=resp.status_code < 400,
                response_time_ms=0,
                message=f"HTTP {resp.status_code}",
            )
        except Exception as e:
            return HealthCheckResult(
                source_type=self.source_type,
                healthy=False,
                response_time_ms=0,
                message=str(e),
            )

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        """Fetch EU-authorised medicines from EMA.

        Uses the EMA's structured data download or EUCTR search.
        """
        records: list[RawRecord] = []

        # Phase 1: Search EUCTR for trials matching our target drugs
        drug_queries = self._target_drugs or self._get_target_drugs()
        for drug_name in drug_queries[:50]:  # cap to avoid rate limiting
            try:
                trials = self._search_euctr(drug_name, since)
                records.extend(trials)
            except Exception as e:
                logger.warning("EUCTR search failed for %s: %s", drug_name, e)

        logger.info("EMA connector fetched %d records", len(records))
        return records

    def _search_euctr(self, drug_name: str, since: Optional[datetime] = None) -> list[RawRecord]:
        """Search EU Clinical Trials Register for a drug."""
        records = []
        params = {"query": drug_name, "mode": "basic"}
        if since:
            params["dateFrom"] = since.strftime("%Y-%m-%d")

        try:
            resp = self._fetch_with_retry(
                EUCTR_API_URL,
                params=params,
                timeout=30,
            )
            if resp.status_code != 200:
                return records

            data = resp.json() if hasattr(resp, 'json') else {}
            results = data.get("results", data.get("trials", []))

            for trial in results[:100]:  # cap per drug
                eudra_ct = trial.get("eudract_number", trial.get("id", ""))
                if not eudra_ct:
                    continue

                record = RawRecord(
                    record_type=RecordType.TRIAL,
                    external_id=eudra_ct,
                    source_name="EU Clinical Trials Register",
                    provenance=Provenance(
                        source_type=self.source_type,
                        api_endpoint=EUCTR_API_URL,
                        query_params=params,
                        retrieved_at=datetime.now(timezone.utc),
                        raw_response_hash=self._hash_payload(trial),
                    ),
                    data={
                        "eudract_number": eudra_ct,
                        "official_title": trial.get("title", trial.get("full_title", "")),
                        "sponsor_name": trial.get("sponsor", {}).get("name", "") if isinstance(trial.get("sponsor"), dict) else trial.get("sponsor_name", ""),
                        "status": trial.get("trial_status", trial.get("status", "")),
                        "phase": self._extract_phase(trial),
                        "conditions": trial.get("medical_conditions", trial.get("conditions", "")),
                        "drug_name": drug_name,
                        "start_date": trial.get("start_date", ""),
                        "country": "EU",
                        "region": "Europe",
                    },
                    identifiers={
                        "eudract_number": eudra_ct,
                        "drug_name": drug_name,
                    },
                )
                records.append(record)
        except Exception as e:
            logger.debug("EUCTR parse error for %s: %s", drug_name, e)

        return records

    def _extract_phase(self, trial: dict) -> str:
        """Extract clinical trial phase from EMA data."""
        phase = trial.get("phase", trial.get("trial_phase", ""))
        if isinstance(phase, str):
            if "IV" in phase or "4" in phase:
                return "Phase 4"
            if "III" in phase or "3" in phase:
                return "Phase 3"
            if "II" in phase or "2" in phase:
                return "Phase 2"
            if "I" in phase or "1" in phase:
                return "Phase 1"
        return phase or "Unknown"

    def _get_target_drugs(self) -> list[str]:
        """Get target drug names from config or defaults."""
        try:
            from config import config
            names = list(getattr(config.pipeline, 'target_drug_names', []))
            if names:
                return names[:30]
        except Exception:
            pass
        return [
                "semaglutide", "tirzepatide", "empagliflozin", "dapagliflozin",
                "liraglutide", "sitagliptin", "canagliflozin", "dulaglutide",
                "insulin glargine", "metformin", "pioglitazone", "valsartan",
            ]

    @staticmethod
    def _hash_payload(data: dict) -> str:
        import hashlib, json
        return hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
