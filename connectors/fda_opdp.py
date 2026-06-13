"""BE-30 — FDA OPDP warning letters connector.

Closes KBQ-3 Regulatory + KBQ-9 Reputational. OPDP's site doesn't
expose a JSON API — production deploys a small scraper job. This
stub registers the source so the scheduler / source registry can
list it.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

import requests

from connectors.base import (
    BaseConnector, ConnectorError, HealthCheckResult, RawRecord, SourceType,
)

logger = logging.getLogger(__name__)

OPDP_LISTING_URL = "https://www.fda.gov/drugs/warning-letters-and-notice-violation-letters-pharmaceutical-companies"
TIMEOUT = 30


class FDAOPDPConnector(BaseConnector):
    """FDA Office of Prescription Drug Promotion — warning letters."""

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        logger.info("fda_opdp.fetch: stub mode (scraper not yet deployed)")
        return []

    def source_type(self) -> SourceType:
        return SourceType.FDA_OPDP

    def health_check(self) -> HealthCheckResult:
        try:
            t0 = datetime.utcnow()
            resp = requests.get(OPDP_LISTING_URL, timeout=TIMEOUT, allow_redirects=True)
            elapsed_ms = (datetime.utcnow() - t0).total_seconds() * 1000
            return HealthCheckResult(
                healthy=resp.status_code == 200,
                source_type=self.source_type(),
                message=f"HTTP {resp.status_code}",
                response_time_ms=elapsed_ms,
            )
        except Exception as exc:
            return HealthCheckResult(
                healthy=False, source_type=self.source_type(),
                message=f"unreachable: {exc}",
            )
