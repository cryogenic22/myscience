"""BE-32 — CMS Medicare B + D pricing files connector.

Closes KBQ-7 Pricing as a free public alternative to RedBook / FDB
until executive cost-benefit on those licensed products lands.
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

CMS_PRICING_URL = "https://www.cms.gov/medicare/payment/fee-schedules"
TIMEOUT = 30


class CMSPricingConnector(BaseConnector):
    """CMS Medicare B + D pricing files (stub)."""

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        logger.info("cms_pricing.fetch: stub mode (file pipeline not yet wired)")
        return []

    def source_type(self) -> SourceType:
        return SourceType.CMS_PRICING

    def health_check(self) -> HealthCheckResult:
        try:
            t0 = datetime.utcnow()
            resp = requests.get(CMS_PRICING_URL, timeout=TIMEOUT, allow_redirects=True)
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
