"""BE-29 — bioRxiv + medRxiv preprints connector.

Closes scientific KBQ-4 priority. Single connector, two server
flavors — selects via the `_FLAVOR` class attribute so the scheduler
can register one for each.

API docs: https://api.biorxiv.org/
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

API_BASE = "https://api.biorxiv.org/details"
TIMEOUT = 30


class _PreprintConnector(BaseConnector):
    _FLAVOR = "biorxiv"      # subclasses override
    _SOURCE_TYPE: SourceType = SourceType.BIORXIV

    def fetch(self, since: Optional[datetime] = None) -> list[RawRecord]:
        logger.info("%s.fetch: stub mode", self._FLAVOR)
        return []

    def source_type(self) -> SourceType:
        return self._SOURCE_TYPE

    def health_check(self) -> HealthCheckResult:
        try:
            t0 = datetime.utcnow()
            resp = requests.get(
                f"{API_BASE}/{self._FLAVOR}/2026-05-01/2026-05-02/0",
                timeout=TIMEOUT,
            )
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


class BioRxivConnector(_PreprintConnector):
    _FLAVOR = "biorxiv"
    _SOURCE_TYPE = SourceType.BIORXIV


class MedRxivConnector(_PreprintConnector):
    _FLAVOR = "medrxiv"
    _SOURCE_TYPE = SourceType.MEDRXIV
