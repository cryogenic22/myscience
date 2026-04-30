"""EMA CHMP meeting-highlights connector.

SPEC-016 §7 swimlane A6.1 (Cycle 7).

Thin HTTP client. Pulls one CHMP meeting-highlights page and runs
it through services.ema_chmp_parser. The caller decides which
meeting URL to fetch (date-stamped index lives at
https://www.ema.europa.eu/en/news/chmp-meeting-highlights).

Errors return empty list / None so the connector can be wrapped in
the standard scheduler retry loop without raising.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import requests

from services.ema_chmp_parser import parse_highlights
from services.extraction.ema_chmp_opinion import ChmpOpinion

logger = logging.getLogger(__name__)


_DEFAULT_TIMEOUT = 30
_DEFAULT_USER_AGENT = "market-zero/1.0 (pulseaction.ai)"


class EMAChmpConnector:
    """Tiny scraper for CHMP meeting-highlights pages."""

    def __init__(
        self,
        *,
        timeout: int = _DEFAULT_TIMEOUT,
        user_agent: str = _DEFAULT_USER_AGENT,
    ):
        self._timeout = timeout
        self._headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml",
        }

    def fetch_meeting_highlights(
        self,
        *,
        meeting_url: str,
        opinion_date: date,
    ) -> list[ChmpOpinion]:
        """Fetch one meeting-highlights page and return CHMP opinions.

        Empty list on 404 / network errors — the caller can retry on
        the next sweep.
        """
        if not meeting_url:
            return []
        try:
            resp = requests.get(
                meeting_url,
                timeout=self._timeout,
                headers=self._headers,
            )
        except requests.RequestException as exc:
            logger.warning("EMA CHMP fetch failed (%s): %s",
                           meeting_url, exc)
            return []

        if resp.status_code != 200:
            logger.info("EMA CHMP %s returned %s",
                        meeting_url, resp.status_code)
            return []

        try:
            return parse_highlights(resp.text, opinion_date=opinion_date)
        except Exception as exc:
            logger.warning("EMA CHMP parser failed (%s): %s",
                           meeting_url, exc)
            return []
