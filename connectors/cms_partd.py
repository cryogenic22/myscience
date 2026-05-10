"""BE-31 — CMS Medicare Part D formulary files connector.

Closes KBQ-8 Access (formularies, prior authorization, step therapy).
Per the spec, batch-downloads ~50 plan files per quarter from the
CMS bulk-download portal; this stub keeps the source registered
ahead of the file-set upload pipeline.

CMS portal: https://www.cms.gov/files/zip/medicare-part-d-formulary-files
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

PORTAL_URL = "https://www.cms.gov/medicare/prescription-drug-coverage/prescriptiondrugcovgenin/partddata"
TIMEOUT = 30


class CMSPartDConnector(BaseConnector):
    """CMS Medicare Part D formulary file batch loader (stub)."""

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        logger.info("cms_partd.fetch: stub mode (file pipeline not yet wired)")
        return []

    def source_type(self) -> SourceType:
        return SourceType.CMS_PARTD

    def health_check(self) -> HealthCheckResult:
        try:
            t0 = datetime.utcnow()
            resp = requests.get(PORTAL_URL, timeout=TIMEOUT, allow_redirects=True)
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
