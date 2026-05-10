"""BE-33 — WHO ICTRP global trial registry connector.

Closes the international trial gap. Cross-walks WHO ICTRP records
to our canonical Trial entity (the existing ClinicalTrials.gov
connector handles US trials). ICTRP exposes weekly XML dumps
rather than a JSON API.

WHO ICTRP: https://www.who.int/clinical-trials-registry-platform
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

ICTRP_PORTAL_URL = "https://www.who.int/clinical-trials-registry-platform"
TIMEOUT = 30


class WHOICTRPConnector(BaseConnector):
    """WHO International Clinical Trials Registry Platform (stub)."""

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        logger.info("who_ictrp.fetch: stub mode (XML dump pipeline not yet wired)")
        return []

    def source_type(self) -> SourceType:
        return SourceType.WHO_ICTRP

    def health_check(self) -> HealthCheckResult:
        try:
            t0 = datetime.utcnow()
            resp = requests.get(ICTRP_PORTAL_URL, timeout=TIMEOUT, allow_redirects=True)
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
