"""DailyMed SPL connector.

SPEC-016 §7 swimlane A4.1 (Cycle 5).

Thin wrapper around DailyMed's v2 services API:

  v2 endpoints used:
    /spls.json?drug_name={...}     — list SPLs by drug name
    /spls/{setid}.xml              — fetch full SPL XML
    /spls.json?published_date_gte={iso} — list recent revisions

The connector is intentionally small — diffing happens in Cycle 6
(services/spl_diff_service.py). Parsing happens in
services/spl_section_parser.py. This module is just I/O.

Network errors do not raise — they return None / [] so the caller
can move on (the diff service will pick the change up next cycle).
"""

from __future__ import annotations

import logging
import time
from datetime import date
from typing import Optional

import requests

logger = logging.getLogger(__name__)


_BASE_URL = "https://dailymed.nlm.nih.gov/dailymed/services/v2"
_DEFAULT_TIMEOUT = 30
_DEFAULT_REQUEST_DELAY = 0.5


class DailyMedSplConnector:
    """Tiny HTTP client for the DailyMed v2 services API.

    Construction is cheap — no network. The caller decides which of
    the three methods to call.
    """

    def __init__(
        self,
        *,
        base_url: str = _BASE_URL,
        request_delay: float = _DEFAULT_REQUEST_DELAY,
        timeout: int = _DEFAULT_TIMEOUT,
        user_agent: str = "market-zero/1.0 (pulseaction.ai)",
    ):
        self._base_url = base_url.rstrip("/")
        self._request_delay = request_delay
        self._timeout = timeout
        self._headers = {"User-Agent": user_agent, "Accept": "*/*"}

    # ------------------------------------------------------------------
    # fetch_spl_xml
    # ------------------------------------------------------------------

    def fetch_spl_xml(self, *, setid: str) -> Optional[str]:
        """Return the full SPL XML for a setid, or None on 404 / error."""
        if not setid:
            return None
        url = f"{self._base_url}/spls/{setid}.xml"
        try:
            resp = requests.get(
                url, timeout=self._timeout, headers=self._headers,
            )
        except requests.RequestException as exc:
            logger.warning("DailyMed fetch_spl_xml(%s) failed: %s",
                           setid, exc)
            return None

        if resp.status_code == 200:
            return resp.text
        if resp.status_code == 404:
            return None
        logger.warning(
            "DailyMed fetch_spl_xml(%s) returned %s",
            setid, resp.status_code,
        )
        return None

    # ------------------------------------------------------------------
    # list_setids_for_drug
    # ------------------------------------------------------------------

    def list_setids_for_drug(self, *, drug_name: str) -> list[str]:
        """Return all setids matching a drug name. Empty list on miss."""
        if not drug_name:
            return []
        url = f"{self._base_url}/spls.json"
        params = {"drug_name": drug_name}
        try:
            resp = requests.get(
                url, params=params, timeout=self._timeout,
                headers=self._headers,
            )
        except requests.RequestException as exc:
            logger.warning(
                "DailyMed list_setids_for_drug(%s) failed: %s",
                drug_name, exc,
            )
            return []

        if resp.status_code != 200:
            logger.warning(
                "DailyMed list_setids_for_drug(%s) returned %s",
                drug_name, resp.status_code,
            )
            return []

        try:
            payload = resp.json()
        except ValueError:
            return []

        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return []

        setids: list[str] = []
        for entry in data:
            if isinstance(entry, dict) and entry.get("setid"):
                setids.append(str(entry["setid"]))
        return setids

    # ------------------------------------------------------------------
    # list_changes_since
    # ------------------------------------------------------------------

    def list_changes_since(self, *, since: date) -> list[str]:
        """List setids that have a new revision published on/after `since`.

        Drives the periodic diff sweep. Empty list on miss / error.
        """
        if not since:
            return []
        url = f"{self._base_url}/spls.json"
        params = {"published_date_gte": since.isoformat()}
        try:
            resp = requests.get(
                url, params=params, timeout=self._timeout,
                headers=self._headers,
            )
        except requests.RequestException as exc:
            logger.warning(
                "DailyMed list_changes_since(%s) failed: %s",
                since, exc,
            )
            return []
        if resp.status_code != 200:
            return []
        try:
            payload = resp.json()
        except ValueError:
            return []
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            return []
        return [str(e["setid"]) for e in data
                if isinstance(e, dict) and e.get("setid")]

    # ------------------------------------------------------------------
    # Polite-fetch helper for paged scrapes (used by Cycle 6 sweep)
    # ------------------------------------------------------------------

    def sleep_between_requests(self) -> None:
        time.sleep(self._request_delay)
