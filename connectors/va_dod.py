"""BE-34 — VA / DoD national formulary connector.

Public-payer access gap. The VA publishes the National Formulary
as a periodic CSV; this stub registers the source ahead of the
file-fetch pipeline.

VA NF: https://www.va.gov/formularyadvisor/
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

VA_FORMULARY_URL = "https://www.va.gov/formularyadvisor/"
TIMEOUT = 30


class VADoDConnector(BaseConnector):
    """VA / DoD National Formulary loader (stub)."""

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        logger.info("va_dod.fetch: stub mode")
        return []

    def source_type(self) -> SourceType:
        return SourceType.VA_DOD_FORMULARY

    def health_check(self) -> HealthCheckResult:
        try:
            t0 = datetime.utcnow()
            resp = requests.get(VA_FORMULARY_URL, timeout=TIMEOUT, allow_redirects=True)
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
