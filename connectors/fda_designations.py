"""FDA expedited-program designations connector.

SPEC-016 §7 swimlane A4.3 (Cycle 8).

Source: OpenFDA `drug/drugsfda.json` endpoint. Each application record
embeds a list of submissions with `review_priority` (PRIORITY|STANDARD)
and `submission_class_code` (BREAKTHROUGH, FAST_TRACK, ORPHAN, RMAT,
QIDP, ACCELERATED, etc.). One submission can yield multiple designation
events when both fields signal an expedited program.

Pure parser is exposed as parse_openfda_results so tests can verify
without HTTP. The connector wraps fetching + paging.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any, Optional

import requests

from services.extraction.fda_designation import (
    DesignationType,
    FdaDesignation,
)

logger = logging.getLogger(__name__)


_OPENFDA_BASE = "https://api.fda.gov/drug/drugsfda.json"
_DEFAULT_TIMEOUT = 30
_DEFAULT_USER_AGENT = "market-zero/1.0 (pulseaction.ai)"


# ────────────────────────────────────────────────────────────────────
# Submission-class-code → DesignationType mapping
# ────────────────────────────────────────────────────────────────────


_CLASS_CODE_MAP: dict[str, DesignationType] = {
    "BREAKTHROUGH": "breakthrough",
    "FAST_TRACK": "fast_track",
    "FASTTRACK": "fast_track",
    "ORPHAN": "orphan",
    "RMAT": "rmat",
    "QIDP": "qidp",
    "ACCELERATED": "accelerated_approval",
    "ACCELERATED_APPROVAL": "accelerated_approval",
}


def _parse_yyyymmdd(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


def _resolve_drug_name(record: dict[str, Any]) -> Optional[str]:
    openfda = record.get("openfda") or {}
    for key in ("generic_name", "brand_name", "substance_name"):
        val = openfda.get(key)
        if isinstance(val, list) and val:
            return str(val[0])
    products = record.get("products") or []
    if products and isinstance(products[0], dict):
        active = products[0].get("active_ingredients") or []
        if active and isinstance(active[0], dict):
            n = active[0].get("name")
            if n:
                return str(n)
    return None


def _resolve_indication(record: dict[str, Any]) -> str:
    """OpenFDA doesn't expose indication directly — leave empty when
    not derivable. Downstream resolver can fill from drug entity."""
    products = record.get("products") or []
    if products and isinstance(products[0], dict):
        return str(products[0].get("indication") or "")[:1000]
    return ""


def _designations_from_submission(
    record: dict[str, Any],
    submission: dict[str, Any],
) -> list[FdaDesignation]:
    drug_name = _resolve_drug_name(record)
    sponsor = record.get("sponsor_name") or ""
    application_number = record.get("application_number")
    granted_date = _parse_yyyymmdd(submission.get("submission_status_date"))
    if not (drug_name and sponsor and granted_date):
        return []

    indication = _resolve_indication(record) or "(indication not in OpenFDA record)"

    out: list[FdaDesignation] = []

    # Class-code based designations
    raw_code = (submission.get("submission_class_code") or "").upper().strip()
    designation = _CLASS_CODE_MAP.get(raw_code)
    if designation is not None:
        try:
            out.append(FdaDesignation(
                drug_name=drug_name,
                sponsor_name=sponsor,
                designation_type=designation,
                granted_date=granted_date,
                indication=indication,
                application_number=str(application_number) if application_number else None,
                submission_number=str(submission.get("submission_number") or "") or None,
                notes=submission.get("submission_class_code_description"),
            ))
        except Exception as exc:
            logger.debug("FDA designation row failed validation: %s", exc)

    # Priority review is a separate field (review_priority)
    priority = (submission.get("review_priority") or "").upper().strip()
    if priority == "PRIORITY":
        try:
            out.append(FdaDesignation(
                drug_name=drug_name,
                sponsor_name=sponsor,
                designation_type="priority_review",
                granted_date=granted_date,
                indication=indication,
                application_number=str(application_number) if application_number else None,
                submission_number=str(submission.get("submission_number") or "") or None,
                notes=None,
            ))
        except Exception as exc:
            logger.debug("Priority-review row failed validation: %s", exc)

    return out


# ────────────────────────────────────────────────────────────────────
# Pure parser
# ────────────────────────────────────────────────────────────────────


def parse_openfda_results(
    payload: dict[str, Any],
) -> list[FdaDesignation]:
    """Pure parser for an OpenFDA drugsfda.json response. Returns
    one FdaDesignation per detected designation marker."""
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    if not isinstance(results, list):
        return []

    out: list[FdaDesignation] = []
    for record in results:
        if not isinstance(record, dict):
            continue
        for sub in record.get("submissions") or []:
            if not isinstance(sub, dict):
                continue
            out.extend(_designations_from_submission(record, sub))
    return out


# ────────────────────────────────────────────────────────────────────
# Connector
# ────────────────────────────────────────────────────────────────────


class FdaDesignationsConnector:
    """Tiny client for the OpenFDA drugsfda endpoint."""

    def __init__(
        self,
        *,
        base_url: str = _OPENFDA_BASE,
        timeout: int = _DEFAULT_TIMEOUT,
        user_agent: str = _DEFAULT_USER_AGENT,
        api_key: Optional[str] = None,
    ):
        self._base_url = base_url
        self._timeout = timeout
        self._headers = {"User-Agent": user_agent}
        self._api_key = api_key

    def fetch_for_drug_name(
        self,
        *,
        drug_name: str,
        limit: int = 100,
    ) -> list[FdaDesignation]:
        """Fetch designations for a generic / brand drug name.

        Returns empty list on 404 / network error.
        """
        if not drug_name:
            return []
        params: dict[str, Any] = {
            "search": (
                f'(openfda.generic_name:"{drug_name}" '
                f'+OR+ openfda.brand_name:"{drug_name}")'
            ),
            "limit": limit,
        }
        if self._api_key:
            params["api_key"] = self._api_key

        try:
            resp = requests.get(
                self._base_url, params=params,
                timeout=self._timeout, headers=self._headers,
            )
        except requests.RequestException as exc:
            logger.warning("FDA designations fetch failed (%s): %s",
                           drug_name, exc)
            return []

        if resp.status_code != 200:
            logger.info("FDA designations %s returned %s",
                        drug_name, resp.status_code)
            return []

        try:
            payload = resp.json()
        except ValueError:
            return []

        return parse_openfda_results(payload)

    def fetch_for_application_number(
        self,
        *,
        application_number: str,
    ) -> list[FdaDesignation]:
        """Fetch designations for an exact NDA/BLA/sNDA application."""
        if not application_number:
            return []
        params: dict[str, Any] = {
            "search": f'application_number:"{application_number}"',
            "limit": 1,
        }
        if self._api_key:
            params["api_key"] = self._api_key
        try:
            resp = requests.get(
                self._base_url, params=params,
                timeout=self._timeout, headers=self._headers,
            )
        except requests.RequestException as exc:
            logger.warning("FDA designations fetch failed (%s): %s",
                           application_number, exc)
            return []
        if resp.status_code != 200:
            return []
        try:
            payload = resp.json()
        except ValueError:
            return []
        return parse_openfda_results(payload)
