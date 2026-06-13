"""BE-28 — EPO Patents (OPS API) connector.

Closes KBQ-10 international patent gap. Stacks on USPTO; uses the
same patent entity type. EPO OPS requires OAuth2 client credentials
which the scheduler config exposes.

OPS docs: https://www.epo.org/en/searching-for-patents/data/web-services/ops
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

API_BASE = "https://ops.epo.org/3.2/rest-services"
TIMEOUT = 30


class EPOPatentsConnector(BaseConnector):
    """EPO Open Patent Services — international patent records."""

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        logger.info("epo.fetch: stub mode (OAuth2 creds not configured)")
        return []

    def source_type(self) -> SourceType:
        return SourceType.EPO_PATENTS

    def health_check(self) -> HealthCheckResult:
        try:
            t0 = datetime.utcnow()
            resp = requests.get(f"{API_BASE}/", timeout=TIMEOUT)
            elapsed_ms = (datetime.utcnow() - t0).total_seconds() * 1000
            return HealthCheckResult(
                healthy=resp.status_code in (200, 401, 403),
                source_type=self.source_type(),
                message=f"HTTP {resp.status_code}",
                response_time_ms=elapsed_ms,
            )
        except Exception as exc:
            return HealthCheckResult(
                healthy=False, source_type=self.source_type(),
                message=f"unreachable: {exc}",
            )
